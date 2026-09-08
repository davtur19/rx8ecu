#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_site.py — deterministic, offline builder for the RX-8 ECU Firmware Explorer.

Usage:
    python3 web/explorer/build_site.py              # build dist/ only (default)
    python3 web/explorer/build_site.py --serve      # build, then serve dist/ on port 8000
    python3 web/explorer/build_site.py --serve 8080 # build, then serve dist/ on port 8080

The optional --serve flag only adds a local http.server on top of the normal
build; it never changes the generated files (byte-identical output with or
without it). Press Ctrl+C to stop the server (clean shutdown, no leftover
processes).

Reads (read-only, nothing is ever modified):
    ../../symbols/callgraph.csv                  (callgraph edges, 60E0FC00 context)
     ../../symbols/cal_tables.csv                 (1209 calibration-table entries: 548 tables + 661 axes)
    ../../symbols/symbols_60E0FC00.csv           (symbols with ranges, ROM 60E0FC00)
    ../../symbols/symbols_60E0FC00_ghidra.csv    (ghidra hand names, ROM 60E0FC00)
    ../../symbols/symbols_60E1D400_ida.csv       (baseline 60E1D400 symbols)
    ../../symbols/symbols_60E1D400_merged.csv    (baseline 60E1D400 symbols, best names)
    ../../roms/stock/60E1D400.bin                (calibration-table values, default model)
    ../../roms/stock/*.bin                       (calibration-table values, all 9 models)
    ../../docs/functions/*.md                    (content: title + address + markdown body)
    ../../docs/subsystems/*.md                   (content: "Subsystems" view)
    data/roms_meta.json                          (the 9 stock ROM models metadata)
     data/table_addr_map_long.csv                 (per-ROM address mapping of the 1209 tables)
    src/index.template.html, src/app.js, src/style.css  (site sources)

Writes the complete static site into dist/:
    index.html   — page assembled from the template (metadata injected)
    app.js       — application logic (copied from src/)
    style.css    — theme (copied from src/)
    data.json    — full dataset (used via fetch with http.server); includes the
                   baseline (60E1D400) table values, the 9 model descriptors and
                   the per-model address map, but NOT the per-model values
    data.js      — `window.EXPLORER_DATA = ...;` (file:// fallback)
    models/<key>.json — per-model value files (one per non-default ROM), fetched
                   on demand by the UI when the user switches the firmware model
    .nojekyll    — tells GitHub Pages not to run Jekyll over the output
    build_manifest.json — input SHA-256 hashes + output counts (freshness check)
    README.md    — auto-generated summary of this build (documents the check)

Firmware-model selector: the UI lets the user pick one of the 9 stock ROMs. The
table addresses then come from data/table_addr_map_long.csv (per-ROM map, never
a global shift) and the values are extracted from the matching roms/stock/*.bin
with the same Map1D/Map2D descriptor logic used for the baseline. To keep
data.json below ~3 MB, only the baseline (60E1D400) values stay embedded; the
other models ship as dist/models/<key>.json, loaded lazily via fetch.

Stdlib-only (no external dependencies, nothing to install). The build is
deterministic: identical inputs produce byte-identical output. Set the
SOURCE_DATE_EPOCH environment variable to pin the optional `generated`
timestamp (a standard reproducible-builds convention); otherwise it is omitted.

Note: cal_tables.csv is labeled "60E1D400" (RE baseline); its addresses match
the verified map descriptors in roms/stock/60E1D400.bin
(RE baseline); the real values are extracted from there.
"""
import argparse
import csv
import json
import math
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
SYM = os.path.join(ROOT, "symbols")
DATA_DIR = os.path.join(HERE, "data")
ROMS_META = os.path.join(DATA_DIR, "roms_meta.json")
ADDR_MAP_LONG = os.path.join(DATA_DIR, "table_addr_map_long.csv")
ROM_DIR = os.path.join(ROOT, "roms", "stock")
ROM_CAL = os.path.join(ROM_DIR, "60E1D400.bin")
# Repo-relative path for the embedded "rom_cal" field: consumers of data.json
# should not see the absolute local path of the generator's checkout.
ROM_CAL_REL = os.path.relpath(ROM_CAL, ROOT)
DOCS_DIR = os.path.join(ROOT, "docs", "functions")
SUBSYS_DIR = os.path.join(ROOT, "docs", "subsystems")
SRC = os.path.join(HERE, "src")
DIST = os.path.join(HERE, "dist")
EXPLORER_DIST = os.path.join(DIST, "explorer")
EMU_DIST_SRC = os.path.join(HERE, "..", "ecu-emu", "dist")
MODELS_DIR = os.path.join(EXPLORER_DIST, "models")
TEMPLATE = os.path.join(SRC, "index.template.html")
SRC_APP = os.path.join(SRC, "app.js")
SRC_CSS = os.path.join(SRC, "style.css")

# Default firmware model: the baseline ROM whose values stay embedded in
# data.json (data.js fallback). The other models are emitted as separate
# dist/models/<key>.json files, fetched on demand by the UI.
DEFAULT_MODEL = "D400"

GENERATOR = "web/explorer/build_site.py"

WARN = []


def warn(msg):
    WARN.append(msg)
    print("WARN:", msg)


class BuildError(Exception):
    """Fatal build error: missing/unreadable required input. Aborts the
    build with a non-zero exit instead of shipping a silently incomplete
    dist/ (fail-closed)."""


def need(path, label):
    """Returns path if it exists, else raises BuildError (fail-closed)."""
    if not os.path.exists(path):
        raise BuildError("missing required input %s (%s)" % (label, path))
    return path


# --------------------------------------------------------------------------
# 1. Symbols: union of the 4 CSV files, with name priority and ROM tags
# --------------------------------------------------------------------------
# ROM bitmask: 1 = 60E0FC00.csv, 2 = 60E0FC00_ghidra.csv, 4 = 60E1D400_ida.csv, 8 = 60E1D400_merged.csv
# Priority 5 (top): symbols/FUNCTION_CATEGORIES.csv names (curated checkpoint,
# provenance: symbols/FUNCTION_RENAMES.csv). FC carries the newer renames, so
# its NAME wins over the 4-CSV union; category is applied separately in
# build_dataset() via load_categories().
def load_symbols():
    by_addr = {}
    order = []
    invalid = 0

    def put(addr, name, src, rombit, end=None, priority=0):
        if addr in by_addr:
            e = by_addr[addr]
            if priority > e["prio"]:
                e["name"] = name
                e["src"] = src
                e["prio"] = priority
            if end is not None and (e.get("end") is None or end > e["end"]):
                e["end"] = end
            e["rom"] |= rombit
        else:
            by_addr[addr] = {"name": name, "src": src, "rom": rombit, "prio": priority,
                             "a": addr, "end": end if end is not None else addr}
            order.append(addr)

    # 60E0FC00.csv  (ranges + auto/hand ghidra names) — priority 1/2
    p = os.path.join(SYM, "symbols_60E0FC00.csv")
    if os.path.exists(p):
        for r in csv.DictReader(open(p, encoding="utf-8", errors="replace")):
            try:
                a = int(r["addr"], 16)
            except Exception:
                invalid += 1
                warn("invalid symbol address in %s: %r" % (p, r.get("addr")))
                continue
            end = None
            try:
                end = int(r.get("end") or "0", 16) or None
            except Exception:
                pass
            src = r.get("source", "")
            prio = 2 if "hand" in src else 1
            put(a, r["name"], src, 1, end=end, priority=prio)
    else:
        warn("missing " + p)

    # 60E0FC00_ghidra.csv (hand names, no ranges) — priority 3
    p = os.path.join(SYM, "symbols_60E0FC00_ghidra.csv")
    if os.path.exists(p):
        for r in csv.DictReader(open(p, encoding="utf-8", errors="replace")):
            try:
                a = int(r["addr"], 16)
            except Exception:
                invalid += 1
                warn("invalid symbol address in %s: %r" % (p, r.get("addr")))
                continue
            put(a, r["name"], r.get("source", "ghidra-hand"), 2, priority=3)
    else:
        warn("missing " + p)

    # 60E1D400_ida.csv — priority 3 (baseline context)
    p = os.path.join(SYM, "symbols_60E1D400_ida.csv")
    if os.path.exists(p):
        for r in csv.DictReader(open(p, encoding="utf-8", errors="replace")):
            try:
                a = int(r["addr"], 16)
            except Exception:
                invalid += 1
                warn("invalid symbol address in %s: %r" % (p, r.get("addr")))
                continue
            end = None
            try:
                end = int(r.get("end") or "0", 16) or None
            except Exception:
                pass
            put(a, r["name"], r.get("source", "ida-ai"), 4, end=end, priority=3)
    else:
        warn("missing " + p)

    # 60E1D400_merged.csv — best names, priority 4 (top)
    p = os.path.join(SYM, "symbols_60E1D400_merged.csv")
    if os.path.exists(p):
        for r in csv.DictReader(open(p, encoding="utf-8", errors="replace")):
            try:
                a = int(r["addr"], 16)
            except Exception:
                invalid += 1
                warn("invalid symbol address in %s: %r" % (p, r.get("addr")))
                continue
            end = None
            try:
                end = int(r.get("end") or "0", 16) or None
            except Exception:
                pass
            put(a, r["name"], r.get("source", "ida-ai"), 8, end=end, priority=4)
    else:
        warn("missing " + p)

    # FUNCTION_CATEGORIES.csv names — priority 5 (curated checkpoint, top).
    # H1: FC carries the newer renames (FUNCTION_RENAMES.csv provenance), so
    # its NAME wins over the 4-CSV union. Fallbacks above are kept for addrs
    # with no FC entry (e.g. callgraph-only placeholders).
    p = os.path.join(SYM, "FUNCTION_CATEGORIES.csv")
    if os.path.exists(p):
        try:
            fc_rows = list(csv.DictReader(open(p, encoding="utf-8-sig", errors="replace")))
        except Exception as ex:
            warn("unreadable %s: %s" % (p, ex))
            fc_rows = []
        for r in fc_rows:
            try:
                a = int((r.get("addr") or "").strip(), 16)
            except Exception:
                invalid += 1
                warn("invalid FC address in %s: %r" % (p, r.get("addr")))
                continue
            name = (r.get("name") or "").strip()
            if not name:
                continue
            put(a, name, "FUNCTION_CATEGORIES", 0, priority=5)
    else:
        warn("missing " + p)

    return by_addr, order, invalid


# --------------------------------------------------------------------------
# 2. Function documentation (real content: title + address + body)
# --------------------------------------------------------------------------
# Normalizes a symbol/doc name: strips the trailing "_<hex>" suffix
# (e.g. can_message_handler_24588 -> can_message_handler) and lowercases.
def norm_doc_name(n):
    return re.sub(r"_[0-9A-Fa-f]{1,6}$", "", n.strip()).lower()


def doc_header(text):
    """Extracts the first heading (# ...) and the first 0x...... address."""
    title, addr = None, None
    for ln in text.splitlines()[:30]:
        s = ln.strip()
        if not s:
            continue
        if title is None and s.startswith("# "):
            title = s[2:].strip()
        if addr is None:
            m = re.search(r"\b0x([0-9A-Fa-f]{4,6})\b", s)
            if m:
                try:
                    addr = int(m.group(1), 16)
                except ValueError:
                    addr = None
        if title is not None and addr is not None:
            break
    return title, addr


def strip_first_heading(text):
    """Removes the first '# ...' line (the title is handled separately)."""
    for i, ln in enumerate(text.splitlines()):
        if ln.strip().startswith("# "):
            return "\n".join(text.splitlines()[i + 1:]).strip()
    return text.strip()


def load_docs():
    """Reads docs/functions/*.md -> (docs, idx_exact, idx_norm, idx_addr).
    docs:     list of {t: title, a: address or None, f: filename, b: body}
    idx_exact: lowercase filename -> docs index
    idx_norm:  normalized name (no _hex suffix) -> docs index
    idx_addr:  address extracted from the header -> docs index
    The README.md index file is not treated as a function doc.
    """
    docs, idx_exact, idx_norm, idx_addr = [], {}, {}, {}
    if os.path.isdir(DOCS_DIR):
        for f in sorted(os.listdir(DOCS_DIR)):
            if not f.endswith(".md"):
                continue
            fname = f[:-3]
            if fname.lower() == "readme":
                continue
            try:
                text = open(os.path.join(DOCS_DIR, f), encoding="utf-8",
                            errors="replace").read()
            except Exception as ex:
                warn("unreadable doc %s: %s" % (f, ex))
                continue
            title, addr = doc_header(text)
            i = len(docs)
            docs.append({"t": title or fname, "a": addr, "f": fname,
                         "b": strip_first_heading(text)})
            idx_exact.setdefault(fname.lower(), i)
            idx_norm.setdefault(norm_doc_name(fname), i)
            if addr is not None:
                idx_addr.setdefault(addr, i)
    return docs, idx_exact, idx_norm, idx_addr


def load_subsystems():
    """Reads docs/subsystems/*.md -> list of {t: title, f: filename, b: body}."""
    out = []
    if os.path.isdir(SUBSYS_DIR):
        for f in sorted(os.listdir(SUBSYS_DIR)):
            if not f.endswith(".md"):
                continue
            try:
                text = open(os.path.join(SUBSYS_DIR, f), encoding="utf-8",
                            errors="replace").read()
            except Exception as ex:
                warn("unreadable subsystem %s: %s" % (f, ex))
                continue
            title, _ = doc_header(text)
            out.append({"t": title or f[:-3], "f": f[:-3],
                        "b": strip_first_heading(text)})
    return out


# --------------------------------------------------------------------------
# 3. Categories (keyword -> subsystem)
# --------------------------------------------------------------------------
SYM_RULES = [
    (r"obd|uds|iso14229|kline", "OBD / UDS"),
    (r"diag|dtc|fault|error|warning|trouble", "Faults & DTC"),
    (r"can|tx_|rx_|message", "CAN Bus"),
    (r"fuel|inject|inj_|fuelling|lambda|o2_|afr|trim|pump", "Fuel & Lambda"),
    (r"ign|spark|dwell|knock|advance|timing", "Ignition & Knock"),
    (r"idle", "Idle Control"),
    (r"throttle|pedal|accel|torque|vdi|boost", "Throttle & Torque"),
    (r"oil|metering", "Oil Metering"),
    (r"rev|rpm|limit", "Rev Limit"),
    (r"sensor|adc|voltage|temp|coolant|iat|maf|map_|pressure|baro|therm", "Sensors"),
    (r"rtos|task|schedule|priorit|semaphore|mutex|queue|thread", "RTOS"),
    (r"init|reset|boot|startup|vector|exception", "Boot & Init"),
    (r"serial|uart|spi|isr|interrupt|irq|timer|counter", "Peripherals & ISR"),
    (r"flash|eeprom|ram|memory|crc|checksum", "Memory & CRC"),
    (r"math|fpu|float|interp|interpolate|scal", "Math / FPU"),
    (r"delay|util|helper|misc|debug|print|log", "Utilities"),
]
SYM_OTHER = "Other / Unclassified"


def sym_category(name):
    for pat, cat in SYM_RULES:
        if re.search(pat, name, re.I):
            return cat
    return SYM_OTHER


def load_categories():
    """Loads symbols/FUNCTION_CATEGORIES.csv into lookups keyed by `name`
    (primary) and by `addr` (fallback). Returns (by_name, by_addr); both are None
    when the CSV is missing. Each value is a tuple (category, signal, confidence).
    This lets the build prefer the offline classifier's category over the regex
    SYM_RULES fallback, and exposes the signal + confidence so the frontend can
    flag low-confidence "graph" rows as tentative."""
    p = os.path.join(SYM, "FUNCTION_CATEGORIES.csv")
    if not os.path.exists(p):
        return None, None
    by_name, by_addr = {}, {}
    for r in csv.DictReader(open(p, encoding="utf-8", errors="replace")):
        name = (r.get("name") or "").strip()
        if not name:
            continue
        cat = (r.get("category") or "").strip()
        signal = (r.get("signal") or "").strip()
        try:
            conf = float(r.get("confidence") or 0)
        except (TypeError, ValueError):
            conf = 0.0
        row = (cat, signal, conf)
        by_name[name] = row
        try:
            a = int(r.get("addr"), 16)
            by_addr[a] = row
        except (TypeError, ValueError):
            pass
    return by_name, by_addr


TBL_RULES = [
    (r"fuel|inject|inj|fuelling|lambda|o2|afr|trim", "Fuel & Lambda"),
    (r"ign|ignition|dwell|spark|knock", "Ignition & Knock"),
    (r"idle", "Idle Control"),
    (r"throttle|pedal|accel", "Throttle & Pedal"),
    (r"torque|load|boost|vdi", "Torque & VDI"),
    (r"oil", "Oil Metering"),
    (r"rev|limit|rpm", "Rev Limit"),
    (r"temp|coolant|iat|sensor|barometric|pressure|maf|map|voltage|battery|alternat", "Sensors & Temp"),
    (r"check datatype|table 2d|table 3d", "Generic / Check DataType"),
]
TBL_OTHER = "Generic / Unclassified"


def table_category(name):
    for pat, cat in TBL_RULES:
        if re.search(pat, name, re.I):
            return cat
    return TBL_OTHER


# --------------------------------------------------------------------------
# 4. Callgraph
# --------------------------------------------------------------------------
def load_edges():
    # B5: fail-closed like the other core inputs — a missing callgraph must
    # abort the build, not ship a 0-edge site.
    p = need(os.path.join(SYM, "callgraph.csv"), "callgraph")
    out = []
    seen = set()
    invalid = 0
    for r in csv.DictReader(open(p, encoding="utf-8", errors="replace")):
        try:
            ca, ka = int(r["caller_addr"], 16), int(r["callee_addr"], 16)
        except Exception:
            invalid += 1
            warn("invalid edge address in %s: %r -> %r" % (p, r.get("caller_addr"), r.get("callee_addr")))
            continue
        raw_kind = (r.get("kind", "ref") or "ref").strip()
        if raw_kind == "bsr":
            kind = "b"
        elif raw_kind == "ref":
            kind = "r"
        else:
            # B8: never coerce an unknown kind silently — warn and skip.
            invalid += 1
            warn("unknown edge kind in %s: %r (%s -> %s)" % (p, raw_kind, r.get("caller_addr"), r.get("callee_addr")))
            continue
        if (ca, ka, kind) in seen:
            continue
        seen.add((ca, ka, kind))
        out.append((ca, ka, kind))
    return out, invalid


# --------------------------------------------------------------------------
# 5. Calibration tables + value extraction from the ROM
# --------------------------------------------------------------------------
CELL = {0: ("f", 4), 4: ("B", 1), 8: ("H", 2), 12: ("b", 1), 16: ("h", 2)}
TYPE_LABEL = {0: "f32", 4: "u8", 8: "u16", 12: "s8", 16: "s16"}


def load_rom(path):
    try:
        return open(path, "rb").read()
    except Exception as ex:
        warn("unreadable ROM (%s): %s" % (path, ex))
        return None


def build_descriptor_index(d):
    """Scans the ROM for Map1D/Map2D descriptors (like mapscan.py)."""
    by_vp, by_axp, by_ayp = {}, {}, {}

    def u16(o):
        return int.from_bytes(d[o:o + 2], "big")

    def u32(o):
        return int.from_bytes(d[o:o + 4], "big")

    def f32(o):
        try:
            return struct.unpack(">f", d[o:o + 4])[0]
        except Exception:
            return None

    def axis(p, n):
        if not (0x1000 <= p < 0x7E000 and p % 4 == 0):
            return None
        out, prev = [], None
        for i in range(n):
            v = f32(p + i * 4)
            if v is None or not math.isfinite(v) or abs(v) > 1e7:
                return None
            if prev is not None and not v > prev:
                return None
            out.append(v)
            prev = v
        return out

    def okf(x):
        return x is not None and math.isfinite(x) and abs(x) < 1e6

    N = len(d)
    for o in range(0x1000, 0x7E000, 2):
        t = d[o + 16] if o + 16 < N else 255
        if 2 <= u16(o) <= 64 and 2 <= u16(o + 2) <= 64 and t in CELL:
            cx, cy = u16(o), u16(o + 2)
            axp, ayp, vp = u32(o + 4), u32(o + 8), u32(o + 12)
            if all(0x1000 <= p < 0x7E000 for p in (axp, ayp, vp)) and len({axp, ayp, vp}) == 3:
                ax, ay = axis(axp, cx), axis(ayp, cy)
                sc, of = f32(o + 20), f32(o + 24)
                if ax and ay and okf(sc) and okf(of) and sc != 0:
                    m = dict(kind="2D", o=o, cx=cx, cy=cy, type=t, vp=vp, axp=axp, ayp=ayp,
                             sc=sc, of=of, ax=ax, ay=ay)
                    by_vp.setdefault(vp, []).append(m)
                    by_axp.setdefault(axp, []).append(m)
                    by_ayp.setdefault(ayp, []).append(m)
        t = d[o + 2] if o + 2 < N else 255
        if 2 <= u16(o) <= 64 and t in CELL:
            c = u16(o)
            axp, vp = u32(o + 4), u32(o + 8)
            if 0x1000 <= axp < 0x7E000 and 0x1000 <= vp < 0x7E000 and axp != vp:
                ax = axis(axp, c)
                sc, of = f32(o + 12), f32(o + 16)
                if ax and okf(sc) and okf(of) and sc != 0:
                    m = dict(kind="1D", o=o, cx=c, type=t, vp=vp, axp=axp, sc=sc, of=of, ax=ax)
                    by_vp.setdefault(vp, []).append(m)
                    by_axp.setdefault(axp, []).append(m)
    return by_vp, by_axp, by_ayp


def rd(d, o, fmt, sz):
    try:
        return struct.unpack(">" + fmt, d[o:o + sz])[0]
    except Exception:
        return None


def phys(raw, m):
    return raw if m["type"] == 0 else raw * m["sc"] + m["of"]


def r4(x):
    """Rounds to 4 digits; returns None for non-finite values (JSON-safe)."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(v):
        return None
    return round(v, 4)


def extract_table(d, by_vp, by_axp, by_ayp, addr):
    """Returns a dict with the extracted values, or None."""
    if d is None:
        return None
    m = None
    if addr in by_vp:
        # prefer the 2D descriptor if present (more informative)
        for cand in by_vp[addr]:
            if cand["kind"] == "2D":
                m = cand
                break
        if m is None:
            m = by_vp[addr][0]
    if m is None:
        return None
    out = {"desc": m["o"], "kind": m["kind"], "cx": m["cx"], "type": TYPE_LABEL.get(m["type"], "?"),
           "scale": r4(m["sc"]), "offset": r4(m["of"])}
    if m["kind"] == "1D":
        out["ax"] = [r4(v) for v in m["ax"]]
        fmt, sz = CELL[m["type"]]
        out["vals"] = [r4(phys(rd(d, m["vp"] + i * sz, fmt, sz), m)) for i in range(m["cx"])]
    else:
        out["ax"] = [r4(v) for v in m["ax"]]
        out["ay"] = [r4(v) for v in m["ay"]]
        out["cy"] = len(m["ay"])
        fmt, sz = CELL[m["type"]]
        grid = []
        for j in range(m["cy"]):
            for i in range(m["cx"]):
                grid.append(r4(phys(rd(d, m["vp"] + (j * m["cx"] + i) * sz, fmt, sz), m)))
        out["grid"] = grid
    return out


def extract_axis(d, addr, maxn=64):
    """Reads a monotonically increasing f32 array starting at addr (heuristic)."""
    if d is None:
        return None
    if not (0x0 <= addr < len(d) - 4 and addr % 4 == 0):
        return None
    out, prev = [], None
    for i in range(maxn):
        o = addr + i * 4
        if o + 4 > len(d):
            break
        v = struct.unpack(">f", d[o:o + 4])[0]
        if not math.isfinite(v) or abs(v) > 1e7:
            break
        if prev is not None and not v > prev:
            break
        out.append(r4(v))
        prev = v
    return out if len(out) >= 2 else None


def heuristic_scalar(d, addr):
    """Plausible f32 for named scalars without a descriptor (conservative)."""
    if d is None or addr < 0 or addr + 4 > len(d):
        return None
    try:
        v = struct.unpack(">f", d[addr:addr + 4])[0]
    except Exception:
        return None
    if not math.isfinite(v):
        return None
    if not (abs(v) >= 0.01 and abs(v) <= 1e6):
        return None
    return r4(v)


def table_role(name, kind=""):
    """Row role for the tables view: 'x'/'y' for axis rows, 't' otherwise.

    Axis rows are the kind=axis entries whose names end with ' X Axis' /
    ' Y Axis' (all 662 do; no table/intermediate row carries the suffix).
    The previous `name == "X"` test never matched, so every axis was
    misclassified as a table (counts.tables_axes == 0 and the X/Y role
    filter in the UI was always empty). The kind column is kept as a
    fallback so a suffix-less axis row still counts as an axis."""
    if name.endswith(" X Axis"):
        return "x"
    if name.endswith(" Y Axis"):
        return "y"
    if kind == "axis":
        return "y"
    return "t"


def load_tables(d, by_vp, by_axp, by_ayp, rows=None):
    if rows is None:
        p = os.path.join(SYM, "cal_tables.csv")
        if not os.path.exists(p):
            warn("missing " + p)
            return []
        rows = list(csv.DictReader(open(p, encoding="utf-8", errors="replace")))
    out = []
    gid = 0
    cur = None  # current group
    for r in rows:
        name = r["name"].strip()
        try:
            addr = int(r["address"], 16)
        except Exception:
            warn("invalid address: %s" % r.get("address"))
            continue
        role = table_role(name, r.get("kind", ""))
        ent = {"n": name, "a": addr, "c": table_category(name), "role": role, "g": gid}
        if role == "t":
            cur = ent
            gid += 1
        else:
            if cur is None:
                cur = {"n": "(axis only)", "a": None}
            ent["tbl"] = cur["n"]
            ent["tbladdr"] = cur.get("a")
        ent["rom"] = "60E1D400"
        if role == "t":
            v = extract_table(d, by_vp, by_axp, by_ayp, addr)
            if v:
                ent["t"] = v
            else:
                ent["raw"] = d[addr:addr + 16].hex() if d and addr < len(d) else None
                ent["scalar"] = heuristic_scalar(d, addr)
                # guess the type from the name (label only)
                ent["t"] = None
        else:
            # axis: try the descriptor (via by_axp/by_ayp) then the heuristic
            ax = None
            for m in (by_axp.get(addr, []) + by_ayp.get(addr, [])):
                if m["kind"] == "1D":
                    ax = m["ax"]
                    break
            if ax is None:
                for m in (by_axp.get(addr, []) + by_ayp.get(addr, [])):
                    if m["kind"] == "2D":
                        ax = m["ax"] if m["axp"] == addr else m["ay"]
                        break
            if ax is None:
                ax = extract_axis(d, addr)
            if ax:
                ent["ax"] = [r4(v) for v in ax]
        out.append(ent)
    return out


# --------------------------------------------------------------------------
# 5b. Firmware models: roms_meta.json + table_addr_map_long.csv
# --------------------------------------------------------------------------
# The address map must ALWAYS be taken from data/table_addr_map_long.csv
# (per-ROM rows). The cal layout is NOT uniformly shifted: the drift is
# piecewise-constant, so a global offset must never be applied.
METHOD_SHORT = {"same_addr": "same", "content_match": "match", "family_shift": "shift",
                "hole": "hole", "unmatched": "unmatched"}
CONF_SHORT = {"high": "high", "medium": "medium", "low": "low"}


def load_roms_meta():
    """Returns the list of model dicts from data/roms_meta.json (stable order)."""
    if not os.path.exists(ROMS_META):
        warn("missing " + ROMS_META)
        return []
    try:
        return json.load(open(ROMS_META, encoding="utf-8"))
    except Exception as ex:
        warn("unreadable %s: %s" % (ROMS_META, ex))
        return []


def load_addr_map_long():
    """Parses data/table_addr_map_long.csv.
    Returns {(table_id, baseline_addr_lower): [(rom, addr_or_None, method, conf), ...]}.
    A key may hold several entries when the master CSV contains duplicate
    (table_id, baseline_addr) rows (one known case: the Y axis @0x7b43c)."""
    if not os.path.exists(ADDR_MAP_LONG):
        warn("missing " + ADDR_MAP_LONG)
        return {}
    out = {}
    for r in csv.DictReader(open(ADDR_MAP_LONG, encoding="utf-8", errors="replace")):
        try:
            a = int(r["addr"], 16) if r["addr"].strip() else None
        except Exception:
            a = None
        out.setdefault((r["table_id"], r["baseline_addr"].lower()), []).append(
            (r["rom"], a, r["method"], r["confidence"]))
    return out


def addr_map_for_model(mapby, key):
    """From the global map, builds {baseline_addr(int): [(target_or_None, method, conf), ...]}
    for one ROM, preserving the CSV order of duplicate entries."""
    d = {}
    for (tid, base), entries in mapby.items():
        try:
            base_int = int(base, 16)
        except Exception:
            continue
        for (rom, a, m, c) in entries:
            if rom == key:
                d.setdefault(base_int, []).append((a, m, c))
    return d


def mapped_item_for_row(dmap, base, seen):
    """Picks the (target_or_None, method, conf) for a master-CSV row with a
    baseline address; `seen` de-queues duplicates (positional alignment)."""
    lst = dmap.get(base)
    if not lst:
        return None
    if len(lst) == 1:
        return lst[0]
    i = seen.get(base, 0)
    seen[base] = i + 1
    return lst[i] if i < len(lst) else lst[0]


def extract_model_values(d, by_vp, by_axp, by_ayp, rows, dmap):
    """Extracts the value-carrying payload (t/ax/scalar/raw) for every master-CSV
    row at the address mapped to this ROM. Returns an array aligned 1:1 with
    `rows` (same indexes as DATA.tables); null = nothing extracted."""
    out = []
    seen = {}
    for r in rows:
        name = r["name"].strip()
        try:
            base = int(r["address"], 16)
        except Exception:
            out.append(None)
            continue
        item = mapped_item_for_row(dmap, base, seen)
        target = item[0] if item else None
        role = table_role(name, r.get("kind", ""))
        ent = None
        if role == "t":
            v = extract_table(d, by_vp, by_axp, by_ayp, target) if target is not None else None
            if v:
                ent = {"t": v}
            elif target is not None and d is not None and target + 4 <= len(d):
                ent = {"raw": d[target:target + 16].hex()}
                sc = heuristic_scalar(d, target)
                if sc is not None:
                    ent["scalar"] = sc
        else:
            ax = None
            if target is not None:
                for m in (by_axp.get(target, []) + by_ayp.get(target, [])):
                    if m["kind"] == "1D":
                        ax = m["ax"]
                        break
                if ax is None:
                    for m in (by_axp.get(target, []) + by_ayp.get(target, [])):
                        if m["kind"] == "2D":
                            ax = m["ax"] if m["axp"] == target else m["ay"]
                            break
                if ax is None:
                    ax = extract_axis(d, target)
                if ax:
                    ent = {"ax": [r4(v) for v in ax]}
        out.append(ent)
    return out


def build_addr_map_arrays(mapby, models, rows):
    """Per-model address arrays aligned 1:1 with `rows`:
    {key: [[hexstr, method_short, conf], ...] or null when the table is not
    mapped in that ROM}."""
    addr_map = {}
    for m in models:
        key = m["id"]
        dmap = addr_map_for_model(mapby, key)
        arr = []
        seen = {}
        for r in rows:
            try:
                base = int(r["address"], 16)
            except Exception:
                arr.append(None)
                continue
            item = mapped_item_for_row(dmap, base, seen)
            if item and item[0] is not None:
                arr.append(["%x" % item[0],
                            METHOD_SHORT.get(item[1], item[1]),
                            CONF_SHORT.get(item[2], item[2])])
            else:
                arr.append(None)
        addr_map[key] = arr
    return addr_map


# --------------------------------------------------------------------------
# 6. Assemble the dataset
# --------------------------------------------------------------------------
def build_dataset():
    # Fail-closed: the core inputs must exist. A missing calibration CSV,
    # baseline ROM, model metadata or address map aborts the build (non-zero
    # exit) instead of producing a silently degraded site.
    need(os.path.join(SYM, "cal_tables.csv"), "calibration tables")
    need(ROM_CAL, "baseline ROM")
    need(ROMS_META, "firmware-model metadata")
    need(ADDR_MAP_LONG, "per-ROM address map")
    by_addr, order, symbols_invalid = load_symbols()
    docs, doc_exact, doc_norm, doc_addr = load_docs()
    subsystems = load_subsystems()
    edges, edges_invalid = load_edges()
    cat_by_name, cat_by_addr = load_categories()
    d = load_rom(ROM_CAL)
    if d is None:
        raise BuildError("unreadable baseline ROM (%s)" % ROM_CAL)
    by_vp, by_axp, by_ayp = build_descriptor_index(d) if d else ({}, {}, {})
    rows = list(csv.DictReader(open(os.path.join(SYM, "cal_tables.csv"),
                                    encoding="utf-8", errors="replace")))
    tables = load_tables(d, by_vp, by_axp, by_ayp, rows)

    # --- firmware models (roms_meta.json + table_addr_map_long.csv) ---
    models = load_roms_meta()
    mapby = load_addr_map_long()
    addr_map = build_addr_map_arrays(mapby, models, rows)
    model_values = {}  # key -> aligned values array (non-default models only)
    model_stats = {}
    if models and mapby:
        for m in models:
            key = m["id"]
            tmap = m.get("table_map", {})
            model_stats[key] = {
                "mapped": tmap.get("mapped", 0),
                "unmatched": tmap.get("unmatched", 0),
                "confidence": tmap.get("confidence", {}),
                "methods": tmap.get("methods", {}),
            }
            if key == DEFAULT_MODEL:
                continue
            path = os.path.join(ROM_DIR, m.get("file", ""))
            dm = load_rom(path)
            if dm is None:
                raise BuildError("missing/unreadable model ROM %s (%s)" % (key, path))
            by_vpm, by_axpm, by_aypm = build_descriptor_index(dm) if dm else ({}, {}, {})
            model_values[key] = extract_model_values(
                dm, by_vpm, by_axpm, by_aypm, rows, addr_map_for_model(mapby, key))
    else:
        warn("firmware-model data missing: models=%d map_entries=%d"
             % (len(models), len(mapby)))

    # --- final symbols ---
    # Every symbol that matches a doc gets "d": 1 and "di": index into docs[].
    # Matching: (1) exact filename, (2) normalized name without the _hex suffix,
    #           (3) address extracted from the doc header.
    # Category: FUNCTION_CATEGORIES.csv (if present) wins over the regex rules;
    # "cs" carries the classifier signal and "ct" flags low-confidence graph rows
    # as tentative (both "" when the CSV is missing / the symbol is unmatched).
    symbols = []
    for a in order:
        e = by_addr[a]
        name = e["name"]
        di = doc_exact.get(name.lower())
        if di is None:
            di = doc_norm.get(norm_doc_name(name))
        if di is None:
            di = doc_addr.get(a)
        cat_csv = None
        if cat_by_name is not None:
            cat_csv = cat_by_name.get(name)
            if cat_csv is None:
                cat_csv = cat_by_addr.get(a)
        if cat_csv is not None:
            csv_cat, csv_signal, csv_conf = cat_csv
            if csv_cat:
                category = csv_cat
            else:
                category = sym_category(name)
            cs = csv_signal
            ct = "tentative" if csv_signal == "graph" and csv_conf < 1.0 else "confirmed"
        else:
            category = sym_category(name)
            cs, ct = "", ""
        symbols.append({
            "a": e["a"], "e": e["end"] or e["a"], "n": name,
            "s": e["src"], "r": e["rom"], "d": 1 if di is not None else 0,
            "c": category, "cs": cs, "ct": ct,
        })
        if di is not None:
            symbols[-1]["di"] = di

    # --- edge index ---
    # Placeholders are inserted BEFORE the final sort: data.json symbols must
    # stay sorted by address because the frontend binary-searches on start
    # address (symContainingAddress). Sorting first and appending after left
    # every placeholder out of order.
    idx = {}
    for i, s in enumerate(symbols):
        idx.setdefault(s["a"], i)
    for ca, ka, kind in edges:
        if ca not in idx:
            # placeholder symbol (only if the addr is not present)
            idx[ca] = len(symbols)
            symbols.append({"a": ca, "e": ca, "n": "FUN_%06x" % ca, "s": "callgraph", "r": 0,
                            "d": 0, "c": sym_category("FUN"), "cs": "", "ct": ""})
        if ka not in idx:
            idx[ka] = len(symbols)
            symbols.append({"a": ka, "e": ka, "n": "FUN_%06x" % ka, "s": "callgraph", "r": 0,
                            "d": 0, "c": sym_category("FUN"), "cs": "", "ct": ""})
    symbols.sort(key=lambda s: s["a"])
    idx = {}
    for i, s in enumerate(symbols):
        idx.setdefault(s["a"], i)
    edge_out = [[idx[ca], idx[ka], kind] for ca, ka, kind in edges]

    with_val = sum(1 for t in tables if (t.get("t") and t["t"].get("vals")) or (t.get("t") and t["t"].get("grid")))
    with_any_val = sum(1 for t in tables if t.get("t") or t.get("ax") or t.get("scalar") is not None)

    data = {
        "meta": {
            "title": "RX-8 ECU Firmware Explorer",
            "script": "build_site.py",
            "contexts": {
                "callgraph": "60E0FC00 (symbols + callgraph)",
                "cal_tables": "cal_tables.csv (labeled 60E1D400) -> values extracted from 60E1D400.bin",
            },
            "rom_cal": ROM_CAL_REL,
            "docs": len(docs),
            "models": [
                {
                    "id": m["id"],
                    "cal_id": m.get("cal_id", ""),
                    "family": m.get("family", ""),
                    "role": m.get("role", ""),
                    "file": m.get("file", ""),
                    "sw": m.get("sw", ""),
                    "task": m.get("task"),
                    "code_end": m.get("code_end"),
                    "cal_lo": m.get("cal_lo"),
                    "cal_span": m.get("cal_span"),
                    "family_shift_vs_baseline": m.get("family_shift_vs_baseline", 0),
                    "stats": model_stats.get(m["id"], {}),
                }
                for m in models
            ],
            "default_model": DEFAULT_MODEL,
            "addr_map": addr_map,
            "sources": [
                "symbols/callgraph.csv", "symbols/cal_tables.csv",
                "symbols/symbols_60E0FC00.csv", "symbols/symbols_60E0FC00_ghidra.csv",
                "symbols/symbols_60E1D400_ida.csv", "symbols/symbols_60E1D400_merged.csv",
                "symbols/FUNCTION_CATEGORIES.csv",
                "roms/stock/60E1D400.bin", "roms/stock/*.bin",
                "docs/functions/*.md", "docs/subsystems/*.md",
                "web/explorer/data/roms_meta.json",
                "web/explorer/data/table_addr_map_long.csv",
            ],
            "counts": {
                "symbols": len(symbols),
                "edges": len(edge_out),
                "edges_bsr": sum(1 for e in edge_out if e[2] == "b"),
                "edges_ref": sum(1 for e in edge_out if e[2] == "r"),
                "symbols_invalid": symbols_invalid,
                "edges_invalid": edges_invalid,
                "tables_rows": len(tables),
                "tables": sum(1 for t in tables if t["role"] == "t"),
                "tables_axes": sum(1 for t in tables if t["role"] != "t"),
                "tables_with_values": with_val,
                "tables_with_any": with_any_val,
                "docs_total": len(docs),
                "docs_attached": sum(1 for s in symbols if "di" in s),
                "docs_unattached": len(docs) - len({s.get("di") for s in symbols if "di" in s}),
                "docs_matched": sum(1 for s in symbols if s["d"]),
                "subsystems": len(subsystems),
                "models": len(models),
                "model_value_files": len(model_values),
                "addr_map_entries": sum(len(v) for v in addr_map.values()),
            },
        },
        "symbols": symbols,
        "edges": edge_out,
        "tables": tables,
        "docs": docs,
        "subsystems": subsystems,
    }

    # Per-model value payloads (non-default models). Kept out of data.json to
    # stay under the size budget; serialized as dist/models/<key>.json by main().
    data["model_values"] = model_values

    # Optional, reproducible timestamp (standard SOURCE_DATE_EPOCH convention).
    if "SOURCE_DATE_EPOCH" in os.environ:
        try:
            data["meta"]["generated"] = datetime_iso_from_epoch(int(os.environ["SOURCE_DATE_EPOCH"]))
        except Exception:
            pass
    return data


def datetime_iso_from_epoch(epoch):
    import datetime
    return datetime.datetime.fromtimestamp(epoch, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------
# 7. Site assembly
# --------------------------------------------------------------------------
def fmt_count(n):
    return format(int(n), ",")


def build_stats(data):
    c = data["meta"]["counts"]
    return ("%s symbols · %s callgraph edges (%s bsr / %s ref) · %s calibration-table entries"
            " (%s tables + %s axes, %s with values) · %s function docs (%s matched) · %s subsystems"
            " · %s firmware models"
            % (fmt_count(c["symbols"]), fmt_count(c["edges"]), fmt_count(c["edges_bsr"]),
               fmt_count(c["edges_ref"]), fmt_count(c["tables_rows"]), fmt_count(c["tables"]),
               fmt_count(c["tables_axes"]), fmt_count(c["tables_with_values"]),
               fmt_count(c["docs_total"]), fmt_count(c["docs_attached"]),
               fmt_count(c["subsystems"]), fmt_count(c["models"])))


def render_html(data):
    with open(TEMPLATE, encoding="utf-8") as f:
        html = f.read()
    html = html.replace("__GENERATOR__", GENERATOR)
    html = html.replace("__BUILD_STATS__", build_stats(data))
    # B1: the role-filter count is emitted from the build (tables_rows), never
    # a hardcoded literal that can drift (1210 vs 1209).
    html = html.replace("__TABLES_COUNT__", str(data["meta"]["counts"]["tables_rows"]))
    return html


def sha256_file(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def manifest_inputs():
    """Required + best-effort input files fingerprinted for build_manifest.json.
    H2: includes FUNCTION_CATEGORIES.csv (names + categories drive the build
    at load_symbols/load_categories) and every docs/functions + docs/subsystems
    file (content is embedded in data.json). Sorted per-file SHA-256 so touching
    one doc changes the manifest."""
    paths = [
        os.path.join(SYM, "callgraph.csv"),
        os.path.join(SYM, "cal_tables.csv"),
        os.path.join(SYM, "symbols_60E0FC00.csv"),
        os.path.join(SYM, "symbols_60E0FC00_ghidra.csv"),
        os.path.join(SYM, "symbols_60E1D400_ida.csv"),
        os.path.join(SYM, "symbols_60E1D400_merged.csv"),
        os.path.join(SYM, "FUNCTION_CATEGORIES.csv"),
        ROM_CAL,
        ROMS_META,
        ADDR_MAP_LONG,
        TEMPLATE,
        SRC_APP,
        SRC_CSS,
    ]
    try:
        for f in sorted(os.listdir(ROM_DIR)):
            if f.endswith(".bin"):
                paths.append(os.path.join(ROM_DIR, f))
    except OSError:
        pass
    # Per-file hashes for both docs dirs (sorted for determinism).
    for d in (DOCS_DIR, SUBSYS_DIR):
        try:
            files = sorted(os.listdir(d))
        except OSError:
            continue
        for f in files:
            if not f.endswith(".md"):
                continue
            if d == DOCS_DIR and f.lower() == "readme.md":
                continue
            paths.append(os.path.join(d, f))
    out = {}
    for p in paths:
        rel = os.path.relpath(p, ROOT)
        out[rel] = sha256_file(p) if os.path.isfile(p) else "missing"
    return out


def build_manifest(data):
    """Freshness record: input hashes + output counts. A dist/ is fresh iff
    every recorded hash still matches the working tree (see the README
    'Freshness check' section); any mismatch means rebuild."""
    return {
        "generator": GENERATOR,
        "default_model": DEFAULT_MODEL,
        "inputs": manifest_inputs(),
        "counts": data["meta"]["counts"],
    }


def render_dist_readme(data):
    c = data["meta"]["counts"]
    lines = [
        "# RX-8 ECU Firmware Explorer — generated build (dist/)",
        "",
        "This directory is **generated** by `web/explorer/build_site.py` and must not",
        "be edited by hand. Regenerate it (deterministic, stdlib-only):",
        "",
        "```bash",
        "python3 web/explorer/build_site.py",
        "```",
        "",
        "## Contents",
        "",
        "- `index.html`, `app.js`, `style.css` — the application (source: `../src/`)",
        "- `data.json` — full dataset (fetched by the app via `fetch`); includes the",
        "  baseline (60E1D400) table values, the 9 firmware-model descriptors and the",
        "  per-model table address map",
        "- `data.js` — `window.EXPLORER_DATA = ...` fallback for opening via `file://`",
        "- `models/<key>.json` — per-model table values (8 files), fetched on demand",
        "  by the firmware-model selector (not available on `file://`)",
        "- `.nojekyll` — required so GitHub Pages serves the raw files as-is",
        "",
        "## Dataset summary",
        "",
        "| Metric | Value |",
        "|---|---|",
        "| Symbols / functions | %s |" % fmt_count(c["symbols"]),
        "| Callgraph edges (bsr / ref) | %s (%s / %s) |" % (fmt_count(c["edges"]), fmt_count(c["edges_bsr"]), fmt_count(c["edges_ref"])),
        "| Calibration-table entries (tables + axes) | %s (%s + %s) |" % (fmt_count(c["tables_rows"]), fmt_count(c["tables"]), fmt_count(c["tables_axes"])),
        "| Tables with extracted values | %s |" % fmt_count(c["tables_with_values"]),
        "| Function docs (matched to symbols) | %s (%s) |" % (fmt_count(c["docs_total"]), fmt_count(c["docs_attached"])),
        "| Subsystem docs | %s |" % fmt_count(c["subsystems"]),
        "| Firmware models | %s (value files: %s) |" % (fmt_count(c["models"]), fmt_count(c["model_value_files"])),
        "",
        "## Freshness check",
        "",
        "`build_manifest.json` (next to `data.json`) records the SHA-256 of every",
        "input file plus the output counts. The checked-in `dist/` output is fresh",
        "iff every recorded hash still matches the working tree; any mismatch (or a",
        "missing `build_manifest.json`) means the site is stale — rerun:",
        "",
        "```bash",
        "python3 web/explorer/build_site.py",
        "```",
        "",
        "Values are extracted from `%s`; symbols + callgraph use the `60E0FC00` context." % ROM_CAL_REL,
        "",
    ]
    return "\n".join(lines)


def write_text(path, text):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def write_bytes(path, b):
    with open(path, "wb") as f:
        f.write(b)


# --------------------------------------------------------------------------
# Optional local serving (--serve). Stdlib-only, in-process: the server runs
# in this same process, so Ctrl+C -> KeyboardInterrupt -> clean close with no
# leftover http.server process. Never touches the build output.
# --------------------------------------------------------------------------
def serve_site(port):
    import functools
    import http.server

    # B9: clean ERROR + return 1 on non-numeric ports (no traceback).
    try:
        port = int(port)
    except (TypeError, ValueError):
        print("ERROR: invalid port %r (expected 1-65535)" % (port,), file=sys.stderr)
        return 1
    if not (0 < port < 65536):
        print("ERROR: invalid port %r" % (port,), file=sys.stderr)
        return 1
    # Serve the combined dist/ (landing page at root, explorer/ and emu/ subdirs)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=DIST)
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    print("Serving %s at http://127.0.0.1:%d/  (Ctrl+C to stop)"
          % (os.path.abspath(DIST), port), flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server.")
    finally:
        httpd.server_close()
    return 0


def render_landing_page(data=None):
    """Landing page for the combined site at the repo root (/).
    Two cards: ROM Explorer and ECU Emulator, matching the dark theme."""
    if data is not None:
        c = data["meta"]["counts"]
        landing_stats = ("Firmware open &middot; %d symbols &middot; %d tables"
                         % (c["symbols"], c["tables_rows"]))
    else:
        landing_stats = "Firmware open &middot; 6083 symbols &middot; 1209 tables"
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="RX-8 ECU — open firmware reverse-engineering project: ROM Explorer and ECU Emulator.">
<meta name="theme-color" content="#0b0e13">
<title>RX-8 ECU</title>
<link rel="icon" href="data:,">
<style>
:root {
  --bg:#0b0e13; --bg2:#12161d; --bg3:#181d26; --border:#252c38; --border2:#333c4a;
  --text:#e6ebf2; --muted:#8b96a3; --accent:#4d7cff; --accent2:#aab4c4;
  --green:#7ee787; --red:#f85149; --purple:#bc8cff; --cyan:#39c5cf;
  --accent-alpha:rgba(77,124,255,.14);
  --mono: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
}
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; height: 100%; }
body {
  background:
    radial-gradient(960px 420px at 50% -120px, rgba(77,124,255,.13), rgba(77,124,255,0) 65%),
    var(--bg);
  color: var(--text);
  font: 14px/1.45 -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  min-height: 100vh; padding: 40px 16px;
}

.hero { text-align: center; margin-bottom: 36px; max-width: 640px; }
.hero .logo {
  width: 72px; height: 72px; border-radius: 16px; margin: 0 auto 16px;
  display: flex; align-items: center; justify-content: center;
  background: var(--bg2); border: 1px solid var(--border); color: var(--accent);
  box-shadow: 0 0 32px rgba(77,124,255,.18);
}
.hero .logo svg { width: 44px; height: 44px; }
.wordmark { font: 800 34px var(--mono); letter-spacing: .03em; color: var(--text); margin: 0; }
.wm-accent { color: var(--accent); }
.tagline { color: var(--muted); font-size: 14px; margin: 8px 0 0; }

.cards { display: flex; gap: 24px; flex-wrap: wrap; justify-content: center; }

.card-link {
  display: block; width: 340px; padding: 0; text-decoration: none; color: inherit;
  background: var(--bg2); border: 1px solid var(--border); border-radius: 14px;
  transition: border-color .2s, box-shadow .2s, transform .2s; overflow: hidden;
}
.card-link:hover, .card-link:focus-visible {
  border-color: var(--accent); box-shadow: 0 0 24px rgba(77,124,255,.15);
  transform: translateY(-2px);
}
.card-link:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }

.card-head {
  padding: 20px 22px 14px; border-bottom: 1px solid var(--border);
  display: flex; align-items: center; gap: 14px;
}
.card-icon {
  width: 44px; height: 44px; border-radius: 10px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  background: var(--accent-alpha); border: 1px solid var(--border);
  color: var(--accent); font: 700 16px var(--mono);
}
.card-icon svg { width: 22px; height: 22px; }
.card-title { font: 700 17px var(--mono); color: var(--text); }
.card-sub { color: var(--muted); font-size: 12px; margin-top: 2px; }

.card-body { padding: 16px 22px 20px; }
.card-body p { margin: 0; color: var(--muted); font-size: 13px; line-height: 1.6; }
.card-body .tags { margin-top: 12px; display: flex; flex-wrap: wrap; gap: 6px; }
.tag {
  display: inline-block; font: 11px var(--mono); padding: 2px 8px;
  border-radius: 10px; border: 1px solid var(--border2); color: var(--muted);
}
.tag.green { color: var(--green); border-color: var(--green); }
.tag.cyan { color: var(--cyan); border-color: var(--cyan); }
.tag.purple { color: var(--purple); border-color: var(--purple); }
.tag.blue { color: var(--accent); border-color: var(--accent); }

.card-footer {
  padding: 10px 22px; border-top: 1px solid var(--border);
  font: 600 12px var(--mono); color: var(--accent); text-align: right;
}
.card-footer::after { content: " \\2192"; }

footer {
  margin-top: 36px; color: var(--muted); font-size: 11.5px; text-align: center;
}
.status { font: 12px var(--mono); color: var(--accent2); margin-bottom: 6px; }

@media (max-width: 760px) {
  .cards { flex-direction: column; align-items: center; }
  .card-link { width: 100%; max-width: 380px; }
}
@media (max-width: 480px) {
  body { padding: 28px 14px; }
  .hero { margin-bottom: 28px; }
  .hero .logo { width: 60px; height: 60px; border-radius: 14px; }
  .hero .logo svg { width: 36px; height: 36px; }
  .wordmark { font-size: 27px; }
  .tagline { font-size: 13px; }
}
</style>
</head>
<body>

<header class="hero">
  <div class="logo" aria-hidden="true">
    <svg viewBox="0 0 24 24" width="44" height="44" fill="currentColor" stroke="currentColor"
         stroke-width="2" stroke-linejoin="round">
      <path d="M12 3.2 Q18.93 8.01 19.62 16.42 Q12 19.98 4.38 16.42 Q5.07 8.01 12 3.2 Z"/>
      <circle cx="12" cy="12" r="3.2" style="fill:var(--bg2)" stroke="none"/>
    </svg>
  </div>
  <h1 class="wordmark">RX-<span class="wm-accent">8</span> ECU</h1>
  <p class="tagline">Open firmware reverse-engineering project &mdash; SH7055 &middot; 96-pin &middot; Renesis</p>
</header>

<main class="cards">

  <a class="card-link" href="explorer/" aria-label="Open ROM Explorer">
    <div class="card-head">
      <div class="card-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
        </svg>
      </div>
      <div>
        <div class="card-title">ROM Explorer</div>
        <div class="card-sub">Firmware reverse-engineering browser</div>
      </div>
    </div>
    <div class="card-body">
      <p>Browse 6,000+ symbols, interactive callgraph, 1,209 calibration
      tables with extracted values across 9 stock firmware models.
      Function documentation, address lookup, and subsystem docs.</p>
      <div class="tags">
        <span class="tag blue">callgraph</span>
        <span class="tag green">calibration tables</span>
        <span class="tag cyan">9 firmware models</span>
        <span class="tag purple">documentation</span>
      </div>
    </div>
    <div class="card-footer">Open Explorer</div>
  </a>

  <a class="card-link" href="emu/" aria-label="Open ECU Emulator">
    <div class="card-head">
      <div class="card-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <rect x="4" y="4" width="16" height="16" rx="2"/>
          <path d="M9 1v3M15 1v3M9 20v3M15 20v3M1 9h3M1 15h3M20 9h3M20 15h3"/>
        </svg>
      </div>
      <div>
        <div class="card-title">ECU Emulator</div>
        <div class="card-sub">Interactive 96-pin connector simulator</div>
      </div>
    </div>
    <div class="card-body">
      <p>Interactive N3J1-18-881L 96-pin connector pinout with schematic view,
      live sensor controls (RPM, ECT, IAT, MAP, TPS, O2),
      ADC simulation, peripheral register view, and preset scenarios.</p>
      <div class="tags">
        <span class="tag blue">96-pin connector</span>
        <span class="tag green">sensor sliders</span>
        <span class="tag cyan">ADC simulation</span>
        <span class="tag purple">schematics</span>
      </div>
    </div>
    <div class="card-footer">Open Emulator</div>
  </a>

</main>

<footer>
  <div class="status">__LANDING_STATS__</div>
  <div>data from the
  <a href="https://github.com/davtur19/rx8ecu" style="color:var(--accent)">rx8ecu</a> project</div>
</footer>

</body>
</html>""".replace("__LANDING_STATS__", landing_stats)


def copy_emu_files():
    """Copy ecu-emu dist files into dist/emu/. Fail-loud: a missing emu
    source aborts the build instead of shipping a landing page whose
    emulator card 404s.
    B12: wipe emu_dst before copy (diff-sync) so stale files from a previous
    emu build cannot linger; warn on skipped non-files."""
    import shutil
    emu_dst = os.path.join(DIST, "emu")
    if not os.path.isdir(EMU_DIST_SRC):
        print("ERROR: ecu-emu dist not found at %s — failing the build "
              "instead of shipping a dead emu/ link" % EMU_DIST_SRC, file=sys.stderr)
        return False
    # Wipe the destination first (fresh dir) to drop stale outputs.
    if os.path.isdir(emu_dst):
        for name in sorted(os.listdir(emu_dst)):
            p = os.path.join(emu_dst, name)
            try:
                if os.path.isfile(p) or os.path.islink(p):
                    os.remove(p)
                elif os.path.isdir(p):
                    shutil.rmtree(p)
                else:
                    warn("skipping non-file emu output %s" % p)
            except Exception as ex:
                warn("cannot clear stale emu output %s: %s" % (p, ex))
    os.makedirs(emu_dst, exist_ok=True)
    for name in sorted(os.listdir(EMU_DIST_SRC)):
        src = os.path.join(EMU_DIST_SRC, name)
        dst = os.path.join(emu_dst, name)
        if os.path.isfile(src):
            with open(src, "rb") as f:
                data = f.read()
            with open(dst, "wb") as f:
                f.write(data)
        else:
            warn("skipping non-file emu source %s" % src)
    print("-> copied ecu-emu dist -> %s/" % os.path.relpath(emu_dst, DIST))
    return True


def main(argv):
    parser = argparse.ArgumentParser(
        prog="build_site.py",
        description="Deterministic, offline builder for the RX-8 ECU Firmware Explorer.",
    )
    parser.add_argument(
        "--serve", nargs="?", const="8000", default=None, metavar="PORT",
        help="after building, serve dist/ with python http.server on PORT "
             "(default 8000). The build output is identical with or without this flag.",
    )
    args = parser.parse_args(argv)

    print("=== %s ===" % GENERATOR)
    os.makedirs(EXPLORER_DIST, exist_ok=True)

    try:
        data = build_dataset()
    except BuildError as ex:
        print("ERROR: %s" % ex, file=sys.stderr)
        return 1
    model_values = data.pop("model_values", {})
    payload = json.dumps(data, separators=(",", ":"), ensure_ascii=False)

    # 1) index.html assembled from the template (goes to dist/explorer/)
    write_text(os.path.join(EXPLORER_DIST, "index.html"), render_html(data))

    # 2) app.js / style.css copied from src/
    with open(SRC_APP, encoding="utf-8") as f:
        write_text(os.path.join(EXPLORER_DIST, "app.js"), f.read())
    with open(SRC_CSS, encoding="utf-8") as f:
        write_text(os.path.join(EXPLORER_DIST, "style.css"), f.read())

    # 3) dataset
    write_text(os.path.join(EXPLORER_DIST, "data.json"), payload)
    with open(os.path.join(EXPLORER_DIST, "data.js"), "w", encoding="utf-8", newline="\n") as f:
        f.write("/* file:// fallback: generated by %s - use data.json via fetch when possible */\n" % GENERATOR)
        f.write("window.EXPLORER_DATA = ")
        f.write(payload)
        f.write(";\n")

    # 4) per-model value files (dist/explorer/models/<key>.json), fetched on demand.
    #    The default model (D400) values stay embedded in data.json.
    os.makedirs(MODELS_DIR, exist_ok=True)
    for key in sorted(model_values):
        mfile = {"key": key, "cal_id": "", "values": model_values[key]}
        for m in data["meta"]["models"]:
            if m["id"] == key:
                mfile["cal_id"] = m["cal_id"]
                break
        write_text(os.path.join(MODELS_DIR, key + ".json"),
                   json.dumps(mfile, separators=(",", ":"), ensure_ascii=False))

    # 5) .nojekyll (explicit empty bytes, no platform newline) + manifest + README
    write_bytes(os.path.join(EXPLORER_DIST, ".nojekyll"), b"")
    write_text(os.path.join(EXPLORER_DIST, "build_manifest.json"),
               json.dumps(build_manifest(data), indent=1, sort_keys=True) + "\n")
    write_text(os.path.join(EXPLORER_DIST, "README.md"), render_dist_readme(data))

    # 6) Landing page at dist/ root + .nojekyll for GitHub Pages
    write_text(os.path.join(DIST, "index.html"), render_landing_page(data))
    write_bytes(os.path.join(DIST, ".nojekyll"), b"")

    # 7) Copy ecu-emu dist into dist/emu/ (fail-loud: no silent 404 card)
    if not copy_emu_files():
        return 1

    # report
    c = data["meta"]["counts"]
    print("-> %s" % os.path.join(EXPLORER_DIST, "index.html"))
    print("-> %s (%.1f KB)" % (os.path.join(EXPLORER_DIST, "data.json"), os.path.getsize(os.path.join(EXPLORER_DIST, "data.json")) / 1024))
    print("-> %s (%.1f KB)" % (os.path.join(EXPLORER_DIST, "data.js"), os.path.getsize(os.path.join(EXPLORER_DIST, "data.js")) / 1024))
    for key in sorted(model_values):
        p = os.path.join(MODELS_DIR, key + ".json")
        print("-> %s (%.1f KB)" % (os.path.relpath(p, DIST), os.path.getsize(p) / 1024))
    print("-> %s (landing page)" % os.path.join(DIST, "index.html"))
    print("symbols=%d edges=%d (bsr=%d ref=%d) tables_rows=%d (tables=%d axes=%d) "
          "with_values=%d function_docs=%d (attached=%d) subsystems=%d models=%d "
          "model_value_files=%d addr_map_entries=%d"
          % (len(data["symbols"]), len(data["edges"]), c["edges_bsr"], c["edges_ref"],
             len(data["tables"]), c["tables"], c["tables_axes"], c["tables_with_values"],
             len(data["docs"]), c["docs_attached"], len(data["subsystems"]),
             c["models"], c["model_value_files"], c["addr_map_entries"]))
    if WARN:
        print("warnings:", len(WARN))

    if args.serve is not None:
        return serve_site(args.serve)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
