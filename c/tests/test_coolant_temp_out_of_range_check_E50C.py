#!/usr/bin/env python3
"""
test_coolant_temp_out_of_range_check_E50C.py — differential test of
coolant_temp_out_of_range_check @0xE50C (lift: c/coolant_temperature_sensor.c).

Real ROM bytes of 0xE50C run in the SH-2E emulator with a seeded random RAM
overlay; the result byte of 0xFFFFA428 is compared bit-exactly against a
pure-Python model from the disassembly.

Disasm (`python3 tools/disasm_sh2e.py 0xE50C 60 60E1D400.bin`):

    r3 = 0xB5B8 ; fr4 = f32[0xFFFFB5B8]     input voltage
    r4 = 0xA428 ; r2 = 0x6CF90 ; fr3 = f32[0x6CF90]  (upper = 250.0)
    fcmp/gt fr4,fr3  -> T = (fr3 > fr4) = (fr4 < upper)
    bf/s 0xE522      -> taken when fr4 >= upper (or NaN)
    mov #0,r0 ; bra 0xE530
    mov.b r0,@r4                            fr4 < upper : A428 = 0
    r1 = 0x6CF94 ; fr2 = f32[0x6CF94]       (lower = 500.0)
    fcmp/gt fr4,fr2  -> T = (fr4 < lower)
    bt/s 0xE530       -> fr4 < lower : A428 unchanged
    mov #1,r0 ; mov.b r0,@r4                else A428 = 1

    -> fr4<upper:0 ; upper<=fr4<lower: unchanged ; fr4>=lower:1 ; NaN:1

Run from repo root:  python3 c/tests/test_coolant_temp_out_of_range_check_E50C.py [N]
"""
import math, os, random, struct, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2, ts  # noqa: E402

rom = open(os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin'), 'rb').read()
cpu = SH2(rom)

ADDR = 0xE50C
INP = 0xFFFFB5B8   # f32 input voltage
OUT = 0xFFFFA428   # u8 result

UPPER = struct.unpack('>f', rom[0x6CF90:0x6CF94])[0]   # 250.0
LOWER = struct.unpack('>f', rom[0x6CF94:0x6CF98])[0]   # 500.0


def putf(ram, a, v):
    b = struct.pack('>f', ts(v))
    for i in range(4):
        ram[a + i] = b[i]


def ref(v, prev):
    """Returns the new A428 value (prev used for the 'unchanged' case)."""
    v = ts(v)
    if v < UPPER:
        return 0
    if v < LOWER:
        return prev
    return 1


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
    rng = random.Random(0xE50C)
    tests = fails = 0
    special = [float('nan'), float('inf'), float('-inf'), -0.0, 0.0,
               UPPER - 1, UPPER, UPPER + 1, LOWER - 1, LOWER, LOWER + 1,
               -1000.0, 1000.0]

    def run(v, prev):
        ram = {}
        putf(ram, INP, v)
        ram[OUT] = prev
        cpu.call(ADDR, ram=ram)
        return cpu.ram.get(OUT, prev)

    for v in special:
        for prev in (0, 1, 0xFF):
            got = run(v, prev)
            want = ref(v, prev)
            tests += 1
            if got != want:
                fails += 1
                if fails <= 10:
                    print("FAIL v=%r prev=%d got=%r want=%r"
                          % (v, prev, got, want))
    for _ in range(N):
        r = rng.random()
        if r < 0.15:
            v = rng.choice(special)
        elif r < 0.30:
            v = rng.uniform(-200, 700)
        else:
            v = rng.uniform(0, 600)
        prev = rng.getrandbits(8)
        got = run(v, prev)
        want = ref(v, prev)
        tests += 1
        if got != want:
            fails += 1
            if fails <= 10:
                print("FAIL v=%r prev=%d got=%r want=%r" % (v, prev, got, want))
    print("coolant_temp_out_of_range_check @0xE50C: %d tests, %d failures"
          % (tests, fails))
    if fails == 0:
        print("OK  coolant_temp_out_of_range_check @0xE50C (%d inputs, 0 mismatches)" % tests)
        return 0
    print("FAIL coolant_temp_out_of_range_check @0xE50C (%d mismatches)" % fails)
    return 1


if __name__ == '__main__':
    sys.exit(main())