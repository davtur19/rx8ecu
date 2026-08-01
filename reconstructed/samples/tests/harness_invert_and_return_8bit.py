#!/usr/bin/env python3
"""
harness_invert_and_return_8bit.py — equivalence of rx8_invert_and_return_8bit
@0x2044.

Reconstructed source: samples/src/rx8_invert_and_return_8bit.c
Verified lift   : c/math_primitives.c (invertAndReturn_8bit_ADDR @0x2044).

Procedure (Track-A pattern):
   1. build a host oracle from tests/oracle_invert_and_return_8bit.c +
      src/rx8_invert_and_return_8bit.c (system gcc; the oracle only reads
      stdin vectors and calls the reconstructed function),
   2. N random (hi,lo) pairs + edge cases (incl. 8-bit masking),
   3. run the ROM bytes @0x2044 in tools/sh2emu.py with the pair stored at a
      scratch RAM cell,
   4. run the host C on the same inputs,
   5. compare — 0 mismatches required.

Usage:  python3 harness_invert_and_return_8bit.py [N]     (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report  # noqa: E402

ADDR = 0x2044
N_DEFAULT = 20000

CELL_ADDR = 0xFFFF9000  # scratch RAM cell holding the (hi, lo) pair

# Edge cases: exact complements (residual must be 0), 0/1/halfway/byte max,
# and values with upper bits set (both sides must mask down to 8 bits).
EDGE = [
    (0x00, 0x00),          # ~(0+0)   -> 0xFF
    (0x01, 0x00),          # ~(1+0)   -> 0xFE
    (0x7F, 0x80),          # exact complement -> 0x00
    (0x80, 0x7F),          # exact complement -> 0x00
    (0xFF, 0x00),          # exact complement -> 0x00
    (0x00, 0xFF),          # exact complement -> 0x00
    (0x80, 0x80),          # ~(0x100) -> 0xFF
    (0xFF, 0xFF),          # ~(0x1FE) -> 0x01
    (0x7F, 0x7F),          # ~(0xFE)  -> 0x01
    (0x100, 0x00),         # hi masked to 0x00 -> 0xFF
    (0x1FF, 0xFF),         # hi masked to 0xFF, lo 0xFF -> 0x01
    (0x00, 0x100),         # lo masked to 0x00 -> 0xFF
    (0xABCD, 0x1234),      # both upper bits set
    (0xDEAD, 0xBEEF),      # both upper bits set
]


def build_oracle(cc='cc'):
    """Compile the reconstructed source + its oracle into a host binary."""
    tests = os.path.dirname(os.path.abspath(__file__))
    samples = os.path.dirname(tests)
    bdir = os.path.join('/tmp', 'rx8-recon-invert_and_return_8bit')
    os.makedirs(bdir, exist_ok=True)
    oracle = os.path.join(bdir, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(samples, 'include'),
           '-I', os.path.join(samples, 'src'),
           os.path.join(tests, 'oracle_invert_and_return_8bit.c'),
           os.path.join(samples, 'src', 'rx8_invert_and_return_8bit.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def run_oracle(oracle, vectors):
    """Feed vectors (list of string lines) to the oracle, return output lines."""
    proc = subprocess.run([oracle], input='\n'.join(vectors) + '\n',
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError('host oracle failed:\n' + proc.stderr)
    lines = proc.stdout.splitlines()
    if len(lines) != len(vectors):
        raise RuntimeError(
            'oracle produced %d outputs for %d vectors' % (len(lines), len(vectors)))
    return lines


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(0x60E1D400)

    vectors = list(EDGE) + [(rng.getrandbits(32), rng.getrandbits(32))
                            for _ in range(n)]

    # (a) ROM behaviour via the emulator, (b) host-C on the same inputs.
    emu = [cpu.call(ADDR, r4=CELL_ADDR,
                    ram={CELL_ADDR: h & 0xFF, CELL_ADDR + 1: l & 0xFF}) & 0xFF
           for h, l in vectors]
    lines = ['u8 %08X %08X' % (h, l) for h, l in vectors]
    host = [int(x, 16) for x in run_oracle(oracle, lines)]

    # (c) compare.
    mismatches = []
    for i, ((h, l), e, r) in enumerate(zip(vectors, emu, host)):
        if e != r:
            mismatches.append(
                'vec#%d hi=0x%X lo=0x%X ROM=0x%02X C=0x%02X' % (i, h, l, e, r))
            if len(mismatches) >= 5:
                break

    report('invertAndReturn_8bit', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
