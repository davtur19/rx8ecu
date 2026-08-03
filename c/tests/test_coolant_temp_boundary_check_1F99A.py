#!/usr/bin/env python3
"""
test_coolant_temp_boundary_check_1F99A.py — differential test of
coolant_temp_boundary_check @0x1F99A (lift: c/coolant_temperature_sensor.c).

Real ROM bytes of 0x1F99A run in the SH-2E emulator with a seeded random RAM
overlay; the result byte of 0xFFFFB14E is compared against a pure-Python
model from the disassembly.

Disasm (`python3 tools/disasm_sh2e.py 0x1F99A 70 60E1D400.bin`):

    fr4 = f32[0xFFFFAA1C]                     temperature input
    fr5 = f32[0x71A48] = 80.0                 boundary (ROM)
    fcmp/gt fr4,fr5 -> T = (fr5 > fr4) = (fr4 < 80.0)
    bf/s 0x1F9BA                              T=0 (fr4>=80) -> 0x1F9BA
    r4 = u16[0xFFFFB364]                      raw ADC
    r0 = extu.w r4 ; t1 = u16[0x719C4]        (2750)
    cmp/ge t1,r0  -> T = (adc >= t1)
    bt/s 0x1F9CE        -> OUT=1
    ; 0x1F9BA:
    fcmp/gt fr4,fr5 (same compare)
    bt/s 0x1FA1C        -> fr4<80 -> OUT=0
    t2 = u16[0x719C6] ; cmp/ge t2,adc ; bf/s 0x1FA1C -> OUT=0
    ; 0x1F9CE: OUT=1 ; 0x1FA1C: OUT=0

    Combined:  fr4<80  -> OUT = (adc>=t1) ? 1:0
               fr4>=80 -> OUT = (adc>=t2) ? 1:0
    NaN fr4 behaves as fr4>=80 (fcmp false).

Run from repo root:  python3 c/tests/test_coolant_temp_boundary_check_1F99A.py [N]
"""
import os, random, struct, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2, ts  # noqa: E402

rom = open(os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin'), 'rb').read()
cpu = SH2(rom)

ADDR = 0x1F99A
TIN = 0xFFFFAA1C   # f32 temperature
ADC = 0xFFFFB364   # u16 raw adc
OUT = 0xFFFFB14E   # u8 result

BOUND = struct.unpack('>f', rom[0x71A48:0x71A4C])[0]   # 80.0
T1 = int.from_bytes(rom[0x719C4:0x719C6], 'big')       # 2750
T2 = int.from_bytes(rom[0x719C6:0x719C8], 'big')       # 2750


def putf(ram, a, v):
    b = struct.pack('>f', ts(v))
    for i in range(4):
        ram[a + i] = b[i]


def ref(v, adc):
    v = ts(v)
    if v < BOUND:
        return 1 if adc >= T1 else 0
    return 1 if adc >= T2 else 0


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
    rng = random.Random(0x1F99A)
    tests = fails = 0
    special = [float('nan'), float('inf'), float('-inf'), -0.0, 0.0,
               BOUND - 1, BOUND, BOUND + 1, 20.0, 100.0, -40.0]
    adc_edge = {0, 1, T1 - 1, T1, T1 + 1, T2 - 1, T2, T2 + 1, 0xFFFF}

    def run(v, adc):
        ram = {}
        putf(ram, TIN, v)
        ram[ADC] = (adc >> 8) & 0xFF
        ram[ADC + 1] = adc & 0xFF
        cpu.call(ADDR, ram=ram)
        return cpu.ram.get(OUT, 0xFF)

    for v in special:
        for adc in adc_edge:
            got = run(v, adc)
            want = ref(v, adc)
            tests += 1
            if got != want:
                fails += 1
                if fails <= 10:
                    print("FAIL v=%r adc=%d got=%r want=%r" % (v, adc, got, want))
    for _ in range(N):
        r = rng.random()
        if r < 0.15:
            v = rng.choice(special)
        else:
            v = rng.uniform(-50, 150)
        adc = rng.getrandbits(16)
        got = run(v, adc)
        want = ref(v, adc)
        tests += 1
        if got != want:
            fails += 1
            if fails <= 10:
                print("FAIL v=%r adc=%d got=%r want=%r" % (v, adc, got, want))
    print("coolant_temp_boundary_check @0x1F99A: %d tests, %d failures"
          % (tests, fails))
    if fails == 0:
        print("OK  coolant_temp_boundary_check @0x1F99A (%d inputs, 0 mismatches)" % tests)
        return 0
    print("FAIL coolant_temp_boundary_check @0x1F99A (%d mismatches)" % fails)
    return 1


if __name__ == '__main__':
    sys.exit(main())