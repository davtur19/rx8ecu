#!/usr/bin/env python3
"""
harness_2d_lookup_fp_8bit.py — equivalence of rx8_2d_lookup_fp_8bit @0x20AC.

Reconstructed source: samples/src/rx8_2d_lookup_fp_8bit.c
Verified lift   : c/2DLookup.c (TwoDLookup_FP_8bit @ 0x20AC)

The ROM function is entered through the normal ABI (r4 = Map1D descriptor,
fr4 = x); internally it drives the non-ABI leaf pair 0x2624/0x26B0 (see
rx8_interpolate_u8_table.c), so this harness can use the plain `cpu.call()`
like c/tests/test_2DLookup_FP_8bit.py.

Procedure (Track-A pattern):
  1. build the host oracle (system gcc; -O2, -Wall, -Wextra, -lm),
  2. real u8 map descriptors read straight from THIS ROM (60E1D400.bin,
     found with tools/mapscan.py) + synthetic extremes tables,
  3. edge vectors (every breakpoint, +/-nextafter, +/-0.001, interval
     midpoints, out-of-range clamps, 0.0, NaN, +/-1e30) + N random
     (uniform in-range plus random raw float bits),
  4. run the ROM bytes @0x20AC in tools/sh2emu.py on the same vectors,
  5. run the host C on the same vectors (x shipped as raw float bits),
  6. compare the truncated uint8 results — 0 mismatches required.

Usage:  python3 harness_2d_lookup_fp_8bit.py [N]   (default N = 20000)
"""
import math
import os
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROM_PATH, make_rng, report, run_oracle  # noqa: E402
from sh2emu import SH2, ts, f2bits, bits2f  # noqa: E402

ADDR = 0x20AC
N_DEFAULT = 20000

# Real 1-D u8 map descriptors in THIS ROM (60E1D400.bin), from mapscan.py.
# 16-cell RPM tables, 10-cell, 6-cell idle/ignition tables...
DESCRIPTORS = (0x69934, 0x69948, 0x6995C, 0x69970, 0x69984, 0x69A54, 0x69A68)

# Synthetic descriptor boundaries: count=2 minimum, cell extremes 0x00/0xFF
# (steepest possible delta), and a constant-cell table (diff == 0.0).
SYNTHETIC = (
    # (axis, cells)
    ([1000.0, 5000.0], [0x00, 0xFF]),
    ([1000.0, 5000.0], [0x80, 0x80]),
)

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = os.path.join('/tmp', 'rx8-recon-2d_lookup_fp_8bit')


def build_oracle(cc='cc'):
    """Compile the reconstructed source + its own oracle into a host binary."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_2d_lookup_fp_8bit.c'),
           os.path.join(SAMPLES, 'src', 'rx8_2d_lookup_fp_8bit.c'),
           '-lm',                              # fmaf() lives in libm
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def load_table(cpu, desc_addr):
    """Read count + axis + u8 values array of a 1-D map descriptor (ROM)."""
    rom = cpu.rom
    count = struct.unpack_from('>H', rom, desc_addr)[0]
    axp = struct.unpack_from('>I', rom, desc_addr + 4)[0]
    vp = struct.unpack_from('>I', rom, desc_addr + 8)[0]
    axis = [struct.unpack_from('>f', rom, axp + 4 * i)[0] for i in range(count)]
    cells = list(rom[vp:vp + count])
    return axis, cells


def gen_edges(axis, cells):
    """Edge vectors: every breakpoint (exact), +/-1 ulp, +/-0.001, interval
    midpoints, out-of-range clamps, 0.0, NaN and huge +/-x."""
    v = []
    n = len(axis)
    for a in axis:
        v.append(a)                                    # exact breakpoint
        v.append(math.nextafter(a, -math.inf))         # 1 ulp below
        v.append(math.nextafter(a, math.inf))          # 1 ulp above
        v.append(a - 0.001)
        v.append(a + 0.001)
    for i in range(n - 1):
        v.append(ts((axis[i] + axis[i + 1]) * 0.5))    # interval midpoint
    v.append(axis[0] - 1000.0)                         # clamp low
    v.append(axis[-1] + 1000.0)                        # clamp high
    v.append(0.0)
    v.append(float('nan'))                             # NaN -> clamp high
    v.append(-1e30)
    v.append(1e30)
    return v


def gen_random(rng, axis, k):
    """k random vectors: uniform in-range +/- margin plus raw float bits."""
    lo, hi = axis[0] - 500.0, axis[-1] + 500.0
    v = []
    for _ in range(k):
        if rng.random() < 0.5:
            v.append(ts(rng.uniform(lo, hi)))
        else:
            v.append(bits2f(rng.getrandbits(32)))
    return v


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    with open(ROM_PATH, 'rb') as f:
        cpu = SH2(f.read())
    oracle = build_oracle()
    rng = make_rng(0x60E1D400)

    tables = [load_table(cpu, d) for d in DESCRIPTORS] + list(SYNTHETIC)
    desc_addrs = list(DESCRIPTORS) + [None] * len(SYNTHETIC)

    # (a) ROM behaviour via the emulator: r4 = descriptor ptr, fr4 = x.
    # Real descriptors are passed by their ROM address (fast emulator path);
    # synthetic ones are materialised as a byte-exact big-endian copy in a
    # scratch-RAM area first.
    vectors = []                    # list of (axis, cells, x)
    emu = []
    for (axis, cells), desc in zip(tables, desc_addrs):
        t = [(axis, cells, x) for x in gen_edges(axis, cells)]
        t += [(axis, cells, x) for x in gen_random(rng, axis, n // len(tables))]
        for (ax2, c2, x) in t:
            if desc is not None:
                emu.append(cpu.call(ADDR, r4=desc, fr={4: x}) & 0xFF)
                continue
            base = 0x20000000
            axp = base + 0x40
            vp = axp + 4 * len(c2)
            ram = {}
            ram[base + 0] = (len(c2) >> 8) & 0xFF     # big-endian u16 count
            ram[base + 1] = len(c2) & 0xFF
            ram[base + 2] = 4                            # type: u8 (never read)
            for i, a in enumerate(ax2):
                b = struct.pack('>f', a)
                for j in range(4):
                    ram[axp + 4 * i + j] = b[j]
            for i, c in enumerate(c2):
                ram[vp + i] = c & 0xFF
            for k in range(4):
                ram[base + 4 + k] = (axp >> (8 * (3 - k))) & 0xFF
                ram[base + 8 + k] = (vp >> (8 * (3 - k))) & 0xFF
            emu.append(cpu.call(ADDR, r4=base, ram=ram, fr={4: x}) & 0xFF)
        vectors += t

    # (b) host C on the same inputs (axis as float bits, cells inline).
    lines = ['fp8 %X %08X %s %s'
             % (len(cells), f2bits(x),
                ' '.join('%08X' % f2bits(a) for a in axis),
                ' '.join('%02X' % c for c in cells))
             for axis, cells, x in vectors]
    host = [int(x, 16) for x in run_oracle(oracle, lines)]

    # (c) compare the truncated uint8 results.
    mismatches = []
    for k, ((axis, cells, x), e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d x=0x%08X cells=%s axis=%s..%s ROM=%02X C=%02X'
                % (k, f2bits(x), cells, axis[0], axis[-1], e, h))
            if len(mismatches) >= 5:
                break

    n_edges = len(vectors) - len(tables) * (n // len(tables))
    report('TwoDLookup_FP_8bit', ADDR, n, mismatches, edges=n_edges)


if __name__ == '__main__':
    main()
