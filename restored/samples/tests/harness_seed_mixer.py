#!/usr/bin/env python3
"""
harness_seed_mixer.py — equivalence of rx8_immo_seed_mixer @0x366B8.

Restored source: samples/src/rx8_immo_seed_mixer.c
Verified lift   : c/seed_mixer.c (IDA-ai symbol `bitwise_field_encoder_366B8`).

Pure function of two 32-bit words (EEPROM key word + rolling code).  The
emulator is run with r4 = key word, r5 = rolling word; the result is r0.

Usage:  python3 harness_seed_mixer.py [N]     (default N = 100000)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import build_oracle, load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0x366B8
N_DEFAULT = 100000

# Edges that exercise the byte rebuild, the 6-bit swap, the negation and the
# fold in isolation (all-bit patterns, byte-aligned patterns, all-zeros).
EDGE = [
    (0x00000000, 0x00000000),
    (0xFFFFFFFF, 0xFFFFFFFF),
    (0xFFFFFFFF, 0x00000000),
    (0x00000000, 0xFFFFFFFF),
    (0x0000FF00, 0x000000FF),
    (0x00FF00FF, 0xFF00FF00),
    (0x0FE00000, 0x00000000),   # bits 5..10 in key[15:8]
    (0x001FC000, 0x00000000),   # bits 14..19 in key[7:0]
    (0x00100000, 0x00000000),   # bit 20 fold
    (0xABCDEF01, 0x12345678),
    (0xDEADBEEF, 0xCAFEBABE),
    (0x6D7A64D0, 0x00000278),   # plausible key/rolling values
]


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(0x60E1D400)

    vectors = list(EDGE) + [(rng.getrandbits(32), rng.getrandbits(32))
                            for _ in range(n)]

    emu = [cpu.call(ADDR, r4=a, r5=b) for a, b in vectors]
    lines = ['mix %08X %08X' % (a, b) for a, b in vectors]
    host = [int(x, 16) for x in run_oracle(oracle, lines)]

    mismatches = []
    for i, ((a, b), e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d r4=0x%08X r5=0x%08X ROM=0x%08X C=0x%08X' % (i, a, b, e, h))
            if len(mismatches) >= 5:
                break

    report('seed_mixer', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
