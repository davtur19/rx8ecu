#!/usr/bin/env python3
"""
harness_2d_lookup_fp_16bit.py — equivalence of rx8_2d_lookup_fp_16bit @0x20C4.

Reconstructed source: samples/src/rx8_2d_lookup_fp_16bit.c
Verified lift   : c/2DLookup.c (TwoDLookup_FP_16bit @ 0x20C4)

Procedure (Track-A pattern):
  1. build the host oracle (system gcc; -O2, -Wall, -Wextra),
  2. edge vectors (every breakpoint exactly, +/-0.001 either side, both
     out-of-range clamps, +/-inf, NaN, +/-0.0) + N random inputs spanning
     well beyond both axis ends, over REAL u16 map descriptors found in
     THIS ROM by tools/mapscan.py,
  3. run the ROM bytes @0x20C4 in tools/sh2emu.py on the same vectors
     (plain ABI call: r4 = descriptor, fr4 = x),
  4. run the host C on the same inputs (x shipped as raw float bits),
  5. compare the uint16 results — 0 mismatches required.

Usage:  python3 harness_2d_lookup_fp_16bit.py [N]   (default N = 20000)
"""
import os
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROM_PATH, make_rng, report  # noqa: E402
# common.py already put <repo>/tools on sys.path (its sh2emu import); fetch
# the single-precision rounding + float-bit helpers from the same module.
from sh2emu import SH2, ts, f2bits  # noqa: E402

ADDR = 0x20C4
N_DEFAULT = 20000

# Real u16-cell 1-D map descriptors in THIS ROM (60E1D400.bin), found with
# tools/mapscan.py's descriptor layout (u16 count; +4 axis ptr; +8 values
# ptr).  axis@0x6CFE4 (-40..110 step 10, values 2500..1400: "Idle Related",
# the 60E1D400 twin of the 60E0FC00 @0x67870 table the c/ lift verified on),
# plus two smaller Idle-Target tables for table-shape coverage.
DESCRIPTORS = (0x699BC, 0x69CEC, 0x69D00)

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = os.path.join('/tmp', 'rx8-recon-2d_lookup_fp_16bit')


def build_oracle(cc='cc'):
    """Compile the reconstructed source + its own oracle into a host binary.
    (common.build_oracle is not reusable: it hardcodes the sample .c list.)"""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_2d_lookup_fp_16bit.c'),
           os.path.join(SAMPLES, 'src', 'rx8_2d_lookup_fp_16bit.c'),
           '-lm',                              # fmaf() lives in libm
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def run_oracle_path(oracle, vectors):
    """Like common.run_oracle, but forwards ROM_PATH so the oracle loads the
    same 60E1D400.bin image the emulator runs."""
    proc = subprocess.run([oracle, ROM_PATH],
                          input='\n'.join(vectors) + '\n',
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError('host oracle failed:\n' + proc.stderr)
    lines = proc.stdout.splitlines()
    if len(lines) != len(vectors):
        raise RuntimeError(
            'oracle produced %d outputs for %d vectors' % (len(lines), len(vectors)))
    return lines


def load_descriptor(cpu, desc):
    """count + axis breakpoints + u16 values of a 1-D map descriptor straight
    from the ROM (big-endian, exactly as the ROM function reads them)."""
    rom = cpu.rom
    count = struct.unpack_from('>H', rom, desc)[0]
    axp = struct.unpack_from('>I', rom, desc + 4)[0]
    vp = struct.unpack_from('>I', rom, desc + 8)[0]
    axis = [ts(struct.unpack_from('>f', rom, axp + 4 * i)[0])
            for i in range(count)]
    vals = [struct.unpack_from('>H', rom, vp + 2 * i)[0]
            for i in range(count)]
    return axis, vals


def gen_edges(axis):
    """Edge inputs: every breakpoint exactly, +/-0.001 either side (hits the
    interval below/above each boundary), wide out-of-range clamps, +/-inf
    (finite -> inf round-trips through single precision), NaN (fcmp is false
    for NaN, so it must clamp high like the ROM) and +/-0.0."""
    xs = [ts(a) for a in axis]
    xs += [ts(a - 0.001) for a in axis]
    xs += [ts(a + 0.001) for a in axis]
    xs += [ts(axis[0] - 1000.0), ts(axis[-1] + 1000.0)]
    xs += [float('-inf'), float('inf'), float('nan'), ts(0.0), ts(-0.0)]
    return xs


def gen_random(rng, axis, k):
    """k random inputs spanning well beyond both axis ends (clamps hit often)."""
    lo = axis[0] - 60.0
    hi = axis[-1] + 60.0
    return [ts(rng.uniform(lo, hi)) for _ in range(k)]


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    with open(ROM_PATH, 'rb') as f:
        cpu = SH2(f.read())
    oracle = build_oracle()
    rng = make_rng(0x60E1D400)

    tables = {d: load_descriptor(cpu, d) for d in DESCRIPTORS}

    vectors = []                 # list of (desc, axis, vals, x)
    n_edge = 0
    for desc in DESCRIPTORS:
        axis, vals = tables[desc]
        edge = gen_edges(axis)
        vectors += [(desc, axis, vals, x) for x in edge]
        n_edge += len(edge)
        vectors += [(desc, axis, vals, x)
                    for x in gen_random(rng, axis, n // len(DESCRIPTORS))]

    # (a) ROM behaviour via the emulator (normal ABI: r4=desc, fr4=x).
    emu = [cpu.call(ADDR, r4=desc, fr={4: x}) & 0xFFFF
           for desc, axis, vals, x in vectors]

    # (b) host C on the same inputs (x shipped as raw float bits).
    lines = ['2d %X %08X' % (desc, f2bits(x))
             for desc, axis, vals, x in vectors]
    host = [int(x, 16) for x in run_oracle_path(oracle, lines)]

    # (c) compare.
    mismatches = []
    for k, ((desc, axis, vals, x), e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d desc=0x%X x=%r ROM=0x%04X C=0x%04X' % (k, desc, x, e, h))
            if len(mismatches) >= 5:
                break

    report('2d_lookup_fp_16bit', ADDR, n, mismatches, edges=n_edge)


if __name__ == '__main__':
    main()
