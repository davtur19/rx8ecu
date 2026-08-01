#!/usr/bin/env python3
"""
harness_set_mem_inside_func_to1.py — equivalence of
rx8_set_mem_inside_func_to1 @0x3E3F0.

Reconstructed source: samples/src/rx8_set_mem_inside_func_to1.c
Verified lift   : c/setMemInsideFUNCto1.c

ROM IMAGE NOTE: this helper lives in **roms/stock/60E0FC00.bin** at 0x3E3F0 —
the lift, docs/functions/setMemInsideFUNCto1.md and c/tests/test_mem_accessors.py
all target that image.  In the shared default image roms/stock/60E1D400.bin the
same address holds mid-function bytes of an unrelated mem-accessor routine, and
executing it there hits the reserved opcode 0x0000 (NotImplementedError), i.e.
that address is NOT a valid function entry in 60E1D400.bin.  So this harness
loads 60E0FC00.bin explicitly (common.load_cpu would give the wrong image).

The ROM function is a plain ABI-clean void leaf: it writes the constant 1 to
the byte RAM[0xFFFFC638] (a fault / "inside function" in-progress flag used by
the redundant-memory read/validate layer, c/mem_accessors.c).  No arguments are
passed and nothing is returned through a register — the observable effect is
the RAM write, so the harness seeds the flag byte in the RAM overlay, drives
the emulator with the standard `cpu.call()`, and compares the side-effected
byte against the host C's mmap-backed RAM (same MAP_FIXED trick as
tests/oracle_radiator_fan_relay_write.c / tests/host_oracle.c).

Procedure (Track-A pattern):
  1. build the host oracle (system gcc; -O2, -Wall, -Wextra),
  2. edge vectors (0, 1, sign/byte boundaries, all-ones) + N random 8-bit seed
     values,
  3. run the ROM bytes @0x3E3F0 in tools/sh2emu.py on the same vectors,
  4. run the host C on the same vectors,
  5. compare the flag byte left in RAM — 0 mismatches required.

Usage:  python3 harness_set_mem_inside_func_to1.py [N]   (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROOT, make_rng, report, run_oracle  # noqa: E402
# sh2emu is on sys.path via common.py's import; fetch the loader directly.
from sh2emu import SH2  # noqa: E402

# Function lives in 60E0FC00.bin (see header note above and the source header).
ROM_PATH = os.path.join(ROOT, 'roms', 'stock', '60E0FC00.bin')
ADDR = 0x3E3F0
FLAG = 0xFFFFC638                    # fault / in-progress flag byte (set to 1)
N_DEFAULT = 20000

# Edge vectors: byte boundaries, 0, max, and the two sides of the 0x01 write.
EDGE = [0x00, 0x01, 0x02, 0x7F, 0x80, 0xFE, 0xFF]

# This harness' own build dir (kept separate from the shared host_oracle build).
SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = '/tmp/rx8-recon-set_mem_inside_func_to1'


def build_oracle(cc='cc'):
    """Compile the reconstructed source + its own oracle into a host binary."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_set_mem_inside_func_to1.c'),
           os.path.join(SAMPLES, 'src', 'rx8_set_mem_inside_func_to1.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    with open(ROM_PATH, 'rb') as f:
        cpu = SH2(f.read())
    oracle = build_oracle()
    rng = make_rng(0x60E1D400)

    vectors = list(EDGE) + [rng.randrange(0, 256) for _ in range(n)]

    # (a) ROM behaviour via the emulator: seed the flag byte in the RAM
    # overlay, then read back the byte the function left there.
    emu = []
    for s in vectors:
        cpu.call(ADDR, ram={FLAG: s})
        emu.append(cpu.ram.get(FLAG))

    # (b) host C on the same inputs (seed shipped as a raw byte).
    lines = ['set %02X' % s for s in vectors]
    host = [int(x, 16) for x in run_oracle(oracle, lines)]

    # (c) compare the side-effected flag byte.
    mismatches = []
    for k, (s, e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d seed=0x%02X ROM=0x%02X C=0x%02X' % (k, s, e, h))
            if len(mismatches) >= 5:
                break

    report('set_mem_inside_func_to1', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
