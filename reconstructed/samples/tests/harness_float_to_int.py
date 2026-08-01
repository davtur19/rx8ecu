#!/usr/bin/env python3
"""
harness_float_to_int.py — equivalence of rx8_float_to_int @0x24D0.

Reconstructed source: samples/src/rx8_float_to_int.c
Verified lift   : c/math_primitives.c  (`floatToInt`, same address).

Calling convention (SH-2E FPU): fr4=signal, fr5=mult, fr6=offset; result is
truncated to int by `ftrc` (toward zero), clamped to [0,255] and returned in
r0.  This is a register-only leaf — no RAM side-effects.

Procedure (Track-A pattern):
  1. build host oracle (system gcc; own binary, common.build_oracle untouched),
  2. edge vectors + N random (seeded) single-precision vectors,
  3. run the ROM bytes @0x24D0 in tools/sh2emu.py on the same vectors,
  4. run the host C on the same vectors,
  5. compare — 0 mismatches required.

NOTE on non-finite inputs: NaN/Inf are NOT exercised.  The emulator's `ftrc`
is `int(float)`, which raises on NaN/Inf (OverflowError/ValueError) — a real
emulator gap, and real SH-2 hardware leaves ftrc of a non-finite value
undefined anyway.  Random/edge `mult` are kept |mult| >= 1e-3 so the division
stays finite and the truncated intermediate stays inside int32 range, keeping
the C side (and its `(int32_t)` cast) well-defined.

Usage:  python3 harness_float_to_int.py [N]   (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, run_oracle, report  # noqa: E402
# common() puts ROOT/tools on sys.path, so sh2emu is importable here.
from sh2emu import bits2f, f2bits  # noqa: E402

ADDR = 0x24D0
N_DEFAULT = 20000

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = os.path.join('/tmp', 'rx8-recon-float_to_int')
ORACLE = os.path.join(BUILD_DIR, 'oracle')


def build_oracle():
    """Compile THIS sample + its own oracle (do NOT touch common.build_oracle)."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    cmd = ['cc', '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_float_to_int.c'),
           os.path.join(SAMPLES, 'src', 'rx8_float_to_int.c'),
           '-lm', '-o', ORACLE]
    subprocess.run(cmd, check=True)
    return ORACLE


# --- edge vectors (signal, mult, offset) as IEEE-754 bit patterns ------------
# Edges per spec: 0, +-0.5, +-0.999, 1.5, -1.5, large, overflow range.
# Intermediate values never leave int32 range and mult is never zero, so both
# the emulator and the host C stay well-defined (see module docstring).
EDGE = [
    (f2bits(0.0),      f2bits(1.0),      f2bits(0.0)),    # 0 -> 0
    (f2bits(-0.0),     f2bits(1.0),      f2bits(0.0)),    # -0 -> 0
    (f2bits(0.5),      f2bits(1.0),      f2bits(0.0)),    # +0.5 -> 1 (half away)
    (f2bits(-0.5),     f2bits(1.0),      f2bits(0.0)),    # -0.5 -> 0 (clamp)
    (f2bits(0.999),    f2bits(1.0),      f2bits(0.0)),    # 1.499 -> 1
    (f2bits(-0.999),   f2bits(1.0),      f2bits(0.0)),    # -0.499 -> 0 (clamp)
    (f2bits(1.5),      f2bits(1.0),      f2bits(0.0)),    # 2.0 -> 2
    (f2bits(-1.5),     f2bits(1.0),      f2bits(0.0)),    # -1.0 -> 0 (clamp)
    (f2bits(1e6),      f2bits(1.0),      f2bits(0.0)),    # large -> 255 (clamp)
    (f2bits(-1e6),     f2bits(1.0),      f2bits(0.0)),    # large -ve -> 0 (clamp)
    (f2bits(1e9),      f2bits(1.0),      f2bits(0.0)),    # huge, int32-safe -> 255
    (f2bits(-1e9),     f2bits(1.0),      f2bits(0.0)),    # -> 0 (clamp)
    (f2bits(254.4),    f2bits(1.0),      f2bits(0.0)),    # 254.9 -> 254
    (f2bits(255.4),    f2bits(1.0),      f2bits(0.0)),    # 255.9 -> 255
    (f2bits(255.6),    f2bits(1.0),      f2bits(0.0)),    # 256.1 -> 255 (clamp)
    (f2bits(-255.0),   f2bits(1.0),      f2bits(0.0)),    # -254.5 -> 0 (clamp)
    (f2bits(255.0),    f2bits(1.0),      f2bits(0.0)),    # 255.5 -> 255
    (f2bits(1e4),      f2bits(1e-3),     f2bits(-1e4)),   # 2e7 -> 255 (overflow range)
    (f2bits(-1e4),     f2bits(1e-3),     f2bits(1e4)),    # -2e7 -> 0 (overflow range)
    (f2bits(1e6),      f2bits(1e-2),     f2bits(0.0)),    # 1e8 -> 255 (overflow range)
    (f2bits(3.0),      f2bits(0.5),      f2bits(0.0)),    # 6.5 -> 6
    (f2bits(2.5),      f2bits(0.5),      f2bits(0.0)),    # 5.5 -> 5
    (f2bits(-1.5),     f2bits(-0.5),     f2bits(0.0)),    # 3.5 -> 3 (neg mult)
    (f2bits(-100.0),   f2bits(-1.0),     f2bits(0.0)),    # 100.5 -> 100 (neg mult)
    (f2bits(0.0),      f2bits(1.0),      f2bits(-0.6)),   # 1.1 -> 1
    (f2bits(0.0),      f2bits(1.0),      f2bits(0.4)),    # 0.1 -> 0
    (f2bits(1.5),      f2bits(1.0),      f2bits(1.0)),    # 1.0 -> 1
    (f2bits(-1.5),     f2bits(1.0),      f2bits(1.0)),    # -2.0 -> 0 (clamp)
    (f2bits(0.0),      f2bits(0.5),      f2bits(-0.6)),   # 1.7 -> 1
]


def rflt(rng):
    """Random single-precision value with realistic firmware magnitudes."""
    return f2bits(rng.choice([rng.uniform(-1e4, 1e4), rng.uniform(-2, 2),
                              rng.uniform(0, 300), rng.uniform(-300, 0)]))


def rmult(rng):
    """Random multiplier, kept |mult| >= 1e-3 so the division stays finite
    and the truncated intermediate stays well inside int32 range."""
    m = rng.choice([rng.uniform(-1e4, 1e4), rng.uniform(-2, 2),
                    rng.uniform(0.01, 50), rng.uniform(-50, -0.01)])
    if abs(m) < 1e-3:
        m = 1.0
    return f2bits(m)


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(0x24D0)

    vectors = list(EDGE) + [(rflt(rng), rmult(rng), rflt(rng))
                            for _ in range(n)]

    # (a) ROM behaviour via the emulator (FPU args fr4..fr6, result in r0).
    emu = []
    for sb, mb, ob in vectors:
        emu.append(cpu.call(ADDR, fr={4: bits2f(sb), 5: bits2f(mb),
                                      6: bits2f(ob)}))
    # (b) host-C on the same inputs (bit patterns round-trip exactly).
    lines = ['f2i %08X %08X %08X' % v for v in vectors]
    host = [int(x, 16) for x in run_oracle(oracle, lines)]

    # (c) compare.
    mismatches = []
    for i, (v, e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            sb, mb, ob = v
            mismatches.append('vec#%d signal=%08X mult=%08X offset=%08X '
                              'ROM=%08X C=%08X' % (i, sb, mb, ob, e, h))
            if len(mismatches) >= 5:
                break

    report('floatToInt', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
