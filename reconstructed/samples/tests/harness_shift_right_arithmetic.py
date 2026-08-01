#!/usr/bin/env python3
"""
harness_shift_right_arithmetic.py — equivalence of
rx8_shift_right_arithmetic @0x43C8.

Reconstructed source: samples/src/rx8_shift_right_arithmetic.c
Verified lift   : c/shift_right_arithmetic_r0.c

Calling convention (SH-2 shift family): value in r0, shift count in r1,
result in r0 — NOT the r4/r5 ABI.  tools/sh2emu.py's call() only seeds
r4..r7, so this harness drives the emulator through the SH2R01 wrapper
below, which re-injects r0/r1 into the register bank (sh2emu.py untouched).

Procedure (Track-A pattern):
  1. build THIS sample's own host oracle (system gcc) — the sample is not
     in common.py's SRC_FILES, so it cannot reuse build_oracle();
  2. EDGE vectors (negative values; counts 0/1/15/16/17/24/31/32/33; cnt<0)
     + N random (val, cnt) with cnt in [-40, 72] to sweep every clamp
     bucket the ROM implements;
  3. run the ACTUAL ROM bytes @0x43C8 in tools/sh2emu.py on those vectors;
  4. run the host C on the same vectors and compare — 0 mismatches required.

Usage:  python3 harness_shift_right_arithmetic.py [N]   (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROOT, SAMPLES, ROM_PATH, make_rng, report, run_oracle  # noqa: E402
from sh2emu import SH2  # noqa: E402  (ROOT/tools is on sys.path via common)

ADDR = 0x43C8
N_DEFAULT = 20000

ORACLE_SRC = os.path.join(SAMPLES, 'tests', 'oracle_shift_right_arithmetic.c')
SAMPLE_SRC = os.path.join(SAMPLES, 'src', 'rx8_shift_right_arithmetic.c')
BUILD_DIR = os.path.join('/tmp', 'rx8-recon-shift_right_arithmetic')
ORACLE = os.path.join(BUILD_DIR, 'oracle')


class SH2R01(SH2):
    """SH2 whose call() also seeds r0/r1.

    The shift helpers (0x43C8 and siblings) follow the SH-2 shift-family
    convention: operand in r0, count in r1, result back in r0.  The base
    class call() resets the register bank to zero and only seeds r4..r7, so
    this wrapper intercepts the reset (`self.r = [0]*16`) and immediately
    re-injects the r0/r1 operands.  All execution still happens inside the
    original, unmodified SH2.call().
    """
    _r0_seed = 0
    _r1_seed = 0

    def __setattr__(self, name, value):
        if name == 'r':
            super().__setattr__(name, value)
            value[0] = self._r0_seed
            value[1] = self._r1_seed
        else:
            super().__setattr__(name, value)

    def call(self, entry, r0=0, r1=0, **kw):
        self._r0_seed = r0 & 0xFFFFFFFF
        self._r1_seed = r1 & 0xFFFFFFFF
        return super().call(entry, **kw)


def build_oracle(cc='cc'):
    """Compile this sample's oracle (standalone; not in common.py's SRC_FILES)."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           ORACLE_SRC, SAMPLE_SRC, '-o', ORACLE]
    subprocess.run(cmd, check=True)
    return ORACLE


# Negative values across every count bucket the ROM implements, plus the
# exact counts from the task spec (0, 1, 15, 16, 17, 31, 32, 33) and cnt<0.
EDGE = [
    # cnt < 0: value returned unchanged
    (0x80000000, -1), (0xFFFFFFFF, -1), (0x00000001, -1),
    (0x80000000, -20), (0x12345678, -1),
    # cnt = 0
    (0x00000000, 0), (0x00000001, 0), (0x80000000, 0), (0xFFFFFFFF, 0),
    # cnt = 1
    (0x00000001, 1), (0x80000000, 1), (0x7FFFFFFF, 1), (0xFFFFFFFF, 1),
    # small counts: shar-chain bucket 0..8 and the 9..23 walk
    (0x80000000, 7), (0x80000000, 8), (0xFFFFFF00, 8),
    (0x80000000, 9), (0x80000000, 15), (0xFFFFFFFF, 15), (0x7FFFFFFF, 15),
    # cnt = 16 / 17
    (0x80000000, 16), (0xFFFFFFFF, 16), (0x00000001, 16), (0xFFFF00FF, 16),
    (0x80000000, 17), (0xFFFFFFFF, 17), (0x00000001, 17), (0x7FFFFFFF, 17),
    # upper bucket 24..31 (jump-table sign-extension tails)
    (0x80000000, 23), (0x80000000, 24), (0x80000000, 25), (0x80000000, 31),
    (0xFF00FFFF, 24), (0x80800000, 25), (0x80808080, 31),
    (0x7FFFFFFF, 24), (0x7FFFFFFF, 31), (0x00000001, 31),
    # cnt = 32 (clamp) and beyond
    (0x80000000, 32), (0x7FFFFFFF, 32), (0xFFFFFFFF, 32), (0x00000001, 32),
    (0x80000000, 33), (0x7FFFFFFF, 33), (0xFFFFFFFF, 33), (0x00000001, 33),
    (0x80000000, 40), (0x00000000, 33),
]


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = SH2R01(open(ROM_PATH, 'rb').read())
    oracle = build_oracle()
    rng = make_rng(0x60E1D400)

    vectors = list(EDGE) + [(rng.getrandbits(32), rng.randint(-40, 72))
                            for _ in range(n)]

    # (a) ROM behaviour via the emulator, (b) host-C on the same inputs.
    emu = [cpu.call(ADDR, r0=v, r1=c) for v, c in vectors]
    lines = ['sra %08X %08X' % (v, c) for v, c in vectors]
    host = [int(x, 16) for x in run_oracle(oracle, lines)]

    # (c) compare.
    mismatches = []
    for i, ((v, c), e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d val=0x%08X cnt=%d ROM=0x%08X C=0x%08X' % (i, v, c, e, h))
            if len(mismatches) >= 5:
                break

    report('shiftRightArithmetic', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
