#!/usr/bin/env python3
"""
Test 3dLookup (0x20DC) with type=8 (u16 cells + scale/offset) via SH-2E emulator.

The C lift (c/3dLookup.c) was previously verified only for type=16; the VIS
intake control (0x23718) uses descriptors with type=8, so verify the type=8
path independently here with fully randomized RAM-based descriptors.

Descriptor (28 bytes):
  +0  u16  count_x     +2  u16  count_y
  +4  f32* axis_x      +8  f32* axis_y
  +12 void* values     +16 u8   type (8 = u16 cells)
  +20 f32  scale       +24 f32  offset

Contract:
  (ix,tx) = search(axis_x, x);  (iy,ty) = search(axis_y, y)   # axis_search_float_array
  row0 = cell[iy][ix]   + tx*(cell[iy][ix+1]   - cell[iy][ix])
  row1 = cell[iy+1][ix] + tx*(cell[iy+1][ix+1] - cell[iy+1][ix])
  interp = row0 + ty*(row1 - row0)
  result = scale*interp + offset
  (search clamps: x below axis[0] -> ix=0,tx=0; x >= axis[last] -> ix=cx-1,tx=0)
"""
import os, sys, struct, random
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'tools'))
from sh2emu import SH2, ts

ROM = os.path.join(os.path.dirname(__file__), '..', '..', 'roms', 'stock', '60E1D400.bin')
ADDR = 0x20DC

BASE = 0xFFFFD600      # descriptor in RAM
AX1 = 0xFFFFD700       # axis_x
AX2 = 0xFFFFD780       # axis_y
VAL = 0xFFFFD800       # values

def rb(ram, a):
    return ram.get(a & 0xFFFFFFFF, 0)

def rd(ram, a, n):
    v = 0
    for i in range(n):
        v = (v << 8) | rb(ram, a + i)
    return v

def wr(ram, a, n, v):
    for i in range(n):
        ram[(a + i) & 0xFFFFFFFF] = (v >> (8 * (n - 1 - i))) & 0xFF

def wrf(ram, a, v):
    for i, b in enumerate(struct.pack('>f', ts(v))):
        ram[(a + i) & 0xFFFFFFFF] = b

def search(axis, n, x):
    # axis_search_float_array semantics: clamped at both ends, interpolates
    # everywhere in [axis[0], axis[last]); all arithmetic is f32.
    if n <= 1:
        return 0, 0.0
    if x >= axis[n - 1]:
        return n - 1, 0.0
    if x < axis[0]:
        return 0, 0.0
    for i in range(n - 1):
        if axis[i] <= x < axis[i + 1]:
            d1 = ts(x - axis[i])
            d2 = ts(axis[i + 1] - axis[i])
            return i, ts(d1 / d2)
    return n - 1, 0.0

def interp_row(ix, tx, rowvals):
    # interp_u16_array @0x26D0: cell + tx*(cell_next - cell), fmac rounding
    a = float(rowvals[ix])
    if tx == 0.0:
        return a
    diff = ts(float(rowvals[ix + 1]) - a)
    return ts(tx * diff + a)

def model(desc, x, y):
    cx, cy = desc['cx'], desc['cy']
    ax = desc['ax']; ay = desc['ay']; vals = desc['vals']
    scale, off = desc['scale'], desc['offset']
    ix, tx = search(ax, cx, x)
    iy, ty = search(ay, cy, y)
    row0 = interp_row(ix, tx, vals[iy * cx:(iy + 1) * cx])
    if ty == 0.0:
        interp = row0
    else:
        row1 = interp_row(ix, tx, vals[(iy + 1) * cx:(iy + 2) * cx])
        interp = ts(row0 + ty * ts(row1 - row0))
    return ts(scale * interp + off)

def build_desc(cx, cy):
    ram = {}
    wr(ram, BASE, 2, cx); wr(ram, BASE + 2, 2, cy)
    wr(ram, BASE + 4, 4, AX1); wr(ram, BASE + 8, 4, AX2); wr(ram, BASE + 12, 4, VAL)
    wr(ram, BASE + 16, 1, 8)                     # type = u16
    wrf(ram, BASE + 20, 1.0 / 327.68)            # scale
    wrf(ram, BASE + 24, 0.0)                     # offset
    ax = sorted(ts(random.uniform(-50, 300)) for _ in range(cx))
    ay = sorted(ts(random.uniform(-50, 300)) for _ in range(cy))
    for i, v in enumerate(ax):
        wrf(ram, AX1 + 4 * i, v)
    for i, v in enumerate(ay):
        wrf(ram, AX2 + 4 * i, v)
    vals = [random.randrange(0, 0x10000) for _ in range(cx * cy)]
    for i, v in enumerate(vals):
        wr(ram, VAL + 2 * i, 2, v)
    return ram, dict(cx=cx, cy=cy, ax=ax, ay=ay, vals=vals, scale=1.0 / 327.68, offset=0.0)

def main():
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    random.seed(20260731)
    fails = tests = 0
    for _ in range(4000):
        cx = random.choice([1, 2, 3, 5, 8])
        cy = random.choice([1, 2, 3, 4, 6])
        init, desc = build_desc(cx, cy)
        x = random.uniform(-80, 350)
        y = random.uniform(-80, 350)
        tests += 1
        cpu.call(ADDR, r4=BASE, fr={4: ts(x), 5: ts(y)}, ram=dict(init))
        exp = model(desc, ts(x), ts(y))
        g = cpu.fr[0]
        # compare as f32 bits
        if struct.pack('>f', g) != struct.pack('>f', exp):
            fails += 1
            print("  3dLookup type=8 FAIL cx=%d cy=%d x=%g y=%g emu=%g (0x%08X) ref=%g (0x%08X)" % (
                cx, cy, x, y, g, struct.unpack('>I', struct.pack('>f', g))[0],
                exp, struct.unpack('>I', struct.pack('>f', exp))[0]))
            if fails >= 5:
                break
    print(f"3dLookup type=8: {tests} tests, {fails} failures")
    print("3DLOOKUP_TYPE8:", "PASS" if fails == 0 else "FAIL")
    return 0 if fails == 0 else 1

if __name__ == '__main__':
    sys.exit(main())
