#!/usr/bin/env python3
"""
Verify obd_dtc_row_update_0x64418 (0x64418) against the ACTUAL ROM bytes,
run in the SH-2E emulator.

Side-effect leaf, takes r4 (byte value):

  row = word@0xFFFF8D74
  p   = 0xFFFF8930 + row * 0x34
  byte@p+0x32 = (s8(byte@p+0x32) + s8(byte@p+0x08) - r4) & 0xFF
  byte@p+0x08 = r4 & 0xFF

C:
  void obd_dtc_row_update_0x64418(uint32_t r4)

Rows restricted to 0..0x14 (realistic table size; larger wraps p into ROM).
Run from repo root:  python3 c/tests/test_obd_dtc_row_update_0x64418.py [N]
"""
import os, sys, random

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0x0064418

ROW_ADDR = 0xFFFF8D74
BASE = 0xFFFF8930
STRIDE = 0x34


def s8(x):
    x &= 0xFF
    return x - 256 if x & 0x80 else x


def addr(row, off):
    p = (BASE + (row & 0xFFFF) * STRIDE) & 0xFFFFFFFF
    return (p + off) & 0xFFFFFFFF


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)

    def run_one(r4, row, b32, b08):
        ram = {ROW_ADDR: (row >> 8) & 0xFF, ROW_ADDR + 1: row & 0xFF,
               addr(row, 0x32): b32, addr(row, 0x08): b08}
        cpu.call(ENTRY, r4=r4, ram=ram)
        return (cpu.ram.get(addr(row, 0x32), -1), cpu.ram.get(addr(row, 0x08), -1))

    def model(r4, row, b32, b08):
        return ((s8(b32) + s8(b08) - r4) & 0xFF, r4 & 0xFF)

    vals = [0x00, 0x01, 0x7E, 0x7F, 0x80, 0x81, 0xFE, 0xFF]
    for row in range(0x15):
        for r4 in vals:
            for b32 in vals:
                for b08 in vals:
                    got = run_one(r4, row, b32, b08)
                    exp = model(r4, row, b32, b08)
                    if got != exp:
                        print("FAIL: r4=%02X row=%d (b32,b08)=(%02X,%02X) -> %s expected %s" % (
                            r4, row, b32, b08, got, exp))
                        sys.exit(1)

    for _ in range(N):
        r4 = random.randint(0, 0xFF)
        row = random.randint(0, 0x14)
        b32, b08 = (random.randint(0, 255) for _ in range(2))
        got = run_one(r4, row, b32, b08)
        exp = model(r4, row, b32, b08)
        if got != exp:
            print("FAIL: r4=%02X row=%d (b32,b08)=(%02X,%02X) -> %s expected %s" % (
                r4, row, b32, b08, got, exp))
            sys.exit(1)

    print("OK  obd_dtc_row_update_0x64418 @0x%04X  (targeted + %d random)" % (ENTRY, N))
    sys.exit(0)


if __name__ == '__main__':
    main()
