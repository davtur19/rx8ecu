#!/usr/bin/env python3
"""
Verify obd_dtc_row_update_0x64258 (0x64258) against the ACTUAL ROM bytes,
run in the SH-2E emulator.

Side-effect leaf over the OBD DTC table (base 0xFFFF8930, stride 0x34,
row index = word@0xFFFF8D74):

  row = word@0xFFFF8D74
  p   = 0xFFFF8930 + (row & 0xFFFF) * 0x34
  byte@p+0x32 = (byte@p+0x32 + byte@p+0x07 + 0xFF) & 0xFF
  byte@p+0x07 = 1
  byte@p+0x32 = (byte@p+0x32 + byte@p+0x08 + 0xF9) & 0xFF
  byte@p+0x08 = 7

C:
  void obd_dtc_row_update_0x64258(void)

Run from repo root:  python3 c/tests/test_obd_dtc_row_update_0x64258.py [N]
"""
import os, sys, random

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0x0064258

ROW_ADDR = 0xFFFF8D74   # 16-bit row index (mov.w read)
BASE = 0xFFFF8930       # DTC table base
STRIDE = 0x34


def model(row, b32, b07, b08):
    p = (BASE + (row & 0xFFFF) * STRIDE) & 0xFFFFFFFF
    b32 = (b32 + b07 + 0xFF) & 0xFF
    b07 = 1
    b32 = (b32 + b08 + 0xF9) & 0xFF
    b08 = 7
    return p, b32, b07, b08


def addr(row, off):
    """Effective byte address, 32-bit wrapped like the SH-2 (p + off) & 0xFFFFFFFF."""
    p = (BASE + (row & 0xFFFF) * STRIDE) & 0xFFFFFFFF
    return (p + off) & 0xFFFFFFFF


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)

    def run_one(row, b32, b07, b08):
        ram = {ROW_ADDR: (row >> 8) & 0xFF, ROW_ADDR + 1: row & 0xFF}
        for off, v in ((0x32, b32), (0x07, b07), (0x08, b08)):
            ram[addr(row, off)] = v
        cpu.call(ENTRY, ram=ram)
        return (cpu.ram.get(addr(row, 0x32), -1),
                cpu.ram.get(addr(row, 0x07), -1),
                cpu.ram.get(addr(row, 0x08), -1))

    # Targeted: corner bytes + rows 0..3.
    vals = [0x00, 0x01, 0x06, 0x07, 0x08, 0x7F, 0x80, 0xFF]
    for row in range(4):
        for b32 in vals:
            for b07 in vals:
                for b08 in vals:
                    got = run_one(row, b32, b07, b08)
                    exp = model(row, b32, b07, b08)[1:]
                    if got != exp:
                        print("FAIL: row=%d (b32,b07,b08)=(%02X,%02X,%02X) -> %s expected %s" % (
                            row, b32, b07, b08, got, exp))
                        sys.exit(1)

    # Random: realistic row indices 0..0x14 (the DTC table is 21 rows —
    # 0xFFFF8930 + 21*0x34 == 0xFFFF8D74, the row-index word itself; larger
    # rows wrap p into ROM code, which is not a real configuration).
    for _ in range(N):
        row = random.randint(0, 0x14)
        b32, b07, b08 = (random.randint(0, 255) for _ in range(3))
        got = run_one(row, b32, b07, b08)
        exp = model(row, b32, b07, b08)[1:]
        if got != exp:
            print("FAIL: row=%d (b32,b07,b08)=(%02X,%02X,%02X) -> %s expected %s" % (
                row, b32, b07, b08, got, exp))
            sys.exit(1)

    print("OK  obd_dtc_row_update_0x64258 @0x%04X  (targeted + %d random)" % (ENTRY, N))
    sys.exit(0)


if __name__ == '__main__':
    main()
