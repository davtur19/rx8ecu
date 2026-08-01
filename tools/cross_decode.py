#!/usr/bin/env python3
"""
cross_decode.py — cross-check the repo SH-2E decode chain against an
INDEPENDENT disassembler.

Repo decode chain (as used by tools/rom_rebuild.py):
    capstone (CS_ARCH_SH, CS_MODE_SH2 | CS_MODE_BIG_ENDIAN) primary,
    tools/disasm_sh2e.py (disasm_one) fallback for words capstone skips.

Independent decoder:
    sh-elf-objdump (binutils). Preferred: tools/toolchain/usr/bin/sh-elf-objdump;
    fallback: system `objdump -m sh2e` (or `-m sh`); fallback: llvm-objdump.

    HONESTY NOTE: binutils objdump belongs to the SAME GNU toolchain family as
    sh-elf-as (already used by rom_rebuild), so it is a SEPARATE decoder from
    capstone/disasm_sh2e.py but NOT a fully independent implementation. This is
    a useful cross-check, not an independent oracle.

Method:
  * For each word offset in [start, end) step 2: decode with the repo chain.
  * Run objdump -D -b binary -m sh2e -EB over the same byte range, parse its
    per-address output, and compare the two decodes word by word.
  * Normalize: lowercase, collapse whitespace, strip objdump '! ann' / repo
    '; ann' comments, and map known syntax aliases:
        fmov.s  == fmov      (binutils prints plain `fmov` for SH-2E single)
        bf.s    == bf/s
        bt.s    == bt/s
    A second, stricter reconciliation converts hex immediates/displacements to
    decimal so `#0x0A` == `#10` and `@(0x10,rn)` == `@(16,rn)`.
  * Classification per word:
        match              both decoders produced equal (normalized) text
        mismatch           both decoders produced a real instruction that differs
        objdump_gap        repo decodes an instruction objdump emits as `.word`
        repo_gap           objdump decodes a word the repo chain cannot
        both_undecoded     neither side decodes it (data)
  * Concordance % = match / (match + mismatch) computed over words BOTH sides
    decoded. Coverage gaps are reported separately, NOT silently folded in.

Usage:
  python tools/cross_decode.py --bin roms/stock/60E1D400.bin \
      --start 0x800 --end 0x60000 --sample 0x100
  python tools/cross_decode.py --start 0x13C2C --end 0x13CFC --full
  python tools/cross_decode.py --mismatches-only
"""

import argparse
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS_DIR)
import disasm_sh2e as SH2E

import capstone as C

# capstone engine used for the repo decode chain (module-level so it can be
# imported by other tools); main() re-creates it for CLI runs.
md = C.Cs(C.CS_ARCH_SH, C.CS_MODE_SH2 | C.CS_MODE_BIG_ENDIAN)
md.skipdata = True

# Known binutils-vs-repo syntax aliases (both directions valid).
ALIAS = {'fmov.s': 'fmov', 'bf.s': 'bf/s', 'bt.s': 'bt/s'}


def norm(s):
    """Trivial normalization: lowercase, collapse whitespace, strip comments."""
    if ';' in s:            # repo annotation " ; 0x...."
        s = s.split(';')[0]
    if '\t' in s:           # objdump annotation "\t! 0x...."
        s = s.split('\t')[0]
    s = s.lower()
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def dec_imm(m):
    """Replace hex immediate/displacement forms with decimal equivalents."""
    def rep(mm):
        v = int(mm.group(1), 16)
        return '#' + str(v)
    def rep2(mm):
        return '@(' + str(int(mm.group(1), 16)) + ','
    s = m
    s = re.sub(r'#0x([0-9a-f]+)', rep, s)
    s = re.sub(r'@\(0x([0-9a-f]+),', rep2, s)
    s = re.sub(r'0x([0-9a-f]+)', lambda mm: str(int(mm.group(1), 16)), s)
    return s


def find_objdump(args):
    """Locate an objdump that can disassemble SH-2E big-endian. Returns (path, -m flag)."""
    cands = [args.objdump] if args.objdump else []
    cands += [
        os.path.join(TOOLS_DIR, 'toolchain/usr/bin/sh-elf-objdump'),
        os.path.join(TOOLS_DIR, '../tools/toolchain/usr/bin/sh-elf-objdump'),
        'sh-elf-objdump',
        'objdump',
        'llvm-objdump',
    ]
    seen = set()
    for c in cands:
        if not c or c in seen:
            continue
        seen.add(c)
        try:
            v = subprocess.run([c, '--version'], capture_output=True, text=True, timeout=10)
        except FileNotFoundError:
            continue
        if v.returncode != 0:
            continue
        arch = subprocess.run([c, '-i'], capture_output=True, text=True, timeout=10)
        if 'sh' not in (arch.stdout + arch.stderr).lower() and 'llvm' not in c.lower():
            continue
        # find best -m flag: sh2e > sh2 > sh
        probe = os.path.join(tempfile.gettempdir(), 'xd_probe.bin')
        open(probe, 'wb').write(b'\xff\xfb')
        if 'llvm-objdump' in c:
            os.unlink(probe)
            continue  # llvm-objdump SH support is generally absent; leave last-resort message
        for flag in ('sh2e', 'sh2', 'sh'):
            r = subprocess.run([c, '-D', '-b', 'binary', '-m', flag, '-EB',
                                '--start-address=0', '--stop-address=2', probe],
                               capture_output=True, text=True, timeout=15)
            if r.returncode == 0:
                os.unlink(probe)
                return c, flag, v.stdout.splitlines()[0].strip()
        os.unlink(probe)
        # GNU objdump supports -m sh with arch variants; sh2e is the closest to SH-2E
        return c, 'sh2e', v.stdout.splitlines()[0].strip()
    return None, None, None


def decode_repo_chain(d, a):
    """Return (src, mnemonic, operands) using rom_rebuild's chain (capstone->disasm_sh2e)."""
    w = int.from_bytes(d[a:a + 2], 'big')
    ins = next(md.disasm(d[a:a + 2], a), None)
    if ins is not None and ins.id != 0:
        return 'capstone', ins.mnemonic, ins.op_str
    mne, ops, _ = SH2E.disasm_one(w, a)
    if mne in ('unknown', 'fpu_unknown'):
        return None, None, None
    return 'disasm_sh2e', mne, ops


def parse_objdump(out):
    """Parse objdump -D -b binary -m sh2e -EB output -> {addr: (mne, ops)}."""
    res = {}
    for ln in out.splitlines():
        m = re.match(r'\s*([0-9a-f]+):', ln)
        if not m:
            continue
        a = int(m.group(1), 16)
        parts = ln.split('\t')
        if len(parts) < 3:
            continue
        mne = parts[2].strip()
        ops = ''
        if mne.startswith('.word'):
            mne = '.word'            # objdump could not decode; no operand field
        elif len(parts) >= 4:
            ops = parts[3].strip()
            if '\t' in ops:          # annotation is tab-separated after operands
                ops = ops.split('\t')[0]
        res[a] = (mne, ops)
    return res


def main():
    ap = argparse.ArgumentParser(description='cross-check repo SH-2E decoder vs sh-elf-objdump')
    ap.add_argument('--bin', default='roms/stock/60E1D400.bin')
    ap.add_argument('--start', type=lambda x: int(x, 0), default=0x0)
    ap.add_argument('--end', type=lambda x: int(x, 0), default=0x80000)
    ap.add_argument('--step', type=lambda x: int(x, 0), default=2, help='byte step between collected words (even)')
    ap.add_argument('--sample', type=lambda x: int(x, 0), default=0x100,
                    help='compare every Nth word; --full sets this to 1')
    ap.add_argument('--full', action='store_true', help='compare every word in range')
    ap.add_argument('--mismatches-only', action='store_true')
    ap.add_argument('--max-examples', type=int, default=5)
    ap.add_argument('--objdump', default=None, help='override objdump path')
    args = ap.parse_args()

    if args.step % 2:
        sys.exit('--step must be even (SH instructions are 2 bytes)')

    d = open(args.bin, 'rb').read()
    N = len(d)
    end = min(args.end, N)
    if args.end > N:
        print(f'# note: --end 0x{args.end:X} > file size 0x{N:X}; clamped to 0x{N:X}')
    sample = 1 if args.full else args.sample
    global md
    md = C.Cs(C.CS_ARCH_SH, C.CS_MODE_SH2 | C.CS_MODE_BIG_ENDIAN)
    md.skipdata = True

    # --- 1. independent decoder discovery --------------------------------
    od_path, od_flag, od_ver = find_objdump(args)
    if od_path is None:
        sys.exit('no independent SH decoder found (tried tools/toolchain, sh-elf-objdump, objdump, llvm-objdump)')
    print(f'# independent decoder: {od_path}')
    print(f'#   version: {od_ver}')
    print(f'#   flag: -m {od_flag}  (big-endian, binary input)')
    if 'toolchain' in od_path or od_path.endswith('sh-elf-objdump'):
        print('#   source: GNU binutils SH toolchain')
    if 'llvm-objdump' in od_path:
        print('#   source: LLVM objdump')
    print('# HONESTY NOTE: binutils objdump is the same GNU toolchain family as '
          'sh-elf-as used by rom_rebuild, but it is a SEPARATE decoder from '
          'capstone/disasm_sh2e.py — a useful but NOT fully independent cross-check.')
    print(f'# syntax aliases normalised as identical: fmov.s==fmov, bf.s==bf/s, bt.s==bt/s')

    # --- 2. run objdump over the range ------------------------------------
    r = subprocess.run([od_path, '-D', '-b', 'binary', '-m', od_flag, '-EB',
                        '--start-address=%d' % args.start,
                        '--stop-address=%d' % end, args.bin],
                       capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        sys.exit('objdump failed: ' + r.stderr[-500:])
    od = parse_objdump(r.stdout)
    print(f'# objdump decoded {len(od)} word lines in range 0x{args.start:X}..0x{end:X}')

    # --- 3. compare ---------------------------------------------------------
    stats = Counter()
    mismatches = []
    visited = 0
    n_compared = 0
    for a in range(args.start, end, args.step):
        visited += 1
        if visited % sample != 0:
            continue
        n_compared += 1
        src, rm, ro = decode_repo_chain(d, a)
        odv = od.get(a)
        if src is None and (not odv or odv[0] == '.word'):
            stats['both_undecoded'] += 1
            continue
        if not odv or odv[0] == '.word':
            stats['objdump_gap_repo_decoded'] += 1
            continue
        if src is None:
            stats['repo_gap_objdump_decoded'] += 1
            continue
        om, oo = odv
        rn, on = ALIAS.get(rm, rm), ALIAS.get(om, om)
        if norm(rn) == norm(on) and norm(ro) == norm(oo):
            stats['match'] += 1
            continue
        # stricter: compare with alias AND hex->decimal operand form
        if norm(rn) == norm(on) and dec_imm(norm(ro)) == dec_imm(norm(oo)):
            stats['match_fmt_only'] += 1
            continue
        stats['mismatch'] += 1
        mismatches.append((a, src, rm, ro, om, oo))

    # --- 4. report -----------------------------------------------------------
    tot_decoded = stats['match'] + stats['match_fmt_only'] + stats['mismatch']
    pct = 100.0 * (stats['match'] + stats['match_fmt_only']) / tot_decoded if tot_decoded else 0.0
    print()
    print('=' * 72)
    print('CROSS-DECODE REPORT')
    print(f'  bin            : {args.bin}  (size 0x{N:X})')
    print(f'  range          : 0x{args.start:X}..0x{end:X}  (step={args.step}, sample=1/{sample} words)')
    print(f'  repo chain     : capstone(SH2,BE) primary + disasm_sh2e.py fallback (== rom_rebuild)')
    print(f'  compared       : {n_compared} words (of {visited} visited)')
    print(f'  both decoded   : {tot_decoded} words')
    print(f'    exact match  : {stats["match"]}  (+{stats["match_fmt_only"]} after hex->decimal operand normalization)')
    print(f'    MISMATCH     : {stats["mismatch"]}')
    print(f'  concordance    : {pct:.2f}%  ({stats["match"] + stats["match_fmt_only"]}/{tot_decoded})')
    print(f'  objdump gap    : {stats["objdump_gap_repo_decoded"]}  (repo decodes, objdump emits .word)')
    print(f'  repo gap       : {stats["repo_gap_objdump_decoded"]}  (objdump decodes, repo cannot)')
    print(f'  both undecoded : {stats["both_undecoded"]}  (data words)')
    print('=' * 72)
    if stats['mismatch'] == 0:
        print('RESULT: no genuine decode mismatches found in sampled words.')
    else:
        print(f'RESULT: {stats["mismatch"]} mismatches; first {args.max_examples}:')
        for a, src, rm, ro, om, oo in mismatches[:args.max_examples]:
            print(f'  0x{a:05X} [{src}] repo={rm:10s} {ro:28s} | objdump={om:10s} {oo}')
    if args.mismatches_only:
        for a, src, rm, ro, om, oo in mismatches:
            print(f'0x{a:05X} [{src}] repo={rm} {ro} | objdump={om} {oo}')


if __name__ == '__main__':
    main()
