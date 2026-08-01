#!/usr/bin/env python3
"""
harness_bitfield_extract_merge.py — equivalence of rx8_bitfield_extract_merge @0x48C8.

Reconstructed source: samples/src/rx8_bitfield_extract_merge.c
Verified lift   : c/bitfield_extract_merge.c (frexp-style float decomposition:
                  x = sig * 2^e, sig in [1,2), into a (exponent, significand)
                  word pair — feeds checkFloatValidity @0x46CC).

Procedure (Track-A pattern, per-sample variant):
  1. build a PRIVATE host oracle (tests/oracle_bitfield_extract_merge.c +
     src/rx8_bitfield_extract_merge.c) into /tmp/rx8-recon-bitfield_extract_merge,
  2. N random IEEE-754 bit patterns + a full edge set (mask boundaries, all
     special values, every exponent byte),
  3. run the ROM bytes @0x48C8 in tools/sh2emu.py on the same bit patterns
     (float passed in FR4, result pointer pre-placed at [r15], exactly as the
     single caller checkFloatValidity @0x46CC does),
  4. run the host C on the same inputs,
  5. compare — 0 mismatches required.

Usage:  python3 harness_bitfield_extract_merge.py [N]   (default N = 20000)
"""
import os
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import make_rng, report, run_oracle  # noqa: E402
from sh2emu import SH2  # noqa: E402

ADDR = 0x48C8
N_DEFAULT = 20000
SEED = 0x48C8

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(os.path.dirname(SAMPLES))
ROM_PATH = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
BUILD_DIR = '/tmp/rx8-recon-bitfield_extract_merge'

R15 = 0xFFFFDF00      # stack pointer used by sh2emu.call()
OUT = 0xFFFFDF80      # scratch buffer in emulator RAM (result pointer target)


def build_oracle():
    """Compile the reconstructed source + its private oracle into one binary."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = ['cc', '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_bitfield_extract_merge.c'),
           os.path.join(SAMPLES, 'src', 'rx8_bitfield_extract_merge.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def rom_run(rom, bits):
    """Execute the ROM function on the float with the given IEEE-754 bit
    pattern (passed in fr4) and return (out0, out1) written via the
    caller-supplied pointer at [r15]."""
    value = struct.unpack('>f', struct.pack('>I', bits & 0xFFFFFFFF))[0]
    cpu = SH2(rom)
    cpu.call(ADDR, fr={4: value},
             ram={R15: (OUT >> 24) & 0xFF,
                  R15 + 1: (OUT >> 16) & 0xFF,
                  R15 + 2: (OUT >> 8) & 0xFF,
                  R15 + 3: OUT & 0xFF})
    return cpu.rd(OUT, 4), cpu.rd(OUT + 4, 4)


def gen_edge_cases():
    """Named edge cases: every branch + the mask/boundary values the bit
    decoder is sensitive to (sign, exponent 0x00/0xFF, mantissa all-0/all-1,
    subnormal/normal boundary, NaN payloads)."""
    return [
        # ---- finite normals (representative values) ----
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
        (0x00800001, 'min normal + 1 ulp'),
        (0x7F000000, 'exp 0xFE, mantissa 0'),
        (0xFF000000, 'exp 0xFE, mantissa 0, negative'),
        (0x7EFFFFFF, 'exp 0xFE, mantissa all ones'),
        (0xFEFFFFFF, 'exp 0xFE, mantissa all ones, negative'),
        (0x0000FFFF, 'exp 0, mantissa all ones (max subnormal-1 ulp)'),
        (0x00010000, 'exp 1, mantissa 0x10000'),
        (0x807F0000, 'negative, exp 0, mantissa 0x7F0000'),
        # ---- zeros ----
        (0x00000000, '+0.0'),
        (0x80000000, '-0.0'),
        # ---- subnormals (normalized on exit) ----
        (0x00000001, 'min subnormal'),
        (0x80000001, '-min subnormal'),
        (0x00000002, 'subnormal 2'),
        (0x000FFFFF, 'subnormal 0xFFFFF'),
        (0x00200000, 'subnormal 2^21'),
        (0x00400000, 'subnormal 2^22 (bit22 set, no shift)'),
        (0x80400000, '-subnormal 2^22'),
        (0x007FFFFF, 'max subnormal'),
        (0x807FFFFF, '-max subnormal'),
        # ---- infinities (sign preserved) ----
        (0x7F800000, '+Inf'),
        (0xFF800000, '-Inf'),
        # ---- NaNs (sign always dropped) ----
        (0x7FC00000, '+quiet NaN'),
        (0xFFC00000, '-quiet NaN'),
        (0x7F800001, '+signaling NaN'),
        (0xFF800001, '-signaling NaN'),
        (0x7FFFFFFF, '+NaN max bits'),
        (0xFFFFFFFF, '-NaN max bits'),
        (0x7FBFFFFF, '+NaN mantissa all ones, no quiet bit'),
        (0xFFBFFFFF, '-NaN mantissa all ones, no quiet bit'),
    ]


def gen_exponent_sweep():
    """One vector per exponent byte (0..0xFF) with a fixed random mantissa,
    so every bit-decoder branch boundary is exercised deterministically."""
    rng = make_rng(SEED ^ 0x5EED)
    mant = rng.getrandbits(23)
    sign = rng.getrandbits(1)
    return [(0x80000000 if sign else 0) | (exp << 23) | mant
            for exp in range(0x100)]


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT

    with open(ROM_PATH, 'rb') as f:
        rom = f.read()
    oracle = build_oracle()
    rng = make_rng(SEED)

    edge = gen_edge_cases()
    sweep = gen_exponent_sweep()
    random_bits = [rng.getrandbits(32) for _ in range(n)]
    vectors = [b for b, _ in edge] + sweep + random_bits

    # (a) ROM behaviour via the emulator, (b) host-C on the same bit patterns.
    emu = [rom_run(rom, b) for b in vectors]
    lines = ['bfe %08X' % b for b in vectors]
    host_raw = run_oracle(oracle, lines)
    host = [tuple(int(x, 16) for x in ln.split())
            for ln in host_raw]

    # (c) compare.
    mismatches = []
    for i, (b, e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append('vec#%d bits=0x%08X ROM=%08X,%08X C=%08X,%08X'
                              % (i, b, e[0], e[1], h[0], h[1]))
            if len(mismatches) >= 5:
                break

    report('bitfield_extract_merge', ADDR, n, mismatches,
           edges=len(edge) + len(sweep))


if __name__ == '__main__':
    main()
