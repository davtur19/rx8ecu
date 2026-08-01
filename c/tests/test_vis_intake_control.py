#!/usr/bin/env python3
"""
Test vis_intake_control (0x23718) via SH-2E emulator.

Decoded behavior (see docs/functions/vis_intake_control_23718.md):

  1. Select a 3D table descriptor from status bytes and look it up:
       RAM8[0xFFFFB33C]==1 -> desc 0x6AC60 ; RAM8[0xFFFFB33D]==1 -> 0x6AC7C
       RAM8[0xFFFFB33E]==1 -> desc 0x6AC98 ; else                  -> 0x6ACB4
     x = RAM32[0xFFFFB5B8] (f32), y = RAM32[0xFFFFAA40] (f32)
     fr15 = 3dLookup(desc, x, y)               ; type=8 u16 cells (verified)

  2. RAM32[0xFFFFB408] = fpu_compare_and_select(fr15, 0.0, 84.0)
                          = clamp(fr15, 0.0, 84.0)

  3. Counter index B45C (RAM8[0xFFFFB45C]):
       cal ROM8[0x73F68] != 0 (stock = 1)  -> B45C = 0
       else (dead in stock ROM):
         fr4 = RAM[B5C8]*2.0*0.125 - 2.0 ; clamp >= 0
         B45C = max(clamp(round(fr4), 0..255), 12)

  4. RAM32[0xFFFFB43C] = table[B45C]  (table[i] = RAM32[0xFFFFB408+4i])

  5. 12-iteration reversed-copy loop:
       RAM32[0xFFFFB40C] = table[0]
       RAM32[0xFFFFB410 .. 0xFFFFB438] (11 cells) = RAM32[0xFFFFB43C]

  6. RAM8[0xFFFFB325] is untouched here; function returns via pop/lds.

  With the stock cal byte (0x73F68 == 1), B45C == 0 so table[B45C] ==
  RAM[0xFFFFB408], and every cell 0xFFFFB408..0xFFFFB43C ends up equal to
  the clamped 3dLookup result.
"""
import os, sys, struct, random
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'tools'))
from sh2emu import SH2, ts
import test_3dlookup_type8 as T3

ROM = os.path.join(os.path.dirname(__file__), '..', '..', 'roms', 'stock', '60E1D400.bin')
ADDR = 0x23718

DESCS = (0x6AC60, 0x6AC7C, 0x6AC98, 0x6ACB4)
B408 = 0xFFFFB408
B40C = 0xFFFFB40C
B410 = 0xFFFFB410
B43C = 0xFFFFB43C
B45C = 0xFFFFB45C
B5B8 = 0xFFFFB5B8
AA40 = 0xFFFFAA40
B33C = 0xFFFFB33C; B33D = 0xFFFFB33D; B33E = 0xFFFFB33E

def rb(ram, a):
    return ram.get(a & 0xFFFFFFFF, 0)

def r32(ram, a):
    return struct.unpack('>f', bytes(rb(ram, a + i) for i in range(4)))[0]

def rom_desc(rom, a):
    cx, cy = struct.unpack('>HH', rom[a:a + 4])
    axp, ayp, valp = struct.unpack('>III', rom[a + 4:a + 16])
    scale, off = struct.unpack('>ff', rom[a + 20:a + 28])
    ax = [struct.unpack('>f', rom[axp + 4 * i:axp + 4 * i + 4])[0] for i in range(cx)]
    ay = [struct.unpack('>f', rom[ayp + 4 * i:ayp + 4 * i + 4])[0] for i in range(cy)]
    vals = [struct.unpack('>H', rom[valp + 2 * i:valp + 2 * i + 2])[0] for i in range(cx * cy)]
    return dict(cx=cx, cy=cy, ax=ax, ay=ay, vals=vals, scale=scale, offset=off)

def lookup(desc, x, y):
    ix, tx = T3.search(desc['ax'], desc['cx'], x)
    iy, ty = T3.search(desc['ay'], desc['cy'], y)
    cx = desc['cx']
    row0 = T3.interp_row(ix, tx, desc['vals'][iy * cx:(iy + 1) * cx])
    if ty == 0.0:
        interp = row0
    else:
        row1 = T3.interp_row(ix, tx, desc['vals'][(iy + 1) * cx:(iy + 2) * cx])
        interp = ts(row0 + ty * ts(row1 - row0))
    return ts(desc['scale'] * interp + desc['offset'])

def ref(init, rom):
    if rb(init, B33C) == 1:
        da = DESCS[0]
    elif rb(init, B33D) == 1:
        da = DESCS[1]
    elif rb(init, B33E) == 1:
        da = DESCS[2]
    else:
        da = DESCS[3]
    x = r32(init, B5B8)
    y = r32(init, AA40)
    fr15 = lookup(rom_desc(rom, da), x, y)
    b408 = min(max(fr15, 0.0), 84.0)        # fpu_compare_and_select(fr15, 0, 84) = clamp
    b45c = 0                                # stock ROM: cal byte 0x73F68 == 1
    b43c = b408                             # table[b45c=0] == RAM[B408] (already updated)
    out = dict(init)                        # untouched cells keep their init values
    for i, b in enumerate(struct.pack('>f', ts(b408))):
        out[B408 + i] = b
    for i, b in enumerate(struct.pack('>f', ts(b43c))):
        out[B43C + i] = b
    for i, b in enumerate(struct.pack('>f', ts(b408))):
        out[B40C + i] = b                   # loop's last read: table[0] = new B408
    for a in range(B410, B43C, 4):          # rolling shift: cell a <- old cell a-4
        for i in range(4):
            out[a + i] = init.get(a - 4 + i, 0)
    out[B45C] = b45c
    return out

def main():
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    random.seed(20260731)
    fails = tests = 0
    for _ in range(10000):
        init = {}
        for c in (B5B8, AA40):
            for i, b in enumerate(struct.pack('>f', ts(random.uniform(-200, 400)))):
                init[c + i] = b
        for a in range(B408, B43C + 4, 4):   # seed the 14-cell history table
            for i, b in enumerate(struct.pack('>f', ts(random.uniform(-50, 50)))):
                init[a + i] = b
        init[B33C] = random.choice([0, 1])
        init[B33D] = random.choice([0, 1])
        init[B33E] = random.choice([0, 1])
        tests += 1
        cpu.call(ADDR, ram=dict(init))
        got = dict(cpu.ram)
        exp = ref(init, rom)
        bad = []
        for a in range(B408, B43C + 4, 4):
            g = struct.pack('>f', r32(got, a))
            e = struct.pack('>f', r32(exp, a))
            if g != e:
                bad.append('%s emu=%g ref=%g' % (hex(a), r32(got, a), r32(exp, a)))
        if rb(got, B45C) != rb(exp, B45C):
            bad.append('B45C emu=%d ref=%d' % (rb(got, B45C), rb(exp, B45C)))
        if bad:
            fails += 1
            print("  vis_intake_control FAIL:", bad[:4])
            if fails >= 5:
                break
    print(f"vis_intake_control: {tests} tests, {fails} failures")
    print("VIS_INTAKE_CONTROL:", "PASS" if fails == 0 else "FAIL")
    return 0 if fails == 0 else 1

if __name__ == '__main__':
    sys.exit(main())
