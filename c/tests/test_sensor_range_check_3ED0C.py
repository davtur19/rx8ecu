#!/usr/bin/env python3
"""test_sensor_range_check_3ED0C.py

Differential test for ROM 0x3ED0C (60E1D400.bin) — lift function
sensor_range_check_3ED0C (declared in c/calc_idle_speed_target.c and
verified through its replay in test_calc_idle_speed_target_0x12F5E.py; this
test exercises it standalone).

Verified disassembly:
   0x3ED0C  fr3 = 0 ; fcmp/eq fr3,fr5        (b == 0?)
   0x3ED16  if not: fr6 = fr4/fr5 ; return fr6
            else: fcmp/eq fr3,fr4           (a == 0?)
                 if a==0: fr6 = 0 ; return
                 if a > 0: fr6 = f32@0x3EF78  (+FLT_MAX ~3.40282e38)
                 else    : fr6 = f32@0x3EF7C  (-FLT_MAX)
   return fr0 = fr6

Run: python3 c/tests/test_sensor_range_check_3ED0C.py [N]
"""
import os, random, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2, ts, f2bits

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ADDR = 0x3ED0C

C_POS = 0x3EF78   # +max
C_NEG = 0x3EF7C   # -max


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
    rom = open(ROM, 'rb').read()
    pos_max = struct.unpack('>f', rom[C_POS:C_POS + 4])[0]
    neg_max = struct.unpack('>f', rom[C_NEG:C_NEG + 4])[0]
    cpu = SH2(rom)
    rng = random.Random(0x3ED0C)
    fails = 0

    for it in range(N):
        mode = rng.randrange(4)
        if mode == 0:                       # b == 0, a == 0
            a, b = 0.0, 0.0
            want = 0.0
        elif mode == 1:                     # b == 0, a > 0
            a = rng.uniform(1e-3, 1e3)
            want = pos_max
            b = 0.0
        elif mode == 2:                     # b == 0, a < 0
            a = rng.uniform(-1e3, -1e-3)
            want = neg_max
            b = 0.0
        else:                               # b != 0 -> a/b
            a = rng.uniform(-1e4, 1e4)
            b = rng.choice([rng.uniform(-1e3, 1e3), rng.uniform(-1, -1e-3), rng.uniform(1e-3, 1)])
            want = ts(ts(a) / ts(b))        # fdiv on single-precision operands
        cpu.call(ADDR, fr={4: a, 5: b}, ram={})
        got = cpu.fr[0]
        if f2bits(got) != f2bits(want):
            print('MISMATCH iter=%d mode=%d a=%g b=%g want=%g got=%g' % (it, mode, a, b, want, got))
            fails += 1
            if fails >= 3:
                break

    if fails:
        print('%d FAILURE(S) sensor_range_check_3ED0C' % fails)
        sys.exit(1)
    print('OK  0x3ED0C sensor_range_check_3ED0C  (%d inputs)' % N)
    sys.exit(0)


if __name__ == '__main__':
    main()