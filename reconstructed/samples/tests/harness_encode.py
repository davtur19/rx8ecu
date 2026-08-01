#!/usr/bin/env python3
"""
harness_encode.py — equivalence of rx8_encode @0x2420.

Reconstructed source: samples/src/rx8_encode.c
Verified lift   : c/math_primitives.c (same address; value/complement byte
                  encoder enc8(x) = (x<<8) | ~x, only the low byte of the
                  argument is used — the ROM starts with `extu.b`).

Procedure (Track-A pattern):
  1. build a host oracle for THIS function alone (system gcc),
  2. N random uint32 inputs (full 32-bit range, so the `extu.b` masking is
     exercised) + edge cases,
  3. run the ROM bytes @0x2420 in tools/sh2emu.py,
  4. run the host C on the same inputs,
  5. compare — 0 mismatches required.

Usage:  python3 harness_encode.py [N]     (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402
from common import ROOT, SAMPLES  # noqa: E402

ADDR = 0x2420
N_DEFAULT = 20000

# Binary directory for this function's oracle (kept separate from the shared
# build dir so we never touch the other samples' artifacts).
BUILD_DIR = os.path.join('/tmp', 'rx8-recon-encode')
ORACLE = os.path.join(BUILD_DIR, 'oracle')

EDGE = [
    0x00000000,
    0x00000001,
    0x0000007F,
    0x00000080,             # top bit of the byte
    0x000000FF,
    0x00000100,             # above byte range -> wraps via extu.b
    0x0000017F,             # high byte nonzero, low byte 0x7F
    0x0000FFFF,             # low byte 0xFF
    0x00010000,             # high bits only
    0x12345678,
    0xDEADBEEF,             # upper bits must be ignored
    0xFFFFFFFF,
]


def build_oracle():
    """Compile rx8_encode.c + oracle_encode.c into a host binary (this
    function's own oracle; common.build_oracle only builds the shared set)."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    cmd = ['cc', '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_encode.c'),
           os.path.join(SAMPLES, 'src', 'rx8_encode.c'),
           '-o', ORACLE]
    subprocess.run(cmd, check=True)
    return ORACLE


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(0x60E1D400)

    vectors = list(EDGE) + [rng.getrandbits(32) for _ in range(n)]

    # (a) ROM behaviour via the emulator, (b) host-C on the same inputs.
    emu = [cpu.call(ADDR, r4=x) & 0xFFFF for x in vectors]
    lines = ['enc %08X' % x for x in vectors]
    host = [int(x, 16) for x in run_oracle(oracle, lines)]

    # (c) compare.
    mismatches = []
    for i, (x, e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d x=0x%08X ROM=0x%04X C=0x%04X' % (i, x, e, h))
            if len(mismatches) >= 5:
                break

    report('encode', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
