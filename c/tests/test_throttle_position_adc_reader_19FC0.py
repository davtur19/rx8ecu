#!/usr/bin/env python3
"""
test_throttle_position_adc_reader_19FC0.py — differential test of
throttle_position_adc_reader @0x19FC0 (lift: c/throttle_position_sensor.c).

Real ROM bytes run in the SH-2E emulator, including the tail-call chain:
0x19FC0 -> 0x3EEB8 (fault handler) -> 0x3920 / 0x3934 (SR helpers).
The chain is self-contained: 0x3934 never reaches 0x3DB0 because r4 = SR&0xF0
= 0xF0 != 0 (default SR=0x000000F0), and no hardware flags are waited on.

Model (disasm 0x19FC0 + 0x3EEB8):
  LIM = u16[ROM 0x6F9EC] (0x7D)
  if u16[0xFFFFA424] < LIM: return 0, no side effects
  else (fr4 = f32[0xFFFFAA10] input):
      if fr4 is NaN: return 1, no side effects
      else:
          f32[0xFFFF8088] = fr4
          bits = f32 bits of fr4
          r14 = ~(se16(bits>>16) + se16(bits&0xFFFF))  (32-bit)
          u16[0xFFFF808C] = u16[0xFFFF808E] = r14 & 0xFFFF
          return 0

Compared: r0 and the three side-effect words (sentinel-checked for the
no-write paths).

Run from repo root: python3 c/tests/test_throttle_position_adc_reader_19FC0.py [N]
"""
import math, os, random, struct, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2, ts  # noqa: E402

rom = open(os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin'), 'rb').read()
cpu = SH2(rom)

ADDR = 0x19FC0
LIM = struct.unpack('>H', rom[0x6F9EC:0x6F9EE])[0]
A424 = 0xFFFFA424
AA10 = 0xFFFFAA10
W8088, W808C, W808E = 0xFFFF8088, 0xFFFF808C, 0xFFFF808E
SENT16 = 0xA5A5
SENT32 = 0x11223344


def s16(x):
    x &= 0xFFFF
    return x - 0x10000 if x & 0x8000 else x


def ref(adc, f):
    adc &= 0xFFFF
    if adc < LIM:
        return (0x6F9EC, False, None, None)   # r0 = table-desc addr, untouched
    if math.isnan(ts(f)):
        return (1, False, None, None)
    bits = struct.unpack('>I', struct.pack('>f', ts(f)))[0]
    r14 = (~((s16(bits >> 16) + s16(bits & 0xFFFF)) & 0xFFFFFFFF)) & 0xFFFFFFFF
    return (0, True, r14 & 0xFFFF, r14 & 0xFFFF)


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
    rng = random.Random(0x19FC0)
    tests = fails = 0
    fspec = [float('nan'), float('inf'), float('-inf'), -0.0, 0.0,
             0.5, 1.0, 2.5, 65535.0, -65535.0, 3.14159, 1e-20, 1e20]

    def run(adc, f):
        ram = {}
        ram[A424] = (adc & 0xFF00) >> 8; ram[A424 + 1] = adc & 0xFF
        b = struct.pack('>f', ts(f))
        for i in range(4):
            ram[AA10 + i] = b[i]
        # sentinels for side-effect words
        ram[W8088] = (SENT32 >> 24) & 0xFF; ram[W8088 + 1] = (SENT32 >> 16) & 0xFF
        ram[W8088 + 2] = (SENT32 >> 8) & 0xFF; ram[W8088 + 3] = SENT32 & 0xFF
        ram[W808C] = (SENT16 >> 8) & 0xFF; ram[W808C + 1] = SENT16 & 0xFF
        ram[W808E] = (SENT16 >> 8) & 0xFF; ram[W808E + 1] = SENT16 & 0xFF
        ret = cpu.call(ADDR, ram=ram)
        g8088 = bytes(cpu.ram.get(W8088 + i, 0) for i in range(4))
        g808c = bytes(cpu.ram.get(W808C + i, 0) for i in range(2))
        g808e = bytes(cpu.ram.get(W808E + i, 0) for i in range(2))
        return ret, g8088, g808c, g808e

    for _ in range(N):
        if rng.random() < 0.4:
            adc = rng.choice((0, 1, LIM - 1, LIM, LIM + 1, 0x7E, 0x7F,
                              0x80, 0xFFFF, 0x8000, 0x4000))
        else:
            adc = rng.getrandbits(16)
        if rng.random() < 0.4:
            f = rng.choice(fspec)
        else:
            f = rng.uniform(-1e4, 1e4)
        ret, w, c, e = ref(adc, f)
        got_ret, g8088, g808c, g808e = run(adc, f)
        tests += 1
        # expected words
        if w:
            exp8088 = struct.pack('>f', ts(f))
            exp808c = struct.pack('>H', c)
            exp808e = struct.pack('>H', e)
        else:
            exp8088 = struct.pack('>I', SENT32)
            exp808c = struct.pack('>H', SENT16)
            exp808e = struct.pack('>H', SENT16)
        if (got_ret != ret or g8088 != exp8088 or g808c != exp808c
                or g808e != exp808e):
            fails += 1
            if fails <= 10:
                print("FAIL adc=%04x f=%r\n  got ret=%x 8088=%s 808C=%s 808E=%s"
                      % (adc, f, got_ret, g8088.hex(), g808c.hex(), g808e.hex()))
                print("  want ret=%x 8088=%s 808C=%s 808E=%s"
                      % (ret, exp8088.hex(), exp808c.hex(), exp808e.hex()))
    print("throttle_position_adc_reader @0x19FC0: %d tests, %d failures"
          % (tests, fails))
    if fails == 0:
        print("OK  throttle_position_adc_reader @0x19FC0 (%d inputs, 0 mismatches)" % tests)
        return 0
    print("FAIL throttle_position_adc_reader @0x19FC0 (%d mismatches)" % fails)
    return 1


if __name__ == '__main__':
    sys.exit(main())