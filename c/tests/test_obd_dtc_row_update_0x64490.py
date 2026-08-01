#!/usr/bin/env python3
"""
Verify obd_dtc_row_update_0x64490 (0x64490) against the ACTUAL ROM bytes,
run in the SH-2E emulator.

Side-effect leaf, takes r4 (16-bit value):

  row = word@0xFFFF8D74
  p   = 0xFFFF8930 + row * 0x34
  w   = word@p+0x02
  delta = (s16(w) + ((w >> 8) & 0xFF)) - (r4 + ((r4 & 0xFFFF) >> 8))
  byte@p+0x32 = (s8(byte@p+0x32) + delta) & 0xFF
  word@p+0x02 = r4 & 0xFFFF

C:
  void obd_dtc_row_update_0x64490(uint32_t r4)

Rows restricted to 0..0x14 (realistic table size).
Run from repo root:  python3 c/tests/test_obd_dtc_row_update_0x64490.py [N]
"""
import os, sys, random

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0x0064490

ROW_ADDR = 0xFFFF8D74
BASE = 0xFFFF8930
STRIDE = 0x34


def s8(x):
    x &= 0xFF
    return x - 256 if x & 0x80 else x


def s16(x):
    x &= 0xFFFF
    return x - 0x10000 if x & 0x8000 else x


def addr(row, off):
    p = (BASE + (row & 0xFFFF) * STRIDE) & 0xFFFFFFFF
    return (p + off) & 0xFFFFFFFF


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)

    def run_one(r4, row, b32, w):
        ram = {ROW_ADDR: (row >> 8) & 0xFF, ROW_ADDR + 1: row & 0xFF,
               addr(row, 0x32): b32,
               addr(row, 0x02): (w >> 8) & 0xFF, addr(row, 0x03): w & 0xFF}
        cpu.call(ENTRY, r4=r4, ram=ram)
        b32g = cpu.ram.get(addr(row, 0x32), -1)
        wg = (cpu.ram.get(addr(row, 0x02), -1) << 8) | cpu.ram.get(addr(row, 0x03), -1)
        return (b32g, wg)

    def model(r4, row, b32, w):
        delta = (s16(w) + ((w >> 8) & 0xFF)) - (r4 + ((r4 & 0xFFFF) >> 8))
        return ((s8(b32) + delta) & 0xFF, r4 & 0xFFFF)

    vals8 = [0x00, 0x01, 0x7E, 0x7F, 0x80, 0x81, 0xFE, 0xFF]
    vals16 = [0x0000, 0x0001, 0x00FF, 0x0100, 0x7FFF, 0x8000, 0x8001, 0xFFFF]
    for row in range(0x15):
        for r4 in vals16:
            for b32 in vals8:
                for w in vals16:
                    got = run_one(r4, row, b32, w)
                    exp = model(r4, row, b32, w)
                    if got != exp:
                        print("FAIL: r4=%04X row=%d (b32,w)=(%02X,%04X) -> %s expected %s" % (
                            r4, row, b32, w, got, exp))
                        sys.exit(1)

    for _ in range(N):
        r4 = random.randint(0, 0xFFFF)
        row = random.randint(0, 0x14)
        b32 = random.randint(0, 255)
        w = random.randint(0, 0xFFFF)
        got = run_one(r4, row, b32, w)
        exp = model(r4, row, b32, w)
        if got != exp:
            print("FAIL: r4=%04X row=%d (b32,w)=(%02X,%04X) -> %s expected %s" % (
                r4, row, b32, w, got, exp))
            sys.exit(1)

    print("OK  obd_dtc_row_update_0x64490 @0x%04X  (targeted + %d random)" % (ENTRY, N))
    sys.exit(0)


if __name__ == '__main__':
    main()
