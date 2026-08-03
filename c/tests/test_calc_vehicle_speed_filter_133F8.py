#!/usr/bin/env python3
"""
test_calc_vehicle_speed_filter_133F8.py — differential test of
calc_vehicle_speed_filter @0x133F8 (lift: c/vehicle_speed_sensor.c) and the
mode-selection tail it shares with calc_throttle_position_filter @0x1345C.

Real ROM bytes run in the SH-2E emulator; helpers @0x23DC (|a-b|), @0x23F4
(min) and @0x23E4 (max) execute natively.  Result floats at
0xFFFFA6CC/A6D0/A6D4/A6D8 and 0xFFFFA6AC/A6B0 are compared bit-exactly
against a pure-Python model from the disassembly.

Model (disasm 0x133F8..0x135BE):

  mode:  A6B9==1 -> (f32[6F73C..]) ; A6B7==1 -> (f32[6F71C..])
         A6B8==1 -> (f32[6F72C..]) ; else    -> (f32[6F74C..])
  A6CC=c0 ; A6D0=c1 ; A6D4=c2 ; A6D8=c3
  if byte[A428]==0: A6AC=0 ; A6B0=0
  else:
    f1 = f32[0x6F704] (=0.1) ; f2 = f32[0x6F708]
    if |A6AC-A6BC| > f1:
        if (A6BC-A6AC)  > f1: A6AC = min(A6AC+c0, A6BC)
        elif (A6AC-A6BC) > f1: A6AC = max(A6AC-c1, A6BC)
    if |A6B0-A6C0| > f2:
        if (A6AC0-A6B00) > f2: A6B0 = min(A6B0+c2, A6C0)
        elif (A6B0-A6C0) > f2: A6B0 = max(A6B0-c3, A6C0)

  (A6AC0/A6B00 = the original pre-filter values, read into fp regs before
   branch 1 runs.)

Run from repo root:  python3 c/tests/test_calc_vehicle_speed_filter_133F8.py [N]
"""
import math, os, random, struct, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2, ts  # noqa: E402

rom = open(os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin'), 'rb').read()
cpu = SH2(rom)

ADDR = 0x133F8
A6AC, A6B0 = 0xFFFFA6AC, 0xFFFFA6B0
A6BC, A6C0 = 0xFFFFA6BC, 0xFFFFA6C0
A6CC, A6D0 = 0xFFFFA6CC, 0xFFFFA6D0
A6D4, A6D8 = 0xFFFFA6D4, 0xFFFFA6D8
A6B9, A6B7, A6B8 = 0xFFFFA6B9, 0xFFFFA6B7, 0xFFFFA6B8
A428 = 0xFFFFA428

F1 = struct.unpack('>f', rom[0x6F704:0x6F708])[0]
F2 = struct.unpack('>f', rom[0x6F708:0x6F70C])[0]
MAPS = {
    'b9': [struct.unpack('>f', rom[0x6F73C + 4 * i:0x6F73C + 4 * i + 4])[0]
           for i in range(4)],
    'b7': [struct.unpack('>f', rom[0x6F71C + 4 * i:0x6F71C + 4 * i + 4])[0]
           for i in range(4)],
    'b8': [struct.unpack('>f', rom[0x6F72C + 4 * i:0x6F72C + 4 * i + 4])[0]
           for i in range(4)],
    'def': [struct.unpack('>f', rom[0x6F74C + 4 * i:0x6F74C + 4 * i + 4])[0]
            for i in range(4)],
}

FMIN = lambda a, b: a if b > a else b   # helper 0x23F4: min(fr4,fr5)
FMAX = lambda a, b: a if a > b else b   # helper 0x23E4: max(fr4,fr5)


def putf(ram, a, v):
    b = struct.pack('>f', ts(v))
    for i in range(4):
        ram[a + i] = b[i]


def getf(ram, a):
    return struct.unpack('>f', bytes(ram.get(a + i, 0) for i in range(4)))[0]


def ref(t):
    b9, b7, b8 = t['b9'] & 0xFF, t['b7'] & 0xFF, t['b8'] & 0xFF
    if b9 == 1:
        c = MAPS['b9']
    elif b7 == 1:
        c = MAPS['b7']
    elif b8 == 1:
        c = MAPS['b8']
    else:
        c = MAPS['def']
    c0, c1, c2, c3 = [ts(x) for x in c]
    # emulator reads f32 from RAM -> round all inputs to f32 first
    ac, b0, bc, c0_ = (ts(t['a6ac']), ts(t['a6b0']),
                       ts(t['a6bc']), ts(t['a6c0']))
    if t['a428'] == 0:
        nac, nb0 = ts(0.0), ts(0.0)
    else:
        nac, nb0 = ac, b0
        abs1 = abs(ts(ac - bc))
        if abs1 > F1:
            if ts(bc - ac) > F1:
                nac = FMIN(ts(ac + c0), bc)
            elif ts(ac - bc) > F1:
                nac = FMAX(ts(ac - c1), bc)
        abs2 = abs(ts(b0 - c0_))
        if abs2 > F2:
            # fr13 was overwritten with A6C0 before the fsub -> A6C0-A6B0
            if ts(c0_ - b0) > F2:
                nb0 = FMIN(ts(b0 + c2), c0_)
            elif ts(b0 - c0_) > F2:
                nb0 = FMAX(ts(b0 - c3), c0_)
    return (nac, nb0, c0, c1, c2, c3)


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
    rng = random.Random(0x133F8)
    tests = fails = 0
    fspec = [float('nan'), float('inf'), float('-inf'), -0.0, 0.0,
             0.05, 0.1, 0.15, 0.5, 1.0, 2.0, 10.0]

    def run(t):
        ram = {A6B9: t['b9'] & 0xFF, A6B7: t['b7'] & 0xFF,
               A6B8: t['b8'] & 0xFF, A428: t['a428'] & 0xFF}
        for a, v in ((A6AC, t['a6ac']), (A6B0, t['a6b0']),
                     (A6BC, t['a6bc']), (A6C0, t['a6c0'])):
            putf(ram, a, v)
        cpu.call(ADDR, ram=ram)
        out = []
        for a in (A6AC, A6B0, A6CC, A6D0, A6D4, A6D8):
            out.append(struct.unpack('>I', bytes(
                cpu.ram.get(a + i, 0) for i in range(4)))[0])
        return tuple(out)

    for _ in range(N):
        def rf():
            r = rng.random()
            if r < 0.35:
                return rng.choice(fspec)
            return rng.uniform(-15, 15)
        t = dict(
            b9=rng.choice((0, 1)), b7=rng.choice((0, 1)),
            b8=rng.choice((0, 1)),
            a428=rng.getrandbits(8),
            a6ac=rf(), a6b0=rf(), a6bc=rf(), a6c0=rf())
        # biased combos for mode priority + gate
        if rng.random() < 0.5:
            t['a428'] = rng.choice((0, 0, 0, 1, 2, 0xFF))
        if rng.random() < 0.4:
            t['b9'], t['b7'], t['b8'] = 0, 0, 0
            t[rng.choice('b9b7b8')] = 1
        got = run(t)
        want = tuple(struct.unpack('>I', struct.pack('>f', ts(x)))[0]
                     for x in ref(t))
        tests += 1
        if got != want:
            fails += 1
            if fails <= 10:
                print("FAIL t=%s\n  got =%s\n  want=%s" % (t, got, want))
    print("calc_vehicle_speed_filter @0x133F8: %d tests, %d failures"
          % (tests, fails))
    if fails == 0:
        print("OK  calc_vehicle_speed_filter @0x133F8 (%d inputs, 0 mismatches)" % tests)
        return 0
    print("FAIL calc_vehicle_speed_filter @0x133F8 (%d mismatches)" % fails)
    return 1


if __name__ == '__main__':
    sys.exit(main())