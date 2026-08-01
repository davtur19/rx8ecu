#!/usr/bin/env python3
"""
harness_immo_bad_state_set.py — equivalence of rx8_immo_bad_state_set @0x365B8.

Reconstructed source: samples/src/rx8_immo_bad_state_set.c
Verified lift   : c/ImmoBadStateSet.c (ImmoBadStateSet @ 0x365B8)

The ROM function is a void, argument-free side-effect leaf: it calls
setImmoLight(0) @0x263C8 (which clears the immo-lamp bits 0x20/0x40 of the
status word 0xFFFFF754), then writes byte@0xFFFFC240 = 0 (CAN TX flag),
word@0xFFFFC284 = 0x01F4 (bad-state timeout) and byte@0xFFFFC28D = 4 (result
code).  No register result is produced, so the equivalence check compares the
four side-effected RAM cells (exactly like harness_radiator_fan_relay_write.py):

  - emulator side: seed the four cells as big-endian bytes in the sparse
    `ram` overlay, call the ROM entry 0x365B8 with plain `cpu.call()`, read
    the cells back;
  - host side: the oracle mmap()s the same pages (0xFFFFC000/0xFFFFF000,
    both above mmap_min_addr), seeds the same numeric values, runs the
    reconstructed C, reads them back.

The lamp bits are exercised with every combination of the 0x20/0x40 mask so
the fold-in of setImmoLight(0) (see the sample header) is validated against
the REAL setImmoLight bytes executed inside the emulator.

Usage:  python3 harness_immo_bad_state_set.py [N]   (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0x365B8
N_DEFAULT = 20000

# Side-effected cells (big-endian word/byte reads).
LAMP    = 0xFFFFF754   # status word, immo-lamp bits 0x20/0x40 (2 bytes)
CAN_TX  = 0xFFFFC240   # CAN TX data flag byte (1 byte)
TIMEOUT = 0xFFFFC284   # bad-state timeout word (2 bytes)
STATE   = 0xFFFFC28D   # state/result code byte (1 byte)

# Edge vectors: every mask combination for the lamp bits, plus 0/0xFF/0x8000
# extremes for each cell (cross product: 10 * 4 * 4 * 4 = 640 vectors).
LAMP_EDGES = [0x0000, 0x0020, 0x0040, 0x0060, 0x7FFF,
              0x8000, 0xFFDF, 0xFFBF, 0xFF9F, 0xFFFF]
BYTE_EDGES = [0x00, 0x01, 0x80, 0xFF]
WORD_EDGES = [0x0000, 0x01F4, 0x8000, 0xFFFF]
EDGES = [(l, c, t, s)
         for l in LAMP_EDGES
         for c in BYTE_EDGES
         for t in WORD_EDGES
         for s in BYTE_EDGES]

# This harness' own build dir (kept separate from the shared host_oracle build).
SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = '/tmp/rx8-recon-immo_bad_state_set'


def seed_cells(lamp, can, timeout, state):
    """Seed the four side-effected cells as big-endian bytes."""
    return {LAMP: (lamp >> 8) & 0xFF, LAMP + 1: lamp & 0xFF,
            CAN_TX: can & 0xFF,
            TIMEOUT: (timeout >> 8) & 0xFF, TIMEOUT + 1: timeout & 0xFF,
            STATE: state & 0xFF}


def read_cells(cpu):
    """Read the four side-effected cells back after the ROM call."""
    lamp = (cpu.ram.get(LAMP, 0) << 8) | cpu.ram.get(LAMP + 1, 0)
    can = cpu.ram.get(CAN_TX, 0)
    timeout = (cpu.ram.get(TIMEOUT, 0) << 8) | cpu.ram.get(TIMEOUT + 1, 0)
    state = cpu.ram.get(STATE, 0)
    return (lamp, can, timeout, state)


def build_oracle(cc='cc'):
    """Compile this harness' own oracle (oracle_immo_bad_state_set.c + the
    reconstructed source) into the task-mandated build dir."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_immo_bad_state_set.c'),
           os.path.join(SAMPLES, 'src', 'rx8_immo_bad_state_set.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(0x60E1D400)

    # Edge vectors + N random initial RAM states (all four cells random).
    vectors = list(EDGES)
    vectors += [(rng.getrandbits(16), rng.getrandbits(8),
                 rng.getrandbits(16), rng.getrandbits(8))
                for _ in range(n)]

    # (a) ROM behaviour via the emulator: seed the four cells in the RAM
    # overlay, then read back the cells after the call.
    emu = []
    for lamp, can, timeout, state in vectors:
        cpu.call(ADDR, ram=seed_cells(lamp, can, timeout, state))
        emu.append(read_cells(cpu))

    # (b) host C on the same inputs (initial values shipped as raw hex).
    lines = ['ibs %04X %02X %04X %02X' % (l, c, t, s)
             for l, c, t, s in vectors]
    host = [tuple(int(x, 16) for x in out.split())
            for out in run_oracle(oracle, lines)]

    # (c) compare the four side-effected cells.
    mismatches = []
    for k, (v, e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            l, c, t, s = v
            mismatches.append(
                'vec#%d seed lamp=0x%04X can=0x%02X timeout=0x%04X state=0x%02X '
                'ROM=(%04X,%02X,%04X,%02X) C=(%04X,%02X,%04X,%02X)'
                % (k, l, c, t, s, e[0], e[1], e[2], e[3],
                   h[0], h[1], h[2], h[3]))
            if len(mismatches) >= 5:
                break

    report('ImmoBadStateSet', ADDR, n, mismatches, edges=len(EDGES))


if __name__ == '__main__':
    main()
