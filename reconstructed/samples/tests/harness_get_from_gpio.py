#!/usr/bin/env python3
"""
harness_get_from_gpio.py — equivalence of rx8_get_from_gpio @0x70D0.

Reconstructed source: samples/src/rx8_get_from_gpio.c
Verified lift   : c/getFromGPIO.c (getFromGPIO @ 0x70D0; see the sample
                  header's DISCREPANCIES section — the lift's A/B helper pair,
                  port setup order and 0xF764 "reset to 0xFF" were corrected
                  against the ROM bytes).

The ROM function takes a single byte selector in r4 and scatters two 16-bit
patterns (0x4000 / 0x8000) into the SH7055 port latch 0xF72C, reconfigures
port cells 0xF000..0xF006, runs an in-RAM busy-wait leaf on port 0xF004 (bit
0x40) plus a bit RMW on 0xF764, and returns the byte read at port 0xF005.
The input is therefore the selector byte AND the pre-state of every port cell;
the outputs are the return byte and the post-state of all cells (emulator
reads/writes them through the sign-extended 0xFFFFF0xx window that the SH-2E
mov.w/mov.l literal loads produce).

Procedure (Track-A pattern):
  1. build host oracle (system gcc; own binary, common.build_oracle untouched),
  2. edge vectors (selector 0/1/2/0xFF, all-zero ports, all-ones cells, masks
     0x4000/0x8000 pre-set/cleared in 0xF72C) + N random (seeded) vectors,
  3. run the ROM bytes @0x70D0 in tools/sh2emu.py on the same vectors,
  4. run the host C on the same vectors,
  5. compare return byte + all 9 cells — 0 mismatches.

Usage:  python3 harness_get_from_gpio.py [N]   (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0x70D0
N_DEFAULT = 20000

# Sign-extended cell window used by the ROM (SH-2E mov.w/mov.l literals).
CELLS = {
    'P0':   (0xFFFFF000, 1),   # u8  port dir/ctrl 0
    'P1':   (0xFFFFF001, 1),   # u8  port control 1
    'P2':   (0xFFFFF002, 1),   # u8  port data/dir (RMW)
    'P3':   (0xFFFFF003, 1),   # u8  selector/pattern (leaf)
    'P4':   (0xFFFFF004, 1),   # u8  poll status cell
    'P5':   (0xFFFFF005, 1),   # u8  INPUT/OUTPUT (result)
    'P6':   (0xFFFFF006, 1),   # u8  port aux control
    'F72C': (0xFFFFF72C, 2),   # u16 pattern scatter latch
    'F764': (0xFFFFF764, 2),   # u16 leaf RMW latch
}

EDGE = [
    # (sel, p0, p1, p2, p3, p4, p5, p6, f72c, f764)
    (0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x0000, 0x0000),
    (0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x0000, 0x0000),
    (0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x0000, 0x0000),
    (0xFF, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x0000, 0x0000),
    (0x00, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFFFF, 0xFFFF),
    (0x01, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFFFF, 0xFFFF),
    (0x02, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFFFF, 0xFFFF),
    (0x01, 0x5A, 0x22, 0x3C, 0x33, 0x3C, 0x27, 0x44, 0xABCD, 0x00FF),
    (0x00, 0x5A, 0x22, 0x3C, 0x33, 0x3C, 0x27, 0x44, 0xABCD, 0x00FF),
    (0x02, 0x5A, 0x22, 0x3C, 0x33, 0x3C, 0x27, 0x44, 0xABCD, 0x00FF),
    # 0xF72C with only the pattern bits pre-set/cleared
    (0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x4000, 0x0000),
    (0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x8000, 0x0000),
    (0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xC000, 0x0000),
    # 0xF764 bit 0 pre-clear -> leaf leaves it set at exit
    (0x03, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x0000, 0x00FE),
]

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = '/tmp/rx8-recon-get_from_gpio'


def build_oracle(cc='cc'):
    """Compile THIS sample + its own oracle into /tmp (same command as the
    verification line in the task; do NOT touch common.build_oracle)."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_get_from_gpio.c'),
           os.path.join(SAMPLES, 'src', 'rx8_get_from_gpio.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def seed_ram(cells):
    """Build the emulator ram overlay from a (name, value) cell dict."""
    ram = {}
    for name, (addr, width) in CELLS.items():
        v = cells[name]
        if width == 2:
            ram[addr] = (v >> 8) & 0xFF
            ram[addr + 1] = v & 0xFF
        else:
            ram[addr] = v & 0xFF
    return ram


def read_cells(cpu):
    out = {}
    for name, (addr, width) in CELLS.items():
        out[name] = cpu.rd(addr, width) if width == 2 else cpu._rb(addr)
    return out


def call_gpio(cpu, sel, cells):
    """Run the ROM bytes @0x70D0; return (ret, cell post-state)."""
    r = cpu.call(ADDR, r4=sel, ram=seed_ram(cells))
    return r & 0xFF, read_cells(cpu)


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(ADDR)

    names = ['P0', 'P1', 'P2', 'P3', 'P4', 'P5', 'P6', 'F72C', 'F764']

    def rand_cells():
        cells = {'P%d' % i: rng.randrange(0x100) for i in range(7)}
        cells['F72C'] = rng.randrange(0x10000)
        cells['F764'] = rng.randrange(0x10000)
        return cells

    vectors = []
    for t in EDGE:
        vectors.append((t[0], dict(zip(names, t[1:]))))
    for _ in range(n):
        cells = rand_cells()
        vectors.append((rng.randrange(0x100), cells))

    # (a) ROM behaviour via the emulator
    emu = [call_gpio(cpu, sel, cells) for sel, cells in vectors]

    # (b) host C on the same inputs
    lines = ['gpio %02X %02X %02X %02X %02X %02X %02X %02X %04X %04X'
             % (sel, cells['P0'], cells['P1'], cells['P2'], cells['P3'],
                cells['P4'], cells['P5'], cells['P6'],
                cells['F72C'], cells['F764'])
             for sel, cells in vectors]
    host = [tuple(x.split()) for x in run_oracle(oracle, lines)]

    # (c) compare bit-exact: return byte + all 9 cells
    mismatches = []
    for i, ((sel, cells), e, h) in enumerate(zip(vectors, emu, host)):
        eret, ecells = e
        want = [eret] + [ecells[nm] for nm in names]
        got = [int(x, 16) for x in h]
        if want != got:
            mismatches.append(
                'vec#%d sel=%02X ROM=%s C=%s'
                % (i, sel,
                   ' '.join('%02X' % v for v in want),
                   ' '.join('%02X' % v for v in got)))
            if len(mismatches) >= 5:
                break

    report('getFromGPIO', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()