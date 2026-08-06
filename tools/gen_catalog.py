#!/usr/bin/env python3
"""
gen_catalog.py -- catalogo master dei simboli (lift-merge).

Collega i nomi autoritativi dei "lift" (c/*.c + c/tests/test_*.py) ai CSV di
simboli (symbols/symbols_*.csv) e produce tre artefatti:

  symbols/CATALOG_MASTER.csv --- merge di TUTTI i symbols_*.csv in un unico
      catalogo. Colonne: bank, addr, end, src_name, source, flag, lift_name,
      verified, also_sources (+ category in coda, join con
      FUNCTION_CATEGORIES.csv su (bank normalizzato, int(addr,16)) — cella
      vuota per le non classificate). Ogni riga originale e' preservata; se
      quel (bank,addr) ha un lift name, la riga viene arricchita (src_name
      preserva il nome originale, lift_name porta il nome autorevole).
      verified = 'YES' se l'addr e' in c/verified_addrs.txt. Gli "orphan"
      (lift addrs senza START di riga in alcun CSV) vengono ADOTTATI come
      entry LIFT_ONLY (boundary non in IDA):
      riga bank, 0x%05X, end vuoto, lift_name, source=lift, flag=LIFT_ONLY,
      verified da c/verified_addrs.txt. Attribuzione bank via range CSV
      (fallback 60E1D400 se fuori range di ogni bank).

  symbols/CATALOG_STATUS.md --- tabella per bank: file, total, nominate
      (non-FUN_/non-sub_), anonime, lift-named (di cui VERIFIED), note +
      nota LIFT_ONLY addrs (boundary non in IDA).

  symbols/NAMES_STATUS.md --- accoda una sezione "## v2 -- catalogo master"
      e una "## v2b -- LIFT_ONLY orphans adopted".

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

EQUINOX_FILE = os.path.join(SYMBOLS_DIR, "equinox311_60E0FC00_named.csv")
EQUINOX_BANK = "60E0FC00"

# bank binario usato dall'end-refinement (primo-return oltre end). Le banche
# twin condividono lo stesso spazio di offset; l'FC00 e' quella con le righe
# che il catalogo vuole correggere.
REFINE_BANK = EQUINOX_BANK
REFINE_ROM = os.path.join(ROOT, "roms", "stock", "60E0FC00.bin")
REFINE_CAP = 64          # massimo avanzamento dell'end in byte

# --- dedup precision sources (per (bank, addr)) ------------------------------
# Priorita' crescente: le righe piu' autorevoli vincono il dedup per (bank,addr).
# LIFT_ONLY e' sempre in cima (boundary autoritativi). Ordine (alto->basso):
#   LIFT_ONLY > c-lift > equinox311-clean(USER_DEFINED) > ghidra-hand-xmap/ghidra-hand
#   > equinox311-clean(DEFAULT/heuristic) > equinox311-uncertain > ida-ai-xmap
#   > ghidra-auto > ida-ai > derived.
# ida-ai-xmap sta SOPRA ghidra-auto: ghidra-auto produce solo nomi generici
# (FUN_xxx) e non porta valore; i nomi ida-ai-xmap (campagna 099bf8b, "+372
# nomi") sono DUBIOUS ma significativi e vanno ripristinati come winner.
# Il tier del FILE (merged2/merged vs base) e' un BONUS piccolo (tie-break per
# la stessa source): non deve ribaltare l'ordine per-source sopra.
_SRC_TIER = {
    "lift": 10,         # LIFT_ONLY / orphans (flag LIFT_ONLY -> 1000 in source_priority)
    "c-lift": 9,
    "ghidra-hand": 7,
    "ghidra-hand-xmap": 7,
    "ida-ai-xmap": 4,   # DUBIOUS ma significativi; SOPRA ghidra-auto (solo FUN_xxx)
    "ghidra-auto": 3,
    "ida-ai": 2,
    "derived": 1,
}
_EQX_TIER = {           # equinox311: tier dal kind (vedi load_equinox_rows)
    "clean-userdef": 8,     # eqx_clean (senza '?') e source USER_DEFINED
    "clean-heur": 6,        # eqx_clean con source DEFAULT/heuristic
    "uncertain": 5,         # eqx_uncertain (con '?')
}
_FILE_BONUS = {         # file basename -> bonus (piccolo, solo tie-break)
    "merged2": 2,       # 60E0FC00_merged2.csv: ghidra-auto+hand + ida-ai-xmap
    "merged": 1,        # 60E1D400_merged.csv: fuso
}


def source_priority(rec):
    """Priorita' di una riga per il dedup (ritorna un int, piu' alto vince)."""
    if rec["flag"] == "LIFT_ONLY":
        return 1000
    kind = rec.get("_eqx_kind")
    if kind:
        tier = _EQX_TIER[kind]
    else:
        tier = _SRC_TIER.get(rec["source"], 0)
    fname = rec["_file"] or ""
    bonus = 0
    for key, b in _FILE_BONUS.items():
        if key in fname:
            bonus = b
            break
    return tier * 100 + bonus  # single-row banks / base csv


MAX_ADDR = 0x70000   # addrs > 0x70000 (RAM 0xFFFFxxxx / padding) are not lift addrs

# --- generic / placeholder names -------------------------------------------
GENERIC_RE = re.compile(r"^(FUN_|sub_|loc_|nullsub_|unk_|byte_|def_|seg_)([0-9a-fA-F]|$)",
                        re.IGNORECASE)


def is_generic(name):
    name = (name or "").strip()
    if not name:
        return True
    return bool(GENERIC_RE.match(name))


# --- nomi DEBOLI (per la regola speciale equinox311 vs ghidra-hand) ----------
_WEAK_RE = re.compile(r"^(task\d+|func\d+|LongFunc|calledLots|reset_ZERO|sub_\w+)$")


def is_weak_name(name):
    """Nome debole (placeholder / incerto): match regex o contiene '?'."""
    name = (name or "").strip()
    if not name:
        return True
    if "?" in name:
        return True
    return bool(_WEAK_RE.match(name))


def _eff_name(rec):
    return (rec.get("lift_name") or rec.get("src_name") or "").strip()


def _is_eqx_clean(rec):
    return rec.get("_eqx_kind") in ("clean-userdef", "clean-heur")


def _is_ghidra_hand(rec):
    return rec.get("source") in ("ghidra-hand", "ghidra-hand-xmap")


def _beats(pa, ra, pb, rb):
    """True se ra vince su rb per (bank,addr) — priorita' + regola speciale.

    REGOLA SPECIALE: equinox311-clean batte ghidra-hand(-xmap) il cui nome e'
    DEBOLE (regex o '?'); in tal caso l'equinox vince anche a parita'/svantaggio
    di priorita'. Altrimenti vince la priorita' piu' alta (o resta il primo)."""
    if _is_eqx_clean(ra) and _is_ghidra_hand(rb) and is_weak_name(_eff_name(rb)):
        return True
    if _is_eqx_clean(rb) and _is_ghidra_hand(ra) and is_weak_name(_eff_name(ra)):
        return False
    return pa > pb


def _lost_tag(rec):
    """Tag da mettere in also_sources quando questa riga perde il dedup."""
    if rec.get("_eqx_kind"):
        return "equinox311:%s" % (rec.get("src_name") or "")
    return rec.get("source") or ""


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
    rows.extend(load_equinox_rows())
    return rows


def load_equinox_rows():
    """Carica symbols/equinox311_60E0FC00_named.csv come sorgente della bank
    60E0FC00 (colonne addr,name,source,flag; source = USER_DEFINED o DEFAULT).

    FILTRO: addr > 0x0 e < 0x70000 (esclude 0xffffff e lo zero). eqx_clean =
    nome senza '?'/'??'; eqx_uncertain = con '?'. Le righe diventano
    source='equinox311' con flag:
      - clean USER_DEFINED          -> GHIDRA-EQX
      - clean DEFAULT/heuristic     -> GHIDRA-EQX-HEUR
      - uncertain (con '?')         -> GHIDRA-EQX-UNCERTAIN
    Il kind e' salvato in `_eqx_kind` per la priorita' di voto.
    """
    rows = []
    if not os.path.exists(EQUINOX_FILE):
        return rows
    with open(EQUINOX_FILE, encoding="utf-8", errors="replace", newline="") as fh:
        for rec in csv.DictReader(fh):
            try:
                addr = int((rec.get("addr") or "").strip(), 16)
            except ValueError:
                continue
            if addr <= 0 or addr >= MAX_ADDR:
                continue
            name = (rec.get("name") or "").strip()
            src = (rec.get("source") or "").strip()
            if "?" in name:
                kind, flag = "uncertain", "GHIDRA-EQX-UNCERTAIN"
            elif src == "USER_DEFINED":
                kind, flag = "clean-userdef", "GHIDRA-EQX"
            else:
                kind, flag = "clean-heur", "GHIDRA-EQX-HEUR"
            rows.append({
                "addr": "0x%06x" % addr,
                "name": name,
                "source": "equinox311",
                "flag": flag,
                "_bank": EQUINOX_BANK,
                "_file": os.path.basename(EQUINOX_FILE),
                "_eqx_kind": kind,
            })
    return rows


def bank_ranges(rows):
    """bank -> (min_addr, max_addr) coperti dalle sue righe CSV (spazio offset)."""
    ranges = {}
    for rec in rows:
        try:
            a = int(rec["addr"], 16)
        except ValueError:
            continue
        lo, hi = ranges.get(rec["_bank"], (a, a))
        ranges[rec["_bank"]] = (min(lo, a), max(hi, a))
    return ranges


def attrib_bank(addr, ranges):
    """Attribuisce un addr alla bank il cui range CSV lo contiene.

    Tutti i CSV coprono (in offset) lo stesso spazio, quindi in caso di
    sovrapposizione si preferiscono le bank canoniche (60E1D400 IDA-ai, poi
    60E0FC00 equiname). Ritorna (bank, note) — note non vuota solo quando
    l'addr era fuori range di ogni bank (fallback 60E1D400).
    """
    hits = sorted(b for b, (lo, hi) in ranges.items() if lo <= addr <= hi)
    if not hits:
        return "60E1D400", "fallback (addr fuori range di ogni bank)"
    for pref in ("60E1D400", "60E0FC00"):
        if pref in hits:
            return pref, ""
    return hits[0], ""


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
        # addr CANONICO lowercase: i CSV base usano 0x%06X (uppercase), il file
        # equinox 0x%06x (lowercase) — normalizzo per far collidere il dedup.
        addr_canon = ("0x%06x" % addr) if addr >= 0 else addr_str
        src = (rec.get("name") or "").strip()
        lift_name = lift_index.get(addr, "")
        out.append({
            "bank": bank,
            "addr": addr_canon,
            "end": (rec.get("end") or "").strip(),
            "src_name": src,
            "source": (rec.get("source") or "").strip(),
            "flag": (rec.get("flag") or "").strip(),
            "lift_name": lift_name,
            "verified": "YES" if addr in verified else "",
            "_file": rec.get("_file") or "",
            "_eqx_kind": rec.get("_eqx_kind") or "",
        })
        input_count.setdefault((bank, rec["_file"]), 0)
        input_count[(bank, rec["_file"])] += 1
    # per_bank counts (cumulative raw rows, incl. variants)
    for (b, _), n in input_count.items():
        per_bank[b] = per_bank.get(b, 0) + n
    return out, per_bank, input_count


def dedup_records(records):
    """Dedup per (bank, addr): tieni UNA riga (regola di voto: priorita' piu'
    alta, con la REGOLA SPECIALE equinox311-clean vs ghidra-hand-debole).

    Il vincitore conserva `src_name`/`source`/`flag`/... della propria riga; la
    colonna `also_sources` elenca le sorgenti Perse (per le righe equinox311:
    'equinox311:<nome>') separate da '|'. Ritorna (deduped, examples,
    eqx_adopted) — examples: 3+ coppie (bank, addr, winner_source,
    lost_sources) per il report; eqx_adopted: [(bank, addr, old_name,
    new_name)] per i nomi equinox che HANNO VINTO il dedup (regola speciale o
    priorita')."""
    best = {}    # key -> [prio, rec]
    lost = {}    # key -> set(tag)
    order = []
    eqx_adopted = []
    for rec in records:
        key = (rec["bank"], rec["addr"])
        prio = source_priority(rec)
        if key not in best:
            best[key] = [prio, rec]
            lost[key] = set()
            order.append(key)
        else:
            cur_prio, cur_rec = best[key]
            if _beats(prio, rec, cur_prio, cur_rec):
                lost[key].add(_lost_tag(cur_rec))
                best[key] = [prio, rec]
                if rec.get("_eqx_kind"):
                    eqx_adopted.append((rec["bank"], rec["addr"],
                                        _eff_name(cur_rec), _eff_name(rec)))
            else:
                lost[key].add(_lost_tag(rec))

    out = []
    for key in order:
        _, rec = best[key]
        r = dict(rec, also_sources="|".join(sorted(s for s in lost[key] if s)))
        out.append(r)
    out.sort(key=lambda r: (r["bank"], r["addr"]))

    examples = []
    for key in order:
        _, rec = best[key]
        s = sorted(x for x in lost[key] if x)
        if s:
            examples.append((key[0], key[1], rec["source"], "|".join(s)))
    return out, examples, eqx_adopted


# --- twin-bank end backfill ------------------------------------------------
# Coppie di banche GEMELLE (stesso spazio offset, EDM4 -> stesso offset).
# La banca con righe prive di `end` (es. 60E0FC00: le righe equinox311 non
# hanno end) prende l'`end` della riga alla STESSA offset nella banca gemella
# (es. 60E0FB00: derived, end presente). SOLO la banca senza-end viene
# modificata; la gemella non viene mai toccata.
TWIN_BANKS = {
    "60E0FC00": "60E0FB00",
}


def twin_end_backfill(records):
    """Riempi l'`end` mancante delle righe di una banca senza-end usando l'`end`
    della riga gemella (stessa offset) nella banca con end.

    Ritorna il numero di righe corrette (solo nel banco senza-end)."""
    by_bank = {}
    for r in records:
        try:
            a = int(r["addr"], 16)
        except ValueError:
            continue
        by_bank.setdefault(r["bank"], {})[a] = r
    filled = 0
    for bank, twin in TWIN_BANKS.items():
        twin_map = by_bank.get(twin)
        if not twin_map:
            continue
        for r in records:
            if r["bank"] != bank or r["end"]:
                continue
            try:
                a = int(r["addr"], 16)
            except ValueError:
                continue
            t = twin_map.get(a)
            if t and t["end"]:
                r["end"] = t["end"]
                filled += 1
    return filled


def _is_ret_word(op):
    """True se e' un return SH-2: rts (0x000B) oppure jmp@Rn (0x4n2B)."""
    return op == 0x000B or (op & 0xF0FF) == 0x402B


def refine_fc00_ends(records):
    """End-refinement SAFE per il banco FC00.

    Il catalogo contiene span troncati a meta' epilogo: l'end attuale cade prima
    del return reale (es. 0x25C40/0x292BA, il cui epilogo esteso contiene
    0x64F6/0x6EF6 prima del `jmp @Rn` finale). Il detector, per ogni riga FC00
    con end valido:

      * prende il PRIMO return (rts / jmp@Rn) all'end o oltre, con cap
        REFINE_CAP byte: new_end = pc_ret + 4 (include il delay slot del
        return, che fa sempre parte della funzione — in sh2emu il delay esegue);
      * se l'ultima parola in-span (end-2) e' gia' un return, il delay slot e'
        fuori span: new_end = end + 2;
      * prologue-guard: NESSUNA riga-catalogo FC00 deve avere start strettamente
        dentro (addr, new_end) — protegge dall'inglobare la funzione successiva
        (e lascia intatte le span gia' corrette: li' il primo return oltre end
        appartiene alla funzione successiva e il guard rifiuta).

    NON tocca le altre banche. Ritorna il numero di righe corrette."""
    try:
        rom = open(REFINE_ROM, "rb").read()
    except OSError as exc:
        print("  refine_fc00_ends: SKIP (%s)" % exc)
        return 0
    cap_end = REFINE_CAP - 4          # l'ultimo pc candidato (new_end - 4)
    starts = set()
    for r in records:
        if r.get("bank") != REFINE_BANK:
            continue
        try:
            starts.add(int(r["addr"], 16))
        except (ValueError, TypeError):
            pass
    refined = 0
    for r in records:
        if r.get("bank") != REFINE_BANK:
            continue
        try:
            a = int(r["addr"], 16)
            e = int(r["end"], 16)
        except (ValueError, TypeError):
            continue
        if e <= a or e + 1 >= len(rom):
            continue
        # boundary gia' valido: l'ultima parola in-span (end-2) e' il delay
        # slot di un return in end-4 (rts/jmp@Rn + delay). Lo span termina
        # esattamente su un return: non raffinare oltre. Senza questo guard il
        # re-run scavalcherebbe data/tabelle o l'inizio della funzione
        # successiva non catalogata (es. 0x45E26, 0x4607A) inghiottendo il
        # primo return TROVATO dopo la tabella invece di quello della funzione.
        if e - 4 >= 0 and _is_ret_word((rom[e - 4] << 8) | rom[e - 3]):
            continue
        end_new = None
        # return come ultima parola in-span: il delay slot e' oltre end
        if e - 2 >= 0 and _is_ret_word((rom[e - 2] << 8) | rom[e - 1]):
            end_new = e + 2
        else:
            last = min(e + cap_end, len(rom) - 4)
            for pc in range(e, last + 2, 2):
                if pc + 1 >= len(rom):
                    break
                if _is_ret_word((rom[pc] << 8) | rom[pc + 1]):
                    end_new = pc + 4
                    break
        if end_new is None or end_new == e or end_new - e > REFINE_CAP:
            continue
        if end_new > len(rom):
            continue
        if any(a < s < end_new for s in starts):
            continue
        r["end"] = "0x%05X" % end_new
        refined += 1
    return refined


def is_noise_span(rec):
    """True se (end - addr) e' un valore intero valido e <= 4 (rumore di
    segmentazione: puntatori pooled / boundary falsi nelle banche derivate)."""
    if not rec.get("end"):
        return False
    try:
        a = int(rec["addr"], 16)
        e = int(rec["end"], 16)
    except ValueError:
        return False
    return 0 <= (e - a) <= 4


def apply_noise_flags(records):
    """Dopo il dedup: per le righe with source=='derived' (e non LIFT_ONLY, non
    nominate) con span (end-addr)<=4 imposta flag 'NOISE' (senza cancellare la
    riga; se la flag esiste gia' vi si AGGIUNGE 'NOISE' con separatore '|').

    Ritorna (records_modificati, noise_counts per bank, noise_examples,
    kept_spread) dove noise_examples = [(bank,addr,end,name), ...] (le righe
    NOISE) e kept_spanned = righe derived span>4 CORRETTAMENTE tenute.
    """
    noise_counts = {}
    noise_examples = []
    kept_spanned = []
    for rec in records:
        if rec["source"] != "derived" or rec["flag"] == "LIFT_ONLY":
            continue
        # escludi le righe NOMINATE (nome autorevole significativo)
        eff = rec["lift_name"] if rec["lift_name"] else rec["src_name"]
        if not is_generic(eff):
            continue
        if is_noise_span(rec):
            rec["flag"] = (rec["flag"] + "|" if rec["flag"] else "") + "NOISE"
            noise_counts[rec["bank"]] = noise_counts.get(rec["bank"], 0) + 1
            noise_examples.append((rec["addr"], rec["end"],
                                   rec["src_name"] or rec["lift_name"]))
        else:
            kept_spanned.append(rec)
    return records, noise_counts, noise_examples, kept_spanned


def bank_note(bank):
    if bank == "60E0FC00":
        return "canonico affidabile (equiname)"
    if bank == "60E1D400":
        return "canonico affidabile (IDA-ai)"
    return "derivata over-segmentata"


def load_category_map():
    """Read symbols/FUNCTION_CATEGORIES.csv into {(bank_norm, addr_int): category}.

    Normalizza bank con .upper() (formato del master) e addr con int(addr, 16),
    cosi' da ignorare differenze di maiuscole/padding. Righe con campi mancanti
    sono saltate. Ritorna il dict (join gia' verificato pulito, missing=0).
    """
    cat_file = os.path.join(SYMBOLS_DIR, "FUNCTION_CATEGORIES.csv")
    cat = {}
    if not os.path.exists(cat_file):
        print(f"WARNING: {cat_file} mancante; output senza colonna category",
              file=sys.stderr)
        return cat
    with open(cat_file, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            bank = (row.get("bank") or "").strip().upper()
            addr = row.get("addr") or ""
            category = row.get("category")
            # guardia: salta righe prive dei campi indispensabili
            if not bank or not addr or category is None:
                continue
            try:
                key = (bank, int(addr, 16))
            except ValueError:
                continue
            cat[key] = category
    return cat


def write_master(out, categories=None):
    if categories is None:
        categories = load_category_map()
    matched = 0
    with open(MASTER_CSV, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=[
            "bank", "addr", "end", "src_name", "source", "flag", "lift_name",
            "verified", "also_sources", "category"])
        w.writeheader()
        for r in out:
            row = {k: r.get(k, "") for k in w.fieldnames}
            bank = (r.get("bank") or "").strip().upper()
            addr = r.get("addr") or ""
            category = ""
            try:
                category = categories.get((bank, int(addr, 16)), "")
            except ValueError:
                category = ""
            if category:
                matched += 1
            row["category"] = category
            w.writerow(row)
    print(f"CATALOG_MASTER category join: {matched} righe matchate")


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


def write_status(agg, input_count, raw_per_bank, orphan_records=None,
                 noise_counts=None):
    noise_counts = noise_counts or {}
    def file_of(bank_file):
        return ", ".join(sorted(f for (b, f) in input_count if b == bank_file))
    lines = []
    lines.append("# CATALOG_STATUS -- stato catalogo master (post lift-merge, DEDUP)\n")
    lines.append("Merge di TUTTI i `symbols_*.csv` (varianti incluse) con i nomi lift "
                 "(`c/*.c`, `c/tests/test_*.py`). `CATALOG_MASTER.csv` e' DEDUP per "
                 "`(bank, addr)`: per chiave si tiene UNA sola riga (source piu' "
                 "autorevole); le altre sorgenti perse sono elencate in `also_sources`. "
                 "`lift_name` porta il nome autorevole se disponibile, altrimenti coincide "
                 "con `src_name`. Colonna `category` in coda: join con "
                 "`FUNCTION_CATEGORIES.csv` su `(bank normalizzato, int(addr,16))` — "
                 "~6.082 righe matchate, cella vuota per le non classificate.\n")
    lines.append("| bank | file | rows (incl. variants) | total (unique) | nominate | anonime | lift-named | di cui VERIFIED | note |")
    lines.append("|-----:|------|----------------------:|---------------:|---------:|--------:|-----------:|----------------:|------|")
    for bank in sorted(agg):
        g = agg[bank]
        files = ", ".join(sorted(f for (b, f) in input_count if b == bank))
        inline = files.replace(", ", "<br/>")
        raw = raw_per_bank.get(bank, 0)
        lines.append(
            f"| {bank} | {inline} | {raw} | {g['total']} | {g['named']} | {g['anon']} | "
            f"{g['lift_named']} | {g['verified_lift']} | {bank_note(bank)} |")
    lines.append("")
    lines.append("* `rows (incl. variants)` = righe CUMULATIVE da TUTTI i CSV della bank "
                 "(varianti ridondanti incluse); `total (unique)` = righe uniche per "
                 "(bank, addr) dopo il dedup — questa e' la cifra reale per bank.")
    orphan_records = orphan_records or []
    if orphan_records:
        n = len(orphan_records)
        nv = sum(1 for r in orphan_records if r["verified"] == "YES")
        lines.append("")
        lines.append(f"**LIFT_ONLY addrs (boundary non in IDA): {n}** — lift addrs senza "
                     f"START di riga in alcun CSV, adottati come entry del catalogo "
                     f"(`source=lift`, `flag=LIFT_ONLY`; di cui {nv} VERIFIED). "
                     f"Attribuzione bank via range CSV, fallback 60E1D400.")

    if noise_counts:
        lines.append("")
        lines.append("## NOISE (span<=4, derived only)\n")
        lines.append("Righe `source=derived` (banche derivate over-segmentate), non "
                     "LIFT_ONLY, non nominate, con span `(end - addr) <= 4` byte — "
                     "quasi certamente rumore di segmentazione (puntatori pooled / "
                     "boundary falsi). La riga NON e' cancellata: `flag` riceve "
                     "`NOISE` (aggiunto con `|` se gia' presente).\n")
        lines.append("| bank | unique | noise | real-estimate (unique - noise) |")
        lines.append("|-----:|-------:|------:|-------------------------------:|")
        for bank in sorted(noise_counts):
            u = agg.get(bank, {}).get("total", 0)
            n = noise_counts.get(bank, 0)
            lines.append(f"| {bank} | {u} | {n} | {u - n} |")
        tot_u = sum(g.get("total", 0) for g in agg.values())
        tot_n = sum(noise_counts.values())
        lines.append(f"| **TOT** | **{tot_u}** | **{tot_n}** | **{tot_u - tot_n}** |")
        lines.append("")
    lines.append("\n")
    with open(STATUS_MD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def append_names_status(agg, input_count, lift_index, orphans, out_rows, raw_per_bank):
    """Aggiorna (sostituisce) la sezione '## v2' a symbols/NAMES_STATUS.md."""
    v2_marker = "## v2 — catalogo master"
    text = ""
    if os.path.exists(NAMES_STATUS_MD):
        with open(NAMES_STATUS_MD, encoding="utf-8") as fh:
            text = fh.read()

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
    lines.append("## v2 — catalogo master (post-lift-merge, DEDUP)\n")
    lines.append("Collega i nomi lift autorevoli (`c/*.c`, `c/tests/test_*.py`) ai CSV: "
                 "ogni riga di `symbols/CATALOG_MASTER.csv` porta `src_name` (originale) e "
                 "`lift_name` (autorevole se disponibile). Il catalogo e' DEDUP per "
                 "`(bank, addr)` — `total (unique)` e' il numero reale di funzioni per "
                 "bank, `rows (incl. variants)` e' il conteggio cumulativo dei CSV "
                 "varianti (ridondanti). `verified=YES` per addr in "
                 "`c/verified_addrs.txt`.\n")
    lines.append("| bank | file | rows (incl. variants) | total (unique) | nominate | anonime | lift-named | di cui VERIFIED | note | Δ nominate |")
    lines.append("|-----:|------|----------------------:|---------------:|---------:|--------:|-----------:|----------------:|------|----------:|")
    for bank in sorted(agg):
        g = agg[bank]
        files = ", ".join(sorted(f for (b, f) in input_count if b == bank))
        files = files.replace(", ", "<br/>")
        before_named = before.get(bank, {}).get("named", 0)
        delta = g["named"] - before_named
        raw = raw_per_bank.get(bank, 0)
        lines.append(
            f"| {bank} | {files} | {raw} | {g['total']} | {g['named']} | {g['anon']} | "
            f"{g['lift_named']} | {g['verified_lift']} | {bank_note(bank)} | +{delta} |")
    lines.append("")
    lines.append("Dedup: `rows (incl. variants)` (cumulativo varianti) vs "
                 "`total (unique)` (post-dedup) — la differenza e' il numero di righe "
                 "ridondanti eliminate. `also_sources` nel CSV elenca i source persi.\n")
    lines.append("Lift addrs senza corrispondenza in alcun CSV (`lift_orphans`): "
                 f"{len(orphans)} "
                 + (f"— es.: 0x{orphans[0]:05X} ({lift_index[orphans[0]]})"
                    + (f", 0x{orphans[1]:05X} ({lift_index[orphans[1]]})" if len(orphans) > 1 else ""))
                 + ".\n")

    with open(NAMES_STATUS_MD, "r", encoding="utf-8") as fh:
        text = fh.read()
    # replace-in-place: strip any old v2/v2b section from the file, then append
    # the fresh v2 section (v2b is appended separately by append_names_status_v2b).
    marker = "## v2 — catalogo master"
    v2b_marker = "## v2b — LIFT_ONLY orphans adopted"
    for m in (marker, v2b_marker):
        i = text.find(m)
        if i != -1:
            text = text[:i].rstrip("\n")
    text = text.rstrip("\n") + "\n\n" + "\n".join(lines)
    with open(NAMES_STATUS_MD, "w", encoding="utf-8") as fh:
        fh.write(text)


def append_names_status_v2b(orphan_records):
    """Accoda/aggiorna la sezione '## v2b' a symbols/NAMES_STATUS.md."""
    marker = "## v2b — LIFT_ONLY orphans adopted"
    if not orphan_records:
        return
    text = ""
    if os.path.exists(NAMES_STATUS_MD):
        with open(NAMES_STATUS_MD, encoding="utf-8") as fh:
            text = fh.read()
    # remove any existing v2b section
    i = text.find(marker)
    if i != -1:
        text = text[:i].rstrip("\n")

    lines = []
    lines.append("## v2b — LIFT_ONLY orphans adopted\n")
    lines.append("Gli `orphan` (lift addrs senza START di riga in alcun CSV) sono ora "
                 "ENTRY del catalogo master con `flag=LIFT_ONLY` (boundary non in IDA). "
                 "Attribuzione bank via range CSV (fallback 60E1D400 se fuori range); "
                 "`verified=YES` per addr in `c/verified_addrs.txt`.\n")
    lines.append("| bank | addr | lift_name | source | flag | verified |")
    lines.append("|-----:|-----:|-----------|--------|------|----------|")
    for r in orphan_records:
        lines.append("| %s | %s | %s | %s | %s | %s |"
                     % (r["bank"], r["addr"], r["lift_name"], r["source"],
                        r["flag"], r["verified"]))
    lines.append("")
    text = text.rstrip("\n") + "\n\n" + "\n".join(lines)
    with open(NAMES_STATUS_MD, "w", encoding="utf-8") as fh:
        fh.write(text)

def main():
    lift_index = build_lift_index()
    verified = load_verified()
    rows = load_csv_rows()
    out, raw_per_bank, input_count = build_records(rows, lift_index, verified)

    # orphans: lift addrs not present in any CSV row
    row_addrs = set()
    for r in rows:
        try:
            row_addrs.add(int(r["addr"], 16))
        except ValueError:
            pass
    orphans = sorted(a for a in lift_index if a not in row_addrs)

    # adopt orphans as LIFT_ONLY catalog entries (v2b)
    ranges = bank_ranges(rows)
    orphan_records, bank_notes = [], []
    for a in orphans:
        bank, note = attrib_bank(a, ranges)
        if note:
            bank_notes.append((a, note))
        name = lift_index[a]
        rec = {
            "bank": bank,
            "addr": "0x%05X" % a,
            "end": "",
            "src_name": name,
            "source": "lift",
            "flag": "LIFT_ONLY",
            "lift_name": name,
            "verified": "YES" if a in verified else "",
            "_file": "lift",
        }
        orphan_records.append(rec)
        out.append(rec)
        raw_per_bank[bank] = raw_per_bank.get(bank, 0) + 1

    # ---- DEDUP per (bank, addr) -------------------------------------------
    deduped, examples, eqx_adopted = dedup_records(out)
    out = deduped

    # ---- NOISE flag: derived, span<=4 (after dedup) -----------------------
    out, noise_counts, noise_examples, kept_spanned = apply_noise_flags(out)

    # ---- twin-bank end backfill (FC00 <- FB00, same offset) ---------------
    n_backfilled = twin_end_backfill(out)

    # ---- safe end-refinement (FC00: first-return beyond end, cap 64) ------
    n_refined = refine_fc00_ends(out)

    write_master(out, load_category_map())

    agg = aggregate(out)
    write_status(agg, input_count, raw_per_bank, orphan_records,
                 noise_counts)

    append_names_status(agg, input_count, lift_index, orphans, out, raw_per_bank)
    append_names_status_v2b(orphan_records)

    # ---- reporting ---------------------------------------------------------
    print("== gen_catalog: catalogo master ==")
    print("  lift entries:", len(lift_index))
    print("  verified addrs:", len(verified))
    print("  CATALOG_MASTER.csv rows (UNIQUE post-dedup):", len(out))
    print("  twin-bank end backfill: filled=%d (bank without end <= twin end)"
          % n_backfilled)
    print("  safe end-refinement (FC00, first-return+boundary, cap<=%d): "
          "refined=%d" % (REFINE_CAP, n_refined))
    print("   rows cumulative (incl. variants):", sum(raw_per_bank.values()))
    for bank in sorted(raw_per_bank):
        g = agg.get(bank, {})
        print("   bank %-10s unique=%d named=%d anon=%d lift_named=%d verified=%d "
              "rows-variants=%d note=%s"
              % (bank, g.get("total", 0), g.get("named", 0), g.get("anon", 0),
                 g.get("lift_named", 0), g.get("verified_lift", 0),
                 raw_per_bank.get(bank, 0), bank_note(bank)))

    # ---- NOISE report (derived, span<=4) ----------------------------------
    print("\n  NOISE (span<=4, derived only): count per bank + real estimate")
    print("   bank        unique   noise   real-estimate (unique - noise)")
    for bank in sorted(raw_per_bank):
        u = agg.get(bank, {}).get("total", 0)
        n = noise_counts.get(bank, 0)
        print("   %-10s %7d %7d %7d" % (bank, u, n, u - n))
    print("   TOT        %7d %7d" % (sum(g.get("total", 0) for g in agg.values()),
                                     sum(noise_counts.values())))

    print("\n  3 esempi righe NOISE (addr, end, name):")
    for addr, end, name in noise_examples[:3]:
        print("     %s %s %s" % (addr, end, name))

    print("  3 esempi funzioni derived CORRETTAMENTE tenute (span>4):")
    shown = 0
    for rec in kept_spanned:
        try:
            a = int(rec["addr"], 16)
            e = int(rec["end"], 16)
        except ValueError:
            continue
        if (e - a) > 4:
            eff = rec["lift_name"] if rec["lift_name"] else rec["src_name"]
            print("     %s %s span=0x%X %s" % (rec["addr"], rec["end"], e - a, eff))
            shown += 1
            if shown >= 3:
                break

    # ---- equinox311 adoption report (bank 60E0FC00) ------------------------
    eqx_wins = [r for r in out if r["source"] == "equinox311"]
    eqx_clean_wins = [r for r in eqx_wins if r["flag"] in ("GHIDRA-EQX", "GHIDRA-EQX-HEUR")]
    eqx_unc_wins = [r for r in eqx_wins if r["flag"] == "GHIDRA-EQX-UNCERTAIN"]
    # conflitti ghidra-hand mantenuti: vincitore ghidra-hand, equinox in also_sources
    gh_conflicts = [r for r in out if r["bank"] == EQUINOX_BANK
                    and r["source"] in ("ghidra-hand", "ghidra-hand-xmap")
                    and "equinox311:" in r.get("also_sources", "")]
    print("\n  equinox311 adoption (bank 60E0FC00):")
    print("    adopted (winner source=equinox311): %d  clean=%d  uncertain=%d"
          % (len(eqx_wins), len(eqx_clean_wins), len(eqx_unc_wins)))
    print("    ghidra-hand conflicts KEPT (ghidra-hand vince, equinox in also_sources): %d"
          % len(gh_conflicts))
    print("    8 esempi nomi equinox ADOTTATI (addr, old, new):")
    for bank, addr, old, new in eqx_adopted[:8]:
        print("       %s %-28s -> %s" % (addr, old, new))
    print("    5 esempi conflitti ghidra-hand mantenuti (addr, ghidra-hand, equinox in also_sources):")
    for r in gh_conflicts[:5]:
        eqx_tag = [t for t in r["also_sources"].split("|") if t.startswith("equinox311:")]
        print("       %s %-28s also=%s" % (r["addr"], r["src_name"], "|".join(eqx_tag)))

    print("  orphan lift addrs:", len(orphans))
    for r in orphan_records:
        print("     LIFT_ONLY %s %-24s bank=%s flag=%s verified=%s"
              % (r["addr"], r["lift_name"], r["bank"], r["flag"], r["verified"]))
    for a, note in bank_notes:
        print("     bank note: 0x%05X %s" % (a, note))
    print("  LIFT_ONLY rows:", len(orphan_records))

    # ---- dedup winning examples -------------------------------------------
    # prefer examples where the winner source differs from the lost sources,
    # spread across banks (one per bank where available)
    differing = [ex for ex in examples
                 if set(ex[3].split("|")) - {ex[2]} or (ex[2] and ex[3] != ex[2])]
    picked, seen_banks = [], set()
    # pass 1: one example per bank
    for ex in (differing or examples):
        if ex[0] not in seen_banks:
            picked.append(ex)
            seen_banks.add(ex[0])
        if len(picked) >= 3:
            break
    # pass 2: fill remaining slots from the same bank
    if len(picked) < 3:
        for ex in (differing or examples):
            if ex not in picked:
                picked.append(ex)
            if len(picked) >= 3:
                break
    if not picked:  # degenerate: no real dedup happened, keep any rows
        picked = examples[:3]
    print("\n  3 esempi dedup vincenti (addr uguale, source vincente vs perso):")
    for ex in picked:
        bank, addr, wsrc, lsrc = ex
        print("    %s %s winner-source=%-14s lost-source=%s"
              % (bank, addr, wsrc or "(none)", lsrc or "(none)"))

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

    # ---- integrity check: re-read master and compare per-bank unique counts --
    print("\n  verify (re-read CATALOG_MASTER.csv):")
    reread = {}
    with open(MASTER_CSV, encoding="utf-8", newline="") as fh:
        for rec in csv.DictReader(fh):
            reread.setdefault(rec["bank"], 0)
            reread[rec["bank"]] += 1
    ok = True
    for bank in sorted(raw_per_bank):
        exp, out_c = agg.get(bank, {}).get("total", 0), reread.get(bank, 0)
        flag = "OK" if exp == out_c else "MISMATCH"
        if exp != out_c:
            ok = False
        print("    %-10s unique-expect=%d  master=%d  %s" % (bank, exp, out_c, flag))
    print("  unique-count integrity: %s" % ("PASS" if ok else "FAIL"))

    print("\nDONE")


if __name__ == "__main__":
    main()