#!/usr/bin/env python3
"""
harness_subtract_absolute.py — equivalence of rx8_subtract_absolute @0x23DC.

Reconstructed source: samples/src/rx8_subtract_absolute.c
Verified lift   : c/math_primitives.c  (0x23DC: `fsub fr5,fr4 ; fabs fr4 ;
                  fmov fr4,fr0` — |a - b|).

Calling convention (SH-2E FPU): fr4=a, fr5=b; result returned in fr0.  This
is a register-only leaf — no RAM side-effects — so the comparison is bit-exact
on the single-precision result.

Procedure (Track-A pattern):
  1. build host oracle (system gcc; own binary, common.build_oracle untouched),
  2. edge vectors + N random (seeded) float-arg vectors,
  3. run the ROM bytes @0x23DC in tools/sh2emu.py on the same vectors,
  4. run the host C on the same vectors,
  5. compare bit-exact — 0 mismatches required.

Usage:  python3 harness_subtract_absolute.py [N]   (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, run_oracle, report  # noqa: E402
# common() puts ROOT/tools on sys.path, so sh2emu is importable here.
from sh2emu import bits2f, f2bits  # noqa: E402

ADDR = 0x23DC
N_DEFAULT = 20000

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = os.path.join('/tmp', 'rx8-recon-subtract_absolute')
ORACLE = os.path.join(BUILD_DIR, 'oracle')


def build_oracle():
    """Compile THIS sample + its own oracle (do NOT touch common.build_oracle)."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    cmd = ['cc', '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_subtract_absolute.c'),
           os.path.join(SAMPLES, 'src', 'rx8_subtract_absolute.c'),
           '-o', ORACLE]
    subprocess.run(cmd, check=True)
    return ORACLE


# --- IEEE-754 single-precision bit patterns used in the edge set -------------
_PINF = 0x7F800000
_NINF = 0xFF800000
_QNAN = 0x7FC00000
_SNAN = 0x7F800001
_ZERO = 0x00000000
_NZERO = 0x80000000
_ONE = 0x3F800000
_NEGONE = 0xBF800000
_HALF = 0x3F000000
_SEV = 0x3F666666              # ~0.7
_P15 = 0x3FC00000              # 1.5
_N15 = 0xBFC00000              # -1.5
_BIG = 0x49742400              # 1.0e6
_MAXF = 0x7F7FFFFF             # FLT_MAX
_DEN = 0x00000001              # min denormal
_I32MIN = 0xCF000000           # -2^31 (INT32_MIN, exactly representable)
_I32MAX = 0x4F000000           # +2^31 (float nearest to INT32_MAX)

# Interesting operand values (swept in the edge set).
_VALS = [_ZERO, _NZERO, _ONE, _NEGONE, _HALF, _SEV, _P15, _N15,
         _PINF, _NINF, _QNAN, _SNAN, _BIG, _MAXF, _DEN, _I32MIN, _I32MAX]

# |a - b| edge sweep: every interesting a against every interesting b (covers
# inf-inf -> NaN, NaN propagation with payload preserved, ±0 -> +0, etc.).
EDGE = [(a, b) for a in _VALS for b in _VALS]


def rflt(rng):
    """Random single-precision value with realistic firmware magnitudes."""
    return f2bits(rng.choice([rng.uniform(-1e4, 1e4), rng.uniform(-2, 2),
                              rng.uniform(0, 300), rng.uniform(-300, 0)]))


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(0x23DC)

    vectors = list(EDGE) + [(rflt(rng), rflt(rng)) for _ in range(n)]

    # (a) ROM behaviour via the emulator (FPU args fr4/fr5, result fr0).
    emu = []
    for ab, bb in vectors:
        cpu.call(ADDR, fr={4: bits2f(ab), 5: bits2f(bb)})
        emu.append(f2bits(cpu.fr[0]))

    # (b) host-C on the same inputs (bit patterns round-trip exactly).
    lines = ['abs %08X %08X' % (ab, bb) for ab, bb in vectors]
    host = [int(x, 16) for x in run_oracle(oracle, lines)]

    # (c) compare bit-exact.
    mismatches = []
    for i, ((ab, bb), e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append('vec#%d a=%08X b=%08X ROM=%08X C=%08X'
                              % (i, ab, bb, e, h))
            if len(mismatches) >= 5:
                break

    report('subtractAbsolute', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
