#!/usr/bin/env python3
"""
test_calc_barometric_pressure_trim_13F68.py — differential bit-exact test of
calc_barometric_pressure_trim @0x13F68 (lift: c/baro_sensor_value.c).

Real ROM bytes of 0x13F68 run in the SH-2E emulator with a seeded random RAM
overlay; the result f32 at 0xFFFFA76C and status byte at 0xFFFFA774 are
compared against a pure-Python model from the disassembly.

Disasm (`python3 tools/disasm_sh2e.py 0x13F68 100 60E1D400.bin`):

    byte =[0xFFFFBDD4] ; byte2 = byte[0xFFFFB623] ; byte5AA = byte[0xFFFFB5AA]
    if bdd4==1 or b623==1:  v = f32[0x72D4C] if b5aa==1 else f32[0x72D50]
    else:                   v = f32[0x72D54] if b5aa==1 else f32[0x72D58]
    f32[0xFFFFA76C] = v
    if v > f32[0xFFFFA678]: byte[0xFFFFA774] = 0 else 1   (NaN -> 1)

All four calibrations (0x72D4C..0x72D58) are -0.02f.

Run from repo root:  python3 c/tests/test_calc_barometric_pressure_trim_13F68.py [N]
"""
import os, random, struct, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2, ts  # noqa: E402

rom = open(os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin'), 'rb').read()
cpu = SH2(rom)

ADDR = 0x13F68
B5AA = 0xFFFFB5AA
BDD4 = 0xFFFFBDD4
B623 = 0xFFFFB623
A678 = 0xFFFFA678   # f32 in
A76C = 0xFFFFA76C   # f32 in/out
A774 = 0xFFFFA774   # u8 out

FOOT = {A76C + i for i in range(4)} | {A774}


def putf(ram, a, v):
    b = struct.pack('>f', ts(v))
    for i in range(4):
        ram[a + i] = b[i]


def getf(ram, a):
    return struct.unpack('>f', bytes(ram.get(a + i, 0) for i in range(4)))[0]


V00 = struct.unpack('>f', rom[0x72D4C:0x72D50])[0]   # -0.02
V01 = struct.unpack('>f', rom[0x72D50:0x72D54])[0]
V10 = struct.unpack('>f', rom[0x72D54:0x72D58])[0]
V11 = struct.unpack('>f', rom[0x72D58:0x72D5C])[0]


def ref(b5aa, bdd4, b623, a678):
    if bdd4 == 1 or b623 == 1:
        v = V00 if b5aa == 1 else V01
    else:
        v = V10 if b5aa == 1 else V11
    v = ts(v)
    status = 0 if (v > ts(a678)) else 1
    return v, status


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
    rng = random.Random(0x13F68)
    tests = fails = 0

    def run(b5aa, bdd4, b623, a678):
        ram = {B5AA: b5aa & 0xFF, BDD4: bdd4 & 0xFF, B623: b623 & 0xFF}
        putf(ram, A678, a678)
        cpu.call(ADDR, ram=ram)
        vb = bytes(cpu.ram.get(A76C + i, 0) for i in range(4))
        gotv = struct.unpack('>I', vb)[0]
        gots = cpu.ram.get(A774, 0)
        return gotv, gots

    for _ in range(N):
        b5aa = rng.getrandbits(8)
        bdd4 = rng.getrandbits(8)
        b623 = rng.getrandbits(8)
        r = rng.random()
        if r < 0.2:
            a678 = rng.choice((-2.0, -0.02, 0.0, 1.0, float('nan'),
                               float('-inf'), float('inf')))
        else:
            a678 = rng.uniform(-5, 5)
        gotv, gots = run(b5aa, bdd4, b623, a678)
        v, st = ref(b5aa, bdd4, b623, a678)
        wantv = struct.unpack('>I', struct.pack('>f', ts(v)))[0]
        tests += 1
        if gotv != wantv or gots != st:
            fails += 1
            if fails <= 10:
                print("FAIL b5aa=%d bdd4=%d b623=%d a678=%r got=(%08X,%d) want=(%08X,%d)"
                      % (b5aa, bdd4, b623, a678, gotv, gots, wantv, st))
    print("calc_barometric_pressure_trim @0x13F68: %d tests, %d failures"
          % (tests, fails))
    if fails == 0:
        print("OK  calc_barometric_pressure_trim @0x13F68 (%d inputs, 0 mismatches)" % tests)
        return 0
    print("FAIL calc_barometric_pressure_trim @0x13F68 (%d mismatches)" % fails)
    return 1


if __name__ == '__main__':
    sys.exit(main())