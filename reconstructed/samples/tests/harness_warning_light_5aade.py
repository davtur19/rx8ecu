#!/usr/bin/env python3
"""
harness_warning_light_5aade.py — equivalence of rx8_warning_light_5aade @0x5AADE.

Reconstructed source: samples/src/rx8_warning_light_5aade.c
Verified lift   : c/warning_light_0x5AADE.c

The ROM function is a plain ABI-clean void leaf: it maps the lamp-status byte
RAM[0xFFFFCD4C] to a warning-light value byte RAM[0xFFFFD2C5].  No arguments
are passed and nothing is returned through a register — the observable effect
is the RAM write, so the harness drives the emulator with the standard
`cpu.call()` (seeding the status byte via the ram= overlay) and compares the
side-effected warning-light byte against the host C's mmap-backed RAM (same
MAP_FIXED trick as tests/host_oracle.c).

Procedure (Track-A pattern):
  1. build the host oracle (system gcc; -O2, -Wall, -Wextra),
  2. edge vectors (0, every tested bit 0x04/0x08/0x10/0x20/0x40/0x80, their
     group masks 0x1C/0x60, priority conflicts 0x80-vs-each-higher bit,
     0x7F/0x80 sign-flip boundary, all-bits 0xFF) + N random 8-bit bytes,
  3. run the ROM bytes @0x5AADE in tools/sh2emu.py on the same vectors,
  4. run the host C on the same vectors,
  5. compare the warning-light byte — 0 mismatches required.

Usage:  python3 harness_warning_light_5aade.py [N]   (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0x5AADE
INP = 0xFFFFCD4C                    # lamp status byte (bitmapped)
OUT = 0xFFFFD2C5                    # warning-light value byte (side effect)
N_DEFAULT = 20000

# Edge vectors: zero, every tested bit alone, the two group masks, the
# 0x80-loses-to-everything priority conflicts, the sign-flip boundary and the
# all-bits byte.  Bits not tested anywhere (0x01/0x02) must map to 0.
EDGE = [0x00, 0x01, 0x02, 0x03,
        0x04, 0x08, 0x10, 0x1C,          # -> 0x69
        0x20, 0x40, 0x60,                # -> 0x6D
        0x80, 0x84, 0x90, 0xC0,          # 0x80 loses to 0x04/0x10/0x40
        0x7F, 0xFE, 0xFF]

# This harness' own build dir (task-mandated; kept separate from the shared
# host_oracle build).
SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = '/tmp/rx8-recon-warning_light_5aade'


def build_oracle(cc='cc'):
    """Compile this harness' own oracle (oracle_warning_light_5aade.c +
    the reconstructed source) into the task-mandated build dir."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_warning_light_5aade.c'),
           os.path.join(SAMPLES, 'src', 'rx8_warning_light_5aade.c'),
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
    # overlay, then read back the warning-light byte the function wrote.
    emu = []
    for s in vectors:
        cpu.call(ADDR, ram={INP: s})
        emu.append(cpu.ram[OUT])

    # (b) host C on the same inputs (status shipped as a raw byte).
    lines = ['wl %02X' % s for s in vectors]
    host = [int(x, 16) for x in run_oracle(oracle, lines)]

    # (c) compare the warning-light byte.
    mismatches = []
    for k, (s, e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d status=0x%02X ROM=0x%02X C=0x%02X' % (k, s, e, h))
            if len(mismatches) >= 5:
                break

    report('warning_light', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
