#!/usr/bin/env python3
"""
harness_checksum_complement_add.py — equivalence of
rx8_checksum_complement_add @0x2034.

Reconstructed source: samples/src/rx8_checksum_complement_add.c
Verified lift   : c/checksum_complement_add.c

Computes the checksum residual of a 32-bit redundant cell:
    (~value - (value >> 16)) & 0xFFFF
Residual 0 => the (data, ~data) pair is self-consistent.  Pure function — the
ROM leaf reads the cell through the pointer in r4 (`mov.l @r4,r3`), computes
in registers, and is 7 instructions long; the caller-side load is reproduced
here on the emulator side by placing the big-endian cell bytes in RAM.

Procedure (Track-A pattern):
  1. build THIS harness's own host oracle (it compiles ONLY
     rx8_checksum_complement_add.c — not the shared host_oracle.c),
  2. N random uint32_t values + edge cases,
  3. run the ROM bytes @0x2034 in tools/sh2emu.py (cell stored at r4),
  4. run the host C on the same inputs,
  5. compare — 0 mismatches required.

Usage:  python3 harness_checksum_complement_add.py [N]   (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0x2034
N_DEFAULT = 20000
SEED = ADDR          # fixed, reproducible

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORACLE_DIR = '/tmp/rx8-recon-checksum_complement_add'
ORACLE = os.path.join(ORACLE_DIR, 'oracle')

# RAM cell used for the caller-side `*r4` load on the emulator side.
CELL_ADDR = 0x2000

EDGE = [
    0x00000000,  # zero cell
    0x00000001,  # lowest set bit
    0x00007FFF,  # max positive 16-bit data
    0x00008000,  # sign-bit data, complement 0x7FFF
    0x0000FFFF,  # complement of data is 0x0000
    0x00010000,  # data=0x0001 / comp=0x0000 (upper half only)
    0x0001FFFE,  # valid pair: (0x0001 << 16) | ~0x0001  -> residual 0
    0x7FFF8000,  # valid pair: (0x7FFF << 16) | ~0x7FFF  -> residual 0
    0x80007FFF,  # valid pair: (0x8000 << 16) | ~0x8000  -> residual 0
    0xFFFF0000,  # valid pair: (0xFFFF << 16) | ~0xFFFF  -> residual 0
    0x7FFFFFFF,  # INT32_MAX
    0x80000000,  # INT32_MIN
    0xFFFFFFFF,  # all ones (complement == 0)
    0xAAAA5555,  # happens to produce residual 0 (per c/tests)
    0x1234ABCD,  # arbitrary
    0xDEADBEEF,  # arbitrary
]


def cell_bytes(val):
    """Big-endian 32-bit representation of the cell, as stored at CELL_ADDR
    (matches the byte order of the RAM load in c/tests/test_checksum_complement_add.py)."""
    return {CELL_ADDR + 0: (val >> 24) & 0xFF,
            CELL_ADDR + 1: (val >> 16) & 0xFF,
            CELL_ADDR + 2: (val >> 8) & 0xFF,
            CELL_ADDR + 3: val & 0xFF}


def build_oracle():
    """Compile the reconstructed source + this harness's own oracle.

    Unlike common.build_oracle() (which links the shared host_oracle.c plus
    the fixed SRC_FILES list), this compiles ONLY the file under test, so the
    oracle exercises no unrelated code.
    """
    os.makedirs(ORACLE_DIR, exist_ok=True)
    cmd = ['cc', '-O2', '-Wall', '-Wextra',
           '-I', 'include', '-I', 'src',
           'tests/oracle_checksum_complement_add.c',
           'src/rx8_checksum_complement_add.c',
           '-o', ORACLE]
    subprocess.run(cmd, cwd=SAMPLES, check=True)
    return ORACLE


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(SEED)

    vectors = list(EDGE) + [rng.getrandbits(32) for _ in range(n)]

    # (a) ROM behaviour via the emulator (cell in RAM, r4 -> pointer),
    #     (b) host-C on the same numeric value.
    emu = [cpu.call(ADDR, r4=CELL_ADDR, ram=cell_bytes(v)) for v in vectors]
    lines = ['sum %08X' % v for v in vectors]
    host = [int(x, 16) for x in run_oracle(oracle, lines)]

    # (c) compare.
    mismatches = []
    for i, (v, e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append('vec#%d val=0x%08X ROM=0x%04X C=0x%04X'
                              % (i, v, e, h))
            if len(mismatches) >= 5:
                break

    report('checksum_complement_add', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
