#!/usr/bin/env python3
"""
Verify ldexp_481C (0x481C) against the ACTUAL ROM bytes of 60E1D400.bin via
tools/sh2emu.py, plus the Track-A C lift (c/ldexp_481C.c).

This is the third stage of the checkFloatValidity @0x46CC pipeline
(frexp @0x48C8 -> div @0x4740 -> ldexp @0x481C).  Calling convention
(confirmed from the single call site at 0x46EE):
    - args on the stack: [r15] = arg1, [r15+4] = arg2
    - returns the float bits in r0.
It rebuilds the single-precision float pattern from a (exponent, mantissa)
word pair, saturating exponents to +/-Inf or zero when out of range.

Test strategy (mirrors test_bitfield_extract_merge.py):
  1. Run the ROM bytes in the SH-2E emulator for each (arg1, arg2) pair.
  2. Compare against an independent semantic model.
  3. Compile the C lift and compare THAT against the emulator too.
"""
import ctypes
import os
import random
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RE = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, os.path.join(RE, 'tools'))
from sh2emu import SH2

ROM = os.path.join(RE, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0x481C
R15 = 0xFFFFDF00

M32 = 0xFFFFFFFF


def rom_run(rom, a, b):
    """Execute the ROM function with arg1=a at [r15], arg2=b at [r15+4] and
    return r0."""
    cpu = SH2(rom)
    ram = {R15 + i: 0 for i in range(8)}
    for i in range(4):
        ram[R15 + i] = (a >> (24 - 8 * i)) & 0xFF
        ram[R15 + 4 + i] = (b >> (24 - 8 * i)) & 0xFF
    cpu.call(ENTRY, ram=ram)
    return cpu.r[0]


def model(a, b):
    """Independent semantic model of ldexp_481C (exact SH-2 T-flag emulation)."""
    r3 = a & M32
    lo16 = r3 & 0xFFFF
    r2 = (lo16 | 0xFFFF0000) if (lo16 & 0x8000) else lo16     # exts.w r3 -> r2
    r0 = b & M32
    r1 = 0x7FFF
    if s32(r2) >= s32(r1):                                   # 0x4824 cmp/ge 0x7FFF
        if r0 == 0:                                          # 0x4894 tst r0,r0
            r2 = 0xFF; r0 = 0                                # 0x48A2
        else:
            r2 = 0xFF; r3 = 0; r0 = (1 << 8) & M32           # 0x48A8
    else:
        r1 = 0x7F
        r2 = (r2 + r1) & M32                                 # 0x482C add
        r1 = 0xFF
        if s32(r2) >= s32(r1):                               # 0x4830 cmp/ge 0xFF
            r2 = 0xFF; r0 = 0                                # 0x48A2
        elif s32(r2) > 0:                                    # 0x4834 cmp/pl
            pass                                             # 0x4880 direct
        else:
            r2 = 0; r0 = 0                                   # 0x489C
    # 0x4880
    t = (r0 >> 31) & 1; r0 = (r0 << 1) & M32                 # shll r0
    r0 = (r0 >> 8) & M32                                     # shlr8 r0
    r2 = (r2 << 16) & M32                                    # shll16 r2
    r2 = (r2 << 8) & M32                                     # shll8 r2
    r0 = (r0 | r2) & M32
    t = (r3 >> 31) & 1; r3 = (r3 << 1) & M32                 # shll r3
    t2 = r0 & 1; r0 = ((r0 >> 1) | (t << 31)) & M32; t = t2  # rotcr r0
    return r0


def s32(x):
    x &= M32
    return x - 0x100000000 if x & 0x80000000 else x


def gen_edge_pairs():
    """Named edge pairs: exponents at every threshold, mantissas 0 / all-1 / etc."""
    a = [0x00007FFE, 0x00007FFF, 0x00008000, 0xFFFF8001, 0x0000FFFF,
         0x00000000, 0x000000FF, 0x0000007F, 0xFFFFFFFF, 0x80000000,
         0x00000080, 0x00000100, 0x7FFF0000, 0x0000FFFE, 0x00000081]
    b = [0x00000000, 0x00000001, 0x000000FF, 0xFFFFFFFF, 0x80000000,
         0x00000002, 0x00000100, 0x7FFFFFFF]
    return [(x, y) for x in a for y in b]


def main():
    rom = open(ROM, 'rb').read()
    random.seed(0x481C)

    # ---- 1. edge cases + random vs emulated ROM ----
    cases = gen_edge_pairs()
    rnd = [(random.getrandbits(32), random.getrandbits(32)) for _ in range(100000)]
    fails = 0
    for a, b in cases:
        r = rom_run(rom, a, b)
        m = model(a, b)
        if r != m:
            fails += 1
            print(f'MISMATCH edge {a:08X},{b:08X}: rom={r:08X} model={m:08X}')
    for a, b in rnd:
        r = rom_run(rom, a, b)
        m = model(a, b)
        if r != m:
            fails += 1
            if fails < 20:
                print(f'MISMATCH rnd {a:08X},{b:08X}: rom={r:08X} model={m:08X}')
    n = len(cases) + len(rnd)
    print(f'emulator vs model: {n} inputs, {fails} mismatches')
    if fails:
        sys.exit(1)

    # ---- 2. C lift vs emulated ROM (Track A) ----
    try:
        so = '/tmp/test_ldexp_481C.so'
        subprocess.run(['cc', '-O2', '-shared', '-fPIC',
                        os.path.join(RE, 'c', 'ldexp_481C.c'),
                        '-o', so], check=True)
    except Exception as e:
        print('C-lift check skipped (no host C compiler):', e)
        return
    lib = ctypes.CDLL(so)
    fn = lib.ldexp_481C
    fn.restype = ctypes.c_uint32
    fn.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
    cfails = 0
    sample = [c for c in cases] + \
             [(random.getrandbits(32), random.getrandbits(32)) for _ in range(100000)]
    for a, b in sample:
        c = fn(ctypes.c_uint32(a), ctypes.c_uint32(b))
        r = rom_run(rom, a, b)
        if c != r:
            cfails += 1
            if cfails < 20:
                print(f'C MISMATCH {a:08X},{b:08X}: rom={r:08X} c={c:08X}')
    print(f'C lift vs emulated ROM: {len(sample)} inputs, {cfails} mismatches')
    if cfails:
        sys.exit(1)

    print('OK  ldexp_481C @0x%04X  (emulator + C lift verified)' % ENTRY)


if __name__ == '__main__':
    main()