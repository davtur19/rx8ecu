#!/usr/bin/env python3
"""
harness_first_order_filter.py — equivalence of rx8_first_order_filter @0x23B0.

Reconstructed source: samples/src/rx8_first_order_filter.c
Verified lift   : c/firstOrderFilter.c (IDA mislabels the ROM symbol
                  `fpu_abs_float`; the code is a generic first-order IIR
                  low-pass filter with a not-finite bootstrap and a
                  minimum-change deadband).

Calling convention (SH-2E FPU): fr4=sig, fr5=sigprev, fr6=ff, fr7=min;
result returned in fr0.  This is a register-only leaf — no RAM side-effects —
so the comparison is bit-exact on the single-precision result.

Procedure (Track-A pattern):
  1. build host oracle (system gcc; own binary, common.build_oracle untouched),
  2. edge vectors + N random (seeded) float-arg vectors,
  3. run the ROM bytes @0x23B0 in tools/sh2emu.py on the same vectors,
  4. run the host C on the same vectors,
  5. compare bit-exact — 0 mismatches required.

Usage:  python3 harness_first_order_filter.py [N]   (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, run_oracle, report  # noqa: E402
# common() puts ROOT/tools on sys.path, so sh2emu is importable here.
from sh2emu import bits2f, f2bits  # noqa: E402

ADDR = 0x23B0
N_DEFAULT = 20000

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = os.path.join('/tmp', 'opencode', 'rx8-recon-first_order_filter')
ORACLE = os.path.join(BUILD_DIR, 'oracle')


def build_oracle():
    """Compile THIS sample + its own oracle (do NOT touch common.build_oracle)."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    cmd = ['cc', '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_first_order_filter.c'),
           os.path.join(SAMPLES, 'src', 'rx8_first_order_filter.c'),
           '-lm', '-o', ORACLE]
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
_TINY = 0x38D1B717             # ~1.0e-4 (typical deadband for min)

# Interesting operand values (swept in the edge set).
_VALS = [_ZERO, _NZERO, _ONE, _NEGONE, _HALF, _SEV, _P15, _N15,
         _PINF, _NINF, _QNAN, _SNAN, _BIG, _MAXF, _DEN]

EDGE = []
# Bootstrap: every interesting sigprev (esp. inf/NaN) with a sweep of sig.
for p in (_PINF, _NINF, _QNAN, _SNAN, _ZERO, _ONE, _HALF):
    for s in (_ZERO, _ONE, _NEGONE, _P15, _PINF, _QNAN, _DEN):
        EDGE.append((s, p, _HALF, _ZERO))
# Sweep filter factor and deadband on a finite, non-trivial pair.
for ff in (_ZERO, _ONE, _HALF, _SEV):
    for mn in (_ZERO, _DEN, _TINY, _PINF):
        EDGE.append((_P15, _N15, ff, mn))
# Identical in/out (sig == sigprev) and a huge deadband (always snaps to sig).
EDGE.append((_P15, _P15, _HALF, _ZERO))
EDGE.append((_P15, _P15, _HALF, _ONE))
EDGE.append((_P15, _N15, _HALF, _MAXF))
EDGE.append((_N15, _P15, _HALF, _MAXF))


def rflt(rng):
    """Random single-precision value with realistic firmware magnitudes."""
    return f2bits(rng.choice([rng.uniform(-1e4, 1e4), rng.uniform(-2, 2),
                              rng.uniform(0, 300), rng.uniform(-300, 0)]))


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(0x23B0)

    vectors = list(EDGE) + [(rflt(rng), rflt(rng), rflt(rng), rflt(rng))
                            for _ in range(n)]

    # (a) ROM behaviour via the emulator (FPU args fr4..fr7, result fr0).
    emu = []
    for sb, pb, fb, mb in vectors:
        cpu.call(ADDR, fr={4: bits2f(sb), 5: bits2f(pb),
                           6: bits2f(fb), 7: bits2f(mb)})
        emu.append(f2bits(cpu.fr[0]))

    # (b) host-C on the same inputs (bit patterns round-trip exactly).
    lines = ['flt %08X %08X %08X %08X' % v for v in vectors]
    host = [int(x, 16) for x in run_oracle(oracle, lines)]

    # (c) compare bit-exact.
    mismatches = []
    for i, (v, e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            sb, pb, fb, mb = v
            mismatches.append('vec#%d sig=%08X sigprev=%08X ff=%08X min=%08X '
                              'ROM=%08X C=%08X' % (i, sb, pb, fb, mb, e, h))
            if len(mismatches) >= 5:
                break

    report('firstOrderFilter', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
