#!/usr/bin/env python3
"""
harness_set_immo_light.py — equivalence of rx8_set_immo_light @0x263C8.

Reconstructed source: samples/src/rx8_set_immo_light.c
Verified lift   : c/setImmoLight.c  (setImmoLight @ 0x263C8)

The ROM routine is the immobilizer warning-lamp driver: a `void f(uint8_t on)`
leaf (argument in r4).  It zero-extends `on`, and when `(on & 0xFF) == 1`
ORs masks 0x40 then 0x20 into the 16-bit status word RX8_STATUS_WORD
@0xFFFFF754 via the reg16SetClear helper (0x4BBC); otherwise it ANDs ~0x20
then ~0x40 out of the same word.  Every access is wrapped in a save/restore
of the SR interrupt-mask nibble (0x2054 / 0x2064), whose slots live in a
transient 24-byte stack frame that the epilogue fully restores — so the only
observable RAM side effect is the lamp register (same rig as the immo
siblings, which inline this routine's net effect as word |= 0x60 / word &=
~0x60).

The standalone sample is exercised over BOTH paths (on == 1 and on != 1) and
over the full 32-bit `on` argument space — the ROM's `cmp/eq #0x01` compares
the zero-extended low byte, so the edge set pins high-byte variants (0x101,
0x80000001, 0xFFFFFFFF, ...) against the ground truth.

Procedure (Track-A pattern):
  1. build the host oracle (system gcc; -O2, -Wall, -Wextra),
  2. edge vectors: 11 `on` values x 10 lamp-bit-pattern seeds (110) +
     N random (32-bit on, 16-bit lamp) vectors,
  3. run the ROM bytes @0x263C8 in tools/sh2emu.py on the same vectors,
  4. run the host C on the same vectors,
  5. compare the 16-bit lamp register — 0 mismatches required.

Usage:  python3 harness_set_immo_light.py [N]   (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0x263C8
N_DEFAULT = 20000

# Side-effected cell: the 16-bit lamp register (RX8_STATUS_WORD).
LAMP = 0xFFFFF754   # status word, immo-lamp bits 0x20/0x40 (2 bytes)

# `on` edge values: cover the (on & 0xFF) == 1 gate on both sides, the exact
# 0/1/2/0x80/0xFF bytes, and 32-bit values whose low byte is 1 / is not 1.
ON_EDGES = [0x00000000, 0x00000001, 0x00000002, 0x00000080,
            0x000000FF, 0x00000100, 0x00000101, 0x00000102,
            0x00008101, 0x80000001, 0xFFFFFFFF]

# Lamp edge seeds: every mask combination for the lamp bits, plus extremes.
LAMP_EDGES = [0x0000, 0x0020, 0x0040, 0x0060, 0x7FFF,
              0x8000, 0xFFDF, 0xFFBF, 0xFF9F, 0xFFFF]

# Edge vectors: cross product (11 * 10 = 110 vectors).
EDGES = [(on, lamp) for on in ON_EDGES for lamp in LAMP_EDGES]

# This harness' own build dir (kept separate from the shared host_oracle build).
SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = '/tmp/rx8-recon-set_immo_light'


def seed_lamp(lamp):
    """Seed the lamp register as big-endian bytes."""
    return {LAMP: (lamp >> 8) & 0xFF, LAMP + 1: lamp & 0xFF}


def read_lamp(cpu):
    """Read the 16-bit lamp register back after the ROM call."""
    return (cpu.ram.get(LAMP, 0) << 8) | cpu.ram.get(LAMP + 1, 0)


def build_oracle(cc='cc'):
    """Compile this harness' own oracle (oracle_set_immo_light.c + the
    reconstructed source) into the task-mandated build dir."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_set_immo_light.c'),
           os.path.join(SAMPLES, 'src', 'rx8_set_immo_light.c'),
           '-lm',
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(0x60E1D400)

    # Edge vectors + N random vectors (32-bit on, 16-bit lamp).
    vectors = list(EDGES)
    vectors += [(rng.getrandbits(32), rng.getrandbits(16))
                for _ in range(n)]

    # (a) ROM behaviour via the emulator: seed the lamp register in the RAM
    # overlay, pass `on` as r4, read the lamp register back after the call.
    emu = []
    for on, lamp in vectors:
        cpu.call(ADDR, r4=on, ram=seed_lamp(lamp))
        emu.append(read_lamp(cpu))

    # (b) host C on the same inputs (initial values shipped as raw hex).
    lines = ['sml %08X %04X' % (on, lamp) for on, lamp in vectors]
    host = [int(out, 16) for out in run_oracle(oracle, lines)]

    # (c) compare the 16-bit lamp register.
    mismatches = []
    for k, ((on, lamp), e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d on=0x%08X lamp=0x%04X ROM=0x%04X C=0x%04X'
                % (k, on, lamp, e, h))
            if len(mismatches) >= 5:
                break

    report('set_immo_light', ADDR, n, mismatches, edges=len(EDGES))


if __name__ == '__main__':
    main()
