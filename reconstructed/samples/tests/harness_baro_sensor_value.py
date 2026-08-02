#!/usr/bin/env python3
"""
harness_baro_sensor_value.py — equivalence of rx8_baro_sensor_value @0xD144.

Reconstructed source: samples/src/rx8_baro_sensor_value.c
Verified lift   : c/baro_sensor_value.c (getBaroSensorVal @ 0xD144) — the lift
                  describes the ADC->fixed-point->float barometric-pressure
                  pipeline of the SIBLING bin roms/stock/60E0FC00.bin @0xD144;
                  the target ROM 60E1D400.bin @0xD144 is a 20-byte leaf that
                  byte-swaps a u16 and stores it to one of two on-chip HCAN
                  mailbox data registers (0xFFFFE40A when r4==0, 0xFFFFE60A
                  otherwise).  The ROM bytes win where the two disagree; the
                  discrepancy is documented in the reconstructed source header.

The function is a REGISTER-ARGUMENT leaf with no ABI return value (r0 is
untouched) and no memory INPUTS: r4 = bank selector (u8), r5 = value (u16).
Its whole effect is on the two MMIO cells, so the equivalence check compares
the two post-state words byte-for-byte:

   MMIO16 [0xFFFFE40A]  mailbox-A data word (overwritten only when bank == 0)
   MMIO16 [0xFFFFE60A]  mailbox-B data word (overwritten only when bank != 0)

  - emulator side: seed the sparse ram overlay with distinguishable pre-states
    for BOTH cells (so an accidental write to the unselected register would be
    caught), call the REAL ROM bytes @0xD144 via cpu.call(0xD144, r4, r5),
    read both cells back;
  - host side: the dedicated oracle mmap()s the page backing the two cells,
    seeds the same bytes, runs the reconstructed C and prints the same cells.

EDGE vectors cover the tst branch (bank 0 vs non-zero), byte-swap boundaries
(val with distinct high/low bytes, symmetric patterns, full-scale) and the
pre-state survival of the unselected cell; N random (bank, value, pre0, pre1)
vectors follow with a fixed seed = the ROM file name 0x60E1D400.

Usage:  python3 harness_baro_sensor_value.py [N]  (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0xD144
N_DEFAULT = 20000
SEED = 0x60E1D400
BUILD_DIR = '/tmp/rx8-recon-baro_sensor_value'

# MMIO cells the ROM function writes (see rx8_baro_sensor_value.c).
MBOX_A = 0xFFFFE40A      # u16 mailbox-A data word (written when bank == 0)
MBOX_B = 0xFFFFE60A      # u16 mailbox-B data word (written when bank != 0)

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def build_oracle(cc='cc'):
    """Compile THIS sample + its own oracle into /tmp (same command as the
    verification line in the task; do NOT touch common.build_oracle)."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_baro_sensor_value.c'),
           os.path.join(SAMPLES, 'src', 'rx8_baro_sensor_value.c'),
           '-lm', '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def seed(init, addr, n, val):
    """Byte-exact big-endian store of a width-`n` value in the ram overlay."""
    for i in range(n):
        init[addr + i] = (val >> (8 * (n - 1 - i))) & 0xFF


def run_emu(cpu, vec):
    """Run the ROM bytes @0xD144 with r4=bank, r5=value and distinguishable
    pre-states in both MMIO cells; return the two post-state words."""
    bank, val, pre0, pre1 = vec
    init = {}
    seed(init, MBOX_A, 2, pre0 & 0xFFFF)
    seed(init, MBOX_B, 2, pre1 & 0xFFFF)
    cpu.call(ADDR, r4=bank, r5=val, ram=init)
    return (cpu.rd(MBOX_A, 2), cpu.rd(MBOX_B, 2))


def gen_edges():
    """Edge (bank, value, pre0, pre1) vectors targeting every branch."""
    v = []
    # (a) tst branch: bank 0 vs non-zero (2, 0x7F, 0x80, 0xFF exercise the
    #     extu.b masking too) across byte-swap boundary values.  Pre-states are
    #     distinguishable so an accidental write to the wrong cell is caught.
    vals = (0x0000, 0x0001, 0x00FF, 0x0100, 0x1234, 0x7FFF,
            0x8000, 0xAB12, 0xFF00, 0xFF01, 0xFFFF)
    for bank in (0x00, 0x01, 0x02, 0x7F, 0x80, 0xFF):
        for val in vals:
            v.append((bank, val, 0x1234, 0x5678))
    # (b) pre-state survival of the unselected cell (each cell keeps a sweep
    #     of distinct pre-states while the other is overwritten).
    for pre in (0x0000, 0x0001, 0xAAAA, 0x5555, 0x8000, 0xFFFF):
        v.append((0x00, 0xBEEF, pre, 0x7777))   # writes MBOX_A, keeps MBOX_B
        v.append((0x01, 0xBEEF, 0x8888, pre))   # writes MBOX_B, keeps MBOX_A
    return v


def gen_random(rng, k):
    """k random (bank, value, pre0, pre1) pre-states over the full ranges."""
    return [(rng.getrandbits(8), rng.getrandbits(16),
             rng.getrandbits(16), rng.getrandbits(16)) for _ in range(k)]


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(SEED)

    EDGE = gen_edges()
    vectors = EDGE + gen_random(rng, n)

    # (a) ROM behaviour via the emulator (real bytes of 60E1D400.bin @0xD144).
    emu = [run_emu(cpu, v) for v in vectors]

    # (b) host-C on the same pre-states.
    lines = ['bsv %02X %04X %04X %04X' % v for v in vectors]
    host = [tuple(int(x, 16) for x in out.split())
            for out in run_oracle(oracle, lines)]

    # (c) compare the two post-state words bit-exactly.
    mismatches = []
    for i, (v, e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d bank=%02X val=%04X pre0=%04X pre1=%04X '
                'ROM=(%04X,%04X) C=(%04X,%04X)'
                % (i, v[0], v[1], v[2], v[3],
                   e[0], e[1], h[0], h[1]))
            if len(mismatches) >= 5:
                break

    report('baro_sensor_value', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
