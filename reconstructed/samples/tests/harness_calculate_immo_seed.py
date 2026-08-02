#!/usr/bin/env python3
"""
harness_calculate_immo_seed.py — equivalence of rx8_calculate_immo_seed @0x3675C.

Reconstructed source: samples/src/rx8_calculate_immo_seed.c
Verified lift   : c/calculateImmoSeed.c (IDA symbol `calculateImmoSeed_3675C`).

Pure function of three 32-bit words (EEPROM key words A/B + rolling code),
passed in r4/r5/r6 and returned in r0.  It reads NO RAM and writes NO RAM —
all state lives in registers and the local stack frame — so the equivalence
check compares the return value only:

  - emulator side: `cpu.call(0x3675C, r4=a, r5=b, r6=c)` runs the ACTUAL ROM
    bytes of the function (the body is a leaf; no bsr/jsr callees, no cal
    pages, so nothing else needs to be pinned);
  - host side: the dedicated oracle seeds the same three words into the
    caller-side immobilizer RAM cells (mmap-backed, MAP_FIXED), passes them
    to the reconstructed C, and prints the returned seed.

Procedure (Track-A pattern, convention of the pure register-arg siblings
harness_seed_mixer.py / harness_immo_get_seed_3664e.py):
  1. build the host oracle (system gcc; -O2, -Wall, -Wextra),
  2. EDGE vectors (0 / all-ones / sign flips / byte boundaries / odd-even
     mixer-branch coverage) + N random (seeded) triples,
  3. run the ROM bytes @0x3675C in tools/sh2emu.py on the same vectors,
  4. run the host C on the same vectors,
  5. compare the returned seed — 0 mismatches required.

Usage:  python3 harness_calculate_immo_seed.py [N]   (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0x3675C
N_DEFAULT = 20000
RNG_SEED = 0x60E1D400            # ROM name, like the sibling harnesses

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = '/tmp/rx8-recon-calculate_immo_seed'

# Edge input words: 0 / all-ones toggle every bit; 0x80000000 / 0x00000001 pin
# the sign-bit and low-bit paths; 0x00FF00FF / 0xFF00FF00 / 0x0D0D0D0D hit every
# byte boundary pair (the seed math extracts bytes 0/1/2/3 from sums and keys);
# 0xABCDEF01 etc. are de-facto "random" patterns.
EDGE_WORDS = (0x00000000, 0xFFFFFFFF, 0x80000000, 0x00000001,
              0x7FFFFFFF, 0x00FF00FF, 0xFF00FF00, 0x0D0D0D0D,
              0x12345678, 0xABCDEF01, 0x00000278)

# Hand-picked triples: exercise the sum16/sum32 high-byte extraction, the four
# mulu.w multiplies and BOTH arms of the odd/even branch on the mixed key word
# B (bit 0 of the mixed r5 — which reduces to bit 0 of the input r5, since the
# sc4 mask is even).  r5 odd  -> odd  arm;  r5 even -> even arm.
EDGE = [
    (0x00000000, 0x00000000, 0x00000000),
    (0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF),
    (0xFFFFFFFF, 0x00000000, 0x00000000),
    (0x00000000, 0xFFFFFFFF, 0x00000000),
    (0x00000000, 0x00000000, 0xFFFFFFFF),
    (0x80000000, 0x7FFFFFFF, 0x00000001),
    (0x00000001, 0x00000000, 0x00000000),
    (0x00000000, 0x00000001, 0x00000000),   # odd branch, keyB low bit
    (0x00000000, 0x00000002, 0x00000000),   # even branch, keyB low bit clear
    (0x7FFFFFFF, 0x7FFFFFFF, 0x7FFFFFFF),
    (0x80000000, 0x80000000, 0x80000000),
    (0x0D0D0D0D, 0xD0D0D0D0, 0x0D0D0000),
    (0x0000FF00, 0x00FF00FF, 0xFF00FF00),
    (0xFF0000FF, 0x00FF00FF, 0xFF00FF00),
    (0x00000278, 0x00000000, 0x00000000),
    (0x00000000, 0x00000000, 0x00000278),
    (0xABCDEF01, 0x12345678, 0x9ABCDEF0),
    (0xDEADBEEF, 0xCAFEBABE, 0x00000278),
    (0x6D7A64D0, 0x00000278, 0x00000278),
]


def build_oracle(cc='cc'):
    """Compile this harness' own oracle (oracle_calculate_immo_seed.c + the
    reconstructed source) into the task-mandated build dir /tmp/rx8-recon-
    calculate_immo_seed/oracle, exactly as mandated:
    cc -O2 -Wall -Wextra -I include -I src tests/oracle_calculate_immo_seed.c
       src/rx8_calculate_immo_seed.c -lm -o /tmp/rx8-recon-calculate_immo_seed/oracle"""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_calculate_immo_seed.c'),
           os.path.join(SAMPLES, 'src', 'rx8_calculate_immo_seed.c'),
           '-lm',
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(RNG_SEED)

    vectors = list(EDGE) + [(rng.getrandbits(32), rng.getrandbits(32),
                             rng.getrandbits(32)) for _ in range(n)]

    # (a) ROM behaviour via the emulator: pure register-argument call, the
    #     whole 0x3675C..0x3686E body runs from the actual ROM bytes; r0 is
    #     the returned seed.
    emu = [cpu.call(ADDR, r4=a, r5=b, r6=c) for a, b, c in vectors]

    # (b) host C on the same inputs (words shipped as raw hex).
    lines = ['seed %08X %08X %08X' % (a, b, c) for a, b, c in vectors]
    host = [int(x, 16) for x in run_oracle(oracle, lines)]

    # (c) compare the returned seed word.
    mismatches = []
    for i, ((a, b, c), e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d keyA=0x%08X keyB=0x%08X rolling=0x%08X '
                'ROM=0x%08X C=0x%08X' % (i, a, b, c, e, h))
            if len(mismatches) >= 5:
                break

    report('calculate_immo_seed', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
