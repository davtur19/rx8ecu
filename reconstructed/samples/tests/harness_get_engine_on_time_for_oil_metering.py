#!/usr/bin/env python3
"""
harness_get_engine_on_time_for_oil_metering.py — equivalence of
rx8_get_engine_on_time_for_oil_metering @0xE492.

Reconstructed source: samples/src/rx8_get_engine_on_time_for_oil_metering.c
Verified lift   : c/getEngineOnTimeForOilMetering.c (same address, same
                  behaviour; also c/add16bitSaturate.c for the 0x2460 leaf).

The ROM routine is ABI-clean (void -> void, both RAM addresses come from
PC-relative literals), so it is entered with the plain `cpu.call(ADDR, ram=...)`.
It acts on fixed RAM cells (u8 engine-running flag @0xFFFFA428, u16 engine-on
timer @0xFFFFA422), so the equivalence check compares the RAM side-effect, not
a return value:

  - emulator side: seed the two cells in the sparse ram overlay, call the ROM
    entry @0xE492 (which internally jsr's the real add16bitSaturate leaf
    @0x2460), read the timer word back;
  - host side: the dedicated oracle mmap()s the page backing the cells, seeds
    the same numeric bytes, runs the reconstructed C, reads them back.

Procedure (Track-A pattern):
  1. build the dedicated oracle (tests/oracle_get_engine_on_time_for_oil_metering.c
     + samples/src/rx8_get_engine_on_time_for_oil_metering.c) with system gcc;
  2. EDGE pre-states (flag boundaries 0/1/2/0x7F/0x80/0xFE/0xFF x timer
     boundaries 0/1/0x7FFF/0x8000/0xFFFE/0xFFFF, incl. the +1 saturation
     point) + N random (seeded) pre-states;
  3. run the ROM bytes @0xE492 in tools/sh2emu.py on the same pre-states;
  4. run the host C on the same pre-states;
  5. compare the post-state timer words — 0 mismatches required.

Usage:  python3 harness_get_engine_on_time_for_oil_metering.py [N]
        (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, SAMPLES  # noqa: E402

ADDR = 0xE492
FLAG_ADDR = 0xFFFFA428          # u8  engine-running flag (ROM: mov.b+extu.b)
TIMER_ADDR = 0xFFFFA422         # u16 engine-on timer     (ROM: mov.w)
N_DEFAULT = 20000
BUILD_DIR = '/tmp/rx8-recon-get_engine_on_time_for_oil_metering'

# Edge pre-states.  The flag matters only as == 1 (0x00/0x02/0x7F/0x80/0xFE/0xFF
# must NOT accumulate; 0x80 pins the mov.b sign-extend + extu.b path).  The
# timer edges bracket the +1 increment: 0x0000 -> 0x0001, 0xFFFF -> 0xFFFF
# (saturate, never wraps), 0x7FFF/0x8000 pin the mov.w sign-extend path.
FLAG_EDGES = (0x00, 0x01, 0x02, 0x7F, 0x80, 0xFE, 0xFF)
TIMER_EDGES = (0x0000, 0x0001, 0x7FFF, 0x8000, 0xFFFE, 0xFFFF)
EDGE = [(f, t) for f in FLAG_EDGES for t in TIMER_EDGES]
EDGE += [(0x01, 0x1234), (0x00, 0xABCD), (0x55, 0x55AA)]   # spot combos


def build_oracle(cc='cc'):
    """Compile the reconstructed source + its own oracle into a host binary.
    (common.build_oracle is not reusable: it hardcodes the sample .c list.)"""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_get_engine_on_time_for_oil_metering.c'),
           os.path.join(SAMPLES, 'src', 'rx8_get_engine_on_time_for_oil_metering.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def run_oracle(oracle, vectors):
    proc = subprocess.run([oracle], input='\n'.join(vectors) + '\n',
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError('host oracle failed:\n' + proc.stderr)
    lines = proc.stdout.splitlines()
    if len(lines) != len(vectors):
        raise RuntimeError(
            'oracle produced %d outputs for %d vectors' % (len(lines), len(vectors)))
    return lines


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(0xE492)

    # Random pre-states: flag over the full byte range (non-canonical values
    # matter — only exactly 1 accumulates), timer over the full u16 range.
    vectors = list(EDGE) + [(rng.randint(0, 255), rng.getrandbits(16))
                            for _ in range(n)]

    # (a) ROM behaviour via the emulator (RAM side-effect at TIMER_ADDR).
    emu = []
    for flag, timer in vectors:
        ram = {FLAG_ADDR: flag & 0xFF,
               TIMER_ADDR: (timer >> 8) & 0xFF,
               TIMER_ADDR + 1: timer & 0xFF}
        cpu.call(ADDR, ram=ram)
        emu.append(cpu.rd(TIMER_ADDR, 2))

    # (b) host-C on the same pre-states (cells seeded by the oracle itself).
    lines = ['omp %02X %04X' % (flag, timer) for flag, timer in vectors]
    host = [int(x, 16) for x in run_oracle(oracle, lines)]

    # (c) compare.
    mismatches = []
    for i, ((flag, timer), e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d flag=%02X timer=%04X ROM=%04X C=%04X'
                % (i, flag, timer, e, h))
            if len(mismatches) >= 5:
                break

    report('getEngineOnTimeForOilMetering', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
