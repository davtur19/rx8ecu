#!/usr/bin/env python3
"""
harness_min_value.py — equivalence of rx8_min_value @0x23F4.

Reconstructed source: samples/src/rx8_min_value.c
Verified lift   : c/math_primitives.c (`minValue`, "minimum of two floats",
                  one of the thirteen scalar helpers in the 0x2044..0x2510
                  cluster).

Calling convention (SH-2E FPU): fr4 = a, fr5 = b; result returned in fr0.
This is a register-only FPU leaf — no RAM side-effects — so the comparison is
bit-exact on the single-precision result (tie-break / NaN operand order is
part of the semantics and is pinned by the edge set below).

Procedure (Track-A pattern):
  1. build the oracle from THIS sample + its own oracle (system gcc; own
     binary, common.build_oracle untouched),
  2. edge vectors (ties, extremes, sign boundaries, NaN/inf) + N random
     (seeded) float-arg vectors,
  3. run the ROM bytes @0x23F4 in tools/sh2emu.py on the same vectors,
  4. run the host C on the same vectors,
  5. compare bit-exact — 0 mismatches required.

Usage:  python3 harness_min_value.py [N]   (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, run_oracle, report  # noqa: E402
# common() puts ROOT/tools on sys.path, so sh2emu is importable here.
from sh2emu import bits2f, f2bits  # noqa: E402

ADDR = 0x23F4
N_DEFAULT = 20000

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = os.path.join('/tmp', 'opencode', 'rx8-recon-min_value')
ORACLE = os.path.join(BUILD_DIR, 'oracle')


def build_oracle():
    """Compile THIS sample + its own oracle (do NOT touch common.build_oracle)."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    cmd = ['cc', '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_min_value.c'),
           os.path.join(SAMPLES, 'src', 'rx8_min_value.c'),
           '-o', ORACLE]
    subprocess.run(cmd, check=True)
    return ORACLE


# --- IEEE-754 single-precision bit patterns used in the edge set -------------
_PINF = 0x7F800000
_NINF = 0xFF800000
_QNAN = 0x7FC00000
_ZERO = 0x00000000
_NZERO = 0x80000000
_ONE = 0x3F800000
_NEGONE = 0xBF800000
_HALF = 0x3F000000
_P15 = 0x3FC00000              # 1.5
_N15 = 0xBFC00000              # -1.5
_BIG = 0x49742400              # 1.0e6
_SMALL = 0x39D6E3A0            # ~1.64e-4, small positive
_MAXF = 0x7F7FFFFF             # FLT_MAX
_MINNORM = 0x00800000          # smallest normal
_DEN = 0x00000001              # min denormal
_TINY = 0x38D1B717             # ~1.0e-4

# Interesting operand values (swept in the edge set).
_VALS = [_ZERO, _NZERO, _ONE, _NEGONE, _HALF, _P15, _N15,
         _PINF, _NINF, _QNAN, _BIG, _SMALL, _MAXF, _MINNORM, _DEN]

EDGE = []
# Ties: identical operands (including ±0.0 and NaN) must round-trip bit-exact.
for v in (_ZERO, _NZERO, _ONE, _NEGONE, _P15, _NINF, _MAXF, _QNAN, _DEN):
    EDGE.append((v, v))
# Sign boundary: +0.0 vs -0.0 in both orders (b wins on the fcmp tie).
EDGE.append((_ZERO, _NZERO))
EDGE.append((_NZERO, _ZERO))
EDGE.append((_ONE, _NZERO))
EDGE.append((_NZERO, _ONE))
# Extremes: infinities, FLT_MAX, denormals, NaN in both operand positions.
for v in (_PINF, _NINF, _MAXF, _DEN, _TINY):
    EDGE.append((v, _NEGONE))
    EDGE.append((_NEGONE, v))
EDGE.append((_PINF, _MAXF))
EDGE.append((_MAXF, _PINF))
EDGE.append((_QNAN, _ONE))          # NaN in a  -> discarded, b returned
EDGE.append((_ONE, _QNAN))          # NaN in b  -> NaN propagates
EDGE.append((_NINF, _NINF))
EDGE.append((_PINF, _PINF))
EDGE.append((_MAXF, _NINF))
EDGE.append((_NINF, _MAXF))
# Full cross-sweep of the interesting values (also covers the equal cases).
for x in _VALS:
    for y in _VALS:
        EDGE.append((x, y))


def rflt(rng):
    """Random single-precision value with realistic firmware magnitudes."""
    return f2bits(rng.choice([rng.uniform(-1e4, 1e4), rng.uniform(-2, 2),
                              rng.uniform(0, 300), rng.uniform(-300, 0)]))


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(0x23F4)

    vectors = list(EDGE) + [(rflt(rng), rflt(rng)) for _ in range(n)]

    # (a) ROM behaviour via the emulator (FPU args fr4, fr5, result fr0).
    emu = []
    for ab, bb in vectors:
        cpu.call(ADDR, fr={4: bits2f(ab), 5: bits2f(bb)})
        emu.append(f2bits(cpu.fr[0]))

    # (b) host-C on the same inputs (bit patterns round-trip exactly).
    lines = ['min %08X %08X' % v for v in vectors]
    host = [int(x, 16) for x in run_oracle(oracle, lines)]

    # (c) compare bit-exact.
    mismatches = []
    for i, (v, e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            ab, bb = v
            mismatches.append('vec#%d a=%08X b=%08X ROM=%08X C=%08X'
                              % (i, ab, bb, e, h))
            if len(mismatches) >= 5:
                break

    report('minValue', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
