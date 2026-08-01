#!/usr/bin/env python3
"""
harness_purge_state_query.py — equivalence of rx8_purge_state_query @0xF5DC.

Reconstructed source: samples/src/rx8_purge_state_query.c
Verified lift   : c/purge_state_query.c (6-byte leaf returning RAM[0xFFFFA4B1]).

The function reads a single fixed RAM byte, so the equivalence check is:

  - emulator side: seed the byte at 0xFFFFA4B1 in the sparse `ram` overlay,
    call the ROM entry and mask r0 to 8 bits (`mov.b @r3,r0` sign-extends);
  - host side: this harness compiles its OWN oracle
    (tests/oracle_purge_state_query.c) which mmap()s the RAM page, seeds the
    same byte, runs the reconstructed C and prints the result.

EDGE vectors cover the sign-extension split (0x7F/0x80), the idle/armed
latch values and the boundary bytes; N random bytes follow (fixed seed).

Usage:  python3 harness_purge_state_query.py [N]     (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0xF5DC
STATE_ADDR = 0xFFFFA4B1
N_DEFAULT = 20000
SEED = 0x60E1D400

# This harness compiles its own oracle (the shared host_oracle.c does not
# know the purge query), into its own /tmp build dir.
SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.join(SAMPLES, 'tests')
ORACLE_DIR = os.path.join('/tmp', 'opencode', 'rx8-recon-purge_state_query')
ORACLE_BIN = os.path.join(ORACLE_DIR, 'oracle')

# State byte edges: idle/armed-latch values, the ROM 4/10 demand thresholds
# surrounding the outputs of purge_control_state_update, and the sign-extension
# split of the `mov.b` delay-slot read (0x7F -> +0x7F, 0x80 -> 0xFFFFFF80).
EDGE = [
    0x00, 0x01, 0x02,
    0x03, 0x04, 0x05,           # ROM_OUT_LOW threshold 4
    0x09, 0x0A, 0x0B,           # ROM_OUT_MID threshold 10
    0x3F, 0x40,
    0x7F, 0x80,                 # sign-extension split
    0x81, 0xFE, 0xFF,
]


def build_oracle(cc='cc'):
    """Compile the reconstructed source + its dedicated oracle into a binary."""
    os.makedirs(ORACLE_DIR, exist_ok=True)
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(TESTS, 'oracle_purge_state_query.c'),
           os.path.join(SAMPLES, 'src', 'rx8_purge_state_query.c'),
           '-o', ORACLE_BIN]
    subprocess.run(cmd, check=True)
    return ORACLE_BIN


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(SEED)

    vectors = list(EDGE) + [rng.randrange(256) for _ in range(n)]

    # (a) ROM behaviour via the emulator (seeded RAM byte, r0 & 0xFF).
    emu = [cpu.call(ADDR, ram={STATE_ADDR: v}) & 0xFF for v in vectors]

    # (b) host-C on the same vectors.
    lines = ['q %02X' % v for v in vectors]
    host = [int(x, 16) for x in run_oracle(oracle, lines)]

    # (c) compare.
    mismatches = []
    for i, (v, e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d state=0x%02X ROM=0x%02X C=0x%02X' % (i, v, e, h))
            if len(mismatches) >= 5:
                break

    report('purge_state_query', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
