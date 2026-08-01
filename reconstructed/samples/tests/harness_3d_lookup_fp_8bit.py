#!/usr/bin/env python3
"""
harness_3d_lookup_fp_8bit.py — equivalence of rx8_3d_lookup_fp_8bit @0x2120.

Reconstructed source: samples/src/rx8_3d_lookup_fp_8bit.c
Verified lift   : c/3dLookup.c (ThreeDLookup_FP_8bit @ 0x2120)

The u8-cell, float-input bilinear map lookup.  Standard ABI entry (r4 =
Map2D* descriptor, fr4 = x, fr5 = y); the uint8_t result comes back
zero-extended in r0 (mask 0xFF).  The internal 1-D u8 leaf uses a non-ABI
register convention, but that lives inside the ROM body — callers of 0x2120
only ever need the plain ABI, so this harness uses plain `cpu.call()`.

Descriptors come from THIS ROM (60E1D400.bin), found with tools/mapscan.py
(Map2D layout: u16 count_x, u16 count_y, f32* axis_x@4, f32* axis_y@8,
void* values@12, u8 type@16 — type 4 = u8 cells, no scale/offset read):
  - 0x699E4  Table 3D - 0_    16x6  u8   X=temp -40..110, Y=1..6
  - 0x69AA4  Ignition Timing Lead  10x7  u8
  - 0x69DA0  Table 3D - 12_    7x3   u8
plus one synthetic 4x3 grid (0x00/0xFF extremes) injected into sparse RAM so
the emulator reads it exactly like a real ROM descriptor.

Procedure (Track-A pattern):
  1. build the host oracle (system gcc; -O2, -Wall, -Wextra, -lm),
  2. edge vectors (every breakpoint on both axes + just below/above each,
     far out-of-range, +/-0.0, NaN — full cross product) + N random (x, y),
  3. run the ROM bytes @0x2120 in tools/sh2emu.py on the same vectors,
  4. run the host C on the same vectors (floats cross the pipe as raw bits),
  5. compare byte results — 0 mismatches required.

Usage:  python3 harness_3d_lookup_fp_8bit.py [N]   (default N = 20000)
"""
import os
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROM_PATH, make_rng, report, run_oracle  # noqa: E402
from sh2emu import SH2, f2bits  # noqa: E402

ADDR = 0x2120
N_DEFAULT = 20000

# Real u8-cell Map2D descriptors in THIS ROM (60E1D400.bin), found with
# tools/mapscan.py.  Descriptor fields (big-endian): u16 cx@0, u16 cy@2,
# f32* axis_x@4, f32* axis_y@8, void* values@12, u8 type@16 (=4, u8 cells).
DESCRIPTORS = (0x699E4, 0x69AA4, 0x69DA0)

# Sparse-RAM region backing the synthetic descriptor (emulator reads ram first).
RAM_BASE = 0x30000000

# Synthetic extremes grid: exercises both uint8 endpoints and steep deltas.
SYNTHETIC = {
    'cx': 4, 'cy': 3,
    'ax': [-10.0, 0.0, 10.0, 20.0],
    'ay': [0.0, 5.0, 10.0],
    'vals': [0x00, 0xFF, 0x80, 0x01,
             0xFF, 0x00, 0x01, 0x80,
             0x01, 0x80, 0xFF, 0x00],
}

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = os.path.join('/tmp', 'rx8-recon-3d_lookup_fp_8bit')


def build_oracle(cc='cc'):
    """Compile the reconstructed source + its own oracle into a host binary.
    (common.build_oracle is not reusable: it hardcodes the sample .c list.)"""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_3d_lookup_fp_8bit.c'),
           os.path.join(SAMPLES, 'src', 'rx8_3d_lookup_fp_8bit.c'),
           '-lm',                              # fmaf() lives in libm
           '-o', oracle]
    subprocess.check_call(cmd)
    return oracle


def load_map2d(cpu, desc):
    """Read a Map2D descriptor + its axes + u8 values straight from the ROM."""
    rom = cpu.rom
    cx = int.from_bytes(rom[desc:desc + 2], 'big')
    cy = int.from_bytes(rom[desc + 2:desc + 4], 'big')
    axp = int.from_bytes(rom[desc + 4:desc + 8], 'big')
    ayp = int.from_bytes(rom[desc + 8:desc + 12], 'big')
    vp = int.from_bytes(rom[desc + 12:desc + 16], 'big')
    ax = [struct.unpack('>f', rom[axp + 4 * i: axp + 4 * i + 4])[0]
          for i in range(cx)]
    ay = [struct.unpack('>f', rom[ayp + 4 * i: ayp + 4 * i + 4])[0]
          for i in range(cy)]
    vals = [rom[vp + i] for i in range(cx * cy)]
    return cx, cy, ax, ay, vals


def build_synthetic_ram(s):
    """Big-endian Map2D descriptor + axes + values in sparse RAM (0x30000000)."""
    ram = {}

    def w(a, n, v):
        for i in range(n):
            ram[a + i] = (v >> (8 * (n - 1 - i))) & 0xFF

    axp, ayp, vp = RAM_BASE + 0x40, RAM_BASE + 0x80, RAM_BASE + 0xC0
    w(RAM_BASE, 2, s['cx'])
    w(RAM_BASE + 2, 2, s['cy'])
    w(RAM_BASE + 4, 4, axp)
    w(RAM_BASE + 8, 4, ayp)
    w(RAM_BASE + 12, 4, vp)
    ram[RAM_BASE + 16] = 4                      # type = u8 (never read)
    w(RAM_BASE + 20, 4, 0)                      # scale / offset (never read)
    w(RAM_BASE + 24, 4, 0)
    for i, v in enumerate(s['ax']):
        w(axp + 4 * i, 4, struct.unpack('>I', struct.pack('>f', v))[0])
    for i, v in enumerate(s['ay']):
        w(ayp + 4 * i, 4, struct.unpack('>I', struct.pack('>f', v))[0])
    for i, v in enumerate(s['vals']):
        ram[vp + i] = v & 0xFF
    return ram


def gen_edges(ax, ay):
    """Cross product of X-edge set x Y-edge set: every breakpoint, just below
    and just above each, far out-of-range on both sides, +/-0.0 and NaN."""
    xs = list(ax) + [a - 0.001 for a in ax] + [a + 0.001 for a in ax]
    xs += [min(ax) - 1000.0, max(ax) + 1000.0, 0.0, -0.0, float('nan')]
    ys = list(ay) + [a - 0.001 for a in ay] + [a + 0.001 for a in ay]
    ys += [min(ay) - 100.0, max(ay) + 100.0, 0.0, -0.0, float('nan')]
    return [(x, y) for x in xs for y in ys]


def gen_random(rng, ax, ay, k):
    """k random (x, y) pairs in/around the map range; 5% far out-of-range."""
    v = []
    for _ in range(k):
        if rng.random() < 0.05:
            x = rng.uniform(min(ax) - 1000.0, max(ax) + 1000.0)
            y = rng.uniform(min(ay) - 1000.0, max(ay) + 1000.0)
        else:
            x = rng.uniform(min(ax) - 50.0, max(ax) + 50.0)
            y = rng.uniform(min(ay) - 5.0, max(ay) + 5.0)
        v.append((x, y))
    return v


def fmt_bits(v):
    return '%08X' % f2bits(v)


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    # plain SH2 over the stock ROM (standard ABI entry, so no call helper
    # needed — unlike the 1-D u8 leaf's non-ABI r0/r1/fr0->fr2 convention)
    with open(ROM_PATH, 'rb') as f:
        cpu = SH2(f.read())
    oracle = build_oracle()
    rng = make_rng(0x60E1D400)

    # tables: (desc_or_None, ram_or_None, cx, cy, ax, ay, vals)
    loaded = []
    for d in DESCRIPTORS:
        cx, cy, ax, ay, vals = load_map2d(cpu, d)
        loaded.append((d, None, cx, cy, ax, ay, vals))
    loaded.append((RAM_BASE, build_synthetic_ram(SYNTHETIC),
                   SYNTHETIC['cx'], SYNTHETIC['cy'],
                   SYNTHETIC['ax'], SYNTHETIC['ay'], SYNTHETIC['vals']))

    vectors = []                    # (desc_or_ram, ram, cx, cy, ax, ay, vals, x, y)
    for d, ram, cx, cy, ax, ay, vals in loaded:
        for x, y in gen_edges(ax, ay):
            vectors.append((d, ram, cx, cy, ax, ay, vals, x, y))
        for x, y in gen_random(rng, ax, ay, n // len(loaded)):
            vectors.append((d, ram, cx, cy, ax, ay, vals, x, y))

    # (a) ROM behaviour via the emulator (result returned in r0, mask 0xFF).
    n_edge = sum(len(gen_edges(ax, ay)) for d, ram, cx, cy, ax, ay, vals in loaded)
    emu = []
    for d, ram, cx, cy, ax, ay, vals, x, y in vectors:
        if ram is not None:
            r0 = cpu.call(ADDR, r4=d, ram=ram, fr={4: x, 5: y})
        else:
            r0 = cpu.call(ADDR, r4=d, fr={4: x, 5: y})
        emu.append(r0 & 0xFF)

    # (b) host C on the same inputs (axes/values inline, floats as raw bits).
    lines = ['f8 %X %X %s %s %s %s %s'
             % (cx, cy,
                ' '.join(fmt_bits(a) for a in ax),
                ' '.join(fmt_bits(a) for a in ay),
                ' '.join('%02X' % c for c in vals),
                fmt_bits(x), fmt_bits(y))
             for d, ram, cx, cy, ax, ay, vals, x, y in vectors]
    host = [int(x, 16) for x in run_oracle(oracle, lines)]

    # (c) compare byte results.
    mismatches = []
    for k, ((d, ram, cx, cy, ax, ay, vals, x, y), e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d desc=0x%X x=%.9g y=%.9g ROM=%02X C=%02X'
                % (k, d, x, y, e, h))
            if len(mismatches) >= 5:
                break

    report('3DLookup_FP_8bit', ADDR, n, mismatches, edges=n_edge)

if __name__ == '__main__':
    main()
