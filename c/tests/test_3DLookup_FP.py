#!/usr/bin/env python3
"""
Verify c/3dLookup.c's ThreeDLookup_FP_8bit (@0x2120) and ThreeDLookup_FP_16bit (@0x213C)
against the ACTUAL ROM bytes, run in the SH-2E emulator (tools/sh2emu.py), fed with REAL
calibration-map descriptors found by tools/mapscan.py:
  - u8  Map2D @0x67898  (16x6, X=temp -40..110, Y=1..6, values@0x6D7AC)
  - u16 Map2D @0x68114  (13x7, values@0x704A0)

Both wrappers are hardwired to their cell type with NO scale/offset applied (never read
m->type/scale/offset — only count_x/count_y/axis_x/axis_y/values). The reference model uses
the ROM's actual `fmac` combine (t*(v1-v0)+v0, ONE rounding) at each of the three blend steps
(row0, row1, final ty blend) rather than a double-rounded `a+t*(b-a)` — the latter measurably
diverges from the emulated ROM over enough random inputs (same finding as
test_interp_leaves.py / test_2DLookup_FP_8bit.py).

Run from repo root:  python3 c/tests/test_3DLookup_FP.py [N]
"""
import os, sys, random, struct
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2, ts, s32


class SH2E(SH2):
    def _exec(self, op, pc):
        if op & 0xF0FF == 0x4011:  # cmp/pz
            self.T = 1 if s32(self.r[(op >> 8) & 0xF]) >= 0 else 0; return
        if op & 0xF0FF == 0x4015:  # cmp/pl
            self.T = 1 if s32(self.r[(op >> 8) & 0xF]) > 0 else 0; return
        return super()._exec(op, pc)


ROM = os.path.join(ROOT, 'roms', 'stock', '60E0FC00.bin')
rom = open(ROM, 'rb').read()
cpu = SH2E(rom)


def u16(p): return int.from_bytes(rom[p:p + 2], 'big')
def u32(p): return int.from_bytes(rom[p:p + 4], 'big')
def f32(p): return struct.unpack('>f', rom[p:p + 4])[0]


def load_map2d(desc, cellsize):
    cx = u16(desc); cy = u16(desc + 2)
    axp = u32(desc + 4); ayp = u32(desc + 8); vp = u32(desc + 12)
    ax = [f32(axp + i * 4) for i in range(cx)]
    ay = [f32(ayp + i * 4) for i in range(cy)]
    if cellsize == 1:
        vals = [rom[vp + i] for i in range(cx * cy)]
    else:
        vals = [u16(vp + i * 2) for i in range(cx * cy)]
    return cx, cy, ax, ay, vals


def axis_search(axis, n, x):
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


def fmac(t, a, b):
    """t*(b-a)+a with the ROM's single-rounding fmac semantics."""
    diff = ts(b - a)
    return ts(t * diff + a)


def ref(cx, cy, ax, ay, vals, x, y, mask):
    ix, tx = axis_search(ax, cx, x)
    iy, ty = axis_search(ay, cy, y)
    ix1 = ix + 1 if ix + 1 < cx else ix
    iy1 = iy + 1 if iy + 1 < cy else iy
    c00 = float(vals[iy * cx + ix]); c10 = float(vals[iy * cx + ix1])
    c01 = float(vals[iy1 * cx + ix]); c11 = float(vals[iy1 * cx + ix1])
    row0 = c00 if tx == 0.0 else fmac(tx, c00, c10)
    row1 = c01 if tx == 0.0 else fmac(tx, c01, c11)
    interp = row0 if ty == 0.0 else fmac(ty, row0, row1)
    return int(interp) & mask


def run(name, entry, desc, cellsize, mask, N):
    cx, cy, ax, ay, vals = load_map2d(desc, cellsize)
    xs = list(ax) + [a - 0.001 for a in ax] + [a + 0.001 for a in ax] + [-1000.0, 1000.0]
    ys = list(ay) + [a - 0.001 for a in ay] + [a + 0.001 for a in ay] + [-1000.0, 1000.0]
    cases = [(x, y) for x in xs for y in ys]
    for _ in range(N):
        cases.append((random.uniform(min(ax) - 50, max(ax) + 50), random.uniform(min(ay) - 5, max(ay) + 5)))
    fails = 0
    tested = 0
    for x, y in cases:
        r0 = cpu.call(entry, r4=desc, fr={4: x, 5: y})
        got = r0 & mask
        want = ref(cx, cy, ax, ay, vals, x, y, mask)
        tested += 1
        if got != want:
            fails += 1
            if fails <= 8:
                print("MISMATCH %s x=%r y=%r got=%d want=%d" % (name, x, y, got, want))
    print("%-24s tested=%d fails=%d  %s" % (name, tested, fails, "OK" if not fails else "FAIL"))
    return fails


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 10000
    total = 0
    total += run("ThreeDLookup_FP_8bit", 0x2120, 0x67898, 1, 0xFF, N)
    total += run("ThreeDLookup_FP_16bit", 0x213C, 0x68114, 2, 0xFFFF, N)
    sys.exit(1 if total else 0)


if __name__ == '__main__':
    main()
