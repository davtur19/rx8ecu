#!/usr/bin/env python3
"""
Verify div_4740 (0x4740) against the ACTUAL ROM bytes of 60E1D400.bin via
tools/sh2emu.py, plus the Track-A C lift (c/div_4740.c).

This is the second stage of the checkFloatValidity @0x46CC pipeline
(frexp @0x48C8 -> div @0x4740 -> ldexp @0x481C).  Calling convention
(confirmed from the single call site at 0x46E4):
    - args on the stack: [r15+4] = arg1, [r15+8] = arg2
    - result pointer at [r15]; writes r3 (extu.w, 16-bit) to [ptr]
      and r1 (32-bit) to [ptr+4].
It runs a 64-by-32 restoring (shift-subtract) division with the exact
SH-2 T-flag semantics (including cmp/pl r6 feeding the loop-top rotcl r0).

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
ENTRY = 0x4740
R15 = 0xFFFFDF00      # stack pointer used by sh2emu.call()
PTR = 0xFFFFDF80      # result buffer in emulator RAM

M32 = 0xFFFFFFFF


def rom_run(rom, a, b):
    """Execute the ROM function with arg1=a, arg2=b on the stack and return
    (hi, lo) written through the caller-supplied pointer at [r15]."""
    cpu = SH2(rom)
    ram = {R15 + i: 0 for i in range(12)}
    ram.update({PTR + i: 0xEE for i in range(8)})       # poison the buffer
    for i in range(4):
        ram[R15 + 4 + i] = (a >> (24 - 8 * i)) & 0xFF   # [r15+4] = arg1
        ram[R15 + 8 + i] = (b >> (24 - 8 * i)) & 0xFF   # [r15+8] = arg2
    for i in range(4):
        ram[R15 + i] = (PTR >> (24 - 8 * i)) & 0xFF     # [r15] = result ptr
    cpu.call(ENTRY, ram=ram)
    hi = int.from_bytes(bytes(cpu.rd(PTR + i, 1) for i in range(4)), 'big')
    lo = int.from_bytes(bytes(cpu.rd(PTR + 4 + i, 1) for i in range(4)), 'big')
    return hi, lo


def model(a, b):
    """Independent semantic model of div_4740 (exact SH-2 T-flag emulation)."""
    r0 = 0; r1 = 0; r2 = b & M32; r4 = a & M32; r5 = 0; r6 = 0; r7 = 0
    lo16 = r4 & 0xFFFF
    r3 = (lo16 | 0xFFFF0000) if (lo16 & 0x8000) else lo16     # exts.w r4 -> r3
    r5 = 0xFFFF8001
    if s32(r5) >= s32(r3):                                   # 0x47F8
        r3 = 0x8001
        t = (r3 >> 31) & 1; r3 = (r3 << 1) & M32             # shll r3
        t = (r4 >> 31) & 1; r4 = (r4 << 1) & M32             # shll r4
        t2 = r3 & 1; r3 = ((r3 >> 1) | (t << 31)) & M32; t = t2  # rotcr r3
        r1 = 0
        return r3 & M32, r1 & M32
    t = (r4 >> 31) & 1; r4 = (r4 << 1) & M32                 # shll r4
    if t:
        return 0x7FFF, 0xFFFFFFFF                            # 0x480C
    r5 = 0x7FFF
    if s32(r3) >= s32(r5):                                   # 0x47F0
        if r2 == 0:
            return 0x7FFF, 0
        return 0x7FFF, 0xFFFFFFFF
    r5 = 0; r1 = 0; r0 = 0; r6 = 29
    t = r3 & 1; r3 = (r3 >> 1) & M32                         # shlr r3
    if t:
        t = (r2 >> 31) & 1; r2 = (r2 << 1) & M32
        t2 = (r5 >> 31) & 1; r5 = ((r5 << 1) | t) & M32; t = t2
    t = (r2 >> 31) & 1; r2 = (r2 << 1) & M32
    t2 = (r5 >> 31) & 1; r5 = ((r5 << 1) | t) & M32; t = t2
    t = 1
    while True:                                             # 0x476C
        t2 = (r0 >> 31) & 1; r0 = ((r0 << 1) | t) & M32; t = t2  # rotcl r0
        t = 1 if r5 >= r0 else 0                            # cmp/hs r0,r5
        if t:
            t2 = (r1 >> 31) & 1; r1 = ((r1 << 1) | t) & M32; t = t2  # rotcl r1
            r5 = (r5 - r0) & M32
            r0 = (r0 + 1) & M32                             # delay of bra
        else:
            r0 = (r0 ^ 1) & M32
            t2 = (r1 >> 31) & 1; r1 = ((r1 << 1) | t) & M32; t = t2  # rotcl r1
        t = (r2 >> 31) & 1; r2 = (r2 << 1) & M32            # shll r2
        t2 = (r5 >> 31) & 1; r5 = ((r5 << 1) | t) & M32; t = t2  # rotcl r5
        t = (r2 >> 31) & 1; r2 = (r2 << 1) & M32            # shll r2
        t2 = (r5 >> 31) & 1; r5 = ((r5 << 1) | t) & M32; t = t2  # rotcl r5
        r6 = (r6 - 1) & M32
        t = 1 if s32(r6) > 0 else 0                         # cmp/pl r6
        if t:
            continue
        break
    # ---- restore phase ----
    r6 = 0; r7 = 0; t = 1
    t2 = (r0 >> 31) & 1; r0 = ((r0 << 1) | t) & M32; t = t2  # rotcl r0
    t = 1 if r5 >= r0 else 0                                # cmp/hs
    if t:
        t2 = (r1 >> 31) & 1; r1 = ((r1 << 1) | t) & M32; t = t2
        r5 = (r5 - r0) & M32
        r0 = (r0 + 1) & M32
    else:
        r0 = (r0 ^ 1) & M32
        t2 = (r1 >> 31) & 1; r1 = ((r1 << 1) | t) & M32; t = t2
    t = (r2 >> 31) & 1; r2 = (r2 << 1) & M32                 # 0x47A4
    t2 = (r5 >> 31) & 1; r5 = ((r5 << 1) | t) & M32; t = t2
    t2 = (r6 >> 31) & 1; r6 = ((r6 << 1) | t) & M32; t = t2
    t = (r2 >> 31) & 1; r2 = (r2 << 1) & M32
    t2 = (r5 >> 31) & 1; r5 = ((r5 << 1) | t) & M32; t = t2
    t2 = (r6 >> 31) & 1; r6 = ((r6 << 1) | t) & M32; t = t2
    t = 1
    t2 = (r0 >> 31) & 1; r0 = ((r0 << 1) | t) & M32; t = t2  # rotcl r0
    t2 = (r7 >> 31) & 1; r7 = ((r7 << 1) | t) & M32; t = t2  # rotcl r7
    t = 1 if r6 > r7 else 0                                 # cmp/hi r7,r6
    if not t:
        t = 1 if r6 >= r7 else 0                            # cmp/hs r7,r6
        if t:
            t = 1 if r5 >= r0 else 0                        # cmp/hs r0,r5
    if t:                                                   # 0x47C2
        t2 = (r1 >> 31) & 1; r1 = ((r1 << 1) | t) & M32; t = t2  # rotcl r1
        d = r5 - r0 - t                                     # subc r0,r5
        t = 1 if d < 0 else 0; r5 = d & M32
        d = r6 - r7 - t                                     # subc r7,r6
        t = 1 if d < 0 else 0; r6 = d & M32
    else:                                                   # 0x47CA
        t2 = (r1 >> 31) & 1; r1 = ((r1 << 1) | t) & M32; t = t2
    t = (r2 >> 31) & 1; r2 = (r2 << 1) & M32                 # 0x47CC
    t2 = (r5 >> 31) & 1; r5 = ((r5 << 1) | t) & M32; t = t2
    t2 = (r6 >> 31) & 1; r6 = ((r6 << 1) | t) & M32; t = t2
    t = (r2 >> 31) & 1; r2 = (r2 << 1) & M32
    t2 = (r5 >> 31) & 1; r5 = ((r5 << 1) | t) & M32; t = t2
    t2 = (r6 >> 31) & 1; r6 = ((r6 << 1) | t) & M32; t = t2
    t = (r1 >> 31) & 1; r1 = (r1 << 1) & M32                # shll r1
    if r6 != 0 or r5 != 0:
        r1 = (r1 | 1) & M32
    r3 = r3 & 0xFFFF                                        # extu.w r3
    return r3, r1


def s32(x):
    x &= M32
    return x - 0x100000000 if x & 0x80000000 else x


def gen_edge_pairs():
    """Named edge pairs covering every early-exit and the loop extremes."""
    a = [0x00000000, 0x00000001, 0x00007FFF, 0x00008000, 0x0000FFFF,
         0x00010000, 0x7FFF0000, 0x7FFFFFFF, 0x80000000, 0x80008001,
         0x8000FFFF, 0xFFFF8001, 0xFFFFFFFF]
    b = [0x00000000, 0x00000001, 0x0000FFFF, 0x00008000, 0x00007FFF,
         0x7FFFFFFF, 0x80000000, 0xFFFFFFFF, 0x00010002, 0x00FFFFFF,
         0xFF000000, 0x01000000]
    return [(x, y) for x in a for y in b]


def main():
    rom = open(ROM, 'rb').read()
    random.seed(0x4740)

    # ---- 1. edge cases + random vs emulated ROM ----
    cases = gen_edge_pairs()
    rnd = [(random.getrandbits(32), random.getrandbits(32)) for _ in range(100000)]
    fails = 0
    for a, b in cases:
        r = rom_run(rom, a, b)
        m = model(a, b)
        if r != m:
            fails += 1
            print(f'MISMATCH edge {a:08X},{b:08X}: rom={r[0]:08X},{r[1]:08X} '
                  f'model={m[0]:08X},{m[1]:08X}')
    for a, b in rnd:
        r = rom_run(rom, a, b)
        m = model(a, b)
        if r != m:
            fails += 1
            if fails < 20:
                print(f'MISMATCH rnd {a:08X},{b:08X}: rom={r[0]:08X},{r[1]:08X} '
                      f'model={m[0]:08X},{m[1]:08X}')
    n = len(cases) + len(rnd)
    print(f'emulator vs model: {n} inputs, {fails} mismatches')
    if fails:
        sys.exit(1)

    # ---- 2. C lift vs emulated ROM (Track A) ----
    try:
        so = '/tmp/test_div_4740.so'
        subprocess.run(['cc', '-O2', '-shared', '-fPIC',
                        os.path.join(RE, 'c', 'div_4740.c'),
                        '-o', so], check=True)
    except Exception as e:
        print('C-lift check skipped (no host C compiler):', e)
        return
    lib = ctypes.CDLL(so)
    fn = lib.div_4740
    fn.restype = None
    fn.argtypes = [ctypes.c_uint32, ctypes.c_uint32,
                   ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint32)]
    cfails = 0
    sample = [c for c in cases] + \
             [(random.getrandbits(32), random.getrandbits(32)) for _ in range(100000)]
    for a, b in sample:
        hi = ctypes.c_uint32(); lo = ctypes.c_uint32()
        fn(ctypes.c_uint32(a), ctypes.c_uint32(b), ctypes.byref(hi), ctypes.byref(lo))
        r = rom_run(rom, a, b)
        if (hi.value, lo.value) != r:
            cfails += 1
            if cfails < 20:
                print(f'C MISMATCH {a:08X},{b:08X}: rom={r[0]:08X},{r[1]:08X} '
                      f'c={hi.value:08X},{lo.value:08X}')
    print(f'C lift vs emulated ROM: {len(sample)} inputs, {cfails} mismatches')
    if cfails:
        sys.exit(1)

    print('OK  div_4740 @0x%04X  (emulator + C lift verified)' % ENTRY)


if __name__ == '__main__':
    main()
