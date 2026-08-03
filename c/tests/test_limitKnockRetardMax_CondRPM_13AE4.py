#!/usr/bin/env python3
"""test_limitKnockRetardMax_CondRPM_13AE4.py

Differential test for ROM 0x13AE4 (60E0FC00.bin) - lift function
limitKnockRetardMax_ConditionalRPM (c/limitKnockRetardMax_CondRPM.c).
NOTE: 0x13AE4 in 60E1D400.bin is DATA; the lift's home ROM is 60E0FC00.bin
where 0x13AE4 is this function.

Verified disassembly (60E0FC00.bin):
   0x13AE4  prologue (saves incoming fr4 @r15)
   0x13AEC  fr4  = f32@0xFFFFB594        (rpm ref, overlaid RAM)
   0x13AF2  r6   = u8 sensor @0xFFFFB580
   0x13AF8  if sensor==1:  sec=u8@0xFFFFBC75, thresh=u8@ROM 0x78544
              if sec>=thresh -> table=0x693CC (A) else table=0x693B8 (B)
             else if sensor==0:
              ref=u8@0xFFFFBB25
              if ref>thresh or ref==0 -> table=0x693B8 (B) else 0x693CC (A)
             else (sensor not 0/1) -> table=0x693B8 (B)
   0x13B32  fr5 = TwoDLookup(0x2068, table=r4, fr4=ref, fr5=incoming fr5)
   0x13B3A  fr6 = f32@ROM 0x78584 (gain)
   0x13B3E  fr0 = clamp(0x2404, fr4=incoming fr4, fr5=twod, fr6=gain)
   return fr0

Callees (0x2068 TwoDLookup, 0x2404 clamp) are replayed on a second emulator
instance from the SAME ROM, so their exact bytes run as the "model".

Run: python3 c/tests/test_limitKnockRetardMax_CondRPM_13AE4.py [N]
"""
import os, random, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2, ts, f2bits

ROM = os.path.join(ROOT, 'roms', 'stock', '60E0FC00.bin')
ADDR = 0x13AE4

TABLE_A = 0x693CC
TABLE_B = 0x693B8
GAIN_ADDR = 0x78584
THRESH_ADDR = 0x78544
TWOD = 0x2068
CLAMP = 0x2404

R_REF = 0xFFFFB594   # f32 rpm ref
R_SENSOR = 0xFFFFB580  # u8
R_REFVAL = 0xFFFFBB25  # u8
R_SEC = 0xFFFFBC75   # u8


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
    rom = open(ROM, 'rb').read()
    gain = struct.unpack('>f', rom[GAIN_ADDR:GAIN_ADDR + 4])[0]
    thresh = rom[THRESH_ADDR]
    cpu = SH2(rom)
    mcp = SH2(rom)  # model: replay callees from same ROM
    rng = random.Random(0x13AE4)
    fails = 0

    for it in range(N):
        # incoming float args (fr4, fr5) to the function entry
        a = rng.choice([rng.uniform(-1e3, 1e3), rng.uniform(0.02, 500.0)])
        b = rng.choice([rng.uniform(-1e3, 1e3), rng.uniform(0.0, 9000.0)])

        ram = {}
        f32 = struct.pack('>f', a)
        for i in range(4):
            ram[R_REF + i] = f32[i]
        ram[R_SENSOR] = rng.randrange(0, 256)
        ram[R_REFVAL] = rng.randrange(0, 256)
        ram[R_SEC] = rng.randrange(0, 256)

        # ---- model: table selection (ROM disasm)
        sensor = ram[R_SENSOR]
        ref = ram[R_REFVAL]
        sec = ram[R_SEC]
        if sensor == 1:
            table_ = TABLE_A if sec >= thresh else TABLE_B
        elif sensor == 0:
            table_ = TABLE_B if (ref > thresh or ref == 0) else TABLE_A
        else:
            table_ = TABLE_B

        # ---- model: replay callees on mcp with the same register/ROM arcs
        fr4_ref = struct.unpack('>f', bytes(ram[R_REF + i] for i in range(4)))[0]
        mcp.call(TWOD, r4=table_, fr={4: fr4_ref, 5: b}, ram={})
        twod = mcp.fr[0]                      # ROM: fmov fr0,fr5
        mcp.call(CLAMP, fr={4: a, 5: twod, 6: gain}, ram={})
        want = mcp.fr[0]

        # ---- real CPU run
        cpu.call(ADDR, fr={4: a, 5: b}, ram=ram)
        got = cpu.fr[0]

        if f2bits(got) != f2bits(want):
            print('MISMATCH iter=%d a=%g b=%g sensor=%d ref=%d sec=%d table=%x want=%g got=%g'
                  % (it, a, b, sensor, ref, sec, table_, want, got))
            fails += 1
            if fails >= 5:
                break

    if fails:
        print('%d FAILURE(S) limitKnockRetardMax_CondRPM_13AE4' % fails)
        sys.exit(1)
    print('OK  0x13AE4 limitKnockRetardMax_CondRPM_13AE4  (%d inputs)' % N)
    sys.exit(0)


if __name__ == '__main__':
    main()
