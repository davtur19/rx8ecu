#!/usr/bin/env python3
"""
classify_functions.py
=====================

Hybrid classifier for the explorer-dashboard function universe. The dashboard
(`web/explorer/build_site.py`) labels 6082 symbols purely from a name regex
(`sym_category`). This standalone tool re-classifies the 3538 symbols that land
in "Other / Unclassified" using a 4-tier hybrid approach and emits a reviewable
CSV at `symbols/FUNCTION_CATEGORIES.csv`.

Tiers (applied in order, first hit wins; a `signal` field records which tier fired):
  * Tier A (name)  : extended name regex (SYM_RULES_EXT).             conf 1.00
  * Tier B (cal)   : function literal-pool references mapped to cal-table
                     address ranges; classify via table-name vocabulary. conf 0.85
  * Tier C (graph) : iterative label propagation along the call graph from
                     confidently classified seeds (agreement >= 0.6).
  * Tier D (none)  : fallback "Other / Unclassified".                 conf 0.0

Every symbol of the 6082-universe appears in the output, classified or not.

Read-only inputs (missing files are reported and skipped gracefully):
  symbols/symbols_60E0FC00.csv           symbols/symbols_60E0FC00_ghidra.csv
  symbols/symbols_60E1D400_ida.csv       symbols/symbols_60E1D400_merged.csv
  symbols/callgraph.csv                  symbols/cal_tables.csv
  symbols/romraider_rx8_tables.csv
  src/60E0FC00_annotated.s               src/60E1D400_annotated.s

Output:
  symbols/FUNCTION_CATEGORIES.csv        (bank,addr,name,category,confidence,signal)

Python 3 stdlib only. Run from the repo root:
  python3 tools/classify_functions.py
"""
import csv, os, re, sys, time
from collections import Counter, defaultdict

REPO = os.path.dirname(os.path.abspath(__file__))
if os.path.isfile(os.path.join(REPO, "Makefile")):
    REPO = REPO
else:
    # climb until we find the repo root (contains Makefile)
    cur = os.path.dirname(REPO)
    while cur != os.path.dirname(cur):
        if os.path.isfile(os.path.join(cur, "Makefile")):
            REPO = cur
            break
        cur = os.path.dirname(cur)
SYM = os.path.join(REPO, "symbols")

# ---------------------------------------------------------------------------
# Category taxonomy (must match web/explorer/build_site.py SYM_RULES exactly)
# ---------------------------------------------------------------------------
OTHER = "Other / Unclassified"
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

# Extended name rules: additional patterns that map to the SAME category names.
# No new category names are introduced by the extensions.
SYM_RULES_EXT = SYM_RULES + [
    (r"\bcan\b|\bcan|frame|txd|rxd", "CAN Bus"),              # CAN frames / transceivers
    (r"\bconvers\w*|sqrt|saturate", "Math / FPU"),            # conversions / FPU helpers
    (r"inlet|intake|altitude|turb|waste", "Sensors"),         # air-path sensors
    (r"\bcoil\b|dwell|ignl", "Ignition & Knock"),
    (r"evap|purge|catalyst|\bcats?\b", "Fuel & Lambda"),
    (r"tach|speedo|\bsd\b", "Rev Limit"),                     # tachometer / speed driver
    (r"watchdog|wdt|stby", "RTOS"),
    (r"\batu\b|atu_|atu\d", "Peripherals & ISR"),            # SH-2 ATU serial/DMA units
    (r"illegal|trap|undef", "Boot & Init"),                   # exception vectors
    (r"verify|write_bytes|read_bytes|\brom\b|block|copy|move", "Memory & CRC"),  # mem/data ops
    # Issue 2: 1D/2D/3D/4D table lookup & interpolation primitives -> Math / FPU.
    # Placed last so clearly domain-specific lookups (fuel/ign/timing/idle/...) still
    # keep their earlier, more specific classification; genuinely-generic lookup /
    # search / index primitives land in Math / FPU (prefer Math over a forced guess).
    (r"lookup|calc2d|calc3d|tablesearch|table_search|binary_search", "Math / FPU"),
]

def base_regex_category(name, rules):
    for pat, cat in rules:
        if re.search(pat, name, re.I):
            return cat
    return None

def name_category(name):
    for pat, cat in SYM_RULES_EXT:
        if re.search(pat, name, re.I):
            return cat
    return None

# ---------------------------------------------------------------------------
# Category precedence for the one-category-per-name rule (Issue 1).
# Must contain the 17 canonical category names exactly once.
# ---------------------------------------------------------------------------
CAT_PRIORITY = [
    "OBD / UDS", "CAN Bus", "Faults & DTC", "Fuel & Lambda", "Sensors",
    "Ignition & Knock", "Math / FPU", "RTOS", "Boot & Init",
    "Peripherals & ISR", "Memory & CRC", "Throttle & Torque", "Rev Limit",
    "Idle Control", "Oil Metering", "Utilities", OTHER,
]
CAT_ORDER = {c: i for i, c in enumerate(CAT_PRIORITY)}

def override_category(name):
    """Issue 3: explicit name-pattern overrides. Returns (cat, conf, signal) or
    None if no override applies. signal stays within the allowed set
    {name, none} (Issue 4); conf 1.0 for real decisions, 0.0 for deliberate
    'leave to Other' decisions. First match wins.
    """
    low = name.lower()
    # --- fpu_div * : FPU divide primitives -> Math / FPU -----------------
    # (also fixes the bogus 'ram' in "pa-ram" hitting Memory & CRC)
    if re.search(r"fpu_div", low):
        return ("Math / FPU", 1.0, "name")
    # --- rear O2 (sensor / fuel trim family) -> Fuel & Lambda ------------
    # note: `low` is lowercase, so the pattern must be lowercase too
    if re.search(r"rearo2", low):
        return ("Fuel & Lambda", 1.0, "name")
    # --- Secondary Shutter Valve control -> Sensors ----------------------
    # `ssv\s*control` matches ssvControl / getSSVControl but NOT ssvDiagControl?
    # (a 'diag' token sits between 'ssv' and 'control', so it keeps Faults & DTC).
    if re.search(r"ssv\s*control", low):
        return ("Sensors", 1.0, "name")
    # --- engine speed family -> Sensors -----------------------------------
    if re.search(r"getenginespeed", low):
        return ("Sensors", 1.0, "name")
    # --- RTOS task-table scanning (the 'scan' substring is NOT CAN) ------
    if re.search(r"task_table_scan|inc_table_table_scan", low):
        return ("RTOS", 1.0, "name")
    # --- Immobilizer / security. Plicy: keep Other/Unclassified unless the
    #     name itself clearly relates to an existing category (Faults & DTC,
    #     Sensors for ADC, Peripherals & ISR for counter/timer). NOTE: the
    #     pattern is `immo(?!d)` so that "...imMode22" (OBD Mode 22 names:
    #     e.g. getRearO2FuelTrimMode22) is NOT treated as immobilizer.
    if re.search(r"immo(?!d)|immobil", low):
        if re.search(r"fault|dtc|error|warning|trouble", low):
            return ("Faults & DTC", 1.0, "name")
        if re.search(r"adc|voltage|sensor", low):
            return ("Sensors", 1.0, "name")
        if re.search(r"counter|timer", low):
            return ("Peripherals & ISR", 1.0, "name")
        return (OTHER, 0.0, "none")
    # --- Dynamic Stability Control (DSC_) --------------------------------
    # Sensible existing category only if the name carries a fault/DTC signal;
    # otherwise keep Other/Unclassified (consistent across all DSC_ rows).
    if re.search(r"^dsc_", low):
        if re.search(r"fault|dtc|error|trouble", low):
            return ("Faults & DTC", 1.0, "name")
        return (OTHER, 0.0, "none")
    # --- eShaft (electric/eccentric shaft) learn: ambiguous -> leave Other
    if re.search(r"eshaft", low):
        return (OTHER, 0.0, "none")
    return None

def dedupe_by_name(order, store, final):
    """Issue 1: one category per distinct function name.

    For every distinct name, pick a single winning category by priority:
      (a) any row whose signal=='name' (conf 1.0) wins outright (deterministic
          name/override classifications);
      (b) else strict majority vote of the name's row categories;
      (c) else tie-break by CAT_ORDER.
    Apply the winning (category, signal, confidence) to all rows with the name.
    Returns the number of distinct names whose rows disagreed pre-dedup.
    """
    by_name = defaultdict(list)
    for k in order:
        by_name[store[k]["name"]].append(k)
    dup_names = 0
    for name, keys in by_name.items():
        rows = [final[k] for k in keys]
        if len({r[0] for r in rows}) <= 1:
            continue
        dup_names += 1
        winner = None
        for r in rows:
            if r[2] == "name" and r[1] >= 1.0 - 1e-9:
                winner = r
                break
        if winner is None:
            votes = Counter(r[0] for r in rows)
            best, nbest = votes.most_common(1)[0]
            tied = [c for c, n in votes.items() if n == nbest]
            chosen = best if len(tied) == 1 else min(tied, key=CAT_ORDER.get)
            winner = max((r for r in rows if r[0] == chosen), key=lambda r: r[1])
        for k in keys:
            final[k] = winner
    return dup_names

# ---------------------------------------------------------------------------
# 1. Load the 6082-symbol universe (replicates build_site.load_symbols)
# ---------------------------------------------------------------------------
def load_universe():
    """Returns (store, order, missing).
    store: dict addr -> row{bank, addr, name, end, prio}
    order: list of addr keys, insertion order.

    NOTE: build_site.load_symbols dedups on `addr` ALONE across all four CSV
    files (a single global by_addr dict), which yields exactly 6082 unique
    addresses. Name priority: merged(4) > ghidra/ida(3) > hand-in-base(2) >
    base-auto(1). The winning source determines the symbol's `bank`.
    """
    store = {}
    order = []

    def put(addr, name, end, prio, bank):
        if addr in store:
            e = store[addr]
            if prio > e["prio"]:
                e["name"] = name
                e["prio"] = prio
                e["bank"] = bank
            if end is not None and (e["end"] is None or end > e["end"]):
                e["end"] = end
        else:
            store[addr] = {"bank": bank, "addr": addr, "name": name,
                           "end": end if end is not None else addr, "prio": prio}
            order.append(addr)

    specs = [
        ("symbols_60E0FC00.csv", "60E0FC00", 1),
        ("symbols_60E0FC00_ghidra.csv", "60E0FC00", 3),
        ("symbols_60E1D400_ida.csv", "60E1D400", 3),
        ("symbols_60E1D400_merged.csv", "60E1D400", 4),
    ]
    missing = []
    for fname, bank, prio0 in specs:
        p = os.path.join(SYM, fname)
        if not os.path.exists(p):
            missing.append(fname)
            continue
        for r in csv.DictReader(open(p, encoding="utf-8", errors="replace")):
            try:
                a = int(r["addr"], 16)
            except Exception:
                continue
            end = None
            try:
                end = int(r.get("end") or "0", 16) or None
            except Exception:
                pass
            src = r.get("source", "")
            prio = prio0
            if fname == "symbols_60E0FC00.csv" and "hand" in src:
                prio = 2  # hand-named entries in the base file outrank auto
            put(a, r["name"], end, prio, bank)
    return store, order, missing

# ---------------------------------------------------------------------------
# 2. Call graph edges (60E0FC00 context)
# ---------------------------------------------------------------------------
def load_edges():
    p = os.path.join(SYM, "callgraph.csv")
    if not os.path.exists(p):
        return [], [p]
    edges = []
    for r in csv.DictReader(open(p, encoding="utf-8", errors="replace")):
        try:
            ca = int(r["caller_addr"], 16)
            ce = int(r["callee_addr"], 16)
        except Exception:
            continue
        edges.append((ca, ce))
    return edges, []

# ---------------------------------------------------------------------------
# 3. Cal tables -> per-bank (start, end, name) list
# ---------------------------------------------------------------------------
def load_table_map():
    tab = defaultdict(list)
    missing = []
    p1 = os.path.join(SYM, "romraider_rx8_tables.csv")
    if os.path.exists(p1):
        for r in csv.DictReader(open(p1, encoding="utf-8", errors="replace")):
            bank = r.get("rom_code", "")
            if bank not in ("60E0FC00", "60E1D400"):
                continue
            try:
                s = int(r["addr"], 16)
                e = int(r.get("end_addr") or r["addr"], 16)
            except Exception:
                continue
            nm = r.get("name", "")
            tab[bank].append((s, e, nm))
    else:
        missing.append(p1)

    p2 = os.path.join(SYM, "cal_tables.csv")
    if os.path.exists(p2):
        for r in csv.DictReader(open(p2, encoding="utf-8", errors="replace")):
            try:
                s = int(r["address"], 16)
            except Exception:
                continue
            nm = r.get("name", "")
            # master reference list: point ranges added to every bank's map
            for b in ("60E0FC00", "60E1D400"):
                tab[b].append((s, s + 4, nm))
    else:
        missing.append(p2)
    return tab, missing

# Cal-table name -> category vocab (maps onto the 17 canonical names).
# Ordered most-specific-first so e.g. "Oil Temperature" -> Oil Metering and
# "Cold Rev Temperature Limit" -> Rev Limit rather than Sensors.
TBL_VOCAB = [
    (r"obd|uds|iso|kline", "OBD / UDS"),
    (r"dtc|fault|diagnostic|mil", "Faults & DTC"),
    (r"can|message|frame|tx|rx", "CAN Bus"),
    (r"ign|ignition|dwell|spark|advance|knock|timing|coil", "Ignition & Knock"),
    (r"inject|injection|fuel|fuelling|lambda|o2|afr|trim|pump|latency|pulse", "Fuel & Lambda"),
    (r"idle", "Idle Control"),
    (r"oil|omp|metering", "Oil Metering"),
    (r"rev|rpm|limit", "Rev Limit"),
    (r"throttle|pedal|torque|tps|vdi|boost|load", "Throttle & Torque"),
    (r"baro|barometric|pressure|temp|coolant|iat|adc|voltage|sensor|maf|therm", "Sensors"),
    (r"interp|lookup|interpolat|scal|convers|2d|3d|fpu|float", "Math / FPU"),
]

def table_category(tabname):
    for pat, cat in TBL_VOCAB:
        if re.search(pat, tabname, re.I):
            return cat
    return None

# ---------------------------------------------------------------------------
# 4. Parse annotated `.s` -> function bodies + literal word map
# ---------------------------------------------------------------------------
def parse_annotated(path):
    """Returns (funcs, words).
    funcs: dict addr -> (end, name, list of raw body lines)
    words: dict addr -> 16-bit word for every real `.word` data line."""
    if not os.path.exists(path):
        return {}, {}
    funcs = {}
    words = {}
    cur = None
    cur_end = None
    cur_body = []
    cname = None
    for ln in open(path, encoding="utf-8", errors="replace"):
        m = re.match(r"\s*! --- (\S+)\s+0x([0-9a-fA-F]+)-0x([0-9a-fA-F]+)\s+\[.*?\]\s+---", ln)
        if m:
            if cname is not None and cur is not None:
                funcs[cur] = (cur_end, cname, cur_body)
            cname = m.group(1)
            cur = int(m.group(2), 16)
            cur_end = int(m.group(3), 16)
            cur_body = [ln]
            continue
        if cur is None:
            continue
        m = re.match(r"^L_([0-9a-fA-F]+):", ln)
        if m:
            cur = int(m.group(1), 16)
            cur_body.append(ln)
            continue
        m = re.match(r"^\s*\.word 0x([0-9a-fA-F]+)", ln)
        if m:
            words[cur] = int(m.group(1), 16)
            cur += 2
            cur_body.append(ln)
            continue
        st = ln.strip()
        if not st or st.startswith("!") or st == ".text":
            continue
        if re.match(r"^[A-Za-z_][A-Za-z0-9_.]*:", st):     # global symbol label
            continue
        cur += 2                                            # instruction = 2 bytes
        cur_body.append(ln)
    if cname is not None and cur is not None:
        funcs[cur] = (cur_end, cname, cur_body)
    return funcs, words

def literal32(words, addr):
    """32-bit big-endian value stored at addr (two consecutive .word lines)."""
    if addr not in words or (addr + 2) not in words:
        return None
    return (words[addr] << 16) | words[addr + 2]

def tier_b_scan(funcs, words, ranges):
    """For each function addr returns (category, table_name) or (None, None).
    Scans body lines for mov.l L_<hex> literal loads, resolves the 32-bit
    constant, and checks membership in the cal-table range list."""
    # sort ranges once; ranges are small (~2700) so linear scan per hit is fine
    out = {}
    for addr, (end, name, body) in funcs.items():
        hits = []
        for ln in body:
            m = re.search(r"mov\.l\s+L_([0-9a-fA-F]+)", ln)
            if not m:
                continue
            la = int(m.group(1), 16)
            val = literal32(words, la)
            if val is None:
                continue
            for (s, e, tn) in ranges:
                if s <= val <= e:
                    hits.append((val, tn))
                    break
        if hits:
            # prefer table names whose vocabulary maps to a category
            for val, tn in hits:
                cat = table_category(tn)
                if cat:
                    out[addr] = (cat, tn, val)
                    break
    return out

def tier_b_scan_rom(rom, funcs, ranges):
    """ROM-based Tier B (the way tools/extract_func.py resolves literals).

    For every function body in `rom` (a bytes object), scan for `mov.l
    @(disp,pc),Rn` (top nibble 0xD), resolve the literal address as
    ((pc+4)&~3) + disp*4, read the 32-bit big-endian constant, and check
    membership in the cal-table range list. Ranges with start < 0x10000 are
    skipped: they are junk bit-address rows (e.g. 'DTC ... Enable/Disable'
    entries at addr 0x0 in romraider) that would create false positives.
    """
    out = {}
    # sort ranges by start so first-match is deterministic
    ranges = sorted(ranges, key=lambda r: (r[0], r[1]))
    for a, e in funcs:
        e = min(e, len(rom))
        b = a
        found = None
        while b + 1 < e:
            w = (rom[b] << 8) | rom[b + 1]
            if (w >> 12) == 0xD:                     # mov.l @(disp,pc),Rn
                lit = ((b + 4) & ~3) + (w & 0xFF) * 4
                if lit + 4 <= len(rom):
                    val = int.from_bytes(rom[lit:lit + 4], 'big')
                    if val >= 0x10000:
                        # first containing range wins; keep the earliest start
                        # (ranges are sorted, so the first match is the lowest
                        #  start; we still scan to the end in case the earliest
                        #  containing range has an unmappable name)
                        for (s, ee, tn) in ranges:
                            if s > val:
                                break
                            if s >= 0x10000 and s <= val <= ee:
                                cat = table_category(tn)
                                if cat:
                                    found = (cat, tn, val)
                                    break
                        if found:
                            break
            b += 2
        if found:
            out[a] = found
    return out

# ---------------------------------------------------------------------------
# 5. Tier C: label propagation on the call graph
# ---------------------------------------------------------------------------
def tier_c_propagate(order, store, seed, edges, iterations=8):
    """seed: dict key -> (category, confidence). Mutates-and-returns a dict of
    key -> (category, confidence) for keys still 'Other'."""
    # adjacency within universe, only 60E0FC00 (callgraph context bank)
    adj = defaultdict(set)
    key_by_addr = {k: k for k in order if store[k]["bank"] == "60E0FC00"}
    for ca, ce in edges:
        a = key_by_addr.get(ca)
        b = key_by_addr.get(ce)
        if a is None or b is None:
            continue
        adj[a].add(b)
        adj[b].add(a)

    cur = dict(seed)                 # key -> (cat, conf[, sig])
    def cpair(v):
        return (v[0], v[1])
    pending = [k for k in order if k not in cur]
    for _ in range(iterations):
        changed = False
        for k in pending[:]:
            if k in cur:
                continue
            votes = Counter()
            total_w = 0.0
            for nb in adj[k]:
                if nb in cur:
                    cat, cf = cpair(cur[nb])
                    if cat == OTHER:
                        continue
                    votes[cat] += cf
                    total_w += cf
            if total_w <= 0:
                continue
            best, wbest = votes.most_common(1)[0]
            agree = wbest / total_w
            if agree >= 0.6:
                cur[k] = (best, agree)
                changed = True
        if not changed:
            break
    return cur

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    t0 = time.time()
    print("== classify_functions.py ==\n")

    # ---- load universe -----------------------------------------------------
    store, order, missing = load_universe()
    if missing:
        print("WARNING missing symbol files:", missing)
    print("universe: %d symbols" % len(order))

    # ---- baseline (build_site pure-name SYM_RULES, no extensions) ----------
    base = Counter()
    for k in order:
        cat = base_regex_category(store[k]["name"], SYM_RULES)
        base[cat or OTHER] += 1
    print("\n-- BEFORE (pure name regex, build_site semantics) --")
    for c, n in base.most_common():
        print("  %5d  %s" % (n, c))
    print("  total", sum(base.values()))
    before_other = base[OTHER]

    # ---- edges -------------------------------------------------------------
    edges, emiss = load_edges()
    if emiss:
        print("WARNING missing:", emiss)
    print("\ncallgraph edges:", len(edges))

    # ---- table map ---------------------------------------------------------
    tabmap, tmiss = load_table_map()
    if tmiss:
        print("WARNING missing table files:", tmiss)
    ntab = sum(len(v) for v in tabmap.values())
    print("table ranges loaded (both banks):", ntab)

    # ---- annotated sources -------------------------------------------------
    srcs = {
        "60E0FC00": os.path.join(REPO, "src", "60E0FC00_annotated.s"),
        "60E1D400": os.path.join(REPO, "src", "60E1D400_annotated.s"),
    }
    parsed = {}
    for b, p in srcs.items():
        if os.path.exists(p):
            parsed[b] = parse_annotated(p)
            print("parsed %s: %d funcs, %d words" % (b, len(parsed[b][0]), len(parsed[b][1])))
        else:
            print("WARNING missing annotated source:", p)
            parsed[b] = ({}, {})

    # ---- ROM binaries (used for Tier B literal resolution) -----------------
    roms = {}
    for b in ("60E0FC00", "60E1D400"):
        p = os.path.join(REPO, "roms", "stock", "%s.bin" % b)
        if os.path.exists(p):
            roms[b] = open(p, "rb").read()
        else:
            print("WARNING missing ROM binary:", p)
            roms[b] = None

    # ---- Tier A + B ---------------------------------------------------------
    final = {}                       # key -> (cat, conf, sig)
    tier_counts = Counter()
    tier_b_notes = {}

    # ---- Tier 0: explicit name overrides (Issue 3) -----------------------
    for k in order:
        r = store[k]
        oc = override_category(r["name"])
        if oc:
            final[k] = oc
            tier_counts["override"] += 1

    # Tier A: name regex
    for k in order:
        if k in final:
            continue
        r = store[k]
        cat = name_category(r["name"])
        if cat:
            final[k] = (cat, 1.0, "name")
            tier_counts["name"] += 1

    # Tier B: literal-pool -> cal table signature for still-unclassified
    # (ROM-based resolution first; falls back to the annotated .s word map)
    for bank in ("60E0FC00", "60E1D400"):
        ranges = tabmap.get(bank, [])
        funcs, words = parsed[bank]
        if roms.get(bank) is not None:
            # function (start,end) pairs from the symbol universe
            pairs = [(r["addr"], r["end"]) for k in order
                     for r in [store[k]] if r["bank"] == bank]
            hits = tier_b_scan_rom(roms[bank], pairs, ranges)
        else:
            hits = tier_b_scan(funcs, words, ranges)
        for k in order:
            if k in final:
                continue
            r = store[k]
            if r["bank"] != bank:
                continue
            h = hits.get(r["addr"])
            if h:
                cat, tn, val = h
                final[k] = (cat, 0.85, "cal")
                tier_counts["cal"] += 1
                tier_b_notes[k] = (tn, val)

    print("\n-- TIER A (name) classified: %d --" % tier_counts["name"])
    print("-- TIER B (cal-signature) classified: %d --" % tier_counts["cal"])

    # Tier C: graph label propagation on the remaining
    prop = tier_c_propagate(order, store, final, edges)
    for k in order:
        if k in final:
            continue
        if k in prop and prop[k][0] != OTHER:
            final[k] = (prop[k][0], prop[k][1], "graph")
            tier_counts["graph"] += 1

    print("-- TIER C (graph propagation) classified: %d --" % tier_counts["graph"])

    # Tier D: remainder
    for k in order:
        if k not in final:
            final[k] = (OTHER, 0.0, "none")
            tier_counts["none"] += 1

    # ---- Issue 1: one category per distinct function name ----------------
    dup_names = dedupe_by_name(order, store, final)

    # ---- write CSV -----------------------------------------------------------
    out_path = os.path.join(SYM, "FUNCTION_CATEGORIES.csv")
    with open(out_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["bank", "addr", "name", "category", "confidence", "signal"])
        for k in sorted(order):
            r = store[k]
            cat, cf, sig = final[k]
            w.writerow([r["bank"], "0x%X" % r["addr"], r["name"],
                        cat, "%.3f" % cf, sig])
    print("\nwrote", out_path)

    # ---- AFTER breakdown ------------------------------------------------------
    after = Counter(final[k][0] for k in order)
    print("\n-- AFTER (hybrid) --")
    for c, n in after.most_common():
        print("  %5d  %s" % (n, c))
    print("  total", sum(after.values()))
    after_other = after[OTHER]
    moved = before_other - after_other
    print("\nMoved out of 'Other / Unclassified': %d  (before %d -> after %d)"
          % (moved, before_other, after_other))

    print("\n-- tier counts --")
    for t in ("name", "override", "cal", "graph", "none"):
        print("  %-8s %d" % (t, tier_counts[t]))
    print("  sum", sum(tier_counts[t] for t in ("name", "override", "cal", "graph", "none")))

    # ---- Issue 1 report -------------------------------------------------------
    print("\n-- Issue 1 (one category per distinct name) --")
    print("names whose rows disagreed before dedup (now unified): %d" % dup_names)

    # ---- sanity spot checks ----------------------------------------------------
    print("\n-- sanity spot checks (keywords must NOT be Other) --")
    probe = [("CAN", "CAN"), ("OBD", "OBD"), ("fuel", "Fuel"), ("knock", "Knock"),
             ("DTC", "DTC"), ("idle", "Idle"), ("throttle", "Throttle"),
             ("inject", "Injection"), ("spark", "Ignition"), ("baro", "Barometric")]
    shown = 0
    for kw, label in probe:
        for k in order:
            r = store[k]
            # skip names deliberately pinned to Other by an explicit override
            # (immo/DSC_/eShaft policy), which is not an anomaly
            oc = override_category(r["name"])
            if oc and oc[0] == OTHER:
                continue
            if kw.lower() in r["name"].lower() and final[k][0] == OTHER:
                print("  ANOMALY: '%s' (%s) still Other" % (r["name"], r["bank"]))
                shown += 1
                break
    if not shown:
        print("  (no keyword anomalies found)")

    # print a sample of what each tier classified
    print("\n-- sample of Tier B (cal) classifications --")
    bcnt = 0
    for k in order:
        if tier_b_notes.get(k) and bcnt < 8:
            r = store[k]
            tn, val = tier_b_notes[k]
            print("  0x%X %-30s -> %-18s (table '%s' @ 0x%X)"
                  % (r["addr"], r["name"], final[k][0], tn, val))
            bcnt += 1
    print("\n-- sample of Tier C (graph) classifications --")
    gcnt = 0
    for k in order:
        if final[k][2] == "graph" and gcnt < 8:
            r = store[k]
            print("  0x%X %-30s -> %s (conf %.2f)"
                  % (r["addr"], r["name"], final[k][0], final[k][1]))
            gcnt += 1

    print("\nruntime: %.2fs" % (time.time() - t0))


if __name__ == "__main__":
    main()
