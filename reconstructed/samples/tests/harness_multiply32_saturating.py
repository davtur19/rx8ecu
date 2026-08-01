#!/usr/bin/env python3
"""
harness_multiply32_saturating.py — equivalence of
rx8_multiply32_saturating @0x231C.

Reconstructed source: samples/src/rx8_multiply32_saturating.c
Verified lift   : c/math_primitives.c -> multiply32Bit_saturating @0x231C

Calling convention: standard SH-2 ABI — a in r4, b in r5, result in r0.
The function uses dmuls.l / rotcr (signed 64-bit multiply in the MAC
register pair and the rotate-with-carry shift chain), both of which
tools/sh2emu.py implements.

Procedure (Track-A pattern):
  1. build THIS sample's own host oracle (system gcc) — the sample is not
     in common.py's SRC_FILES, so it cannot reuse build_oracle();
  2. EDGE vectors (0/1/-1, exact INT32_MAX/MIN result boundaries, and
     product-overflow pairs on both sides of the clamp) + N random
     int32 pairs spanning the full range;
  3. run the ACTUAL ROM bytes @0x231C in tools/sh2emu.py on those vectors;
  4. run the host C on the same vectors and compare — 0 mismatches required.

Usage:  python3 harness_multiply32_saturating.py [N]   (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROOT, SAMPLES, ROM_PATH, make_rng, report, run_oracle  # noqa: E402
from sh2emu import SH2  # noqa: E402  (ROOT/tools is on sys.path via common)

ADDR = 0x231C
N_DEFAULT = 20000

ORACLE_SRC = os.path.join(SAMPLES, 'tests', 'oracle_multiply32_saturating.c')
SAMPLE_SRC = os.path.join(SAMPLES, 'src', 'rx8_multiply32_saturating.c')
BUILD_DIR = os.path.join('/tmp', 'rx8-recon-multiply32_saturating')
ORACLE = os.path.join(BUILD_DIR, 'oracle')

# Trivial values, the exact INT32_MAX/MIN result boundaries (product of
# 0x7FFFFFFF or 0x80000000 with 0x00010000 == 2^16), and product-overflow
# pairs that force the clamp on both the positive and the negative side.
EDGE = [
    # 0 / 1 / -1
    (0x00000000, 0x00000000),
    (0x00000001, 0x00000001),
    (0x00000001, 0xFFFFFFFF),   # 1 * -1
    (0xFFFFFFFF, 0xFFFFFFFF),   # -1 * -1
    (0x00008000, 0x00008000),   # 1.0 * 1.0 in Q16.16 = 0x4000
    # exact result boundaries (fits, no clamp)
    (0x7FFFFFFF, 0x00010000),   # product >> 16 == +INT32_MAX exactly
    (0x80000000, 0x00010000),   # product >> 16 == -INT32_MIN exactly
    (0x80000000, 0xFFFFFFFF),   # INT32_MIN * -1 -> +0x8000 (fits)
    # just past the boundaries (clamp engaged)
    (0x7FFFFFFF, 0x00010001),   # +INT32_MAX overflow
    (0x80000000, 0x00020000),   # -INT32_MIN overflow
    # extremes / big-magnitude pairs
    (0x7FFFFFFF, 0x7FFFFFFF),
    (0x80000000, 0x80000000),   # positive product, clamps +MAX
    (0x7FFFFFFF, 0x80000000),   # negative product, clamps -MIN
    (0x40000000, 0x40000000),   # positive product, clamps +MAX
    (0x12345678, 0x9ABCDEF0),
    (0xDEADBEEF, 0xCAFEBABE),
]


def build_oracle(cc='cc'):
    """Compile this sample's oracle (standalone; not in common.py's SRC_FILES)."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           ORACLE_SRC, SAMPLE_SRC, '-o', ORACLE]
    subprocess.run(cmd, check=True)
    return ORACLE


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = SH2(open(ROM_PATH, 'rb').read())
    oracle = build_oracle()
    rng = make_rng(0x60E1D400)

    vectors = list(EDGE) + [(rng.getrandbits(32), rng.getrandbits(32))
                            for _ in range(n)]

    # (a) ROM behaviour via the emulator, (b) host-C on the same inputs.
    emu = [cpu.call(ADDR, r4=a, r5=b) for a, b in vectors]
    lines = ['mul %08X %08X' % (a, b) for a, b in vectors]
    host = [int(x, 16) for x in run_oracle(oracle, lines)]

    # (c) compare.
    mismatches = []
    for i, ((a, b), e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d a=0x%08X b=0x%08X ROM=0x%08X C=0x%08X' % (i, a, b, e, h))
            if len(mismatches) >= 5:
                break

    report('multiply32Saturating', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
