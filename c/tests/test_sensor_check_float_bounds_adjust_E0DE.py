#!/usr/bin/env python3
"""
test_sensor_check_float_bounds_adjust_E0DE.py — differential test of
sensor_check_float_bounds_adjust @0xE0DE (lift: c/sensor_check_float_bounds_adjust.c).

Real ROM bytes of 0xE0DE run in the SH-2E emulator with a seeded random RAM
overlay; the byte at 0xFFFFA400 is compared bit-exactly against a pure-Python
model from the disassembly.

Disasm (`python3 tools/disasm_sh2e.py 0xE0DE 60 60E1D400.bin`):

    r5 = 0xA400 ; r3 = 0x6CF8C ; fr3 = f32[0x6CF8C]      (bound = 10.0)
    r2 = 0xB600 ; fr2 = f32[0xFFFFB600]                  (input f32)
    fcmp/gt fr2,fr3  -> T = (fr3 > fr2) = (10.0 > in)
    bf/s 0xE0F6
    r1 = 0x6CF88 ; r0 = byte[0x6CF88]                    (const = 47)
    bra 0xE106
    mov.b r0,@r5                   10.0 > in : A400 = 47
    r4 = byte[A400] ; r1 = extu.b r4 ; tst r1,r1
    bt/s 0xE106                     current == 0 : no write
    mov #0xFF,r0 ; add r0,r4 ; mov.b r4,@r5              A400 = (cur-1)&0xFF

    -> 10.0>in: A400=47 ; else cur!=0: A400=cur-1 ; cur==0: unchanged

Run from repo root:  python3 c/tests/test_sensor_check_float_bounds_adjust_E0DE.py [N]
"""
import os, random, struct, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2, ts  # noqa: E402

rom = open(os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin'), 'rb').read()
cpu = SH2(rom)

ADDR = 0xE0DE
INP = 0xFFFFB600   # f32 input voltage
OUT = 0xFFFFA400   # u8 output / current

BOUND = struct.unpack('>f', rom[0x6CF8C:0x6CF90])[0]   # 10.0
CONST = rom[0x6CF88]                                   # 47


def putf(ram, a, v):
    b = struct.pack('>f', ts(v))
    for i in range(4):
        ram[a + i] = b[i]


def ref(v, cur):
    v = ts(v)
    if BOUND > v:
        return CONST
    if cur != 0:
        return (cur - 1) & 0xFF
    return cur


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
    rng = random.Random(0xE0DE)
    tests = fails = 0
    special = [float('nan'), float('inf'), float('-inf'), -0.0, 0.0,
               BOUND - 1, BOUND, BOUND + 1, 5.0, 12.0, -5.0]

    def run(v, cur):
        ram = {}
        putf(ram, INP, v)
        ram[OUT] = cur
        cpu.call(ADDR, ram=ram)
        return cpu.ram.get(OUT, cur)

    for v in special:
        for cur in (0, 1, 2, 0xFF, 0x7F, 0x80):
            got = run(v, cur)
            want = ref(v, cur)
            tests += 1
            if got != want:
                fails += 1
                if fails <= 10:
                    print("FAIL v=%r cur=%d got=%r want=%r"
                          % (v, cur, got, want))
    for _ in range(N):
        r = rng.random()
        if r < 0.15:
            v = rng.choice(special)
        else:
            v = rng.uniform(-20, 30)
        cur = rng.getrandbits(8)
        got = run(v, cur)
        want = ref(v, cur)
        tests += 1
        if got != want:
            fails += 1
            if fails <= 10:
                print("FAIL v=%r cur=%d got=%r want=%r" % (v, cur, got, want))
    print("sensor_check_float_bounds_adjust @0xE0DE: %d tests, %d failures"
          % (tests, fails))
    if fails == 0:
        print("OK  sensor_check_float_bounds_adjust @0xE0DE (%d inputs, 0 mismatches)" % tests)
        return 0
    print("FAIL sensor_check_float_bounds_adjust @0xE0DE (%d mismatches)" % fails)
    return 1


if __name__ == '__main__':
    sys.exit(main())