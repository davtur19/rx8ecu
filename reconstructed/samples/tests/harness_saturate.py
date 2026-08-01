#!/usr/bin/env python3
"""
harness_saturate.py — equivalence of rx8_saturate @0x2404.

Reconstructed source: samples/src/rx8_saturate.c
Verified lift   : c/math_primitives.c, function `saturate` @0x2404 (clamp a
                  signal into [lower, upper]; equinox hand Ghidra RE, also
                  cross-checked in c/tests/test_math_primitives.py).

Calling convention (SH-2E FPU): fr4=sig, fr5=lower, fr6=upper; result returned
in fr0.  This is a register-only leaf — no RAM side-effects — so the
comparison is bit-exact on the single-precision result.

Procedure (Track-A pattern):
  1. build host oracle (system gcc; own binary, common.build_oracle untouched),
  2. edge vectors + N random (seeded) float-arg vectors,
  3. run the ROM bytes @0x2404 in tools/sh2emu.py on the same vectors,
  4. run the host C on the same vectors,
  5. compare bit-exact — 0 mismatches required.

Usage:  python3 harness_saturate.py [N]   (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, run_oracle, report  # noqa: E402
# common() puts ROOT/tools on sys.path, so sh2emu is importable here.
from sh2emu import bits2f, f2bits  # noqa: E402

ADDR = 0x2404
N_DEFAULT = 20000

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = os.path.join('/tmp', 'rx8-recon-saturate')
ORACLE = os.path.join(BUILD_DIR, 'oracle')


def build_oracle():
    """Compile THIS sample + its own oracle (do NOT touch common.build_oracle)."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    cmd = ['cc', '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_saturate.c'),
           os.path.join(SAMPLES, 'src', 'rx8_saturate.c'),
           '-o', ORACLE]
    subprocess.run(cmd, check=True)
    return ORACLE


# --- IEEE-754 single-precision bit patterns used in the edge set -------------
_ZERO = 0x00000000
_NZERO = 0x80000000
_ONE = 0x3F800000
_NEGONE = 0xBF800000
_HALF = 0x3F000000
_SEV = 0x3F666666              # ~0.7
_P15 = 0x3FC00000              # 1.5
_N15 = 0xBFC00000              # -1.5
_PINF = 0x7F800000
_NINF = 0xFF800000
_QNAN = 0x7FC00000
_SNAN = 0x7F800001
_BIG = 0x49742400              # 1.0e6
_MAXF = 0x7F7FFFFF             # FLT_MAX
_NMAXF = 0xFF7FFFFF            # -FLT_MAX
_DEN = 0x00000001              # min denormal

_VALS = [_ZERO, _NZERO, _ONE, _NEGONE, _HALF, _SEV, _P15, _N15,
         _PINF, _NINF, _QNAN, _BIG, _MAXF, _NMAXF, _DEN]


def _e(s, lo, hi):
    return (s, lo, hi)


EDGE = [
    # Classic band [1.0, 3.0]: below / at-lower / between / at-upper / above.
    _e(_HALF, _ONE, _P15),          # 0.5 < 1.0  -> lower
    _e(_ONE, _ONE, _P15),           # sig == lower -> lower (strict >)
    _e(_SEV, _ONE, _P15),           # in band      -> sig
    _e(_P15, _ONE, _P15),           # sig == upper -> upper (strict >)
    _e(_BIG, _ONE, _P15),           # 1e6 > 1.5   -> upper
    # Degenerate band: lower == upper.
    _e(_ONE, _P15, _P15),           # sig below the point  -> lower
    _e(_P15, _P15, _P15),           # sig == the point     -> lower (strict >)
    _e(_BIG, _P15, _P15),           # sig above the point  -> upper
    # Inverted bounds (lower > upper): mirrors the ROM branch-for-branch.
    _e(_BIG, _P15, _ONE),           # sig > lower -> upper
    _e(_SEV, _P15, _ONE),           # lower < sig but upper not > sig -> upper
    _e(_HALF, _P15, _ONE),          # sig < lower -> lower
    # Negative band.
    _e(_NEGONE, _N15, _HALF),       # -1.0 in [-1.5, 0.5]  -> sig
    _e(_N15, _N15, _HALF),          # -1.5 == lower        -> lower
    _e(_HALF, _N15, _HALF),         # 0.5 == upper         -> upper
    _e(_BIG, _N15, _HALF),          # +1e6 above upper     -> upper
    _e(_NINF, _N15, _HALF),         # -inf                 -> lower
    # Zero / negative zero (compare equal; register bits preserved).
    _e(_ZERO, _NEGONE, _ONE),
    _e(_NZERO, _NEGONE, _ONE),
    _e(_NEGONE, _NZERO, _ZERO),     # lower = -0.0, sig below -> returns -0.0
    _e(_ONE, _NZERO, _ZERO),        # sig above upper +0.0   -> returns +0.0
    # Wide-open / infinite bounds.
    _e(_MAXF, _NMAXF, _MAXF),       # sig == both bounds     -> lower (strict >)
    _e(_MAXF, _NINF, _PINF),        # +FLT_MAX inside ]-inf, +inf[
    _e(_NMAXF, _NINF, _PINF),       # -FLT_MAX inside
    _e(_DEN, _NINF, _PINF),         # denormal passes through
    _e(_PINF, _NINF, _PINF),        # +inf at the ceiling    -> upper (+inf)
    _e(_NINF, _NINF, _PINF),        # -inf at the floor      -> lower (-inf)
    # NaN operands: fcmp/gt clears T for unordered, so `sig` NaN snaps to
    # lower and a NaN bound forces the same path as an unequal value.
    _e(_QNAN, _ZERO, _ONE),         # sig = NaN -> lower
    _e(_SNAN, _NEGONE, _HALF),      # sig = sNaN -> lower
    _e(_HALF, _QNAN, _ONE),         # lower = NaN -> lower (the NaN itself)
    _e(_HALF, _ZERO, _QNAN),        # upper = NaN, in band otherwise -> sig
    _e(_BIG, _ZERO, _QNAN),         # upper = NaN, sig above -> upper (NaN)
]


def rflt(rng):
    """Random single-precision value with realistic firmware magnitudes."""
    return f2bits(rng.choice([rng.uniform(-1e4, 1e4), rng.uniform(-2, 2),
                              rng.uniform(0, 300), rng.uniform(-300, 0)]))


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(0x2404)

    vectors = list(EDGE) + [(rflt(rng), rflt(rng), rflt(rng))
                            for _ in range(n)]

    # (a) ROM behaviour via the emulator (FPU args fr4..fr6, result fr0).
    emu = []
    for sb, lb, ub in vectors:
        cpu.call(ADDR, fr={4: bits2f(sb), 5: bits2f(lb), 6: bits2f(ub)})
        emu.append(f2bits(cpu.fr[0]))

    # (b) host-C on the same inputs (bit patterns round-trip exactly).
    lines = ['sat %08X %08X %08X' % v for v in vectors]
    host = [int(x, 16) for x in run_oracle(oracle, lines)]

    # (c) compare bit-exact.
    mismatches = []
    for i, (v, e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            sb, lb, ub = v
            mismatches.append('vec#%d sig=%08X lower=%08X upper=%08X '
                              'ROM=%08X C=%08X' % (i, sb, lb, ub, e, h))
            if len(mismatches) >= 5:
                break

    report('saturate', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
