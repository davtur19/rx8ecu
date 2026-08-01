#!/usr/bin/env python3
"""
harness_interpolate_u16_table.py — equivalence of rx8_interpolate_u16_table @0x26D0.

Reconstructed source: samples/src/rx8_interpolate_u16_table.c
Verified lift   : c/interp_leaves.c (interpolate_uint16Table @ 0x26D0)

The ROM leaf is NOT entered through the normal r4-r7/fr4-fr6 C ABI. It is an
internal leaf invoked via `bsr` straight after the axis-search helper (0x2624)
with that helper's results still live in registers:

    in:  r0 = cell index i, r1 = u16-cell-array pointer, fr0 = t in [0,1)
    out: fr2 = interpolated float (fr0 left untouched for the 2-D callers)

`cpu.call()` only seeds r4-r7, so this harness uses `call_leaf` — a line-for-line
copy of SH2.call()'s body that accepts arbitrary initial registers (same trick as
c/tests/test_interp_leaves.py; no edit to sh2emu.py needed).

Procedure (Track-A pattern):
  1. build the host oracle (system gcc; -O2, -Wall, -Wextra, -lm),
  2. edge vectors (every index with t=0.0 incl. the clamp-high i=n-1 case,
     t at 0/0.25/0.5/0.75/1-eps/1.0, out-of-range t, tiny t) + N random
     (i, t) pairs, over real u16 cell arrays read from ROM map descriptors of
     the same 60E1D400.bin plus one synthetic extremes array,
  3. run the ROM bytes @0x26D0 in tools/sh2emu.py on the same vectors,
  4. run the host C on the same vectors,
  5. compare the raw float bits — 0 mismatches required.

Usage:  python3 harness_interpolate_u16_table.py [N]   (default N = 20000)
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

ADDR = 0x26D0
N_DEFAULT = 20000

# Real u16-cell arrays from 1-D map descriptors in THIS ROM (60E1D400.bin),
# found with tools/mapscan.py's descriptor layout (u16 count; +8 values ptr;
# type 8 = u16 cells).
# values@0x6D1E0 16 cells [2500,2500,2500,2400,2100,2100,2075,2000,1800,1700,1700,1400,1400,1400,1400,1400]  Idle Related
# values@0x6E4BC  6 cells [25,25,25,35,35,35]          Table 2D - 10_ (0.001 scale)
# values@0x6E5BC 16 cells [203,200,198,198,192,183,178,174,172,169,177,174,172,170,120,70]  Table 2D - 16_
# values@0x6E880  7 cells [1700,1700,1650,1450,1200,950,810]  Idle Target
DESCRIPTORS = (0x699BC, 0x69BC0, 0x69C38, 0x69CEC)

# Synthetic extremes table: exercises both uint16 endpoints and steep deltas.
SYNTHETIC = [0x0000, 0xFFFF, 0x8000, 0x0001, 0xFFFE, 0x7FFF, 0x4000, 0xBFFF,
             0x0000, 0xFFFF]

CELL_BASE = 0x30000000            # sparse-RAM address backing the cell array

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = os.path.join('/tmp', 'rx8-recon-interpolate_u16_table')


class SH2E(SH2):
    """SH2 + call_leaf(): inject arbitrary initial registers (r0-r15, fr0-fr15),
    needed for interpolate_uint16Table's r0/r1/fr0 -> fr2 leaf-level convention
    (it is not entered via r4-r7).  Line-for-line copy of SH2.call()'s body,
    as in c/tests/test_interp_leaves.py."""

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
           os.path.join(SAMPLES, 'tests', 'oracle_interpolate_u16_table.c'),
           os.path.join(SAMPLES, 'src', 'rx8_interpolate_u16_table.c'),
           '-lm',                              # fmaf() lives in libm
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def load_u16_table(cpu, desc_addr):
    """Read count + u16 values array of a 1-D map descriptor straight from the ROM."""
    rom = cpu.rom
    count = struct.unpack_from('>H', rom, desc_addr)[0]
    vp = struct.unpack_from('>I', rom, desc_addr + 8)[0]
    return [struct.unpack_from('>H', rom, vp + i * 2)[0] for i in range(count)]


def gen_edges(cells):
    """Edge vectors: every index with t=0.0 (both clamp ends incl. i=n-1 where
    the no-read-past-end fast path must fire), plus t at 0/0.25/0.5/0.75/1-eps/
    1.0, tiny-nonzero t, negative zero and out-of-range t (always with i<n-1 so
    cells[i+1] stays a valid read, exactly the leaf's contract)."""
    n = len(cells)
    v = []
    for i in range(n):
        v.append((i, 0.0))                       # all indices, clamp t=0 (i=n-1 safe)
    for i in range(n - 1):
        v.append((i, -0.0))                      # -0.0 == 0.0 -> fast path
        v.append((i, 0.0 + 1e-30))               # nonzero but t*diff rounds away
        v.append((i, 0.25))
        v.append((i, 0.5))                       # exact midpoint
        v.append((i, 0.75))
        v.append((i, 1.0 - 1e-7))                # just below the [0,1) ceiling
        v.append((i, 1.0))                       # contract edge (still valid: i<n-1)
        v.append((i, -0.5))                      # out-of-range t (overflow guard)
        v.append((i, 1.5))
        v.append((i, 2.0))
        v.append((i, 1000.0))
    return v


def gen_random(rng, cells, k):
    """k random (i, t) vectors; 5% high-clamp hits to exercise the fast path."""
    n = len(cells)
    v = []
    for _ in range(k):
        if rng.random() < 0.05:
            v.append((n - 1, 0.0))
        else:
            v.append((rng.randrange(0, n - 1), rng.uniform(0.0, 1.0)))
    return v


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    # plain SH2 lacks call_leaf; build SH2E over the same ROM bytes
    with open(ROM_PATH, 'rb') as f:
        cpu = SH2E(f.read())
    oracle = build_oracle()
    rng = make_rng(0x60E1D400)

    tables = [load_u16_table(cpu, d) for d in DESCRIPTORS] + [SYNTHETIC]

    vectors = []                    # list of (i, t, cells) triples
    for cells in tables:
        vectors += [(i, t, cells) for (i, t) in gen_edges(cells)]
        vectors += [(i, t, cells) for (i, t) in gen_random(rng, cells,
                                                           n // len(tables))]

    # (a) ROM behaviour via the emulator: seed r0/r1/fr0, read fr2.
    emu = []
    for i, t, cells in vectors:
        ram = {}
        for k, c in enumerate(cells):
            ram[CELL_BASE + k * 2] = (c >> 8) & 0xFF
            ram[CELL_BASE + k * 2 + 1] = c & 0xFF
        cpu.call_leaf(ADDR, regs={0: i, 1: CELL_BASE}, fr={0: t}, ram=ram)
        emu.append(f2bits(cpu.fr[2]))

    # (b) host C on the same inputs (cells shipped inline, float t as raw bits).
    lines = ['u16 %X %08X %X %s' % (i, f2bits(t), len(cells),
                                    ' '.join('%04X' % c for c in cells))
             for i, t, cells in vectors]
    host = [int(x, 16) for x in run_oracle(oracle, lines)]

    # (c) compare raw float bits.
    mismatches = []
    for k, ((i, t, cells), e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d i=%d t=%.9g cells=%s ROM=0x%08X C=0x%08X'
                % (k, i, t, cells, e, h))
            if len(mismatches) >= 5:
                break

    report('interpolate_uint16Table', ADDR, n, mismatches, edges=len(vectors))


if __name__ == '__main__':
    main()
