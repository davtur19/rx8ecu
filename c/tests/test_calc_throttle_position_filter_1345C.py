#!/usr/bin/env python3
"""
test_calc_throttle_position_filter_1345C.py — differential test of
calc_throttle_position_filter @0x1345C (lift: c/throttle_position_sensor.c).

0x1345C is a MID-FUNCTION entry: it falls straight through from the frame
setup of 0x133F8 (prologue 0x133F8..0x1340E pushes r14/r13/r12/r11,
fr15..fr12 and pr, reserving a 0xF4 scratch area; the |a-b| helper 0x23DC is
run twice before 0x1345C).  The emulator supports register/FP/stack presets,
so we replicate that exact pre-entry state and call 0x1345C directly.

The 0x1345C entry always takes the b9 mode (it is the fall-through of the
b9 branch, so the mode bytes are not re-read) -> constants = 5.0 each.
The shared filter tail (0x1345C..0x135BE, helpers 0x23F4 min / 0x23E4 max;
gate byte @0xFFFFA428) then runs natively.

Frame (sp=0xFFFFDFD0): [sp]=|A6B0-A6C0|, [sp+4]=A6B0-A6C0, [sp+8]=|A6AC-A6BC|,
saved pr @0xFFFFDFDC = SENT (0xEEEE0000) so the epilogue rts lands on SENT.

Model:
  mode b9 -> c = (5,5,5,5)
  A6CC=c0; A6D0=c1; A6D4=c2; A6D8=c3
  if byte[A428]==0: A6AC=0 ; A6B0=0
  else:
    f1 = f32[0x6F704] ; f2 = f32[0x6F708]
    if |A6AC-A6BC| > f1:
        if (A6BC-A6AC)  > f1: A6AC = min(A6AC+c0, A6BC)
        elif (A6AC-A6BC) > f1: A6AC = max(A6AC-c1, A6BC)
    if |A6B0-A6C0| > f2:
        if (A6C0-A6B0)  > f2: A6B0 = min(A6B0+c2, A6C0)
        elif (A6B0-A6C0) > f2: A6B0 = max(A6B0-c3, A6C0)

Run from repo root: python3 c/tests/test_calc_throttle_position_filter_1345C.py [N]
"""
import os, random, struct, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2, ts  # noqa: E402

rom = open(os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin'), 'rb').read()
cpu = SH2(rom)

ADDR = 0x1345C
SENT = 0xEEEE0000
SP = 0xFFFFDFD0
A6AC, A6B0 = 0xFFFFA6AC, 0xFFFFA6B0
A6BC, A6C0 = 0xFFFFA6BC, 0xFFFFA6C0
A6CC, A6D0 = 0xFFFFA6CC, 0xFFFFA6D0
A6D4, A6D8 = 0xFFFFA6D4, 0xFFFFA6D8
A428 = 0xFFFFA428

F1 = struct.unpack('>f', rom[0x6F704:0x6F708])[0]
F2 = struct.unpack('>f', rom[0x6F708:0x6F70C])[0]
C = [struct.unpack('>f', rom[0x6F73C + 4 * i:0x6F73C + 4 * i + 4])[0]
     for i in range(4)]                      # b9 mode: (5.0,5.0,5.0,5.0)

FMIN = lambda a, b: a if b > a else b
FMAX = lambda a, b: a if a > b else b


def putf(ram, a, v):
    b = struct.pack('>f', ts(v))
    for i in range(4):
        ram[a + i] = b[i]


def ref(t):
    c0, c1, c2, c3 = [ts(x) for x in C]
    ac, b0, bc, c0_ = (ts(t['a6ac']), ts(t['a6b0']),
                       ts(t['a6bc']), ts(t['a6c0']))
    if t['a428'] == 0:
        nac, nb0 = ts(0.0), ts(0.0)
    else:
        nac, nb0 = ac, b0
        if abs(ts(ac - bc)) > F1:
            if ts(bc - ac) > F1:
                nac = FMIN(ts(ac + c0), bc)
            elif ts(ac - bc) > F1:
                nac = FMAX(ts(ac - c1), bc)
        if abs(ts(b0 - c0_)) > F2:
            if ts(c0_ - b0) > F2:
                nb0 = FMIN(ts(b0 + c2), c0_)
            elif ts(b0 - c0_) > F2:
                nb0 = FMAX(ts(b0 - c3), c0_)
    return (nac, nb0, c0, c1, c2, c3)


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
    rng = random.Random(0x1345C)
    tests = fails = 0
    fspec = [float('nan'), float('inf'), float('-inf'), -0.0, 0.0,
             0.05, 0.1, 0.15, 0.5, 1.0, 2.0, 5.0, 10.0]

    def run(t):
        ac, b0, bc, c0_ = (ts(t['a6ac']), ts(t['a6b0']),
                           ts(t['a6bc']), ts(t['a6c0']))
        ram = {A428: t['a428'] & 0xFF}
        for a, v in ((A6AC, ac), (A6B0, b0), (A6BC, bc), (A6C0, c0_)):
            putf(ram, a, v)
        # frame
        putf(ram, SP, abs(ts(b0 - c0_)))      # [sp]   abs2
        putf(ram, SP + 4, ts(b0 - c0_))       # [sp+4] b0-c0_
        putf(ram, SP + 8, abs(ts(ac - bc)))   # [sp+8] abs1
        for i in range(4):
            ram[SP + 12 + i] = (SENT >> (8 * (3 - i))) & 0xFF  # saved pr
        fr = {2: ts(C[0]), 6: ts(ac - bc), 7: ts(bc - ac),
              13: ts(c0_ - b0), 14: c0_, 15: bc}
        regs = {4: 0xFFFFA6D0, 5: 0xFFFFA6CC, 11: 0xFFFFA6B0,
                12: 0xFFFFA6D4, 13: 0xFFFFA6D8, 14: 0xFFFFA6AC,
                15: SP}
        cpu.call(ADDR, ram=ram, fr=fr, regs=regs)
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
        t = dict(a428=rng.choice((0, 0, 0, 1, 2, 0xFF, 0x7F))
                 if rng.random() < 0.65 else rng.getrandbits(8),
                 a6ac=rf(), a6b0=rf(), a6bc=rf(), a6c0=rf())
        got = run(t)
        want = tuple(struct.unpack('>I', struct.pack('>f', ts(x)))[0]
                     for x in ref(t))
        tests += 1
        if got != want:
            fails += 1
            if fails <= 10:
                print("FAIL t=%s\n  got =%s\n  want=%s" % (t, got, want))
    print("calc_throttle_position_filter @0x1345C: %d tests, %d failures"
          % (tests, fails))
    if fails == 0:
        print("OK  calc_throttle_position_filter @0x1345C (%d inputs, 0 mismatches)" % tests)
        return 0
    print("FAIL calc_throttle_position_filter @0x1345C (%d mismatches)" % fails)
    return 1


if __name__ == '__main__':
    sys.exit(main())