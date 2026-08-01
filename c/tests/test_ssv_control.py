#!/usr/bin/env python3
"""
Test ssvControl (0x225C8) via SH-2E emulator.

Decoded behavior (see docs/functions/ssvControl.md):

  temp = RAM32[0xFFFFAA10] (f32)
  mode = RAM8[0xFFFFAAE0]

  1. Hysteresis (cal ROM[0x72F74]=200.0, ROM[0x226D4]=-3.0):
       temp >= 200  -> RAM8[0xFFFFB324] = 1
       temp <  197  -> RAM8[0xFFFFB324] = 0
       197 <= temp < 200 -> hold previous RAM8[0xFFFFB324]

  2. Counter RAM16[0xFFFFB322]:
       if mode == 0 AND RAM8[0xFFFFB325] == 1:  RAM16[B322] = ROM16[0x72F72] (188)
       elif RAM16[B322] > 0:                    RAM16[B322] -= 1
       else: unchanged

  3. enable = 1 iff  ROM8[0x72F70]==1 (cal, =0)
                   OR RAM8[0xFFFFBF39]==1
                   OR (mode==0 AND B322>0 AND RAM8[0xFFFFB324]==0)
       else 0

  4. out = 0x5D3E8(enable, 0)   ; alternating_sensor_sm_08 (verified)
       RAM8[0xFFFFB320] = out

  5. RAM16[0xFFFFF754] bit 0x80 = (out == 1) ? 1 : 0   (via 0x4BBC)

  6. RAM8[0xFFFFB325] = mode

The 0x5D3E8 model is imported from test_alt_sensor_sm (independently
verified 20000 inputs vs the emulator).
"""
import os, sys, struct, random
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'tools'))
from sh2emu import SH2
from test_alt_sensor_sm import ref as sm_ref, PTR_CELL

ROM = os.path.join(os.path.dirname(__file__), '..', '..', 'roms', 'stock', '60E1D400.bin')
ADDR = 0x225C8

B324 = 0xFFFFB324   # SSV command (u8)
B322 = 0xFFFFB322   # counter (u16)
B320 = 0xFFFFB320   # sm output (u8)
B325 = 0xFFFFB325   # previous mode (u8)
F754 = 0xFFFFF754   # bit 0x80 <- (out == 1)
AA10 = 0xFFFFAA10   # temp (f32)
AAE0 = 0xFFFFAAE0   # mode (u8)
BF39 = 0xFFFFBF39   # status (u8)
D355 = 0xFFFFD355; D350 = 0xFFFFD350; D352 = 0xFFFFD352
D354 = 0xFFFFD354; D3A8 = 0xFFFFD3A8; D387 = 0xFFFFD387

def rb(ram, a):
    return ram.get(a & 0xFFFFFFFF, 0)

def rd16(ram, a):
    return (rb(ram, a) << 8) | rb(ram, a + 1)

def r32(ram, a):
    return struct.unpack('>f', bytes(rb(ram, a + i) for i in range(4)))[0]

def ref(ram_in, cpu2):
    ram = dict(ram_in)
    temp = r32(ram, AA10)
    mode = rb(ram, AAE0)
    # 1. hysteresis
    if temp >= 200.0:
        ram[B324] = 1
    elif temp < 197.0:
        ram[B324] = 0
    # 2. counter
    if mode == 0 and rb(ram, B325) == 1:
        b322 = 188
    elif rd16(ram, B322) > 0:
        b322 = (rd16(ram, B322) - 1) & 0xFFFF
    else:
        b322 = rd16(ram, B322)
    for i, b in enumerate(struct.pack('>H', b322)):
        ram[B322 + i] = b
    # 3. enable
    if rb(ram, BF39) == 1 or (mode == 0 and rd16(ram, B322) > 0 and rb(ram, B324) == 0):
        enable = 1
    else:
        enable = 0
    # 4. state machine
    out, sram = sm_ref(ram, enable)
    ram.update(sram)
    ram[B320] = out
    # 5. F754 bit 0x80
    f754 = rd16(ram, F754)
    if out == 1:
        f754 |= 0x80
    else:
        f754 &= ~0x80
    for i, b in enumerate(struct.pack('>H', f754 & 0xFFFF)):
        ram[F754 + i] = b
    # 6.
    ram[B325] = mode
    return ram

def main():
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    random.seed(20260731)
    fails = tests = 0
    for _ in range(12000):
        init = {}
        temp = random.uniform(150, 250)
        for i, b in enumerate(struct.pack('>f', temp)):
            init[AA10 + i] = b
        init[AAE0] = random.choice([0, 0, 1, 2])
        init[B325] = random.randrange(0, 4)
        init[B324] = random.randrange(0, 4)
        for i, b in enumerate(struct.pack('>H', random.randrange(0, 300))):
            init[B322 + i] = b
        init[BF39] = random.choice([0, 1])
        # state machine inputs
        init[0x6021C] = random.choice([0, 1, 0xFF, 0x0F])
        for i, b in enumerate(struct.pack('>I', PTR_CELL)):
            init[0x60220 + i] = b
        init[D355] = random.randrange(0, 256)
        for i, b in enumerate(struct.pack('>H', random.randrange(0, 0x10000))):
            init[D350 + i] = b
        for i, b in enumerate(struct.pack('>H', random.randrange(0, 0x10000))):
            init[D352 + i] = b
        init[D354] = random.randrange(0, 256)
        init[D3A8] = random.randrange(0, 256)
        init[D387] = random.randrange(0, 256)
        init[PTR_CELL] = random.choice([0, 1, 5, 7, random.randrange(0, 256)])
        tests += 1
        cpu.call(ADDR, ram=dict(init))
        got = dict(cpu.ram)
        exp = ref(init, cpu)
        bad = []
        for cell in (B324, B320, B325, D355, D387, PTR_CELL):
            if rb(got, cell) != rb(exp, cell):
                bad.append('%s emu=%d ref=%d' % (hex(cell), rb(got, cell), rb(exp, cell)))
        for cell in (B322, F754):
            if rd16(got, cell) != rd16(exp, cell):
                bad.append('%s emu=%04X ref=%04X' % (hex(cell), rd16(got, cell), rd16(exp, cell)))
        if bad:
            fails += 1
            print("  ssvControl FAIL:", bad[:4])
            if fails >= 5:
                break
    print(f"ssvControl: {tests} tests, {fails} failures")
    print("SSV_CONTROL:", "PASS" if fails == 0 else "FAIL")
    return 0 if fails == 0 else 1

if __name__ == '__main__':
    sys.exit(main())
