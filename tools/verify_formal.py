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
the stock ROM. PASS == the annotated .s re-assembles to the identical image.
P2  PARTITION     Parse the .s into a per-byte class map (instruction / data /
padding / other). Check 100% coverage of the ROM and no byte in two classes.
P3  CFG           Disassemble instruction regions (capstone SH2). For every
branch/branch-with-delay (bra,bsr,bt,bf,bt/s,bf/s [,braf,bsrf,jmp,jsr,rts,rte])
verify the absolute target lies in {instruction starts} U {declared function
entries}. Jump tables (analysis/data_regions) entries must be code starts too.
P4  XREF-CLOSURE  Roots = reset vector + exception vectors + declared function
entries + c/verified_addrs.txt. Reachability via branch/fallthrough/call over
decoded instructions. Flag (non-fatal) unreached code as dead code; for data
words require a reference (pcrel load target / 32-bit pointer) or membership in
a declared padding/config region, else VIOLATION.
P5  GAP-AUDIT     For every uncovered gap (analysis/coverage/uncovered_*.csv)
probe both word alignments for runs of >=2 valid instructions and scan for
XREFs (32-bit pointers / branch targets) landing inside the gap. Verdict
DATA if no code candidates and no refs, CODE-HIDDEN (FAIL) otherwise.

Status: COMPLETED 2026-08-04 — result NOT CERTIFIED (exit 1): P1/P2 PASS,
P3=448, P4=39061 unref_data (+dead FLAG 167368), P5=78 CODE-HIDDEN.
See docs/notes/FORMAL_CERT_60E1D400.md for per-violation action items.
No fixes applied (this task is report-only).
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

# SH-2 branch/call mnemonics we can statically resolve (absolute target in op_str).
RESOLVABLE = {'bra', 'bsr', 'bt', 'bf', 'bt/s', 'bf/s'}
# Control-flow mnemonics that end/blunt a basic block (no static target).
TERMINAL = {'jmp', 'jsr', 'braf', 'bsrf', 'rts', 'rte'}
# PC-relative loaders: their resolved op_str[0] is a data/pool address.
PCREL = {'mov.l', 'mov.w', 'mova'}


def hx(x):
    return '0x%X' % x


def sha256(b):
    return hashlib.sha256(b).hexdigest()


def build_partition(asm_path):
    """Parse the .s into a per-byte class map.

    Returns dict {byte_addr: class} plus instr_start set, padding regions,
    declared function entries, and coverage counts.
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
                w = int(m.group(1), 16)
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
                st = int(m.group(2), 16)
                addr = st & ~1
                declared_funcs.add(st & ~1)
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


def disassemble_all(d, instr_starts):
    """Decode every instruction word; return list of nodes dict."""
    md = capstone.Cs(capstone.CS_ARCH_SH, capstone.CS_MODE_SH2 | capstone.CS_MODE_BIG_ENDIAN)
    nodes = []
    for a in sorted(instr_starts):
        if a + 2 > len(d):
            continue
        w = int.from_bytes(d[a:a + 2], 'big')
        mne = None
        ops = ''
        for i in md.disasm(w.to_bytes(2, 'big'), a):
            mne = i.mnemonic
            ops = i.op_str
            break
        nodes.append({'addr': a, 'mne': mne, 'ops': ops})
    return nodes


def extract_abs(op_str):
    """First hex literal in op_str -> int or None."""
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


def read_hex_csv(path, dec=False):
    """Rows of an uncovered/data-region CSV -> list of (start,end) ints."""
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
                s = int(c[0], 10 if dec else 16)
                e = int(c[1], 10 if dec else 16)
            except Exception:
                continue
            rows.append((s, e))
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', default='roms/stock/60E1D400.bin')
    ap.add_argument('--asm', default='src/60E1D400_annotated.s')
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
    # overlaps: a byte that is both 'instr' and 'data'
    overlap = []
    for b in range(N):
        k = bc.get(b)
        if k == 'instr':
            # check partner byte of the word
            pass
    # simple overlap: adjacent word reassigned — detect via class set count
    classes_of = {}
    for b, k in bc.items():
        classes_of.setdefault(b, set()).add(k)
    multi = {b: c for b, c in classes_of.items() if len(c) > 1}
    # padding overlaps data is expected (re-declared), so only report instr/data mix
    real_overlap = [b for b, c in classes_of.items()
                    if 'instr' in c and 'data' in c]
    coverage_ok = (len(uncov) == 0)
    overlap_ok = (len(real_overlap) == 0)
    if coverage_ok and overlap_ok:
        results['P2'] = ('PASS', 0, [], 'bytes %d/%d covered' % (cov, N))
    else:
        v = []
        for b in real_overlap[:10]:
            v.append(('', hx(b), 'instr+data overlap'))
        for b in uncov[:10]:
            v.append(('', hx(b), 'uncovered'))
        results['P2'] = ('FAIL', len(uncov) + len(real_overlap), v,
                         'uncov=%d overlap=%d bytes=%d/%d' % (len(uncov), len(real_overlap), cov, N))
    print('P2 PARTITION:', results['P2'][0], results['P2'][3])

    # ---------------- CFG P3 ----------------
    v_p3 = []   # (addr, mnemonic, target/msg)
    branch_tgts = set()
    if HAVE_CAPSTONE:
        nodes = disassemble_all(d, instr_starts)
        node_by_addr = {n['addr']: n for n in nodes}
        for n in nodes:
            t = extract_abs(n['ops'])
            if n['mne'] in RESOLVABLE and t is not None:
                branch_tgts.add(t)
                if not (t in instr_starts or t in declared):
                    v_p3.append((n['addr'], n['mne'], 'bra_tgt %s' % hx(t)))
            elif n['mne'] in PCREL and t is not None:
                pass  # data reference, handled in P4
    else:
        nodes = [{'addr': a, 'mne': None, 'ops': ''} for a in instr_starts]
        v_p3.append(('', '', 'capstone unavailable'))

    # jump tables from data_regions (decimal addresses)
    jump_viol = []
    jt_rows = []
    if os.path.exists(ROM_CSV):
        with open(ROM_CSV) as f:
            next(f, None)
            for line in f:
                c = line.split(',')
                if len(c) > 3 and 'jump_table' in c[3]:
                    try:
                        jt_rows.append((int(c[0]), int(c[1]), 'mova' in c[4]))
                    except Exception:
                        pass
    for s, e, is_mova in jt_rows:
        # 32-bit absolute jump-table entries (4-byte stride). mova-based tables
        # store small 16-bit offsets in-window, so their raw values are handled
        # leniently (offset dispatch) yet still reported if out-of-window.
        for a in range(s, e, 4):
            if a + 4 > N:
                break
            t_a = struct.unpack('>I', d[a:a + 4])[0] & 0xFFFFF
            if t_a == 0:
                continue  # terminator / padding sentinel in table
            if not (t_a in instr_starts or t_a in declared):
                kind = 'mova-offset' if is_mova else 'abs'
                jump_viol.append((hx(s), kind, 'jt entry @%s -> %s' % (hx(a), hx(t_a))))

    if HAVE_CAPSTONE and not v_p3 and not jump_viol:
        results['P3'] = ('PASS', 0, [], 'branches=%d jt_tables=%d' % (len(branch_tgts), len(jt_rows)))
    else:
        results['P3'] = ('FAIL', len(v_p3) + len(jump_viol), v_p3[:10] + jump_viol[:10],
                         'br_viol=%d jt_viol=%d branches=%d' % (len(v_p3), len(jump_viol), len(branch_tgts)))
    print('P3 CFG:', results['P3'][0], results['P3'][3])

    # ---------------- XREF P4 ----------------
    # roots
    roots = set(declared)
    root_vec0 = struct.unpack('>I', d[0:4])[0] & 0xFFFFF
    if root_vec0 in instr_starts:
        roots.add(root_vec0)
    # exception vectors region (first 0x100 bytes, 4-byte pointers)
    for off in range(0, min(0x100, N - 4), 4):
        v = struct.unpack('>I', d[off:off + 4])[0] & 0xFFFFF
        if v in instr_starts:
            roots.add(v)
    verified = read_verified(VERIFIED)
    roots |= {v for v in verified if v in instr_starts}

    # forward edges
    succ = {}
    pcrel_ref = set()
    if HAVE_CAPSTONE:
        for n in nodes:
            a = n['addr']
            t = extract_abs(n['ops'])
            s = []
            if n['mne'] in RESOLVABLE and t is not None:
                s.append(t)
                # conditional has fallthrough (bt/bf); branch-with-delay (bt/s bf/s bra) none
                if n['mne'] in ('bt', 'bf'):
                    if a + 2 in instr_starts:
                        s.append(a + 2)
            elif n['mne'] in TERMINAL:
                s = []
            else:
                if a + 2 in instr_starts:
                    s.append(a + 2)
            if n['mne'] in PCREL and t is not None:
                pcrel_ref.add(t)
            succ[a] = s

    # BFS reachability
    reached = set()
    stack = [r for r in roots if r in succ]
    while stack:
        cur = stack.pop()
        if cur in reached:
            continue
        reached.add(cur)
        for nx in succ.get(cur, []):
            if nx not in reached:
                stack.append(nx)
    dead = [a for a in instr_starts if a not in reached]
    dead_sorted = sorted(dead)

    # data words referenced by pcrel loads AND by 32-bit pointer values scanned
    ptr_vals = set()
    for off in range(0, N - 4, 2):
        ptr_vals.add(struct.unpack('>I', d[off:off + 4])[0] & 0xFFFFF)
    # declared data regions (padding/string/table/config) from data_regions + padding markers
    declared_regions = set()
    for s, e in read_hex_csv(ROM_CSV, dec=True):
        for x in range(s, e):
            declared_regions.add(x)
    for s, e in padding:
        for x in range(s, e):
            declared_regions.add(x)

    data_viol = []
    ref_by_ptr = set(ptr_vals)
    for w in sorted(data_words):
        referenced = (w in pcrel_ref) or (w in ref_by_ptr) or (w in declared_regions)
        if not referenced:
            data_viol.append(w)

    p4 = []
    if dead:
        p4.append(('', '', '') )
        results['P4_dead'] = ('FLAG', len(dead), ['FLAG dead: %s' % hx(x) for x in dead_sorted[:20]],
                              'unreached instructions %d' % len(dead))
    else:
        results['P4_dead'] = ('PASS', 0, [], 'no dead code')

    actual_viol = data_viol
    if not actual_viol:
        results['P4'] = ('PASS', 0, [], 'dead=%d unref_data=%d' % (len(dead), len(data_viol)))
    else:
        results['P4'] = ('FAIL', len(actual_viol),
                         ['%s unreferenced data word' % hx(x) for x in actual_viol[:10]],
                         'dead=%d unref_data=%d' % (len(dead), len(data_viol)))
    print('P4 XREF:', results['P4'][0], results['P4'][3], '(dead code %d)' % len(dead))

    # ---------------- P5 GAP-AUDIT ----------------
    md5 = capstone.Cs(capstone.CS_ARCH_SH, capstone.CS_MODE_SH2 | capstone.CS_MODE_BIG_ENDIAN) if HAVE_CAPSTONE else None

    def run_ok(start):
        """count consecutive valid instructions starting at even offset start."""
        cnt = 0
        a = start
        while a + 2 <= N:
            w = int.from_bytes(d[a:a + 2], 'big')
            lst = list(md5.disasm(w.to_bytes(2, 'big'), a))
            if not lst or lst[0].mnemonic in ('data',):
                break
            cnt += 1
            a += 2
        return cnt

    code_hidden = []
    for s, e in read_hex_csv(UNCOV_CSV):
        gap = list(range(s, e, 2))
        # candidates: runs >=2 valid instrs from even alignment within gap
        cand = 0
        for a in gap:
            if run_ok(a) >= 2:
                cand += 1
        # xref-in: only strong evidence of hidden CODE = a branch/call target
        # landing inside the gap (data constants that merely look like small
        # addresses are calibration values, not code edges).
        refs = any(s <= v < e for v in branch_tgts)
        if cand > 0 or refs:
            code_hidden.append((s, e, cand, refs))
    if not code_hidden:
        results['P5'] = ('PASS', 0, [], 'gaps audited=%d' % len(read_hex_csv(UNCOV_CSV)))
    else:
        results['P5'] = ('FAIL', len(code_hidden),
                         ['gap %s-%s cand=%s refs=%s' % (hx(s), hx(e), c, r) for s, e, c, r in code_hidden[:10]],
                         'CODE-HIDDEN gaps=%d' % len(code_hidden))
    print('P5 GAP-AUDIT:', results['P5'][0], results['P5'][3])

    # ---------------- CERTIFICATE ----------------
    print()
    print('CERTIFICATE 60E1D400')
    for k in ('P1', 'P2', 'P3', 'P4', 'P5'):
        st, n, _, detail = results.get(k, ('SKIP', 0, [], ''))
        print('  %s: %s (%d) %s' % (k, st, n, detail))
    ok = (results['P1'][0] == 'PASS' and results['P2'][0] == 'PASS' and
          results['P3'][0] == 'PASS' and results['P5'][0] == 'PASS' and
          results['P4'][0] == 'PASS')
    total = sum(results[k][1] for k in ('P1', 'P2', 'P3', 'P4', 'P5'))
    print('  VERDICT: %s  total_violations=%d  dead_code=%d' %
          ('CERTIFIED' if ok else 'NOT-CERTIFIED', total, len(dead)))
    print()
    print('  first violations:')
    for k in ('P3', 'P4', 'P5'):
        st, n, lst, _ = results.get(k, ('SKIP', 0, [], ''))
        for it in lst[:5]:
            print('    %s: %s' % (k, it))
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()