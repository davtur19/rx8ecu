#!/usr/bin/env python3
"""
harness_index_lookup.py — equivalence of rx8_index_lookup @0x2658.

Reconstructed source: samples/src/rx8_index_lookup.c
Verified lift   : c/3dLookup.c (indexLookupSomething @ 0x2658 — the 2-axis
                  search helper that ThreeDLookup and its FP typed-cell
                  variants dispatch through; each axis searched by the same
                  verified 1-D helper @0x2624).

Calling convention (ordinary ABI): r4 = Map2D descriptor, fr4 = x, fr5 = y;
the four results are returned in registers — r2 = ix, r3 = iy, fr0 = tx,
fr1 = ty (read directly off the emulated CPU after the call).

Procedure (Track-A pattern):
  1. build the host oracle (system gcc; -O2, -Wall, -Wextra),
  2. edge vectors (all breakpoints on both axes, ±epsilon, midpoints, both
     out-of-range clamps, NaN/±inf on either axis) + N random (seeded)
     (x,y) pairs, over two REAL Map2D descriptors of this ROM,
  3. run the ROM bytes @0x2658 in tools/sh2emu.py on the same vectors,
  4. run the host C on the same vectors,
  5. compare — 0 mismatches required (indices exact, tx/ty bit-exact).

Usage:  python3 harness_index_lookup.py [N]   (default N = 20000)
"""
import os
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report  # noqa: E402
# common() puts <repo>/tools on sys.path, so sh2emu is importable here.
from sh2emu import f2bits, ts  # noqa: E402

ADDR = 0x2658
N_DEFAULT = 20000

# Real Map2D descriptors in THIS ROM (60E1D400.bin) — u16 counts @+0/+2 and
# f32 axis pointers @+4/+8, exactly the layout 0x2658 consumes:
#   0x699E4  16x6  X = temp -40..110 step 10,  Y = 1..6        (same map family
#            as the 16x6 surface c/tests/test_interp_leaves.py runs at)
#   0x69AC0  20x18 X = 0.0625..1.25 step 0.0625, Y = 750..9000 (RPM x load)
DESCRIPTORS = (0x699E4, 0x69AC0)

# Special inputs that must never be reachable inside the interval loop: the
# high clamp must swallow them (NaN fails every comparison).
SPECIAL = [float('nan'), float('inf'), float('-inf')]

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = os.path.join('/tmp', 'opencode', 'rx8-recon-index_lookup')
ORACLE = os.path.join(BUILD_DIR, 'oracle')


def build_oracle(cc='cc'):
    """Compile the reconstructed source + its own oracle into a host binary.
    (common.build_oracle is not reusable: it hardcodes the sample .c list.)"""
    os.makedirs(BUILD_DIR, exist_ok=True)
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_index_lookup.c'),
           os.path.join(SAMPLES, 'src', 'rx8_index_lookup.c'),
           '-lm', '-o', ORACLE]
    subprocess.run(cmd, check=True)
    return ORACLE


def load_axis(cpu, desc_addr):
    """Read count_x/count_y + the two f32 axis arrays of a Map2D descriptor
    straight from the ROM (same addresses the emulator reads via r4)."""
    rom = cpu.rom
    cx, cy = struct.unpack_from('>HH', rom, desc_addr)
    axp, ayp = struct.unpack_from('>II', rom, desc_addr + 4)
    xs = [struct.unpack_from('>f', rom, axp + 4 * i)[0] for i in range(cx)]
    ys = [struct.unpack_from('>f', rom, ayp + 4 * i)[0] for i in range(cy)]
    return cx, cy, xs, ys


def gen_values(ax):
    """Edge values along one axis: every breakpoint, just-inside on both sides
    (relative epsilon), interval midpoints, both out-of-range clamps, 0.0."""
    eps = (ax[1] - ax[0]) * 1e-4
    v = list(ax)
    for a in ax:
        v.append(ts(a - eps))
        v.append(ts(a + eps))
    for a, b in zip(ax, ax[1:]):
        v.append(ts((a + b) * 0.5))
        v.append(ts(b - eps))
    v += [ts(ax[0] - 1000.0), ts(ax[-1] + 1000.0), 0.0]
    return v


def gen_edges(xs, ys):
    """Cross product of the per-axis edge values plus the NaN/±inf specials."""
    xv = gen_values(xs) + SPECIAL
    yv = gen_values(ys) + SPECIAL
    return [(x, y) for x in xv for y in yv]


def gen_random(rng, xlo, xhi, ylo, yhi, k):
    return [(rng.uniform(xlo, xhi), rng.uniform(ylo, yhi)) for _ in range(k)]


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(0x2658)

    # (0) pull the real axis arrays out of the ROM
    desc = [load_axis(cpu, d) for d in DESCRIPTORS]

    # (1) build vectors: edge cross products + N random (split across maps)
    vectors = []                       # (desc_id, x, y)
    for di, (cx, cy, xs, ys) in enumerate(desc):
        vectors += [(di, x, y) for (x, y) in gen_edges(xs, ys)]
    rng_ranges = [(-60.0, 130.0, -1.0, 8.0),     # temp map: keep to axis range
                  (0.0, 1.5, 500.0, 10000.0)]    # rpm/load map
    for di in range(len(desc)):
        xlo, xhi, ylo, yhi = rng_ranges[di]
        vectors += [(di, x, y) for (x, y) in
                    gen_random(rng, xlo, xhi, ylo, yhi, n // len(desc))]

    # (2) ROM behaviour via the emulator (r4 = desc addr, fr4/fr5 = x/y;
    #     results come back in r2/r3/fr0/fr1).
    emu = []
    for di, x, y in vectors:
        cpu.call(ADDR, r4=DESCRIPTORS[di], fr={4: x, 5: y})
        emu.append((cpu.r[2], cpu.r[3], f2bits(cpu.fr[0]), f2bits(cpu.fr[1])))

    # (3) host C on the same inputs (axes shipped once per descriptor, then
    #     one lk line per vector; floats as raw bit patterns round-trip
    #     exactly).
    setup = ['axis %d %X %X %s %s' % (di, cx, cy,
                                      ' '.join('%08X' % f2bits(x) for x in xs),
                                      ' '.join('%08X' % f2bits(y) for y in ys))
             for di, (cx, cy, xs, ys) in enumerate(desc)]
    lines = setup + ['lk %d %08X %08X' % (di, f2bits(x), f2bits(y))
                     for di, x, y in vectors]
    # run_oracle() counts output lines against input lines; the `axis` setup
    # lines are silent, so invoke the oracle directly and check the count.
    proc = subprocess.run([oracle], input='\n'.join(lines) + '\n',
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError('host oracle failed:\n' + proc.stderr)
    out = proc.stdout.splitlines()
    if len(out) != len(vectors):
        raise RuntimeError('oracle produced %d outputs for %d lk vectors'
                           % (len(out), len(vectors)))
    host = []
    for o in out:
        parts = o.split()
        host.append((int(parts[0], 16), int(parts[1], 16),
                     int(parts[2], 16), int(parts[3], 16)))

    # (4) compare — indices exact, fractions bit-exact.
    mismatches = []
    for i, (v, e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            di, x, y = v
            mismatches.append(
                'vec#%d map=0x%X x=%.9g y=%.9g '
                'ROM=(%d,%d,%08X,%08X) C=(%d,%d,%08X,%08X)'
                % (i, DESCRIPTORS[di], x, y,
                   e[0], e[1], e[2], e[3], h[0], h[1], h[2], h[3]))
            if len(mismatches) >= 5:
                break

    report('indexLookup', ADDR, n, mismatches, edges=len(vectors))


if __name__ == '__main__':
    main()
