#!/usr/bin/env python3
"""
rom2asm.py — disassemble an SH-2 (big-endian) ROM range into a *reassemblable*
GNU-as source file, and (optionally) prove the round-trip is byte-exact.

This is the core of the "asm-first" baseline: turn the read-only disassembly view
into buildable `.s` source that `sh-elf-as` re-assembles into the identical bytes.
From there, functions are lifted to C one at a time (Track A) without ever losing
the ability to rebuild the ROM.

Method
------
1. Fix-point pass: linearly decode the range; every PC-relative load target
   (`mov.l/@(disp,pc)`, `mov.w/@(disp,pc)`, `mova`) is a literal-pool entry, i.e.
   DATA. Re-run until the data set is stable so pools are never mis-decoded as code.
2. Emit pass: walk the range; emit `.long/.word` for pool/data addresses, real
   instructions otherwise. Branch and pool operands are rewritten to symbolic
   labels (`L_xxxxxx`) so the assembler recomputes displacements from layout.
3. Verify: sh-elf-as -big | sh-elf-ld -Ttext=<start> | objcopy -O binary -j .text,
   then compare against ROM[start:end].

Limitations (by design, resolved at whole-program scale)
--------------------------------------------------------
* Isolated slices whose branches/pools point OUTSIDE the slice fail to assemble:
  SH short branches (8/12-bit) cannot target undefined externals. Assemble the
  whole `.text` as one unit (all labels present) so ranges stay original.
* Code/data classification here only recovers *literal pools* (PC-relative refs).
  Jump tables and computed-address data must come from the Ghidra/IDA map
  (the shipped symbol CSVs in symbols/, e.g. symbols/symbols_60E1D400_merged.csv)
  when scaling to the full ROM.

Requires: capstone>=5.0 (SH support) and sh-elf binutils on PATH
          (see tools/get_toolchain.sh).

Examples
--------
  python rom2asm.py roms/stock/60E1D400.bin 0x2460 0x2478 --verify
  python rom2asm.py roms/stock/60E1D400.bin 0x23b0 0x2478 -o out.s
"""
import argparse, re, subprocess, sys

try:
    import capstone as C
except ImportError:
    sys.exit("capstone not installed: pip install capstone --break-system-packages")

PCREL = {'mov.l': 4, 'mov.w': 2, 'mova': 4}   # pc-relative load -> pool entry size
BR = {'bra', 'bsr', 'bt', 'bf', 'bt/s', 'bf/s'}


def _target(op_str):
    m = re.search(r'0x([0-9a-fA-F]+)', op_str)
    return int(m.group(1), 16) if m else None


def export(d, start, end):
    """Return (asm_text, data_map, external_targets)."""
    md = C.Cs(C.CS_ARCH_SH, C.CS_MODE_SH2 | C.CS_MODE_BIG_ENDIAN)

    def dec1(a):
        g = list(md.disasm(d[a:a + 2], a))
        return g[0] if g else None

    # 1. fix-point: locate literal pools
    data = {}
    for _ in range(8):
        a, nd = start, {}
        while a < end:
            if a in data:
                a += data[a]; continue
            i = dec1(a)
            if i and i.mnemonic in PCREL:
                t = _target(i.op_str)
                if t is not None and start <= t < end:
                    nd[t] = PCREL[i.mnemonic]
            a += 2
        if nd == data:
            break
        data = nd

    # 2. collect labels / externals
    labels, ext = set(data), set()
    a = start
    while a < end:
        if a in data:
            a += data[a]; continue
        i = dec1(a)
        if i and (i.mnemonic in BR or i.mnemonic in PCREL):
            t = _target(i.op_str)
            if t is not None:
                labels.add(t)
                if not (start <= t < end):
                    ext.add(t)
        a += 2

    # 3. emit
    out = ['\t.global L_%06x' % t for t in sorted(ext)] + ['\t.text']
    a = start
    while a < end:
        if a in labels:
            out.append('L_%06x:' % a)
        if a in data:
            sz = data[a]; v = int.from_bytes(d[a:a + sz], 'big')
            out.append('\t.long 0x%08x' % v if sz == 4 else '\t.word 0x%04x' % v)
            a += sz; continue
        i = dec1(a)
        if not i:                       # undecodable -> preserve as data word
            out.append('\t.word 0x%04x' % int.from_bytes(d[a:a + 2], 'big'))
            a += 2; continue
        op = i.op_str
        if i.mnemonic in PCREL or i.mnemonic in BR:
            t = _target(op)
            if t is not None:
                op = re.sub(r'0x[0-9a-fA-F]+', 'L_%06x' % t, op, count=1)
        out.append(('\t%s %s' % (i.mnemonic, op)).rstrip())
        a += 2
    return '\n'.join(out) + '\n', data, ext


def verify(d, start, end, asm_path):
    """Assemble+link+extract and compare to ROM[start:end]. Returns (ok, msg)."""
    steps = [
        (['sh-elf-as', '-big', asm_path, '-o', asm_path + '.o'], 'as'),
        (['sh-elf-ld', '-Ttext=0x%x' % start, '-e', '0x%x' % start]
         + ['-o', asm_path + '.elf', asm_path + '.o'], 'ld'),
        (['sh-elf-objcopy', '-O', 'binary', '-j', '.text',
          asm_path + '.elf', asm_path + '.bin'], 'objcopy'),
    ]
    for cmd, tag in steps:
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode:
            return False, '%s error: %s' % (tag, r.stderr.strip()[:400])
    got = open(asm_path + '.bin', 'rb').read()
    orig = d[start:end]
    if got == orig:
        return True, 'MATCH %d bytes' % len(orig)
    diffs = [k for k in range(min(len(got), len(orig))) if got[k] != orig[k]]
    if diffs:
        k = diffs[0]
        return False, 'first diff @0x%x built=%02x orig=%02x (%d diff bytes)' % (
            start + k, got[k], orig[k], len(diffs))
    return False, 'length mismatch built=%d orig=%d' % (len(got), len(orig))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom')
    ap.add_argument('start', type=lambda x: int(x, 0))
    ap.add_argument('end', type=lambda x: int(x, 0))
    ap.add_argument('-o', '--out', help='write .s here (default: stdout)')
    ap.add_argument('--verify', action='store_true',
                    help='assemble+link+cmp against the ROM (needs sh-elf binutils)')
    a = ap.parse_args()
    d = open(a.rom, 'rb').read()
    asm, data, ext = export(d, a.start, a.end)
    path = a.out or '/tmp/_rom2asm.s'
    open(path, 'w').write(asm)
    if not a.out and not a.verify:
        sys.stdout.write(asm)
    sys.stderr.write('range 0x%x..0x%x  pools=%d externals=%d\n'
                     % (a.start, a.end, len(data), len(ext)))
    if a.verify:
        ok, msg = verify(d, a.start, a.end, path)
        print(('[OK] ' if ok else '[FAIL] ') + msg)
        sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
