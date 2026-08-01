#!/usr/bin/env python3
"""
harness_saturate_low.py — equivalence of rx8_saturate_low @0x23E4.

Reconstructed source: samples/src/rx8_saturate_low.c
Verified lift   : c/math_primitives.c, `saturateLow` @0x23E4 (low-side
                  saturation: max(sig, lower)).

Procedure (Track-A pattern):
  1. build THIS harness's own host oracle (it compiles ONLY
     rx8_saturate_low.c — not the shared host_oracle.c),
  2. N random (sig, lower) single-precision pairs + edge cases
     (below / at / above the bound),
  3. run the ROM bytes @0x23E4 in tools/sh2emu.py,
  4. run the host C on the same inputs,
  5. compare bit-exact IEEE-754 results — 0 mismatches required.

Inputs travel as raw 32-bit float patterns, so the host float and the
emulator float are bit-identical (the emulator ts()-rounds on load, which is
a no-op for an already-exact single).  Results are compared as bit patterns:
f2bits(cpu.fr[0]) on the emulator side vs the oracle's %08X of the return
value.  The ROM returns its float in FR0.

Usage:  python3 harness_saturate_low.py [N]     (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402
from sh2emu import bits2f, f2bits, ts  # noqa: E402  (tools/ already on sys.path via common)

ADDR = 0x23E4
N_DEFAULT = 20000
SEED = ADDR          # fixed, reproducible

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORACLE_DIR = '/tmp/rx8-recon-saturate_low'
ORACLE = os.path.join(ORACLE_DIR, 'oracle')

INF = float('inf')


def build_oracle():
    """Compile the reconstructed source + this harness's own oracle.

    Unlike common.build_oracle() (which links the shared host_oracle.c plus
    the fixed SRC_FILES list), this compiles ONLY the file under test, so the
    oracle exercises no unrelated code.
    """
    os.makedirs(ORACLE_DIR, exist_ok=True)
    cmd = ['cc', '-O2', '-Wall', '-Wextra',
           '-I', 'include', '-I', 'src',
           'tests/oracle_saturate_low.c',
           'src/rx8_saturate_low.c',
           '-o', ORACLE]
    subprocess.run(cmd, cwd=SAMPLES, check=True)
    return ORACLE


def b(v):
    """32-bit IEEE-754 pattern of a Python float (rounds to single first)."""
    return f2bits(v)


# Edge vectors as (sig, lower) floats, spanning below/at/above the bound.
EDGE = [
    # below the bound -> returns `lower`
    (1.0, 2.0), (-1.0, 1.0), (-3.0, -2.0), (0.0, 1.0), (-1e30, 1e30),
    # exactly at the bound (sig == lower) -> strict > is false, returns `lower`
    (2.0, 2.0), (-2.0, -2.0), (0.0, 0.0), (-0.0, 0.0), (1e30, 1e30),
    # above the bound -> returns `sig`
    (3.0, 2.0), (1.0, -1.0), (-2.0, -3.0), (1.0, 0.0), (1e30, -1e30),
    # signed-zero hygiene: -0.0 and 0.0 are equal, so both pick `lower`
    (0.0, -0.0), (-0.0, -0.0),
    # extremes of the single-precision range
    (3.4028235e38, -3.4028235e38), (-3.4028235e38, -3.4028234e38),
    (1.4012985e-45, 0.0), (0.0, 1.4012985e-45), (-1.4012985e-45, -1.4012985e-45),
    # infinities
    (INF, 1.0), (1.0, INF), (-INF, -1.0), (-1.0, -INF), (INF, INF),
    (INF, -INF), (-INF, INF), (-INF, -INF),
]

# NaNs are intentionally excluded: fcmp unordered semantics are IEEE-clear
# (both sides fall through to returning `lower`), but the emulator's NaN
# path is not exercised elsewhere and is out of scope for this lift.


def rfl(rng):
    """Random finite single-precision value from practical sensor ranges
    (mirrors the c/tests generator: mixed small/wide magnitudes)."""
    return ts(rng.choice([rng.uniform(-1e4, 1e4), rng.uniform(-2, 2),
                          rng.uniform(0, 300), rng.uniform(-300, 0)]))


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(SEED)

    vectors = [(b(s), b(l)) for s, l in EDGE] \
        + [(b(rfl(rng)), b(rfl(rng))) for _ in range(n)]

    # (a) ROM behaviour via the emulator, (b) host-C on the same inputs.
    emu = []
    for s, l in vectors:
        cpu.call(ADDR, fr={4: bits2f(s), 5: bits2f(l)})
        emu.append(f2bits(cpu.fr[0]))

    lines = ['f32 %08X %08X' % (s, l) for s, l in vectors]
    host = [int(x, 16) for x in run_oracle(oracle, lines)]

    # (c) compare bit-exact.
    mismatches = []
    for i, ((s, l), e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append('vec#%d sig=0x%08X lower=0x%08X ROM=0x%08X C=0x%08X'
                              % (i, s, l, e, h))
            if len(mismatches) >= 5:
                break

    report('saturateLow', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
