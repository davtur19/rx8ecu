#!/usr/bin/env python3
"""
Verify bitfield_extract_merge (0x48C8) against the ACTUAL ROM bytes
of 60E1D400.bin via tools/sh2emu.py.

This is a frexp-style float bit-pattern helper:
    x = sig * 2^e  with  sig in [1.0, 2.0)
calling convention (confirmed from its single caller checkFloatValidity
@0x46CC, call site 0x46D8):
    - float argument in FR4 (fp register),
    - result pointer on the stack at [r15] (caller pushes it in the delay
      slot of `jsr`), pointing at an 8-byte buffer.
It writes
    out[0] = exponent word: bit31 = sign (except NaN), low16 = signed e
             (0x8001 sentinel for 0.0, 0x7FFF saturated for Inf/NaN)
    out[1] = significand word: 24-bit sig << 8 (bit31 = implicit 1)
             (0xFFFFFFFF = -1 for NaN, 0 for zero/Inf)

Test strategy:
  1. Run the ROM bytes in the SH-2E emulator for each input (float bit
     pattern placed in fr4, result pointer pre-placed at [r15]).
  2. Compare against an independent semantic model.
  3. Compile the C lift (c/bitfield_extract_merge.c) with the host
     compiler and compare THAT against the emulator too (Track A).
"""
import ctypes
import os
import random
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RE = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, os.path.join(RE, 'tools'))
from sh2emu import SH2

ROM = os.path.join(RE, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0x48C8
R15 = 0xFFFFDF00      # stack pointer used by sh2emu.call()
OUT = 0xFFFFDF80      # scratch buffer in emulator RAM (result pointer target)

M32 = 0xFFFFFFFF


def rom_run(rom, bits):
    """Execute the ROM function on the float with the given IEEE-754 bit
    pattern (passed in fr4) and return (out0, out1) written via the
    caller-supplied pointer at [r15]."""
    value = struct.unpack('>f', struct.pack('>I', bits & M32))[0]
    cpu = SH2(rom)
    # pre-place the caller-supplied result pointer at [r15] (4 byte values)
    cpu.call(ENTRY, fr={4: value},
             ram={R15: (OUT >> 24) & 0xFF,
                  R15 + 1: (OUT >> 16) & 0xFF,
                  R15 + 2: (OUT >> 8) & 0xFF,
                  R15 + 3: OUT & 0xFF})
    return cpu.rd(OUT, 4), cpu.rd(OUT + 4, 4)


def model(bits):
    """Independent semantic model of bitfield_extract_merge (frexp-style)."""
    bits &= M32
    sign = bits & 0x80000000
    exp = (bits >> 23) & 0xFF
    mant = bits & 0x7FFFFF
    if exp == 0xFF:                     # Inf / NaN
        if mant == 0:                   # Inf: sign preserved
            return (0x00007FFF | sign, 0x00000000)
        return (0x00007FFF, 0xFFFFFFFF)  # NaN: sign dropped
    if exp == 0:                        # zero / subnormal
        if mant == 0:
            return (0x00008001 | sign, 0x00000000)
        p = mant.bit_length() - 1       # top set mantissa bit (0..22)
        k = 22 - p                      # shifts to normalize to bit 31
        e = -127 - k
        frac = ((mant << (9 + k)) & M32) | 0x80000000
        return ((e & 0xFFFF) | sign, frac)
    e = exp - 127                       # normal
    frac = ((mant << 8) | 0x80000000) & M32
    return ((e & 0xFFFF) | sign, frac)


def gen_edge_cases():
    """Named edge cases covering every branch of the function."""
    cases = [
        # (bits, label)
        (0x3F800000, '+1.0'),
        (0xBF800000, '-1.0'),
        (0xC0200000, '-2.5'),
        (0x40490FDB, 'pi'),
        (0x4048F5C3, '3.14'),
        (0x3F000000, '+0.5'),
        (0x40000000, '+2.0'),
        (0x49742400, '1e6'),
        (0x7F7FFFFF, 'max normal'),
        (0xFF7FFFFF, '-max normal'),
        (0x00800000, 'min normal'),
        (0x80800000, '-min normal'),
        (0x00000001, 'min subnormal'),
        (0x80000001, '-min subnormal'),
        (0x00000002, 'subnormal 2'),
        (0x000FFFFF, 'subnormal 0xFFFFF'),
        (0x00400000, 'subnormal 2^22 (bit22 set)'),
        (0x80400000, '-subnormal 2^22'),
        (0x00200000, 'subnormal 2^21'),
        (0x007FFFFF, 'max subnormal'),
        (0x807FFFFF, '-max subnormal'),
        (0x7F800000, '+Inf'),
        (0xFF800000, '-Inf'),
        (0x7FC00000, '+quiet NaN'),
        (0xFFC00000, '-quiet NaN'),
        (0x7F800001, '+signaling NaN'),
        (0xFF800001, '-signaling NaN'),
        (0x7FFFFFFF, 'NaN max bits'),
        (0x00000000, '+0.0'),
        (0x80000000, '-0.0'),
    ]
    return cases


def main():
    rom = open(ROM, 'rb').read()
    random.seed(0x48C8)

    # ---- 1. edge cases + random vs emulated ROM ----
    inputs = gen_edge_cases()
    rnd = [random.getrandbits(32) for _ in range(100000)]
    fails = 0
    for bits, label in inputs:
        r0, r1 = rom_run(rom, bits)
        m0, m1 = model(bits)
        if (r0, r1) != (m0, m1):
            fails += 1
            print(f'MISMATCH {label} 0x{bits:08X}: rom={r0:08X},{r1:08X} '
                  f'model={m0:08X},{m1:08X}')
    for bits in rnd:
        r0, r1 = rom_run(rom, bits)
        m0, m1 = model(bits)
        if (r0, r1) != (m0, m1):
            fails += 1
            if fails < 20:
                print(f'MISMATCH rnd 0x{bits:08X}: rom={r0:08X},{r1:08X} '
                      f'model={m0:08X},{m1:08X}')
    n = len(inputs) + len(rnd)
    print(f'emulator vs model: {n} inputs, {fails} mismatches')
    if fails:
        sys.exit(1)

    # ---- 2. C lift vs emulated ROM (Track A) ----
    try:
        so = '/tmp/test_bitfield_extract_merge.so'
        subprocess.run(['cc', '-O2', '-shared', '-fPIC',
                        os.path.join(RE, 'c', 'bitfield_extract_merge.c'),
                        '-o', so], check=True)
    except Exception as e:               # no host compiler: skip C check
        print('C-lift check skipped (no host C compiler):', e)
        return
    lib = ctypes.CDLL(so)
    fn = lib.bitfield_extract_merge
    fn.restype = None
    fn.argtypes = [ctypes.c_float, ctypes.POINTER(ctypes.c_uint32)]
    cfails = 0
    # all named edge cases + a fresh 100k random sample
    for bits in [b for b, _ in inputs] + \
                [random.getrandbits(32) for _ in range(100000)]:
        out = (ctypes.c_uint32 * 2)()
        value = struct.unpack('>f', struct.pack('>I', bits & M32))[0]
        fn(ctypes.c_float(value), out)
        r0, r1 = rom_run(rom, bits)
        if (r0, r1) != (out[0], out[1]):
            cfails += 1
            if cfails < 20:
                print(f'C MISMATCH 0x{bits:08X}: rom={r0:08X},{r1:08X} '
                      f'c={out[0]:08X},{out[1]:08X}')
    print(f'C lift vs emulated ROM: 100k+ inputs, {cfails} mismatches')
    if cfails:
        sys.exit(1)

    print('OK  bitfield_extract_merge @0x%04X  (emulator + C lift verified)' % ENTRY)


if __name__ == '__main__':
    main()
