#!/usr/bin/env python3
"""
harness_radiator_fan_relay_write.py — equivalence of
rx8_radiator_fan_relay_write @0x259C0.

Reconstructed source: samples/src/rx8_radiator_fan_relay_write.c
Verified lift   : c/radiator_fan_relay_write.c

The ROM function is a plain ABI-clean void leaf: it reads the fan-status byte
RAM[0xFFFF9ECD] (bit 0) and writes the active-low radiator-fan relay byte
RAM[0xFFFFB5AB].  No arguments are passed and nothing is returned through a
register — the observable effect is the RAM write, so the harness drives the
emulator with the standard `cpu.call()` (seeding the status byte via the ram=
overlay) and compares the side-effected relay byte against the host C's
mmap-backed RAM (same MAP_FIXED trick as tests/host_oracle.c).

Procedure (Track-A pattern):
  1. build the host oracle (system gcc; -O2, -Wall, -Wextra),
  2. edge vectors (0, bit-0 flips, boundaries 0x7F/0x80/0xFE/0xFF) + N random
     8-bit status bytes,
  3. run the ROM bytes @0x259C0 in tools/sh2emu.py on the same vectors,
  4. run the host C on the same vectors,
  5. compare the relay byte — 0 mismatches required.

Usage:  python3 harness_radiator_fan_relay_write.py [N]   (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0x259C0
INP = 0xFFFF9ECD                    # fan status byte (bit 0 = request)
OUT = 0xFFFFB5AB                    # radiator fan relay byte (active-low)
N_DEFAULT = 20000

# Edge vectors: zero, the two bit-0 states, bit-0 flips across the byte
# boundaries, all-low/high nibbles and the 8-bit extremes.
EDGE = [0x00, 0x01, 0x02, 0x03, 0x7E, 0x7F, 0x80, 0x81, 0xFE, 0xFF]

# This harness' own build dir (kept separate from the shared host_oracle build).
SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = '/tmp/rx8-recon-radiator_fan_relay_write'


def build_oracle(cc='cc'):
    """Compile this harness' own oracle (oracle_radiator_fan_relay_write.c +
    the reconstructed source) into the task-mandated build dir."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_radiator_fan_relay_write.c'),
           os.path.join(SAMPLES, 'src', 'rx8_radiator_fan_relay_write.c'),
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
    # overlay, then read back the relay byte the function wrote.
    emu = []
    for s in vectors:
        cpu.call(ADDR, ram={INP: s})
        emu.append(cpu.ram[OUT])

    # (b) host C on the same inputs (status shipped as a raw byte).
    lines = ['rl %02X' % s for s in vectors]
    host = [int(x, 16) for x in run_oracle(oracle, lines)]

    # (c) compare the relay byte.
    mismatches = []
    for k, (s, e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d status=0x%02X ROM=0x%02X C=0x%02X' % (k, s, e, h))
            if len(mismatches) >= 5:
                break

    report('radiator_fan_relay_write', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
