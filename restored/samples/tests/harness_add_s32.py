#!/usr/bin/env python3
"""
harness_add_s32.py — equivalence of rx8_add_s32_saturate @0x2304.

Restored source: samples/src/rx8_s32_saturate.c
Verified lift   : c/addS32Saturate.c (IDA mislabels the ROM symbol
                  `fpu_compare_float`; the code is an `addv`-based saturating
                  signed 32-bit add).

Procedure (Track-A pattern):
  1. build host oracle (system gcc),
  2. N random int32 pairs + edge cases,
  3. run the ROM bytes @0x2304 in tools/sh2emu.py,
  4. run the host C on the same inputs,
  5. compare — 0 mismatches required.

Usage:  python3 harness_add_s32.py [N]     (default N = 100000)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import build_oracle, load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0x2304
N_DEFAULT = 100000

EDGE = [
    (0x00000000, 0x00000000),
    (0x7FFFFFFF, 0x00000000),
    (0x7FFFFFFF, 0x00000001),   # positive overflow
    (0x7FFFFFFF, 0x7FFFFFFF),   # positive overflow
    (0x80000000, 0x00000000),
    (0x80000000, 0xFFFFFFFF),   # negative overflow
    (0xFFFFFFFF, 0xFFFFFFFF),   # negative overflow
    (0x7FFFFFFF, 0xFFFFFFFF),   # INT32_MAX + (-1)
    (0x80000000, 0x80000000),   # negative overflow
    (0x40000000, 0x40000000),   # exact 0x80000000
    (0xC0000000, 0x40000000),   # exact 0x00000000
    (0xABCDEF01, 0x12345678),
    (0xDEADBEEF, 0xCAFEBABE),
]


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(0x60E1D400)

    vectors = list(EDGE) + [(rng.getrandbits(32), rng.getrandbits(32))
                            for _ in range(n)]

    # (a) ROM behaviour via the emulator, (b) host-C on the same inputs.
    emu = [cpu.call(ADDR, r4=a, r5=b) for a, b in vectors]
    lines = ['s32 %08X %08X' % (a, b) for a, b in vectors]
    host = [int(x, 16) for x in run_oracle(oracle, lines)]

    # (c) compare.
    mismatches = []
    for i, ((a, b), e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d a=0x%08X b=0x%08X ROM=0x%08X C=0x%08X' % (i, a, b, e, h))
            if len(mismatches) >= 5:
                break

    report('addS32Saturate', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
