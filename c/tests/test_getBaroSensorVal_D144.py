#!/usr/bin/env python3
"""
test_getBaroSensorVal_D144.py — differential test of getBaroSensorVal @0xD144
(lift: c/baro_sensor_value.c).

Real ROM bytes run in the SH-2E emulator.  The function is a select +
byte-swap + store helper:

  sel = r4 & 0xFF ; val = r5 & 0xFFFF
  sw  = ((val & 0xFF) << 8) | ((val >> 8) & 0xFF)
  addr = 0xFFFFE40A if sel == 0 else 0xFFFFE60A
  *(u16)addr = sw
  return r0 (untouched -> 0); r3 = sw

Compared: r0, r3, and the u16 written at the selected address.

Run from repo root:  python3 c/tests/test_getBaroSensorVal_D144.py [N]
"""
import os, random, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2  # noqa: E402

rom = open(os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin'), 'rb').read()
cpu = SH2(rom)

ADDR = 0xD144
A0, A1 = 0xFFFFE40A, 0xFFFFE60A


def ref(sel, val):
    sel &= 0xFF
    val &= 0xFFFF
    sw = ((val & 0xFF) << 8) | ((val >> 8) & 0xFF)
    addr = A0 if sel == 0 else A1
    return (0, sw, addr)


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
    rng = random.Random(0xD144)
    tests = fails = 0
    for _ in range(N):
        if rng.random() < 0.4:
            sel = rng.choice((0, 0, 1, 2, 0xFF, 0x100, 0x200, 0x7F))
        else:
            sel = rng.getrandbits(16)
        if rng.random() < 0.3:
            val = rng.choice((0, 0xFFFF, 0x0100, 0x00FF, 0x1234, 0xABCD,
                              0x8080, 0x8000, 0x0001))
        else:
            val = rng.getrandbits(16)
        r0, r3, addr = ref(sel, val)
        got = cpu.call(ADDR, r4=sel, r5=val)
        g3 = cpu.r[3] & 0xFFFF
        gmem = bytes(cpu.ram.get(addr + i, 0) for i in range(2))
        wmem = ((r3 >> 8) & 0xFF, r3 & 0xFF)
        tests += 1
        if got != r0 or g3 != r3 or gmem != bytes(wmem):
            fails += 1
            if fails <= 10:
                print("FAIL sel=%04x val=%04x\n  got r0=%x r3=%04x mem=%s"
                      % (sel, val, got, g3, gmem.hex()))
                print("  want r0=%x r3=%04x mem=%s" % (r0, r3, bytes(wmem).hex()))
    print("getBaroSensorVal @0xD144: %d tests, %d failures" % (tests, fails))
    if fails == 0:
        print("OK  getBaroSensorVal @0xD144 (%d inputs, 0 mismatches)" % tests)
        return 0
    print("FAIL getBaroSensorVal @0xD144 (%d mismatches)" % fails)
    return 1


if __name__ == '__main__':
    sys.exit(main())