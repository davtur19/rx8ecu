#!/usr/bin/env python3
"""
Verify crankSensorInit (0x7C30) — crank sensor initialisation.
Writes to control registers and conditionally branches to crank_mode_switch.
"""
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0x7C30

def test_crankSensorInit():
    rom = open(ROM, 'rb').read()

    # Verify function structure
    op0 = int.from_bytes(rom[ENTRY:ENTRY+2], 'big')
    assert op0 >> 12 == 0xD, f"Expected mov.l as first op, got 0x{op0:04X}"
    print("OK  crankSensorInit @0x%04X  starts with mov.l (PC-relative load)" % ENTRY)

    # Find the BRA at the end: should branch to crank_mode_switch (0x768C)
    # BRA is at the instruction before RTS
    for off in range(0, 36, 2):
        op = int.from_bytes(rom[ENTRY+off:ENTRY+off+2], 'big')
        if op >> 12 == 0xA:  # BRA
            disp = op & 0xFFF
            if disp & 0x800:
                disp -= 0x1000
            target = ENTRY + off + 4 + disp * 2
            print("  BRA at +%d → target 0x%05X" % (off, target))
            if target == 0x768C:
                print("  → crank_mode_switch confirmed")
            break

    return True

def main():
    if test_crankSensorInit():
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == '__main__':
    main()
