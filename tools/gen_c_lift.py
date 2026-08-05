#!/usr/bin/env python3
"""
gen_c_lift.py — deterministic CLI that lifts PURE straight-line SH-2 functions
from the RX-8 ECU ROM into C (c/<name>_<addr>.c) plus a differential spec_mirror
test (c/tests/test_<name>_<addr>.py) that checks the Python mirror against the
sh2emu oracle over 2000 random inputs.

Semantics for every instruction come from tools/c_lift_ops.py (big-endian
SH-2) — that table mirrors tools/sh2emu.py exactly, so a lift generated here is
guaranteed to agree with the emulator.  Only opcodes the mapper accepts (its
pure straight-line set: register/literal/PC-pool/T-flag ops; statement dicts
carry no 'kind' key) are lifted; any unsupported/branch/return/memory opcode
terminates the pure span, so the lifted body is genuinely "no calls, no memory
side effects".

Usage:
    python3 tools/gen_c_lift.py [--category CAN Bus] [--n 10] [--seed 0] [--addr 0x1234]
    python3 tools/gen_c_lift.py --stats
"""
import argparse
import csv
import glob
import os
import random
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))
sys.path.insert(0, os.path.join(ROOT, 'c', 'tests'))

import c_lift_ops as ops

MASK = 0xFFFFFFFF
ROM_LABEL = '60E1D400'
MAX_INSTR = 48          # size cap: <= 96 bytes / 2
MIN_LEN, MAX_LEN = 8, 96
N_CASES = 2000


def load_catalog_end(path):
    """CATALOG_MASTER.csv -> {addr: end}, dropping NOISE rows."""
    m = {}
    with open(path) as f:
        for row in csv.DictReader(f):
            if (row.get('flag') or '').strip() == 'NOISE':
                continue
            try:
                addr = int(row['addr'].strip(), 16)
            except (ValueError, TypeError):
                continue
            try:
                m[addr] = int(row['end'].strip(), 16)
            except (ValueError, TypeError):
                m[addr] = None
    return m


def load_categories(path):
    """FUNCTION_CATEGORIES.csv -> list of {addr, name, category}."""
    rows = []
    with open(path) as f:
        for row in csv.DictReader(f):
            try:
                addr = int(row['addr'].strip(), 16)
            except (ValueError, TypeError):
                continue
            rows.append({
                'addr': addr,
                'name': (row.get('name') or '').strip(),
                'category': (row.get('category') or '').strip(),
            })
    return rows


def decode_pure_span(rom, addr, end):
    """Decode the maximal pure straight-line span starting at addr.

    Big-endian SH-2 decode using c_lift_ops.translate.  Stops at the first
    instruction that is unsupported (translate->None) or not a straight-line
    statement (kind != 'st': branch/ret, or any memory/side-effect op).  Returns
    list of (pc, op, translate_dict) tuples, or None if nothing pure.
    """
    bound = end if end is not None else addr + 0x1000
    bound = min(bound, len(rom))
    instrs = []
    pc = addr
    while pc + 1 < bound and len(instrs) < MAX_INSTR:
        op = (rom[pc] << 8) | rom[pc + 1]
        d = ops.translate(op, pc, rom)
        # unsupported / branch / return / memory access / side-effect -> end span
        # (statement ops carry no 'kind' key; only branch/ret dicts do)
        if d is None or d.get('kind') in ('branch', 'ret'):
            break
        instrs.append((pc, op, d))
        pc += 2
    return instrs if instrs else None


def sanitize(name):
    return re.sub(r'\W', '_', name or 'fun') or 'fun'


def gen_c_body(instrs, rom):
    """Return (c_text, used_set) — full lift body incl. locals + return r0."""
    stmts = []
    used = set()
    for pc, op, d in instrs:
        ann = d.get('ann') or ('op 0x%04X' % op)
        stmts.append('/* 0x%06X: %s */' % (pc, ann))
        stmts.extend(d['c'])
        used |= d.get('uses', set())

    reg_used = {u for u in used if re.fullmatch(r'r\d+', u)}
    flag_used = {u for u in used if u in ('T', 'Q', 'M', 'mach', 'macl', 'pr')}
    reg_nums = sorted({int(u[1:]) for u in reg_used})

    lines = []
    # r4..r7 are the (potential) function args — declared as C parameters below.
    lines.append('    // locals; r0..r3 and r8..r15 start as 0')
    lines.append('    uint32_t ' + ', '.join('r%d=0' % n for n in range(4)) + ';')
    extra = [n for n in range(8, 16) if n in reg_nums]
    if extra:
        lines.append('    uint32_t ' + ', '.join('r%d=0' % n for n in extra) + ';')
    if flag_used:
        defs = []
        for fl in sorted(flag_used):
            if fl == 'pr':
                defs.append('pr=0x%08Xu' % 0xEEEE0000)
            else:
                defs.append('%s=0' % fl)
        lines.append('    uint32_t ' + ', '.join(defs) + ';')
    lines.append('    // r4..r7 are possible function arguments (set at entry)')
    lines.extend('    ' + s for s in stmts)
    lines.append('    return r0;')
    return '\n'.join(lines), used


def emit(addr, name, size, instrs, rom, seed, out_c, out_t):
    fn = sanitize(name)
    cbody, used = gen_c_body(instrs, rom)

    # collect raw bytes (for the emulator copy in the test)
    raw = rom[addr:addr + size]
    flat = ' '.join('%02X' % b for b in raw)

    banner = '/* ROM: %s | Address: 0x%X | Size: %d bytes | STATUS: DRAFT\n' \
             ' * Auto-generated by tools/gen_c_lift.py - not human-verified.\n' \
             ' * Pure straight-line function: no calls, no memory side effects. */' % (
                 ROM_LABEL, addr, size)

    c_text = (
        banner + '\n'
        '#include <stdint.h>\n'
        'uint32_t %s_%x(uint32_t r4, uint32_t r5, uint32_t r6, uint32_t r7)\n'
        '{\n%s\n}\n') % (fn, addr, cbody)

    with open(out_c, 'w') as f:
        f.write(c_text)

    # ---- spec_mirror: replicate the same semantics in Python ----
    py_stmts = []
    for pc, op, d in instrs:
        py_stmts.append('    # 0x%06X: op 0x%04X' % (pc, op))
        for s in d['py']:
            joined = '\n    '.join(ln.strip() for ln in s.split('\n') if ln.strip())
            py_stmts.append('    ' + joined)

    test = (
        '#!/usr/bin/env python3\n'
        '"""Differential test for %s (0x%X) — pure straight-line lift, %d bytes.\n'
        'Auto-generated by tools/gen_c_lift.py — not human-verified.\n'
        'Compares a Python spec_mirror against the sh2emu oracle (which runs the\n'
        'actual ROM bytes) over %d random inputs.\n'
        'Run from repo root: python3 c/tests/test_%s_%x.py\n'
        '"""\n'
        'import os, random, sys\n\n'
        'ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))\n'
        'sys.path.insert(0, os.path.join(ROOT, "tools"))\n'
        'from sh2emu import SH2\n'
        'from c_lift_ops import s8, s16, s32\n\n'
        'ROM = os.path.join(ROOT, "roms", "stock", "60E1D400.bin")\n'
        'ENTRY = 0x%X\n'
        'RAW = bytes.fromhex("%s")\n'
        'SEED = %d\n'
        'N = 2000\n\n'
        'def spec_mirror(r4, r5, r6, r7):\n'
        '    r = [0] * 16\n'
        '    r[4], r[5], r[6], r[7] = r4 & 0xFFFFFFFF, r5 & 0xFFFFFFFF, r6 & 0xFFFFFFFF, r7 & 0xFFFFFFFF\n'
        '    T = 0; Q = 0; M = 0; mach = 0; macl = 0; pr = 0xEEEE0000\n'
        '    ns = {"r": r, "T": T, "Q": Q, "M": M, "mach": mach, "macl": macl, "pr": pr,\n'
        '          "s8": s8, "s16": s16, "s32": s32}\n'
        '%s\n'
        '    return ns["r"][0] & 0xFFFFFFFF\n\n'
        'def run(cpu, a, b, c_, d):\n'
        '    # run at the original ROM entry; overlay a synthetic rts(0x000B)+nop\n'
        '    # right after the pure span so PC-relative literal pools stay intact.\n'
        '    # pr defaults to SENT -> emulator returns r0.\n'
        '    end = ENTRY + len(RAW)\n'
        '    ram = {end: 0x00, end + 1: 0x0B, end + 2: 0x00, end + 3: 0x09}\n'
        '    return cpu.call(ENTRY, r4=a, r5=b, r6=c_, r7=d, ram=ram)\n\n'
        'def main():\n'
        '    rnd = random.Random(SEED)\n'
        '    cpu = SH2(open(ROM, "rb").read())\n'
        '    for _ in range(N):\n'
        '        a = rnd.randint(0, 0xFFFFFFFF)\n'
        '        b = rnd.randint(0, 0xFFFFFFFF)\n'
        '        c_ = rnd.randint(0, 0xFFFFFFFF)\n'
        '        d = rnd.randint(0, 0xFFFFFFFF)\n'
        '        exp = spec_mirror(a, b, c_, d)\n'
        '        got = run(cpu, a, b, c_, d)\n'
        '        if got != exp:\n'
        '            print("MISMATCH args=(%%08X %%08X %%08X %%08X) mirror=%%08X emu=%%08X" %% (a,b,c_,d,exp,got))\n'
        '            sys.exit(1)\n'
        '    print("PASS 2000/2000")\n\n'
        'if __name__ == "__main__":\n'
        '    main()\n'
    ) % (fn, addr, size, N_CASES, fn, addr, addr, flat, seed, '\n'.join(py_stmts).rstrip())

    with open(out_t, 'w') as f:
        f.write(test)


def compute_stats():
    """unique lift addrs from existing c/*.c banners + catalog totals."""
    unique = set()
    for p in glob.glob(os.path.join(ROOT, 'c', '*.c')):
        try:
            with open(p) as f:
                head = f.read(4000)
        except OSError:
            continue
        for m in re.finditer(r'Address:\s*0x([0-9A-Fa-f]+)', head):
            unique.add(int(m.group(1), 16))
            break  # one banner per file
    total = sum(
        1 for row in csv.DictReader(open(os.path.join(ROOT, 'symbols', 'CATALOG_MASTER.csv')))
        if (row.get('flag') or '').strip() != 'NOISE'
    )
    of_classified = sum(1 for _ in csv.DictReader(
        open(os.path.join(ROOT, 'symbols', 'FUNCTION_CATEGORIES.csv'))))
    pct = 100.0 * len(unique) / total if total else 0.0
    return len(unique), total, of_classified, pct


def main():
    ap = argparse.ArgumentParser(description='Generate C lifts for pure SH-2 functions')
    ap.add_argument('--category', default=None, help='filter by FUNCTION_CATEGORIES category')
    ap.add_argument('--n', type=int, default=1, help='number of functions to lift')
    ap.add_argument('--seed', type=int, default=0, help='RNG seed (deterministic)')
    ap.add_argument('--addr', default=None, help='lift only this addr (hex, e.g. 0x1234)')
    ap.add_argument('--stats', action='store_true', help='print lift stats and exit')
    ap.add_argument('--rom', default=os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin'))
    args = ap.parse_args()

    if args.stats:
        n, total, ofc, pct = compute_stats()
        print('unique_lift_addrs=%d total=%d pct=%.2f' % (n, total, pct))
        print('of_classified=%d' % ofc)
        return

    rom = open(args.rom, 'rb').read()
    catalog = load_catalog_end(os.path.join(ROOT, 'symbols', 'CATALOG_MASTER.csv'))
    categories = load_categories(os.path.join(ROOT, 'symbols', 'FUNCTION_CATEGORIES.csv'))

    if args.addr is not None:
        addr = int(args.addr, 16)
        cands = [c for c in categories if c['addr'] == addr]
        if not cands:
            print('error: addr 0x%X not in FUNCTION_CATEGORIES.csv' % addr)
            sys.exit(2)
    else:
        cands = categories
        if args.category:
            cands = [c for c in cands if c['category'] == args.category]

    # decode + purity + length filter, keep stable (size) order for selection
    pool = []
    for c in cands:
        span = decode_pure_span(rom, c['addr'], catalog.get(c['addr']))
        if not span:
            continue
        size = span[-1][0] + 2 - c['addr']
        if not (MIN_LEN <= size <= MAX_LEN):
            continue
        pool.append({'g': c, 'size': size, 'span': span})

    pool.sort(key=lambda x: x['size'])            # stable
    rnd = random.Random(args.seed)

    emitted = 0
    skipped = 0
    for hit in rnd.sample(pool, min(args.n, len(pool))):
        c = hit['g']
        size = hit['size']
        span = hit['span']
        base = sanitize(c['name'])
        lf = '%s_%x' % (base, c['addr'])
        out_c = os.path.join(ROOT, 'c', lf + '.c')
        out_t = os.path.join(ROOT, 'c', 'tests', 'test_' + lf + '.py')

        # dedup: skip if c/<name>_<addr>.c already exists or addr already lifted
        if os.path.exists(out_c) or os.path.exists(out_t):
            skipped += 1
            continue
        if glob.glob(os.path.join(ROOT, 'c', '*_%x.c' % c['addr'])):
            skipped += 1
            continue

        emit(c['addr'], c['name'], size, span, rom, args.seed, out_c, out_t)
        emitted += 1
        print('lifted 0x%X %-40s size=%3d -> %s' % (c['addr'], c['name'], size, out_c))

    print('emitted=%d skipped_dedup=%d pool=%d' % (emitted, skipped, len(pool)))


if __name__ == '__main__':
    main()