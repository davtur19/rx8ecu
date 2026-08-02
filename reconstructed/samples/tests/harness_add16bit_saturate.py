#!/usr/bin/env python3
"""
harness_add16bit_saturate.py — equivalence of rx8_add16bit_saturate @0x2460.

Reconstructed source: samples/src/rx8_add16bit_saturate.c
Verified lift   : c/add16bitSaturate.c  (`add16bitSaturate_ADD1_ADD2`, equinox311
                  hand Ghidra RE; byte-identical in 60E1D400 / 60E0FC00).

Calling convention: non-ABI integer leaf — add1 in r4, add2 in r5, result in r0
(no stack frame, no RAM side-effects).  The arguments sit in the first two
argument registers, so the ROM bytes are invoked with the plain
SH2.call(0x2460, r4=..., r5=...) entry point — the same choice as the sibling
math-primitive leaves (harness_add_s32.py, harness_math_primitives_2490.py).
The emulator `extu.w`s both registers to 16 bits; the oracle receives the same
raw 32-bit values and truncates them with the uint16_t parameters, so the
masking paths are exercised on both sides.

Semantics under test:  min(add1 + add2, 0xFFFF)  — a saturated unsigned 16-bit
add (clamp via `cmp/hs` against the 0x0000FFFF literal at the ROM's pool
@0x2474).

Procedure (Track-A pattern):
  1. build host oracle (system gcc; own binary, common.build_oracle untouched),
  2. edge vectors + N random (seeded) u16 pairs,
  3. run the ROM bytes @0x2460 in tools/sh2emu.py on the same vectors,
  4. run the host C on the same vectors,
  5. compare bit-exact on the 16-bit result — 0 mismatches required.

Usage:  python3 harness_add16bit_saturate.py [N]   (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402
# common.py already put <repo>/tools on sys.path (its sh2emu import).

ADDR = 0x2460
N_DEFAULT = 20000

# Edge vectors: (add1, add2) raw 32-bit r4/r5 values.  Zero, 1, boundaries,
# max operands, the clamp threshold (sum >= 0xFFFF), overflow wraps, bit-15
# sign flips, and extu.w masking cases (high 16 bits must be dropped before
# the add — the uint16_t parameters mirror that truncation on the host side).
EDGE = [
    # Zero and small.
    (0x00000000, 0x00000000),
    (0x00000001, 0x00000000),
    (0x00000000, 0x00000001),
    (0x00000001, 0x00000001),
    (0x00000002, 0x00000003),
    # Max operands.
    (0x0000FFFF, 0x00000000),
    (0x00000000, 0x0000FFFF),
    (0x0000FFFF, 0x0000FFFF),
    (0x0000FFFF, 0x00007FFF),
    (0x00007FFF, 0x0000FFFF),
    (0x00007FFF, 0x00007FFF),
    # Clamp threshold boundary: sum == 0xFFFF exactly (clamped, same value),
    # sum just below it (kept raw) and just above it (clamped).
    (0x0000FFFE, 0x00000000),   # 0xFFFE (no clamp)
    (0x0000FFFE, 0x00000001),   # 0xFFFF (threshold)
    (0x0000FFFE, 0x00000002),   # clamped
    (0x0000FFFF, 0x00000000),   # 0xFFFF (threshold)
    (0x0000FFFD, 0x00000002),   # 0xFFFF (threshold)
    (0x0000FFFC, 0x00000002),   # 0xFFFE (no clamp)
    # Overflow wraps (32-bit add would exceed 16 bits).
    (0x00008000, 0x00008000),
    (0x00008000, 0x00007FFF),
    (0x00007FFF, 0x00008000),
    (0x00008000, 0x0000FFFF),
    (0x0000FFFF, 0x00000001),
    (0x00000001, 0x0000FFFF),
    # Bit-15 sign flips (unsigned, but the boundary the ABI callers care about).
    (0x00008000, 0x00000001),
    (0x00007FFF, 0x00000001),
    (0x00000001, 0x00008000),
    (0x0000FFFF, 0x00008000),
    # extu.w masking: high 16 bits of r4/r5 must be dropped before the add.
    (0x0001FFFF, 0x00000001),   # 0xFFFF + 1     -> clamp 0xFFFF
    (0x0001FFFE, 0x00000002),   # 0xFFFE + 2     -> clamp 0xFFFF
    (0x00010001, 0x00010000),   # 0x0001 + 0x0000 -> 0x0001
    (0xFFFFFFFF, 0xFFFFFFFF),   # 0xFFFF + 0xFFFF -> clamp 0xFFFF
    (0x00010000, 0x00000000),   # 0x0000 + 0x0000 -> 0x0000
    (0x0000FFFF, 0xFFFF0000),   # 0xFFFF + 0x0000 -> 0xFFFF
    (0xDEADBEEF, 0x12345678),   # 0xBEEF + 0x5678 -> 0x11667 -> clamp 0xFFFF
]

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = os.path.join('/tmp', 'rx8-recon-add16bit_saturate')
ORACLE = os.path.join(BUILD_DIR, 'oracle')


def build_oracle():
    """Compile THIS sample + its own oracle (do NOT touch common.build_oracle)."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    cmd = ['cc', '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_add16bit_saturate.c'),
           os.path.join(SAMPLES, 'src', 'rx8_add16bit_saturate.c'),
           '-lm', '-o', ORACLE]
    subprocess.run(cmd, check=True)
    return ORACLE


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(0x60E1D400)

    vectors = list(EDGE) + [(rng.getrandbits(32), rng.getrandbits(32))
                            for _ in range(n)]

    # (a) ROM behaviour via the emulator (r4=add1, r5=add2; result in r0).
    emu = [cpu.call(ADDR, r4=a, r5=b) & 0xFFFF for a, b in vectors]

    # (b) host-C on the same inputs (raw 32-bit values; the uint16_t params
    #     truncate them exactly like the ROM's extu.w).
    lines = ['add %08X %08X' % (a, b) for a, b in vectors]
    host = [int(x, 16) for x in run_oracle(oracle, lines)]

    # (c) compare bit-exact.
    mismatches = []
    for i, ((a, b), e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d add1=0x%08X add2=0x%08X ROM=0x%04X C=0x%04X'
                % (i, a, b, e, h))
            if len(mismatches) >= 5:
                break

    report('add16bitSaturate', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
