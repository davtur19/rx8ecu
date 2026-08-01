#!/usr/bin/env python3
"""
harness_bitfield_flag_selector_33a98.py — equivalence of
rx8_bitfield_flag_selector_33a98 @0x33A98.

Reconstructed source: samples/src/rx8_bitfield_flag_selector_33a98.c
Verified lift   : c/bitfield_flag_selector_33A98.c

The ROM function is a plain ABI-clean void leaf: it reads the flag status byte
RAM[0xFFFFCD4E], selects a priority code v = (b&0x40)?0 : (b&0x20)?1 :
(b&0x80)?2 : 3, and writes v << 4 into the top nibble of the select-code byte
RAM[0xFFFFC05C].  No arguments are passed and nothing is returned through a
register — the observable effect is the RAM write, so the harness drives the
emulator with the standard `cpu.call()` (seeding the status byte via the ram=
overlay) and compares the side-effected select-code byte against the host C's
mmap-backed RAM (same MAP_FIXED trick as tests/host_oracle.c).

Procedure (Track-A pattern):
  1. build the host oracle (system gcc; -O2, -Wall, -Wextra),
  2. edge vectors (0, 0xFF, each priority bit alone and in every pairing,
     boundary bytes around the priority bits) + N random 8-bit status bytes,
  3. run the ROM bytes @0x33A98 in tools/sh2emu.py on the same vectors,
  4. run the host C on the same vectors,
  5. compare the select-code byte — 0 mismatches required.

Usage:  python3 harness_bitfield_flag_selector_33a98.py [N]   (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0x33A98
INP = 0xFFFFCD4E                     # flag status byte (bits 5/6/7 = priority)
OUT = 0xFFFFC05C                     # select-code byte (top nibble = v << 4)
N_DEFAULT = 20000

# Edge vectors: zero, all-ones, each priority bit alone (0x40 > 0x20 > 0x80),
# every pairing of priority bits, each priority bit plus a lower-priority
# neighbour, and the boundary bytes around each priority bit.
EDGE = [0x00, 0xFF, 0x01, 0x02, 0x04, 0x08, 0x10, 0x1F, 0x20, 0x21, 0x3F,
        0x40, 0x41, 0x5F, 0x60, 0x7F, 0x80, 0x81, 0x9F, 0xA0, 0xBF, 0xC0,
        0xDF, 0xE0, 0xFE, 0x7E]

# This harness' own build dir (kept separate from the shared host_oracle build).
SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = '/tmp/rx8-recon-bitfield_flag_selector_33a98'


def build_oracle(cc='cc'):
    """Compile this harness' own oracle (oracle_bitfield_flag_selector_33a98.c
    + the reconstructed source) into the task-mandated build dir."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_bitfield_flag_selector_33a98.c'),
           os.path.join(SAMPLES, 'src', 'rx8_bitfield_flag_selector_33a98.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(0x60E1D400)

    vectors = list(EDGE) + [rng.randrange(0, 256) for _ in range(n)]

    # (a) ROM behaviour via the emulator: seed the status byte in the RAM
    # overlay, then read back the select-code byte the function wrote.
    emu = []
    for s in vectors:
        cpu.call(ADDR, ram={INP: s})
        emu.append(cpu.ram.get(OUT, -1))

    # (b) host C on the same inputs (status shipped as a raw byte).
    lines = ['bs %02X' % s for s in vectors]
    host = [int(x, 16) for x in run_oracle(oracle, lines)]

    # (c) compare the select-code byte.
    mismatches = []
    for k, (s, e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d status=0x%02X ROM=0x%02X C=0x%02X' % (k, s, e, h))
            if len(mismatches) >= 5:
                break

    report('bitfield_flag_selector_33a98', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
