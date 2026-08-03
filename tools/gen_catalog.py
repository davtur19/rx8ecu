#!/usr/bin/env python3
"""
gen_catalog.py -- catalogo master dei simboli (lift-merge).

Collega i nomi autoritativi dei "lift" (c/*.c + c/tests/test_*.py) ai CSV di
simboli (symbols/symbols_*.csv) e produce tre artefatti:

  symbols/CATALOG_MASTER.csv --- merge di TUTTI i symbols_*.csv in un unico
      catalogo. Colonne: bank, addr, end, src_name, source, flag, lift_name,
      verified. Ogni riga originale e' preservata; se quel (bank,addr) ha un
      lift name, la riga viene arricchita (src_name preserva il nome originale,
      lift_name porta il nome autorevole). verified = 'YES' se l'addr e' in
      c/verified_addrs.txt.

  symbols/CATALOG_STATUS.md --- tabella per bank: file, total, nominate
      (non-FUN_/non-sub_), anonime, lift-named (di cui VERIFIED), note.

  symbols/NAMES_STATUS.md --- accoda una sezione "## v2 -- catalogo master".

Idempotente ed autonomo:  python3 tools/gen_catalog.py
Non tocca i CSV originali, non tocca c/, non tocca tools/xmap.
"""
import csv
import glob
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SYMBOLS_DIR = os.path.join(ROOT, "symbols")
C_DIR = os.path.join(ROOT, "c")
TESTS_DIR = os.path.join(C_DIR, "tests")
VERIFIED_FILE = os.path.join(C_DIR, "verified_addrs.txt")

MASTER_CSV = os.path.join(SYMBOLS_DIR, "CATALOG_MASTER.csv")
STATUS_MD = os.path.join(SYMBOLS_DIR, "CATALOG_STATUS.md")
NAMES_STATUS_MD = os.path.join(SYMBOLS_DIR, "NAMES_STATUS.md")

MAX_ADDR = 0x70000   # addrs > 0x70000 (RAM 0xFFFFxxxx / padding) are not lift addrs

# --- generic / placeholder names -------------------------------------------
GENERIC_RE = re.compile(r"^(FUN_|sub_|loc_|nullsub_|unk_|byte_|def_|seg_)([0-9a-fA-F]|$)",
                        re.IGNORECASE)


def is_generic(name):
    name = (name or "").strip()
    if not name:
        return True
    return bool(GENERIC_RE.match(name))


def sanitize_addr(val):
    """Return canonical addr int, or None if out-of-band (not a function addr)."""
    if val is None:
        return None
    if val <= 0x0000 or val >= MAX_ADDR:
        return None
    return val


# trailing `_HEX` address suffix: `_11A34`, `_0x19190`
_TRAIL = re.compile(r"_(?:0x)?([0-9A-Fa-f]{4,6})$")


def strip_addr_suffix(stem):
    return _TRAIL.sub("", stem)


def pick_name(stem):
    """Regime primario: stem senza `test_` e senza suffisso `_HEX`."""
    if stem.startswith("test_"):
        stem = stem[len("test_"):]
    return strip_addr_suffix(stem)


def addr_from_stem_suffix(stem):
    """Read addr from trailing `_HEX` suffix, or None."""
    m = _TRAIL.search("_" + stem)   # re-anchor: suffix includes the leading underscore
    if m:
        return sanitize_addr(int(m.group(1), 16))
    return None


# --- parsing sources for tests / c files ------------------------------------
_ENTRY_ASSIGN = re.compile(r"\bENTRY\s*=\s*0x([0-9A-Fa-f]{1,7})\b")
_ENTRIES_DICT = re.compile(r"\bENTRIES\s*=\s*\{([^{}]*)\}")
_ADDR_ASSIGN = re.compile(r"\bADDR\s*=\s*0x([0-9A-Fa-f]{1,7})\b")
_CALL_LIT = re.compile(r"cpu\.call\(\s*0x([0-9A-Fa-f]{1,7})\b")
_DICT_ELEM = re.compile(r"0x([0-9A-Fa-f]{1,7})\s*[,}]")


def parse_test_file(path):
    """Lift index entries from a c/tests/test_*.py file -> [(addr, name)]."""
    stem = os.path.basename(path)[:-len(".py")]
    name = pick_name(stem)
    text = open(path, encoding="utf-8", errors="replace").read()

    # 1) multi-entry dict ENTRIES = { ... } (2+ addrs) -> all entries, task rule
    multi = []
    for dm in _ENTRIES_DICT.finditer(text):
        for am in _DICT_ELEM.finditer(dm.group(1)):
            v = sanitize_addr(int(am.group(1), 16))
            if v:
                multi.append(v)
    if len(multi) >= 2:
        return [(v, name) for v in dict.fromkeys(multi)]

    # 2) trailing _HEX suffix in filename (primary target)
    a = addr_from_stem_suffix(stem)
    if a is None:
        # 3) ENTRY = 0x...
        m = _ENTRY_ASSIGN.search(text)
        if m:
            a = sanitize_addr(int(m.group(1), 16))
    if a is None:
        # 4) ADDR = 0x... (ROM entry in fixtures; RAM 0xFFFF.. filtered)
        m = _ADDR_ASSIGN.search(text)
        if m:
            a = sanitize_addr(int(m.group(1), 16))
    if a is not None:
        return [(a, name)]

    # 5) literal cpu.call(0x...): use ONLY when a single distinct target exists
    out = []
    for mm in _CALL_LIT.finditer(text):
        v = sanitize_addr(int(mm.group(1), 16))
        if v and v not in [x for x, _ in out]:
            out.append((v, name))
    if len(out) == 1:
        return out
    return []


_HEADER_ADDR = re.compile(r"\bAddress\s*:\s*0x([0-9A-Fa-f]{4,6})\b")
_FUNCDEF = re.compile(r"^\s*[A-Za-z_][A-Za-z0-9_ \*]*\s+[A-Za-z_][A-Za-z0-9_]*\s*\([^;]*$")
_FUNNAME = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(")


def has_matching_function(path, name):
    """True if the C file defines a function whose name (case-insensitive) equals
    `name` or starts with `name_` — i.e. it is a single-target lift, not a
    multi-function "family" file pinned at an arbitrary cluster address."""
    low = name.lower()
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            s = line.strip()
            if not s or s.startswith("extern") or s.startswith("static"):
                continue
            if not _FUNCDEF.match(line):
                continue
            m = _FUNNAME.search(line)
            if not m:
                continue
            d = m.group(1).lower()
            if d == low or d.startswith(low + "_"):
                return True
    return False


def read_leading_comment(path):
    """Return the contiguous leading `/* ... */` comment block text."""
    lines = []
    in_block = False
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            s = line.strip()
            if not in_block and s.startswith("/*"):
                in_block = True
                lines.append(line)
                continue
            if in_block:
                lines.append(line)
                if "*/" in line:
                    break
            else:
                # //-comment lines at the very top
                if s.startswith("//"):
                    lines.append(line)
                elif not s and lines:
                    break
                elif s and not s.startswith("//"):
                    break
    return "".join(lines)


def parse_c_file(path):
    """Lift entry (addr, name) from a c/*.c file, or None."""
    stem = os.path.basename(path)[:-len(".c")]
    name = pick_name(stem)
    a = addr_from_stem_suffix(stem)
    if a is not None:
        return (a, name)

    comment = read_leading_comment(path)
    # a) Address: 0x... (ROM header, most reliable)
    m = _HEADER_ADDR.search(comment)
    if m:
        v = sanitize_addr(int(m.group(1), 16))
        if v:
            return (v, name)
    # b) generic fallback: first free-standing `0x[4-6]` in the leading comment —
    #    only trusted for single-target lift files (the function name matches).
    if not has_matching_function(path, name):
        return None
    for mm in re.finditer(r"(?<![0-9a-fA-Fx])0x([0-9A-Fa-f]{4,6})\b", comment):
        v = sanitize_addr(int(mm.group(1), 16))
        if v:
            return (v, name)
    return None


def build_lift_index():
    """addr(int) -> lift name. Regime primario: c/tests/test_*.py; i c/*.c
    riempiono i buchi (nome autorevole) solo dove il test non ha dato addr."""
    idx = {}
    for path in sorted(glob.glob(os.path.join(TESTS_DIR, "test_*.py"))):
        for a, n in parse_test_file(path):
            if a not in idx:
                idx[a] = n
    for path in sorted(glob.glob(os.path.join(C_DIR, "*.c"))):
        res = parse_c_file(path)
        if res:
            a, n = res
            if a not in idx:
                idx[a] = n
    return idx


def load_verified():
    vset = set()
    with open(VERIFIED_FILE, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith(";"):
                continue
            for m in re.finditer(r"0x([0-9a-fA-F]+)", line):
                vset.add(int(m.group(1), 16))
    return vset


# ----------------------------------------------------------------------------
BANK_RE = re.compile(r"symbols_(60E[0-9A-F]+)")
CSV_FILES = sorted(glob.glob(os.path.join(SYMBOLS_DIR, "symbols_*.csv")))


def bank_of(filename):
    m = BANK_RE.search(os.path.basename(filename))
    return m.group(1) if m else os.path.basename(filename)


def load_csv_rows():
    rows = []          # list of dicts, CSV-column + _bank/_file
    for path in CSV_FILES:
        bank = bank_of(path)
        with open(path, encoding="utf-8", errors="replace", newline="") as fh:
            for rec in csv.DictReader(fh):
                rec["_bank"] = bank
                rec["_file"] = os.path.basename(path)
                rows.append(rec)
    return rows


# ----------------------------------------------------------------------------
def build_records(rows, lift_index, verified):
    out, input_count, per_bank = [], {}, {}
    for rec in rows:
        bank = rec["_bank"]
        addr_str = (rec.get("addr") or "").strip()
        try:
            addr = int(addr_str, 16)
        except ValueError:
            addr = -1
        src = (rec.get("name") or "").strip()
        lift_name = lift_index.get(addr, "")
        out.append({
            "bank": bank,
            "addr": addr_str,
            "end": (rec.get("end") or "").strip(),
            "src_name": src,
            "source": (rec.get("source") or "").strip(),
            "flag": (rec.get("flag") or "").strip(),
            "lift_name": lift_name,
            "verified": "YES" if addr in verified else "",
        })
        input_count.setdefault((bank, rec["_file"]), 0)
        input_count[(bank, rec["_file"])] += 1
        per_bank.setdefault(bank, 0)
        per_bank[bank] += 1
    return out, per_bank, input_count


def bank_note(bank):
    if bank == "60E0FC00":
        return "canonico affidabile (equiname)"
    if bank == "60E1D400":
        return "canonico affidabile (IDA-ai)"
    return "derivata over-segmentata"


def write_master(out):
    with open(MASTER_CSV, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=[
            "bank", "addr", "end", "src_name", "source", "flag", "lift_name", "verified"])
        w.writeheader()
        for r in out:
            w.writerow(r)


def aggregate(records):
    """per-bank dict of counts (nominate/anonime effettive, lift-named, verified)."""
    agg = {}
    for r in records:
        bank = r["bank"]
        eff = r["lift_name"] if r["lift_name"] else r["src_name"]
        g = agg.setdefault(bank, {"total": 0, "named": 0, "anon": 0,
                                  "lift_named": 0, "verified_lift": 0})
        g["total"] += 1
        if is_generic(eff):
            g["anon"] += 1
        else:
            g["named"] += 1
        if r["lift_name"]:
            g["lift_named"] += 1
            if r["verified"] == "YES":
                g["verified_lift"] += 1
    return agg


def write_status(agg, input_count):
    def file_of(bank_file):
        return ", ".join(sorted(f for (b, f) in input_count if b == bank_file))
    lines = []
    lines.append("# CATALOG_STATUS -- stato catalogo master (post lift-merge)\n")
    lines.append("Merge di tutti i `symbols_*.csv` con i nomi lift (`c/*.c`, "
                 "`c/tests/test_*.py`). `CATALOG_MASTER.csv` preserva ogni riga "
                 "originale; `lift_name` porta il nome autorevole se disponibile, "
                 "altrimenti coincide con `src_name`.\n")
    lines.append("| bank | file | total | nominate | anonime | lift-named | di cui VERIFIED | note |")
    lines.append("|-----:|------|------:|---------:|--------:|-----------:|----------------:|------|")
    for bank in sorted(agg):
        g = agg[bank]
        files = ", ".join(sorted(f for (b, f) in input_count if b == bank))
        inline = files.replace(", ", "<br/>")
        lines.append(
            f"| {bank} | {inline} | {g['total']} | {g['named']} | {g['anon']} | "
            f"{g['lift_named']} | {g['verified_lift']} | {bank_note(bank)} |")
    lines.append("\n")
    with open(STATUS_MD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def append_names_status(agg, input_count, lift_index, orphans, out_rows):
    """Accoda (se non presente) la sezione '## v2' a symbols/NAMES_STATUS.md."""
    v2_marker = "## v2 — catalogo master"
    text = ""
    if os.path.exists(NAMES_STATUS_MD):
        with open(NAMES_STATUS_MD, encoding="utf-8") as fh:
            text = fh.read()
    if v2_marker in text:
        print("  NAMES_STATUS.md: sezione v2 gia' presente, skip append")
        return

    def eff(r):
        return r["lift_name"] if r["lift_name"] else r["src_name"]

    # named/anon counts BEFORE the lift merge (pure src_name), per bank
    before = {}
    for r in out_rows:
        b = r["bank"]
        g = before.setdefault(b, {"total": 0, "named": 0, "anon": 0})
        g["total"] += 1
        if is_generic(r["src_name"]):
            g["anon"] += 1
        else:
            g["named"] += 1

    lines = []
    lines.append("## v2 — catalogo master (post-lift-merge)\n")
    lines.append("Collega i nomi lift autorevoli (`c/*.c`, `c/tests/test_*.py`) ai CSV: "
                 "ogni riga di `symbols/CATALOG_MASTER.csv` porta `src_name` (originale) e "
                 "`lift_name` (autorevole se disponibile). `verified=YES` per addr in "
                 "`c/verified_addrs.txt`.\n")
    lines.append("| bank | file | total | nominate | anonime | lift-named | di cui VERIFIED | note | Δ nominate |")
    lines.append("|-----:|------|------:|---------:|--------:|-----------:|----------------:|------|----------:|")
    for bank in sorted(agg):
        g = agg[bank]
        files = ", ".join(sorted(f for (b, f) in input_count if b == bank))
        files = files.replace(", ", "<br/>")
        before_named = before.get(bank, {}).get("named", 0)
        delta = g["named"] - before_named
        lines.append(
            f"| {bank} | {files} | {g['total']} | {g['named']} | {g['anon']} | "
            f"{g['lift_named']} | {g['verified_lift']} | {bank_note(bank)} | +{delta} |")
    lines.append("")
    lines.append("Lift addrs senza corrispondenza in alcun CSV (`lift_orphans`): "
                 f"{len(orphans)} "
                 + (f"— es.: 0x{orphans[0]:05X} ({lift_index[orphans[0]]})"
                    + (f", 0x{orphans[1]:05X} ({lift_index[orphans[1]]})" if len(orphans) > 1 else ""))
                 + ".\n")

    with open(NAMES_STATUS_MD, "r", encoding="utf-8") as fh:
        text = fh.read()
    # append-only: preserve original content, separate the v2 section by one
    # blank line (idempotent: skip if already present).
    text = text.rstrip("\n") + "\n\n" + "\n".join(lines)
    with open(NAMES_STATUS_MD, "w", encoding="utf-8") as fh:
        fh.write(text)

def main():
    lift_index = build_lift_index()
    verified = load_verified()
    rows = load_csv_rows()
    out, per_bank, input_count = build_records(rows, lift_index, verified)
    write_master(out)

    agg = aggregate(out)
    write_status(agg, input_count)

    # orphans: lift addrs not present in any CSV row
    row_addrs = set()
    for r in rows:
        try:
            row_addrs.add(int(r["addr"], 16))
        except ValueError:
            pass
    orphans = sorted(a for a in lift_index if a not in row_addrs)

    append_names_status(agg, input_count, lift_index, orphans, out)

    # ---- reporting ---------------------------------------------------------
    print("== gen_catalog: catalogo master ==")
    print("  lift entries:", len(lift_index))
    print("  verified addrs:", len(verified))
    print("  CATALOG_MASTER.csv rows:", len(out))
    for bank in sorted(per_bank):
        g = agg.get(bank, {})
        print("   bank %-10s total=%d named=%d anon=%d lift_named=%d verified=%d note=%s"
              % (bank, per_bank[bank], g.get("named", 0), g.get("anon", 0),
                 g.get("lift_named", 0), g.get("verified_lift", 0), bank_note(bank)))

    print("  orphan lift addrs:", len(orphans))
    for a in orphans[:5]:
        print("     orphan 0x%05X (name=%s)" % (a, lift_index[a]))

    # 5 examples where lift replaced FUN_/ida-ai
    n = 0
    print("\n  5 esempi lift-corrected rows:")
    for r in out:
        if r["lift_name"] and r["lift_name"] != r["src_name"] and is_generic(r["src_name"]):
            print("    %s %s src='%s' source='%s'  ->  lift='%s' verified=%s"
                  % (r["bank"], r["addr"], r["src_name"], r["source"],
                     r["lift_name"], r["verified"]))
            n += 1
            if n >= 5:
                break

    # ---- no-data-loss check: re-read master and compare per-bank counts ----
    print("\n  verify (re-read CATALOG_MASTER.csv):")
    reread = {}
    with open(MASTER_CSV, encoding="utf-8", newline="") as fh:
        for rec in csv.DictReader(fh):
            reread.setdefault(rec["bank"], 0)
            reread[rec["bank"]] += 1
    ok = True
    for bank in sorted(per_bank):
        inp, out_c = per_bank[bank], reread.get(bank, 0)
        flag = "OK" if inp == out_c else "MISMATCH"
        if inp != out_c:
            ok = False
        print("    %-10s input=%d  master=%d  %s" % (bank, inp, out_c, flag))
    print("  no-data-loss: %s" % ("PASS" if ok else "FAIL"))

    print("\nDONE")


if __name__ == "__main__":
    main()