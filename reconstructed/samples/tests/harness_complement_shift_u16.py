#!/usr/bin/env python3
"""
harness_complement_shift_u16.py — equivalence of rx8_complement_shift_u16 @0x2430.

Reconstructed source: samples/src/rx8_complement_shift_u16.c
Verified lift   : c/complement_shift_u16.c

Packs a 16-bit value with its ones' complement into a 32-bit word
(redundant-storage encoding).  Pure function — no RAM, no FPU: the leaf reads
r4, returns r0, and is 8 instructions long.

Procedure (Track-A pattern):
  1. build THIS harness's own host oracle (it compiles ONLY
     rx8_complement_shift_u16.c — not the shared host_oracle.c),
  2. N random uint16_t values + edge cases,
  3. run the ROM bytes @0x2430 in tools/sh2emu.py,
  4. run the host C on the same inputs,
  5. compare — 0 mismatches required.

Usage:  python3 harness_complement_shift_u16.py [N]     (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0x2430
N_DEFAULT = 20000
SEED = ADDR          # fixed, reproducible

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORACLE_DIR = '/tmp/rx8-recon-complement_shift_u16'
ORACLE = os.path.join(ORACLE_DIR, 'oracle')

EDGE = [
    0x00000000,  # zero
    0x00000001,  # lowest set bit
    0x00007FFF,  # max positive 16-bit
    0x00008000,  # sign bit alone
    0x00008001,  # sign bit + 1
    0x0000FFFE,  # all but bit 0 set
    0x0000FFFF,  # all ones (complement == 0x0000)
    0x00001234,  # arbitrary
    0x0000ABCD,  # arbitrary
    # Upper-bit sets: the ROM's leading `extu.w` truncates to the low 16 bits,
    # so these must behave exactly like their low halves.
    0x0001FFFF,
    0x1234ABCD,
    0xFFFFFFFF,
    0x80000000,
]


def build_oracle():
    """Compile the reconstructed source + this harness's own oracle.

    Unlike common.build_oracle() (which links the shared host_oracle.c plus
    the fixed SRC_FILES list), this compiles ONLY the file under test, so the
    oracle exercises no unrelated code.
    """
    os.makedirs(ORACLE_DIR, exist_ok=True)
    cmd = ['cc', '-O2', '-Wall', '-Wextra',
           '-I', 'include', '-I', 'src',
           'tests/oracle_complement_shift_u16.c',
           'src/rx8_complement_shift_u16.c',
           '-o', ORACLE]
    subprocess.run(cmd, cwd=SAMPLES, check=True)
    return ORACLE


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(SEED)

    vectors = list(EDGE) + [rng.getrandbits(16) for _ in range(n)]

    # (a) ROM behaviour via the emulator, (b) host-C on the same inputs.
    emu = [cpu.call(ADDR, r4=v) for v in vectors]
    lines = ['u16 %08X' % v for v in vectors]
    host = [int(x, 16) for x in run_oracle(oracle, lines)]

    # (c) compare.
    mismatches = []
    for i, (v, e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append('vec#%d val=0x%08X ROM=0x%08X C=0x%08X'
                              % (i, v, e, h))
            if len(mismatches) >= 5:
                break

    report('complement_shift_u16', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
