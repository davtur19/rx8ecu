#!/usr/bin/env python3
"""
harness_immo_key_expander_365d6.py — equivalence of
rx8_immo_key_expander_365d6 @0x365D6.

Reconstructed source: samples/src/rx8_immo_key_expander_365d6.c
Verified lift   : c/ImmoKeyExpander.c (ImmoKeyExpander_365D6 @ 0x365D6)

The ROM routine is a memory-to-memory leaf: it takes NO register arguments
and returns nothing meaningful in r0.  It reads three 32-bit words (rolling
code @0xFFFFC278, EEPROM key words @0xFFFFC2E0/@0xFFFFC2DC), derives four
expected key words via the seed_mixer primitive (`bsr` @0x366B8, emulated
inline as part of the ROM bytes) and writes eight 32-bit words (slots
@0xFFFFC24C..0xFFFFC258, expected @0xFFFFC260..0xFFFFC26C).  The equivalence
check therefore compares RAM side-effects, not a return value:

  - emulator side: seed the three input words in the sparse ram overlay,
    `cpu.call(ADDR, ram=...)` the ROM entry @0x365D6, read the eight output
    words back;
  - host side: the dedicated oracle mmap()s the page backing the words, seeds
    the same numeric values, runs the reconstructed C, reads them back.

Procedure (Track-A pattern):
  1. build the host oracle (system gcc; -O2, -Wall, -Wextra),
  2. EDGE vectors (0 / all-ones / sign flips / byte boundaries) + N random
     (seeded) triples,
  3. run the ROM bytes @0x365D6 in tools/sh2emu.py on the same vectors,
  4. run the host C on the same vectors,
  5. compare all eight written words — 0 mismatches required.

Usage:  python3 harness_immo_key_expander_365d6.py [N]   (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0x365D6
N_DEFAULT = 20000

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = '/tmp/rx8-recon-immo_key_expander_365d6'

KEY_ADDR = 0xFFFFC278
W2E0_ADDR = 0xFFFFC2E0
W2DC_ADDR = 0xFFFFC2DC

# Written words: slots @0xFFFFC24C..0xFFFFC258, expected @0xFFFFC260..0xFFFFC26C.
OUT_ADDRS = (0xFFFFC24C, 0xFFFFC250, 0xFFFFC254, 0xFFFFC258,
             0xFFFFC260, 0xFFFFC264, 0xFFFFC268, 0xFFFFC26C)

# Edge input words: 0 / all-ones toggle every bit; 0x80000000 and 0x00000001
# pin the sign-bit and low-bit paths; 0x00FF00FF / 0xFF00FF00 hit every byte
# boundary pair (the mixer rebuilds and byte-swaps bytes 0/1/2).
EDGE_WORDS = (0x00000000, 0xFFFFFFFF, 0x80000000, 0x00000001,
              0x7FFFFFFF, 0x00FF00FF, 0xFF00FF00, 0x12345678)

# Cross product of the edge words: covers key-only, word-only and coupled
# boundary cases (e.g. key=0 / w2E0=0xFFFFFFFF / w2DC=0).
EDGE = [(k, a, b) for k in EDGE_WORDS for a in EDGE_WORDS for b in EDGE_WORDS]


def seed_words(ram, base, v):
    """Expand a 32-bit big-endian word into 4 bytes of the sparse ram overlay."""
    for i in range(4):
        ram[base + i] = (v >> (24 - 8 * i)) & 0xFF


def build_oracle(cc='cc'):
    """Compile this harness' own oracle (oracle_immo_key_expander_365d6.c +
    the reconstructed source)."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_immo_key_expander_365d6.c'),
           os.path.join(SAMPLES, 'src', 'rx8_immo_key_expander_365d6.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(0x365D6)

    # Edge triples + N random (key, w2E0, w2DC) triples.
    vectors = list(EDGE) + [(rng.getrandbits(32), rng.getrandbits(32),
                             rng.getrandbits(32)) for _ in range(n)]

    # (a) ROM behaviour via the emulator (RAM side-effects).  The whole
    #     function — including the four inline `bsr` calls into seed_mixer
    #     @0x366B8 — runs from the actual ROM bytes.
    emu = []
    for key, w2E0, w2DC in vectors:
        ram = {}
        seed_words(ram, KEY_ADDR, key)
        seed_words(ram, W2E0_ADDR, w2E0)
        seed_words(ram, W2DC_ADDR, w2DC)
        cpu.call(ADDR, ram=ram)
        emu.append([cpu.rd(a, 4) for a in OUT_ADDRS])

    # (b) host C on the same inputs.
    lines = ['immo %08X %08X %08X' % (k, a, b) for k, a, b in vectors]
    host = [[int(x, 16) for x in out.split()] for out in run_oracle(oracle, lines)]

    # (c) compare all eight written words.
    mismatches = []
    for i, ((key, w2E0, w2DC), e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d key=%08X w2E0=%08X w2DC=%08X ROM=%s C=%s'
                % (i, key, w2E0, w2DC,
                   ' '.join('%08X' % x for x in e),
                   ' '.join('%08X' % x for x in h)))
            if len(mismatches) >= 5:
                break

    report('immo_key_expander', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
