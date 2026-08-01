#!/usr/bin/env python3
"""
harness_3d_lookup_fp_16bit.py — equivalence of rx8_three_d_lookup_fp_16bit @0x213C.

Reconstructed source: samples/src/rx8_3d_lookup_fp_16bit.c
Verified lift   : c/3dLookup.c (ThreeDLookup_FP_16bit @ 0x213C)

ThreeDLookup_FP_16bit is the u16-cell FP-input bilinear map read: normal ABI
(descriptor in r4, x in fr4, y in fr5, result in r0), so plain SH2.call() works
— no leaf-level register injection needed.

The map grid is read from a REAL u16 Map2D descriptor of THIS ROM
(60E1D400.bin) found with tools/mapscan.py: "Torque To Accel Position"
@0x6A96C, 26x19 u16, values@0x73090.  (The c/tests descriptor @0x68114 is from
the sibling ROM 60E0FC00.bin and does not exist here.)

Procedure (Track-A pattern):
  1. build the host oracle (system gcc; -O2, -Wall, -Wextra),
  2. edge vectors: every breakpoint on both axes, +/-0.001 offsets,
     out-of-range (-1000/1000), NaN — full cross product; plus N random
     (x, y) pairs uniform in the axis ranges +/-50 (x) / +/-5 (y) so
     out-of-range interpolation is exercised continuously,
  3. run the ROM bytes @0x213C in tools/sh2emu.py on the same vectors,
  4. run the host C on the same vectors,
  5. compare the truncated u16 results — 0 mismatches required.

Usage:  python3 harness_3d_lookup_fp_16bit.py [N]   (default N = 20000)
"""
import os
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROM_PATH, make_rng, report  # noqa: E402
from sh2emu import SH2, f2bits  # noqa: E402

ADDR = 0x213C
N_DEFAULT = 20000

# Real u16 Map2D descriptor in THIS ROM, found by tools/mapscan.py.
# Torque To Accel Position: 26x19 u16, X=0..250, Y=500..9000, values@0x73090.
DESC = 0x6A96C

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = os.path.join('/tmp', 'rx8-recon-3d_lookup_fp_16bit')


def build_oracle(cc='cc'):
    """Compile the reconstructed source + its own oracle into a host binary.
    (common.build_oracle is not reusable: it hardcodes the sample .c list.)"""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_3d_lookup_fp_16bit.c'),
           os.path.join(SAMPLES, 'src', 'rx8_3d_lookup_fp_16bit.c'),
           '-lm',                              # fmaf() lives in libm
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def load_map2d(cpu):
    """Read a Map2D descriptor straight from the ROM (big-endian, same layout
    as c/3dLookup.c: +0 cx, +2 cy, +4 axis_x*, +8 axis_y*, +12 values*)."""
    rom = cpu.rom
    cx, cy = struct.unpack_from('>HH', rom, DESC)
    axp, ayp, vp = struct.unpack_from('>III', rom, DESC + 4)
    ax = [struct.unpack_from('>f', rom, axp + i * 4)[0] for i in range(cx)]
    ay = [struct.unpack_from('>f', rom, ayp + i * 4)[0] for i in range(cy)]
    vals = [struct.unpack_from('>H', rom, vp + i * 2)[0] for i in range(cx * cy)]
    return cx, cy, ax, ay, vals


def axis_edges(axis):
    """Breakpoints, +-0.001 offsets, wide out-of-range, and NaN (which must
    clamp HIGH — the ROM's fcmp/gt-based test makes NaN clamp high)."""
    xs = list(axis)
    for a in axis:
        xs += [a - 0.001, a + 0.001]
    xs += [-1000.0, 1000.0, float('nan')]
    return xs


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    with open(ROM_PATH, 'rb') as f:
        cpu = SH2(f.read())
    oracle = build_oracle()
    rng = make_rng(0x60E1D400)

    cx, cy, ax, ay, vals = load_map2d(cpu)

    # (i) map line for the oracle (grid shipped once), (ii) edge + random
    # (x, y) vectors.
    map_line = ('map 0 %X %X %s %s %s'
                % (cx, cy,
                   ' '.join('%08X' % f2bits(a) for a in ax),
                   ' '.join('%08X' % f2bits(a) for a in ay),
                   ' '.join('%04X' % v for v in vals)))

    edges = [(x, y) for x in axis_edges(ax) for y in axis_edges(ay)]
    rnd = [(rng.uniform(min(ax) - 50, max(ax) + 50),
            rng.uniform(min(ay) - 5, max(ay) + 5)) for _ in range(n)]
    vectors = edges + rnd

    # (a) ROM behaviour via the emulator (ABI: r4=desc, fr4=x, fr5=y -> r0).
    emu = [cpu.call(ADDR, r4=DESC, fr={4: x, 5: y}) & 0xFFFF
           for x, y in vectors]

    # (b) host C on the same inputs.  (The oracle is stateful: the `map` line
    # ships the grid and prints nothing, so common.run_oracle's per-line count
    # check does not apply — do the run and the count check inline.)
    xy_lines = ['xy 0 %08X %08X' % (f2bits(x), f2bits(y)) for x, y in vectors]
    proc = subprocess.run([oracle], input='\n'.join([map_line] + xy_lines) + '\n',
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError('host oracle failed:\n' + proc.stderr)
    out_lines = proc.stdout.splitlines()
    if len(out_lines) != len(xy_lines):
        raise RuntimeError(
            'oracle produced %d outputs for %d vectors'
            % (len(out_lines), len(xy_lines)))
    host = [int(x, 16) for x in out_lines]

    # (c) compare.
    mismatches = []
    for i, ((x, y), e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d x=%r y=%r ROM=0x%04X C=0x%04X' % (i, x, y, e, h))
            if len(mismatches) >= 5:
                break

    report('ThreeDLookup_FP_16bit', ADDR, n, mismatches, edges=len(edges))


if __name__ == '__main__':
    main()
