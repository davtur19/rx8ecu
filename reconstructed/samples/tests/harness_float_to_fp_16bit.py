#!/usr/bin/env python3
"""
harness_float_to_fp_16bit.py — equivalence of the 0x24C0 fixed-point->float
conversion.

Reconstructed source: samples/src/rx8_float_to_fp_16bit.c
Verified lift   : c/math_primitives.c  (0x24C0: `fixedPointToFloat_16bit`).
                  NOTE: the "floatToFP_16bit @ 0x24C0" task label is a
                  misnomer — 0x24C0 converts fixed-point -> float (fr0 =
                  mult*raw + off via a fused `fmac`); the float -> fixed-point
                  helper named floatToFP_16bit is the neighbor at 0x2490.

Calling convention (SH-2E FPU): r4 = raw (u16, extu.w-masked), fr4 = mult,
fr5 = off; result returned in fr0.  Pure register-level leaf — no RAM
side-effects — so the comparison is bit-exact on the single-precision result.

ROUNDING MODEL: the ROM fuses multiply+add in one rounding (`fmac`); the
emulator keeps the exact product in double and rounds once to f32
(fmac: fr = ts(fr0*fr3 + fr5)).  The host C mirrors that with double
intermediates and a single float cast; a naive float mul+add double-rounds
and diverges (verified empirically: thousands of mismatches per 30k vectors).

Procedure (Track-A pattern):
  1. build host oracle (system gcc; own binary, common.build_oracle untouched),
  2. edge vectors + N random (seeded) vectors,
  3. run the ROM bytes @0x24C0 in tools/sh2emu.py on the same vectors,
  4. run the host C on the same vectors,
  5. compare bit-exact — 0 mismatches required.

Usage:  python3 harness_float_to_fp_16bit.py [N]   (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, run_oracle, report  # noqa: E402
# common() puts ROOT/tools on sys.path, so sh2emu is importable here.
from sh2emu import bits2f, f2bits  # noqa: E402

ADDR = 0x24C0
N_DEFAULT = 20000

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = os.path.join('/tmp', 'rx8-recon-float_to_fp_16bit')
ORACLE = os.path.join(BUILD_DIR, 'oracle')


def build_oracle():
    """Compile THIS sample + its own oracle (do NOT touch common.build_oracle)."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    cmd = ['cc', '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_float_to_fp_16bit.c'),
           os.path.join(SAMPLES, 'src', 'rx8_float_to_fp_16bit.c'),
           '-lm', '-o', ORACLE]
    subprocess.run(cmd, check=True)
    return ORACLE


# --- IEEE-754 single-precision bit patterns used in the edge set -------------
_ZERO = 0x00000000
_NZERO = 0x80000000
_ONE = 0x3F800000
_NEGONE = 0xBF800000
_HALF = 0x3F000000
_PINF = 0x7F800000
_NINF = 0xFF800000
_QNAN = 0x7FC00000
_P10000 = 0x461C4000             # 1.0e4
_P1E30 = 0x731D254A              # ~1.0e30 (|mult|*65535 ~ 6.5e34 < FLT_MAX)
_N1E30 = 0xF31D254A              # ~-1.0e30
_DEN = 0x00000001                # min denormal
_SMALL = 0x15A92A40              # ~1.0e-30 (underflow corner with tiny raw)

# Interesting mult / off values (swept in the edge set).  Magnitudes are kept
# so that |mult|*65535 stays below FLT_MAX: the emulator's ts() helper raises
# OverflowError instead of producing inf on f32-overflow (emulator gap, not
# exercised here).
_MVALS = [_ZERO, _NZERO, _ONE, _NEGONE, _HALF, _P10000, _P1E30, _N1E30,
          _SMALL, _DEN, _PINF, _NINF, _QNAN]
_OVALS = [_ZERO, _NZERO, _ONE, _NEGONE, _P1E30, _N1E30, _PINF, _NINF, _QNAN]

# raw (u16 fixed-point) interesting values, incl. clamp/boundary/byte-split.
_RAWS = [0x0000, 0x0001, 0x7FFF, 0x8000, 0xFFFF, 0x1234, 0xDEAD]

# Full sweep: every mult x every off x every raw.
EDGE = [(r, m, o) for m in _MVALS for o in _OVALS for r in _RAWS]


def rflt(rng):
    """Random single-precision value with realistic firmware magnitudes."""
    return f2bits(rng.choice([rng.uniform(-1e4, 1e4), rng.uniform(-2, 2),
                              rng.uniform(0, 300), rng.uniform(-300, 0)]))


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(0x24C0)

    vectors = list(EDGE) + [(rng.getrandbits(16), rflt(rng), rflt(rng))
                            for _ in range(n)]

    # (a) ROM behaviour via the emulator (r4 = raw u16, fr4/fr5 = mult/off,
    #     result fr0).
    emu = []
    for raw, mb, ob in vectors:
        cpu.call(ADDR, r4=raw, fr={4: bits2f(mb), 5: bits2f(ob)})
        emu.append(f2bits(cpu.fr[0]))

    # (b) host-C on the same inputs (bit patterns round-trip exactly).
    lines = ['fpf %04X %08X %08X' % (raw, mb, ob) for raw, mb, ob in vectors]
    host = [int(x, 16) for x in run_oracle(oracle, lines)]

    # (c) compare bit-exact.
    mismatches = []
    for i, ((raw, mb, ob), e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append('vec#%d raw=%04X mult=%08X off=%08X ROM=%08X C=%08X'
                              % (i, raw, mb, ob, e, h))
            if len(mismatches) >= 5:
                break

    report('fixedPointToFloat_16bit', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
