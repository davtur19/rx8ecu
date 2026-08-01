#!/usr/bin/env python3
"""
harness_data_lookup.py — equivalence of rx8_data_lookup @0x2624.

Reconstructed source: samples/src/rx8_data_lookup.c
Verified lift   : c/2DLookup.c (dataLookup @ 0x2624 — the 1-D axis-search
                  leaf every 2D/3D lookup calls via `bsr`).

The ROM leaf is NOT entered through the normal r4-r7/fr4-fr6 C ABI. It is an
internal leaf invoked via `bsr` with its arguments already live:

    in:  r0 = count, r1 = axis pointer (ascending f32 breakpoints),
         fr0 = x
    out: r0 = index i, fr0 = t

`cpu.call()` only seeds r4-r7, so this harness uses `call_leaf` — a
line-for-line copy of SH2.call()'s body that accepts arbitrary initial
registers (same technique as c/tests/test_dataLookup.py and
c/tests/test_interp_leaves.py; no edit to sh2emu.py needed). The axis array is
staged in sparse RAM at a fixed base (dataLookup only reads it), so synthetic
count==1 / count==2 axes can be tested next to real ROM axes.

Procedure (Track-A pattern):
  1. build the host oracle (system gcc; -O2, -Wall, -Wextra),
  2. edge vectors (every breakpoint, +/-0.001 either side, interval
     midpoints, far out-of-range, +/-inf, NaN, 0.0) + N random x values,
     over real f32 axis arrays read from 1-D map descriptors of THIS ROM
     (60E1D400.bin) plus synthetic count==1 / count==2 axes,
  3. run the ROM bytes @0x2624 in tools/sh2emu.py on the same vectors,
  4. run the host C on the same vectors,
  5. compare the raw float bits of t and the index i — 0 mismatches required.

Usage:  python3 harness_data_lookup.py [N]   (default N = 20000)
"""
import os
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROM_PATH, make_rng, report, run_oracle  # noqa: E402
# common.py already put <repo>/tools on sys.path (its sh2emu import); fetch the
# leaf-helper pieces of the emulator API from the same module.
from sh2emu import SH2, MASK, ts, f2bits  # noqa: E402

ADDR = 0x2624
N_DEFAULT = 20000

# Real 1-D map descriptors in THIS ROM (60E1D400.bin) with f32 ASCENDING axis
# arrays (count @+0, axis ptr @+4; found with tools/mapscan.py).
# axis@0x6E57C  16 pts [600..3500]          RPM -> u16 map  (dense 1700/1701)
# axis@0x6E4A4   6 pts [-20..80]            temp -> u16 map
# axis@0x6CFA4  16 pts [800..6800]          RPM -> u8 map
# axis@0x6D120   6 pts [0..25000]           u8 map
# axis@0x6D140   6 pts [500..3500]          f32 map
DESCRIPTORS = (0x69C38, 0x69BC0, 0x69934, 0x69984, 0x69998)

# Synthetic extremes: count==1 and count==2 axes (the ROM's count==1 fast path
# and the k==0 middle-case / clamp-low boundary).
SYNTHETIC = [[37.5], [-5.0, 100.0]]

AXIS_BASE = 0x30000000            # sparse-RAM address backing the axis array

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = os.path.join('/tmp', 'rx8-recon-data_lookup')


class SH2E(SH2):
    """SH2 + call_leaf(): inject arbitrary initial registers (r0-r15, fr0-fr15),
    needed for dataLookup's r0/r1/fr0 -> r0/fr0 leaf-level convention (it is not
    entered via r4-r7).  Line-for-line copy of SH2.call()'s body, as in
    c/tests/test_dataLookup.py."""

    def call_leaf(self, entry, regs=None, fr=None, ram=None):
        self.ram = dict(ram or {})
        self.r = [0] * 16
        for k, v in (regs or {}).items():
            self.r[k] = v & MASK
        self.r[15] = 0xFFFFDF00
        self.fr = [0.0] * 16
        for k, v in (fr or {}).items():
            self.fr[k] = ts(v)
        self.pr = self.SENT; self.T = 0; self.macl = 0; self.mach = 0; self.gbr = 0
        self.fpul = 0; self.fpscr = 0
        self.pc = entry & MASK
        steps = 0
        while True:
            if self.pc == self.SENT:
                return self.r[0] & MASK
            steps += 1
            if steps > 500000:
                raise RuntimeError("runaway at 0x%X" % self.pc)
            op = self.rd(self.pc, 2)
            br = self._delayed(op)
            if br is None:
                self._exec(op, self.pc); self.pc = (self.pc + 2) & MASK
            else:
                target, take = br
                self._exec(self.rd(self.pc + 2, 2), self.pc + 2)
                self.pc = target if take else (self.pc + 4) & MASK


def build_oracle(cc='cc'):
    """Compile the reconstructed source + its own oracle into a host binary.
    (common.build_oracle is not reusable: it hardcodes the sample .c list.)"""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_data_lookup.c'),
           os.path.join(SAMPLES, 'src', 'rx8_data_lookup.c'),
           '-lm',
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def load_axis(cpu, desc_addr):
    """Read count + f32 axis array of a 1-D map descriptor straight from the ROM."""
    rom = cpu.rom
    count = struct.unpack_from('>H', rom, desc_addr)[0]
    ap = struct.unpack_from('>I', rom, desc_addr + 4)[0]
    return [struct.unpack_from('>f', rom, ap + 4 * i)[0] for i in range(count)]


def gen_edges(axis):
    """Edge vectors: every breakpoint (both clamp boundaries are breakpoints),
    +/-0.001 either side, interval midpoints, far out-of-range both sides,
    +/-inf, NaN (must clamp high) and plain 0.0."""
    n = len(axis)
    v = []
    for i, a in enumerate(axis):
        v.append(a)                             # exact breakpoint
        v.append(ts(a - 0.001))
        v.append(ts(a + 0.001))
        if i + 1 < n:
            v.append(ts((a + axis[i + 1]) * 0.5))   # interval midpoint
    v.append(ts(axis[0] - 100.0))               # far below axis[0]
    v.append(ts(axis[-1] + 100.0))              # far above axis[-1]
    v.append(float('-inf'))                     # clamps low
    v.append(float('inf'))                      # clamps high
    v.append(float('nan'))                      # clamps high (fcmp/gt false)
    v.append(0.0)
    return v


def gen_random(rng, axis, k):
    """k random x values spanning below axis[0] .. above axis[-1]."""
    lo = min(axis[0], 0.0) - 100.0
    hi = axis[-1] + 100.0
    return [ts(rng.uniform(lo, hi)) for _ in range(k)]


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    # plain SH2 lacks call_leaf; build SH2E over the same ROM bytes
    with open(ROM_PATH, 'rb') as f:
        cpu = SH2E(f.read())
    oracle = build_oracle()
    rng = make_rng(0x60E1D400)

    tables = [load_axis(cpu, d) for d in DESCRIPTORS] + SYNTHETIC

    vectors = []                    # list of (axis, x) pairs
    for axis in tables:
        vectors += [(axis, x) for x in gen_edges(axis)]
        vectors += [(axis, x) for x in gen_random(rng, axis, n // len(tables))]

    # (a) ROM behaviour via the emulator: seed r0/r1/fr0, read r0/fr0.
    emu = []
    for axis, x in vectors:
        ram = {}
        for i, a in enumerate(axis):
            b = struct.pack('>f', a)
            for j in range(4):
                ram[AXIS_BASE + 4 * i + j] = b[j]
        cpu.call_leaf(ADDR, regs={0: len(axis), 1: AXIS_BASE}, fr={0: x}, ram=ram)
        emu.append((cpu.r[0] & MASK, f2bits(cpu.fr[0])))

    # (b) host C on the same inputs (axis shipped inline, floats as raw bits).
    lines = ['dl %X %08X %s' % (len(axis), f2bits(x),
                                ' '.join('%08X' % f2bits(a) for a in axis))
             for axis, x in vectors]
    host = [tuple(int(tok, 16) for tok in ln.split())
            for ln in run_oracle(oracle, lines)]

    # (c) compare index and raw t bits.
    mismatches = []
    for k, ((axis, x), e, h) in enumerate(zip(vectors, emu, host)):
        if e[0] != h[0] or e[1] != h[1]:
            mismatches.append(
                'vec#%d x=%r axis=%s ROM=(%d,0x%08X) C=(%d,0x%08X)'
                % (k, x, axis, e[0], e[1], h[0], h[1]))
            if len(mismatches) >= 5:
                break

    report('dataLookup', ADDR, n, mismatches, edges=len(vectors))


if __name__ == '__main__':
    main()
