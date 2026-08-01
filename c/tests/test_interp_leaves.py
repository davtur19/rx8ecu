#!/usr/bin/env python3
"""
Verify c/interp_leaves.c (interpolate_uint8Table @0x26B0, interpolate_uint16Table @0x26D0)
and c/3dLookup.c's indexLookupSomething (@0x2658) against the ACTUAL ROM bytes, run in the
SH-2E emulator (tools/sh2emu.py).

The two interpolate_* leaves use a non-ABI, register-level calling convention (r0=index,
r1=cell-array pointer, fr0=t -> result in fr2), invoked inline right after axis-search rather
than through the normal r4-r7/fr4-fr6 C ABI. To feed that from Python we add `call_leaf`, a
line-for-line copy of SH2.call()'s body that accepts arbitrary initial registers instead of
just r4-r7 — no edit to sh2emu.py needed (mount serves truncated copies of just-edited files;
see CRITICAL GOTCHA #1 in the task brief).

indexLookupSomething uses the ordinary ABI (r4=desc, fr4=x, fr5=y) and returns via r2/r3/fr0/
fr1 — read directly off `cpu` after cpu.call() returns.

Real cell/axis data: 60E0FC00.bin @0x677E8 (16-pt u8 1-D table) and @0x67870 (16-pt u16 1-D
table, the one TwoDLookup_FP_16bit's test already uses) for the leaves; @0x67898 (16x6 u8
Map2D) for indexLookupSomething's axes.

Run from repo root:  python3 c/tests/test_interp_leaves.py [N]
"""
import os, sys, random, struct
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2, MASK, ts, s32


class SH2E(SH2):
    """+ cmp/pz, cmp/pl, and call_leaf() — a copy of SH2.call()'s body that accepts arbitrary
    initial registers (r0-r15), needed for interpolate_uint8Table/uint16Table's r0/r1/fr0
    leaf-level calling convention (they are not entered via r4-r7)."""
    def _exec(self, op, pc):
        if op & 0xF0FF == 0x4011:  # cmp/pz
            self.T = 1 if s32(self.r[(op >> 8) & 0xF]) >= 0 else 0; return
        if op & 0xF0FF == 0x4015:  # cmp/pl
            self.T = 1 if s32(self.r[(op >> 8) & 0xF]) > 0 else 0; return
        return super()._exec(op, pc)

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


ROM = os.path.join(ROOT, 'roms', 'stock', '60E0FC00.bin')
rom = open(ROM, 'rb').read()
cpu = SH2E(rom)


def u16(p): return int.from_bytes(rom[p:p + 2], 'big')
def u32(p): return int.from_bytes(rom[p:p + 4], 'big')
def f32(p): return struct.unpack('>f', rom[p:p + 4])[0]


# ---- interpolate_uint8Table @ 0x26B0 : real u8 cell array from 60E0FC00.bin @0x677E8 ----
D8 = 0x677E8
N8 = u16(D8)
VP8 = u32(D8 + 8)
CELLS8 = [rom[VP8 + i] for i in range(N8)]

# ---- interpolate_uint16Table @ 0x26D0 : real u16 cell array @0x67870 (TwoDLookup_FP_16bit's map) ----
D16 = 0x67870
N16 = u16(D16)
VP16 = u32(D16 + 8)
CELLS16 = [u16(VP16 + i * 2) for i in range(N16)]

# ---- indexLookupSomething @ 0x2658 : real Map2D axes from @0x67898 ----
D2D = 0x67898
CX = u16(D2D); CY = u16(D2D + 2)
AXP = u32(D2D + 4); AYP = u32(D2D + 8)
AXIS_X = [f32(AXP + i * 4) for i in range(CX)]
AXIS_Y = [f32(AYP + i * 4) for i in range(CY)]


def ref_leaf(cells, n, i, t):
    """Mirrors the ROM's single `fmac fr0,fr1,fr2` combine (fr2 = t*(v1-v0)+v0, ONE rounding —
    matches the emulator's fmac model `ts(f0*fm+fn)`), NOT `ts(v0)+ts(t*ts(v1-v0))` (which
    rounds twice and measurably diverges over ~1% of random continuous-t inputs)."""
    t = ts(t)
    v0 = float(cells[i])
    if t == 0.0:
        return v0
    v1 = float(cells[i + 1])
    diff = ts(v1 - v0)          # fsub: single rounding
    interp = ts(t * diff + v0)  # fmac: double-precision intermediate, ONE final rounding
    return interp


def ref_axis_search(axis, n, x):
    x = ts(x)
    if not (x < axis[n - 1]):
        return n - 1, ts(0.0)
    if x < axis[0]:
        return 0, ts(0.0)
    i = 0
    while i + 1 < n and not (axis[i] <= x < axis[i + 1]):
        i += 1
    t = ts(ts(x - axis[i]) / ts(axis[i + 1] - axis[i]))
    return i, t


def run_leaf(name, entry, cells, n, cellsize):
    fails = 0
    tested = 0
    # every valid index with t=0.0 (exercise the no-read-past-end shortcut) + random t
    cases = []
    for i in range(n):
        cases.append((i, 0.0))
    for i in range(n - 1):
        cases.append((i, 1.0 - 1e-6))
        for _ in range(3):
            cases.append((i, random.uniform(0.0001, 0.9999)))
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 10000
    for _ in range(N):
        i = random.randint(0, n - 2)
        cases.append((i, random.uniform(0.0, 1.0)))
    for i, t in cases:
        ram = {}
        base = 0x30000000
        for k, v in enumerate(cells):
            if cellsize == 1:
                ram[base + k] = v & 0xFF
            else:
                ram[base + k * 2] = (v >> 8) & 0xFF
                ram[base + k * 2 + 1] = v & 0xFF
        cpu.call_leaf(entry, regs={0: i, 1: base}, fr={0: t}, ram=ram)
        got = cpu.fr[2]
        want = ref_leaf(cells, n, i, t)
        tested += 1
        if struct.pack('>f', got) != struct.pack('>f', want):
            fails += 1
            if fails <= 8:
                print("MISMATCH %s i=%d t=%r got=%r want=%r" % (name, i, t, got, want))
    print("%-24s tested=%d fails=%d  %s" % (name, tested, fails, "OK" if not fails else "FAIL"))
    return fails


def run_index_lookup():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 10000
    fails = 0
    tested = 0
    xs = list(AXIS_X) + [a - 0.001 for a in AXIS_X] + [a + 0.001 for a in AXIS_X] + [-1000.0, 1000.0]
    ys = list(AXIS_Y) + [a - 0.001 for a in AXIS_Y] + [a + 0.001 for a in AXIS_Y] + [-1000.0, 1000.0]
    cases = [(x, y) for x in xs for y in ys]
    for _ in range(N):
        cases.append((random.uniform(-60, 130), random.uniform(-1, 8)))
    for x, y in cases:
        cpu.call(0x2658, r4=D2D, fr={4: x, 5: y})
        ix, iy, tx, ty = cpu.r[2], cpu.r[3], cpu.fr[0], cpu.fr[1]
        want_ix, want_tx = ref_axis_search(AXIS_X, CX, x)
        want_iy, want_ty = ref_axis_search(AXIS_Y, CY, y)
        tested += 1
        ok = (ix == want_ix and iy == want_iy and
              struct.pack('>f', tx) == struct.pack('>f', want_tx) and
              struct.pack('>f', ty) == struct.pack('>f', want_ty))
        if not ok:
            fails += 1
            if fails <= 8:
                print("MISMATCH indexLookupSomething x=%r y=%r got=(%d,%d,%r,%r) want=(%d,%d,%r,%r)"
                      % (x, y, ix, iy, tx, ty, want_ix, want_iy, want_tx, want_ty))
    print("%-24s tested=%d fails=%d  %s" % ("indexLookupSomething", tested, fails, "OK" if not fails else "FAIL"))
    return fails


def main():
    total_fails = 0
    total_fails += run_leaf("interpolate_uint8Table", 0x26B0, CELLS8, N8, 1)
    total_fails += run_leaf("interpolate_uint16Table", 0x26D0, CELLS16, N16, 2)
    total_fails += run_index_lookup()
    sys.exit(1 if total_fails else 0)


if __name__ == '__main__':
    main()
