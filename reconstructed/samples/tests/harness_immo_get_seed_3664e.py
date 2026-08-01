#!/usr/bin/env python3
"""
harness_immo_get_seed_3664e.py — equivalence of rx8_immo_get_seed @0x3664E.

Reconstructed source: samples/src/rx8_immo_get_seed_3664e.c
Verified lift   : c/ImmoGetSeed.c (IDA symbol `ImmoGetSeed`; same address).

The ROM function is a plain ABI-clean void function with NO arguments: it
reads the three immobilizer RAM words (key A @0xFFFFC2DC, key B @0xFFFFC2E0,
rolling code @0xFFFFC278), computes the seed with the embedded
calculateImmoSeed helper @0x3675C, and stores it at 0xFFFFC270 (IMMO_SEED_OUT).
The observable effect is the RAM write, so the harness drives the emulator
with the standard `cpu.call()` (seeding the input words via the ram= overlay)
and compares the side-effected seed word against the host C's mmap-backed RAM
(same MAP_FIXED trick as tests/host_oracle.c), as well as the returned r0.

Procedure (Track-A pattern):
  1. build the host oracle (system gcc; -O2, -Wall, -Wextra),
  2. edge vectors (all-zero/all-one, byte masks, rolling-code extremes,
     odd/even mixer-branch coverage) + N random 32-bit triples,
  3. run the ROM bytes @0x3664E in tools/sh2emu.py on the same vectors,
  4. run the host C on the same vectors,
  5. compare the seed word @0xFFFFC270 and the emulator's r0 — 0 mismatches
     required.

Usage:  python3 harness_immo_get_seed_3664e.py [N]   (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0x3664E
KEY_A = 0xFFFFC2DC              # EEPROM[0x02..05] working copy
KEY_B = 0xFFFFC2E0              # EEPROM[0x06..09] working copy
ROLL  = 0xFFFFC278              # rolling code out
SEED  = 0xFFFFC270              # calculated seed (result)
N_DEFAULT = 20000

# Edge vectors: (keyA, keyB, rolling).  Exercise the byte arithmetic, the
# 16-bit wide multiplies, the high-byte extraction and both arms of the
# mixer's odd/even branch (bit 0 of the mixed key word B), plus 0/max/sign
# extremes of each input word.
EDGE = [
    (0x00000000, 0x00000000, 0x00000000),
    (0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF),
    (0xFFFFFFFF, 0x00000000, 0x00000000),
    (0x00000000, 0xFFFFFFFF, 0x00000000),
    (0x00000000, 0x00000000, 0xFFFFFFFF),
    (0x00000001, 0x00000000, 0x00000000),
    (0x00000000, 0x00000001, 0x00000000),
    (0x00000000, 0x00000000, 0x00000001),
    (0x7FFFFFFF, 0x7FFFFFFF, 0x7FFFFFFF),
    (0x80000000, 0x80000000, 0x80000000),
    (0x80000000, 0x7FFFFFFF, 0x00000001),
    (0x0000FF00, 0x00FF00FF, 0xFF00FF00),
    (0x0D0D0D0D, 0xD0D0D0D0, 0x0D0D0000),
    (0x00000278, 0x00000000, 0x00000000),   # plausible rolling code
    (0x00000000, 0x00000000, 0x00000278),
    (0xABCDEF01, 0x12345678, 0x9ABCDEF0),
    (0xDEADBEEF, 0xCAFEBABE, 0x00000278),
    (0x6D7A64D0, 0x00000278, 0x00000278),   # plausible key/rolling values
]


def _wr32(ram, addr, v):
    for i in range(4):
        ram[addr + i] = (v >> (8 * (3 - i))) & 0xFF


def _rd32(ram, addr):
    v = 0
    for i in range(4):
        v = (v << 8) | ram[addr + i]
    return v


# This harness' own build dir (kept separate from the shared host_oracle build).
SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = '/tmp/rx8-recon-immo_get_seed_3664e'


def build_oracle(cc='cc'):
    """Compile this harness' own oracle (oracle_immo_get_seed_3664e.c +
    the reconstructed source) into the task-mandated build dir."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_immo_get_seed_3664e.c'),
           os.path.join(SAMPLES, 'src', 'rx8_immo_get_seed_3664e.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(0x60E1D400)

    vectors = list(EDGE) + [(rng.getrandbits(32), rng.getrandbits(32),
                             rng.getrandbits(32)) for _ in range(n)]

    # (a) ROM behaviour via the emulator: seed the three input words in the
    # RAM overlay, run the function, then read back the seed word it wrote.
    emu = []
    for a, b, c in vectors:
        ram = {}
        _wr32(ram, KEY_A, a)
        _wr32(ram, KEY_B, b)
        _wr32(ram, ROLL, c)
        r0 = cpu.call(ADDR, ram=ram)
        seed = _rd32(cpu.ram, SEED)
        if r0 != seed:
            raise RuntimeError(
                'emulator self-check failed: r0=0x%08X != RAM seed=0x%08X'
                % (r0, seed))
        emu.append(seed)

    # (b) host C on the same inputs (words shipped as raw hex).
    lines = ['imm %08X %08X %08X' % (a, b, c) for a, b, c in vectors]
    host = [int(x, 16) for x in run_oracle(oracle, lines)]

    # (c) compare the side-effected seed word.
    mismatches = []
    for i, ((a, b, c), e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d keyA=0x%08X keyB=0x%08X rolling=0x%08X '
                'ROM=0x%08X C=0x%08X' % (i, a, b, c, e, h))
            if len(mismatches) >= 5:
                break

    report('immo_get_seed', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
