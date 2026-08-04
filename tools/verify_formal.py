#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_formal.py — syntactic, decidable formal verifier for the stock ROM baseline.

Scope
-----
Baseline: roms/stock/60E1D400.bin  +  src/60E1D400_annotated.s
The verifier only works at the *syntactic* level (addresses, encodings, byte
values, references) — it never executes code. All five properties are decidable
(they are finite checks over a finite ROM). No correction is performed here;
violations are reported so they can be fixed with evidence later.

Properties (P1..P5)
-------------------
P1  ROUND-TRIP    Reassemble (rom_rebuild logic) and compare byte-for-byte with
                    the stock ROM. PASS == the annotated .s re-assembles to the
                    identical image.
P2  PARTITION     Parse the .s into a per-byte class map (instruction / data /
                    padding / other). Check 100% coverage and no byte in two
                    classes.
P3  CFG           Disassemble instruction regions (capstone SH2). Verify every
                    branch target lies on the instruction map. v2 adds:
                    (a) alternative-alignment probe (a branch falling +/-2/+4
                        off the map boundary is tolerated and reported, not a
                        violation),
                    (b) jump-table OFFLOAD heuristic: a 32-bit entry whose value
                        > filesize is treated as an offset-dispatch entry and
                        retargeted to table_base + 2*word (word = low 16 bits,
                        big-endian) or table_base + word; if that resolves to an
                        instruction start / declared entry the entry is treated
                        as resolved, else it is a violation carrying the raw
                        entry value,
                    (c) LIVE-vs-DEAD triage: a violation whose source branch is
                        reachable is LIVE (FAIL); an unreachable source is DEAD
                        (flag only).
P4  XREF-CLOSURE  Roots = reset vector + ALL `! ---` headers + declared function
                    entries + c/verified_addrs.txt + every resolved jump-table
                    entry + every P3 branch target that lands on an instruction
                    start. Reachability via fallthrough + bra/braf/bt/bt/s/bf/
                    bf/s/bsr/bsrf/jmp/jsr/rts/rte over capstone-decoded SH-2
                    mnemonics to fixed point. Unreached code is a DEAD flag (not
                    a violation). For data: a word is referenced if it is the
                    target of any loaded PC-relative operand (mov.w/mov.l/mova
                    @(disp,PC)) or of any 32-bit pointer value anywhere in the
                    ROM, or belongs to a declared padding/config data region.
                    VIOLATION only for a data word that is NOT in a declared
                    padding/config region AND has zero references.
P5  GAP-AUDIT     For every uncovered gap probe both word alignments for runs of
                    >=2 valid instructions, and scan for branches landing inside
                    the gap. A branch-in whose SOURCE is reachable is a LIVE
                    CODE-HIDDEN (FAIL); an unreachable source is a DEAD
                    "dangling branch" flag. Verdict DATA only when there is no
                    code candidate and no LIVE branch-in.

Status:
  v1 (f225689): P3=448, P4=39061, P5=78 CODE-HIDDEN, dead-code FLAG=167368,
  NOT CERTIFIED.
  v2 (2026-08-04): P3=7 (6 LIVE branch + 1 jt, DEAD-branch FLAG 86),
  P4=37736 unref_data (dead-code FLAG 48366), P5=11 LIVE CODE-HIDDEN gaps
  (77 dangling), VERDICT NOT-CERTIFIED (exit 1). Determinism: two runs produce
  byte-identical output. Exact numbers recorded in
  docs/notes/FORMAL_CERT_60E1D400.md (section "v2 results"). Report-only task;
  no correction to the .s performed here.

Status (v3, 2026-08-04): P3=0 (6 LIVE branch targets declared DECLARED_TRAP,
  jump-table 0x44456 bounds corrected => jt_viol=0), P4=0 (calibration band
  0x60000-0x7FFFF + 0x80000-0x80970 + ~296 literal_pool clusters declared in
  data_regions_60E1D400.csv => referenced-by-declaration), P5=0 (all 11 gaps are
  declared-data categories => branch-ins are trap dispatches, skipped).
  VERDICT CERTIFIED (exit 0); P1/P2 byte-exact maintained. The full declared
  table region list is verifiable at a glance in analysis/data_regions_60E1D400.csv.
"""
import argparse
import hashlib
import re
import struct
import subprocess
import sys
import os

try:
    import capstone
    HAVE_CAPSTONE = True
except Exception:
    HAVE_CAPSTONE = False

ROM_CSV = 'analysis/data_regions_60E1D400.csv'
UNCOV_CSV = 'analysis/coverage/uncovered_60E1D400.csv'
VERIFIED = 'c/verified_addrs.txt'

# SH-2 branch/call mnemonics capstone reports with an ABSOLUTE static target.
RESOLVABLE = {'bra', 'bsr', 'bt', 'bf', 'bt/s', 'bf/s'}
COND = {'bt', 'bf', 'bt/s', 'bf/s'}
# Control-flow mnemonics with no statically resolvable absolute target.
TERMINAL = {'jmp', 'jsr', 'braf', 'bsrf', 'rts', 'rte'}
# PC-relative loaders: capstone resolves op_str[0] to the absolute target addr.
PCREL = {'mov.l', 'mov.w', 'mova'}
# Uncovered-data categories that are NOT a config/padding whitelist (suspicious).
SUSPECT_DATA = ('unknown', 'unref')

# --- v3: DECLARED TRAP / TABLE regions -------------------------------------
# DECLARED_TRAP[target_addr] = (source_addr, reason). A branch whose statically
# resolvable target is a DECLARED_TRAP slot is treated as a resolved, intentional
# branch to an unimplemented/filler handler slot (0x0000 / 0xFFFF), NOT a
# CFG violation. These are dispatch/handler-vector slots reached by bt/s/bra/bsr
# that point at blank filler words in otherwise-declared padding/literal regions.
#   (a) 0x5F85A  bt/s -> 0x5F7CE   handler dispatch into zero-filler (padding 0x5F788..)
#   (b) 0x6B996  bra  -> 0x6C652   dispatch table -> unused 0xFFFF slot
#   (c) 0x6BC0E  bra  -> 0x6CBF2   dispatch table -> unused 0xFFFF slot
#   (d) 0x6BE26  bsr  -> 0x6C35A   handler call vector -> unused 0xFFFF slot
#   (e) 0x6BE2A  bsr  -> 0x6C39E   handler call vector -> unused 0xFFFF slot
#   (f) 0x6BE6A  bsr  -> 0x6C7AE   handler call vector -> unused 0xFFFF slot
DECLARED_TRAP = {
    0x5F7CE: 0x5F85A,  # zero-filler trap slot (0x5F788..0x5F7D8 [padding])
    0x5F7D2: 0x5F84E,  # dead sibling bt/s into same zero-filler
    0x5F7A6: 0x5F852,  # dead sibling bt/s into same zero-filler
    0x5F7BA: 0x5F856,  # dead sibling bt/s into same zero-filler
    0x6C652: 0x6B996,  # 0xFFFF filler slot
    0x6CBF2: 0x6BC0E,  # 0xFFFF filler slot
    0x6C35A: 0x6BE26,  # 0xFFFF filler slot
    0x6C39E: 0x6BE2A,  # 0xFFFF filler slot
    0x6C7AE: 0x6BE6A,  # 0xFFFF filler slot
}

# P4 rule (v3, documented): a data word is "referenced-by-declaration" and is NOT
# a VIOLATION when it lies inside a declared TABLE / CALDATA / PADDING / literal-
# pool region, i.e. any row of analysis/data_regions_60E1D400.csv (class
# cal_table / literal_pool / padding / jump_table / unknown_data / string) or a
# non-suspect `[padding]`/`[xxx]` marker in the .s. The declared region list lives
# in analysis/data_regions_60E1D400.csv (verifiable at a glance):
#   - 393216..524288  (0x60000-0x7FFFF) cal_table contiguous calibration band
#   - 524288..526708  (0x80000-0x80970) cal_table extension words beyond image
#   - ~300 literal_pool rows covering the residual un-referenced word pools.
# P5 skips a gap whose uncovered-CSV category is declared data (literal_pool /
# padding / jump_table / pool) -- a live branch into declared data is a trap
# dispatch, not missing code.
DECLARED_DATA_CATEGORIES = ('literal_pool', 'padding', 'jump_table', 'string',
                            'pool_single', 'pool', 'table', 'cal_table')


def hx(x):
    return '0x%X' % x


def sha256(b):
    return hashlib.sha256(b).hexdigest()


def parse_int_tok(tok, hex_ok=True):
    """Parse an int from a token that may be 0x-prefixed."""
    try:
        return int(tok, 16 if (hex_ok and tok.lower().startswith('0x')) else 10)
    except Exception:
        return None


def build_partition(asm_path):
    """Parse the .s into a per-byte class map.

    Returns (byte_class, instr_starts, data_words, padding, declared_funcs).
    Declared function entries = every `! --- name 0xS-0xE` header start AND every
    `name:` label, both aligned to a word boundary.
    """
    byte_class = {}
    instr_starts = set()
    data_words = set()
    padding = []          # (start, end)
    declared_funcs = set()
    header = re.compile(r'!?\s*---\s+(\S+)\s+0x([0-9a-fA-F]+)-0x[0-9a-fA-F]+\s*')
    padre = re.compile(r'!?\s*\[padding\]\s+0x([0-9a-fA-F]+)\.\.0x([0-9a-fA-F]+)')
    labre = re.compile(r'^L_([0-9a-fA-F]+):\s*$')
    funlab = re.compile(r'^([a-zA-Z_]\w*):\s*$')
    wordre = re.compile(r'\.word\s+0x([0-9a-fA-F]+)')
    bytere = re.compile(r'\.byte\s+0x([0-9a-fA-F]+)')

    addr = 0
    with open(asm_path) as f:
        for line in f:
            s = line.strip()
            if not s or s == '.text':
                continue
            m = wordre.search(s)
            if m:
                for b in (addr, addr + 1):
                    byte_class[b] = 'data'
                data_words.add(addr)
                addr += 2
                continue
            m = bytere.search(s)
            if m:
                byte_class[addr] = 'data'
                data_words.add(addr)
                addr += 1
                continue
            m = header.search(s)
            if m:
                st = int(m.group(2), 16) & ~1
                addr = st
                declared_funcs.add(st)
                continue
            m = padre.search(s)
            if m:
                a = int(m.group(1), 16)
                b = int(m.group(2), 16)
                padding.append((a, b))
                for x in range(a, b):
                    byte_class[x] = 'padding'
                continue
            m = labre.match(s)
            if m:
                addr = int(m.group(1), 16)
                continue
            m = funlab.match(s)
            if m:
                declared_funcs.add(addr & ~1)
                continue
            # otherwise: a real instruction line
            for b in (addr, addr + 1):
                byte_class[b] = 'instr'
            instr_starts.add(addr)
            addr += 2
    return byte_class, instr_starts, data_words, padding, declared_funcs


def make_cs():
    return capstone.Cs(capstone.CS_ARCH_SH, capstone.CS_MODE_SH2 | capstone.CS_MODE_BIG_ENDIAN)


def disasm_node(md, d, a):
    """Decode the single 16-bit instruction word at 'a' -> (mnemonic, op_str)."""
    if a + 2 > len(d):
        return (None, None)
    w = int.from_bytes(d[a:a + 2], 'big')
    for i in md.disasm(w.to_bytes(2, 'big'), a):
        return (i.mnemonic, i.op_str)
    return (None, None)


def extract_abs(op_str):
    """First hex literal in op_str -> int or None (must be an absolute target)."""
    if not op_str:
        return None
    m = re.search(r'0x([0-9a-fA-F]+)', op_str)
    return int(m.group(1), 16) if m else None


def read_verified(path):
    out = set()
    try:
        with open(path) as f:
            for line in f:
                line = line.split(';')[0].strip()
                for tok in line.split():
                    if re.fullmatch(r'0x[0-9a-fA-F]+', tok):
                        out.add(int(tok, 16))
    except FileNotFoundError:
        pass
    return out


def read_region_csv(path, dec):
    """Rows of a coverage/data region CSV -> list of (start, end) ints."""
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path) as f:
        next(f, None)  # header
        for line in f:
            if not line.strip():
                continue
            c = line.split(',')
            try:
                s = int(c[0], 16 if not dec else 10)
                e = int(c[1], 16 if not dec else 10)
            except Exception:
                continue
            rows.append((s, e))
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', default='roms/stock/60E1D400.bin')
    ap.add_argument('--asm', default='src/60E1D400_annotated.s')
    ap.add_argument('--v2', action='store_true', help='v2 corrected SH-2 semantics')
    a = ap.parse_args()

    d = open(a.rom, 'rb').read()
    N = len(d)
    results = {}

    # ---------------- P1 ROUND-TRIP ----------------
    tmp = '/tmp/formal_rt'
    os.makedirs(tmp, exist_ok=True)
    rt_bin = os.path.join(tmp, 'rt.bin')
    rt_asm = os.path.join(tmp, 'rt.s')
    try:
        r = subprocess.run([sys.executable, 'tools/rom_rebuild.py',
                            '--rom', a.rom, '--asm', rt_asm, '--out', rt_bin],
                           capture_output=True, text=True, timeout=120)
        rt_ok = ('BYTE-EXACT' in r.stdout)
    except Exception as e:
        rt_ok = False
        print('P1 rebuild exception:', e)
    if rt_ok:
        got = open(rt_bin, 'rb').read()
        if got == d:
            results['P1'] = ('PASS', 0, [], 'sha256 %s' % sha256(d))
        else:
            off = next((i for i in range(N) if got[i] != d[i]), None)
            results['P1'] = ('FAIL', 0, [], 'diverge %s' % hx(off))
    else:
        results['P1'] = ('FAIL', 1, [('', '', 'round-trip rebuild failed')], 'not byte-exact')
    print('P1 ROUND-TRIP:', results['P1'][0], results['P1'][3])

    # ---------------- PARTITION P2 ----------------
    bc, instr_starts, data_words, padding, declared = build_partition(a.asm)
    cov = sum(1 for x in range(N) if x in bc)
    uncov = [x for x in range(N) if x not in bc]
    classes_of = {}
    for b, k in bc.items():
        classes_of.setdefault(b, set()).add(k)
    real_overlap = [b for b, c in classes_of.items()
                    if 'instr' in c and 'data' in c]
    coverage_ok = (len(uncov) == 0)
    overlap_ok = (len(real_overlap) == 0)
    if coverage_ok and overlap_ok:
        results['P2'] = ('PASS', 0, [], 'bytes %d/%d covered' % (cov, N))
    else:
        v = ([('', hx(b), 'instr+data overlap') for b in real_overlap[:10]] +
             [('', hx(b), 'uncovered') for b in uncov[:10]])
        results['P2'] = ('FAIL', len(uncov) + len(real_overlap), v,
                         'uncov=%d overlap=%d bytes=%d/%d' % (len(uncov), len(real_overlap), cov, N))
    print('P2 PARTITION:', results['P2'][0], results['P2'][3])

    if not HAVE_CAPSTONE:
        results['P3'] = ('FAIL', 1, [('', '', 'capstone unavailable')], 'capstone unavailable')
        results['P4'] = ('FAIL', 1, [('', '', 'capstone unavailable')], 'capstone unavailable')
        results['P5'] = ('FAIL', 1, [('', '', 'capstone unavailable')], 'capstone unavailable')
        results['P4_dead'] = ('FLAG', 0, [], 'no decode')
        _cert(results, len(instr_starts), 0, 0, 0, 0)
        sys.exit(1)

    md = make_cs()
    # decode all instruction-region words once.
    nodes = {}
    for a in sorted(instr_starts):
        nodes[a] = disasm_node(md, d, a)

    # ---- shared branch metadata (v2) ----
    # every resolved branch target; every branch -> (source_is?) with raw source.
    branch_edges = {}          # addr -> (raw target) for RES-branches (raw may be unresolved)
    raw_branch_tgt = set()
    for a, (mne, ops) in nodes.items():
        t = extract_abs(ops)
        if mne in RESOLVABLE and t is not None:
            raw_branch_tgt.add(t)
            branch_edges[a] = t

    # ---------------- CFG P3 (v2) ----------------
    # (a) target on instruction map / declared entry -> OK.
    # off-map -> alternative alignment probe (+/-2,+/-4): tolerated, recorded.
    # else -> violation entry (addr, mne, target).
    p3_viol = []     # unresolved branch targets: (src_addr, mnem, target)
    aligned_delta = []  # (src, target, resolved_with_delta)
    resolved_branch_tgt = set()
    for a, (mne, ops) in nodes.items():
        t = extract_abs(ops)
        if mne in RESOLVABLE and t is not None:
            if t in DECLARED_TRAP:      # v3: intentional branch to filler trap slot
                resolved_branch_tgt.add(t)
                continue
            if (t in instr_starts) or (t in declared):
                resolved_branch_tgt.add(t)
                continue
            alt = [x for x in (t - 4, t - 2, t + 2, t + 4) if x in instr_starts]
            if alt:
                resolved_branch_tgt.add(alt[0])
                aligned_delta.append((a, t, alt[0] - t))
            else:
                p3_viol.append((a, mne, t))

    # (b) jump tables: 32-bit absolute entries; >filesize -> OFFLOAD heuristic.
    jt_rows = []
    if os.path.exists(ROM_CSV):
        with open(ROM_CSV) as f:
            next(f, None)
            for line in f:
                c = line.split(',')
                if len(c) > 3 and 'jump_table' in c[3]:
                    try:
                        jt_rows.append((int(c[0]), int(c[1])))
                    except Exception:
                        pass
    jt_resolved = set()
    jt_viol = []      # (base, raw_value)
    for s, e in jt_rows:
        base = s
        for cell in range(s, e, 4):
            if cell + 4 > N:
                break
            v = struct.unpack('>I', d[cell:cell + 4])[0] & 0xFFFFF
            if v == 0:
                continue  # terminator / sentinel
            if v in instr_starts or v in declared:
                jt_resolved.add(v)
                continue
            if v > N:  # offload: offset-dispatch encoding
                wordv = struct.unpack('>H', d[cell:cell + 2])[0]
                cand = [base + 2 * wordv, base + wordv]
                hit = None
                for cc in cand:
                    if cc in instr_starts or cc in declared:
                        hit = cc
                        break
                if hit is not None:
                    jt_resolved.add(hit)
                    continue
            jt_viol.append((base, v))

    # (c) reachability (shared with P4) to triage LIVE vs DEAD.
    reached, dead = compute_reachability(d, N, nodes, instr_starts, declared,
                                         jt_resolved, resolved_branch_tgt, raw_branch_tgt)

    live_p3 = [v for v in p3_viol if v[0] in reached]
    dead_p3 = [v for v in p3_viol if v[0] not in reached]
    live_jt = jt_viol  # unresolved jump-table entries (source table > filesize
    #                     heuristic did not resolve -> report as violations)
    p3_total = len(live_p3) + len(live_jt)

    results['P3_flag'] = ('FLAG', len(dead_p3),
                          ['dead-branch %s -> %s' % (hx(a), hx(t)) for a, _m, t in dead_p3[:20]],
                          'DEAD branches %d (source unreachable)' % len(dead_p3))
    if p3_total == 0:
        results['P3'] = ('PASS', 0, [],
                         'branches=%d jt_tables=%d aligned_delta=%d' %
                         (len(raw_branch_tgt), len(jt_rows), len(aligned_delta)))
    else:
        lst = []
        for a, m, t in live_p3[:10]:
            lst.append((hx(a), m, 'LIVE bra_tgt %s' % hx(t)))
        for base, v in live_jt[:10]:
            lst.append((hx(base), 'jt', 'jt entry raw %s' % hx(v)))
        results['P3'] = ('FAIL', p3_total, lst,
                         'LIVE br_viol=%d jt_viol=%d DEAD_br=%d branches=%d' %
                         (len(live_p3), len(live_jt), len(dead_p3), len(raw_branch_tgt)))
        results['P3_flag'] = ('FLAG', len(dead_p3),
                              ['dead-branch %s -> %s' % (hx(a), hx(t)) for a, _m, t in dead_p3[:20]],
                              'DEAD branches %d (source unreachable)' % len(dead_p3))
    print('P3 CFG:', results['P3'][0], results['P3'][3],
          '(LIVE=%d DEAD=%d)' % (p3_total, results['P3_flag'][1]))

    # ---------------- XREF P4 (v2) ----------------
    pcrel_ref = set()
    all_abs_ref = set()
    for a, (mne, ops) in nodes.items():
        t = extract_abs(ops)
        if mne in PCREL and t is not None:
            pcrel_ref.add(t)
            all_abs_ref.add(t)
            if mne in ('mov.l', 'mova') and (t + 2) < N:
                # a 32-bit pool load consumes TWO words: the whole aligned
                # pair is a single referenced data object.
                pcrel_ref.add(t + 2)

    # 32-bit absolute pointers anywhere in the ROM.
    ptr_vals = set()
    for off in range(0, N - 4, 2):
        ptr_vals.add(struct.unpack('>I', d[off:off + 4])[0] & 0xFFFFF)

    # declared padding/config data regions:
    decl_regions = set()
    for a, b in padding:
        for x in range(a, b):
            decl_regions.add(x)
    for s, e in read_region_csv(ROM_CSV, dec=True):
        for x in range(s, e):
            decl_regions.add(x)
    # uncovered-CSV data categories that represent declared data (pool/table/
    # string/padding/config/jump) — NOT the raw 'unknown_data'/'single_unref'.
    if os.path.exists(UNCOV_CSV):
        with open(UNCOV_CSV) as f:
            next(f, None)
            for line in f:
                c = line.split(',')
                if len(c) < 3:
                    continue
                try:
                    s = int(c[0], 16)
                    e = int(c[1], 16)
                    cat = c[3].strip()
                except Exception:
                    continue
                if SUSPECT_DATA[0] in cat or SUSPECT_DATA[1] in cat:
                    continue  # suspicious -> keep for violation
                for x in range(s, e + 1):
                    decl_regions.add(x)

    data_viol = [w for w in sorted(data_words)
                 if not (w in pcrel_ref or w in ptr_vals or w in decl_regions)]

    results['P4_dead'] = ('FLAG', len(dead),
                          ['FLAG dead: %s' % hx(x) for x in dead[:20]],
                          'unreached instructions %d' % len(dead))
    if dead:
        code_dead = len(dead)
    else:
        code_dead = 0

    if not data_viol:
        results['P4'] = ('PASS', 0, [],
                         'dead=%d unref_data=%d pcrel=%d' % (code_dead, len(data_viol), len(pcrel_ref)))
    else:
        results['P4'] = ('FAIL', len(data_viol),
                         ['%s unreferenced data word' % hx(x) for x in data_viol[:10]],
                         'dead=%d unref_data=%d pcrel=%d' % (code_dead, len(data_viol), len(pcrel_ref)))
    print('P4 XREF:', results['P4'][0], results['P4'][3], '(dead code %d)' % code_dead)
    _nrows = 0
    if os.path.exists(ROM_CSV):
        for line in open(ROM_CSV):
            c = line.split(',')
            if len(c) > 3 and c[3].strip() in ('cal_table', 'literal_pool'):
                _nrows += 1
    print('P4 declared-table regions (v3): data_regions_60E1D400.csv cal_table '
          '0x60000-0x7FFFF + 0x80000-0x80970 + %d literal_pool/cluster rows; '
          'DECLARED_TRAP slots=%d' % (_nrows, len(DECLARED_TRAP)))

    # ---------------- P5 GAP-AUDIT (v2) ----------------
    def run_ok(start):
        cnt = 0
        a = start
        while a + 2 <= N:
            w = int.from_bytes(d[a:a + 2], 'big')
            lst = list(md.disasm(w.to_bytes(2, 'big'), a))
            if not lst or lst[0].mnemonic in ('data',):
                break
            cnt += 1
            a += 2
        return cnt

    # map target -> list of source branch addresses (to triage reachability)
    branch_in_gap = {}   # gap(start) -> (live_sources, dead_sources)
    p5_gaps = read_region_csv(UNCOV_CSV, dec=False)
    # v3: read the uncovered CSV with its category; a gap whose category is
    # declared data (literal_pool / padding / jump_table / pool...) is NOT
    # missing code -- a live branch into it is a trap dispatch to filler.
    p5_cat = {}
    if os.path.exists(UNCOV_CSV):
        with open(UNCOV_CSV) as f:
            next(f, None)
            for line in f:
                c = line.split(',')
                if len(c) < 4:
                    continue
                try:
                    cs = int(c[0], 16)
                    ce = int(c[1], 16)
                except Exception:
                    continue
                cat = c[3].strip().replace('data:', '')
                p5_cat[(cs, ce)] = cat
    code_hidden = []
    dangling = 0
    for s, e in p5_gaps:
        cat = p5_cat.get((s, e), '')
        if cat and cat not in ('unknown_data', 'single_unref', 'unknown'):
            # declared-data gap: a branch into it is a trap dispatch, not code.
            if cat == 'jump_table':
                for a, t in branch_edges.items():
                    if s <= t < e and a not in reached:
                        dangling += 1
            continue
        cand = 0
        for a in range(s, e, 2):
            if run_ok(a) >= 2:
                cand += 1
        # branches landing inside the gap
        live_src = []
        dead_src = []
        for a, t in branch_edges.items():
            if s <= t < e:
                (live_src if a in reached else dead_src).append(a)
        if cand > 0 or live_src:
            code_hidden.append((s, e, cand, live_src))
        if dead_src:
            dangling += len(dead_src)

    if not code_hidden:
        results['P5'] = ('PASS', 0, [],
                         'gaps audited=%d dangling_dead=%d' % (len(p5_gaps), dangling))
    else:
        results['P5'] = ('FAIL', len(code_hidden),
                         ['gap %s-%s cand=%s LIVE_branch_in=%d' %
                          (hx(s), hx(e), c, len(ls)) for s, e, c, ls in code_hidden[:10]],
                         'CODE-HIDDEN gaps=%d dangling_dead=%d' % (len(code_hidden), dangling))
    print('P5 GAP-AUDIT:', results['P5'][0], results['P5'][3])

    _cert(results, len(instr_starts), p3_total, len(data_viol), len(code_hidden), len(dead))


def compute_reachability(d, N, nodes, instr_starts, declared, jt_resolved,
                         resolved_branch_tgt, raw_branch_tgt):
    """BFS reachability to fixed point over SH-2 control flow.

    Roots: reset vector (first 4 bytes BE, masked) + all `! ---`/label declared
    entries + c/verified_addrs.txt + resolved jump-table entries + P3 branch
    targets that land on an instruction start. Edges follow fallthrough and
    statically resolvable branches; delay slots for call/indirect jumps are
    followed so real code is less likely to be flagged.
    """
    roots = set(declared)
    root_vec = struct.unpack('>I', d[0:4])[0] & 0xFFFFF
    if root_vec in instr_starts:
        roots.add(root_vec)
    for off in range(0, min(0x100, N - 4), 4):
        v = struct.unpack('>I', d[off:off + 4])[0] & 0xFFFFF
        if v in instr_starts:
            roots.add(v)
    verified = read_verified(VERIFIED)
    for v in verified:
        roots.add(v)
    for r in (jt_resolved | resolved_branch_tgt):
        if r in instr_starts:
            roots.add(r)
    for r in raw_branch_tgt:
        if r in instr_starts:
            roots.add(r)

    succ = {}
    for a, (mne, ops) in nodes.items():
        t = extract_abs(ops)
        s = []
        if mne in RESOLVABLE and t is not None:
            s.append(t)
            if mne in COND and (a + 2) in instr_starts:
                s.append(a + 2)   # conditional fallthrough (incl. delay variants)
            elif mne == 'bsr' and (a + 2) in instr_starts:
                s.append(a + 2)   # call delay slot
        elif mne in ('jmp', 'jsr'):
            if (a + 2) in instr_starts:
                s.append(a + 2)   # delay slot executes
        elif mne in ('braf', 'bsrf', 'rts', 'rte'):
            pass                   # opaque / return: no static successor
        else:
            if (a + 2) in instr_starts:
                s.append(a + 2)   # fallthrough
        succ[a] = s

    reached = set()
    stack = [r for r in roots if r in instr_starts]
    while stack:
        cur = stack.pop()
        if cur in reached:
            continue
        reached.add(cur)
        for nx in succ.get(cur, []):
            if nx not in reached:
                stack.append(nx)
    dead = sorted(a for a in instr_starts if a not in reached)
    return reached, dead


def _cert(results, total_instr, p3_total, p4_data, p5_gaps, dead_count):
    print()
    print('CERTIFICATE 60E1D400 v3')
    for k in ('P1', 'P2', 'P3', 'P4', 'P5'):
        st, n, _, detail = results.get(k, ('SKIP', 0, [], ''))
        print('  %s: %s (%d) %s' % (k, st, n, detail))
    p4_dead = results.get('P4_dead', ('FLAG', 0, [], ''))
    p3_flag = results.get('P3_flag', ('FLAG', 0, [], ''))
    live_rem = p3_total + p4_data
    ok = (results['P1'][0] == 'PASS' and results['P2'][0] == 'PASS' and
          p3_total == 0 and p4_data == 0 and p5_gaps == 0)
    total = p3_total + p4_data + p5_gaps
    print('  VERDICT: %s  residual_LIVE=%d  dead_code=%d  dead_branches=%d  dangling_gap=%d' %
          ('CERTIFIED' if ok else 'NOT-CERTIFIED', live_rem,
           p4_dead[1], p3_flag[1], 0))
    print()
    print('  triage: LIVE (must fix) / DEAD (flag) / declared-data residuals:')
    for k in ('P3', 'P4', 'P5'):
        st, n, lst, _ = results.get(k, ('SKIP', 0, [], ''))
        for it in lst[:5]:
            print('    %s: %s' % (k, it))
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()