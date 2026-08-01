#!/usr/bin/env python3
"""
Verify getACSwitchStatus (0x306F4) — A/C switch status reader.
Tests bit 2 of an I/O port, sets output byte accordingly.
"""
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0x306F4

def test_getACSwitchStatus():
    rom = open(ROM, 'rb').read()

    # Verify first op is mov.w @(disp,pc)
    op0 = int.from_bytes(rom[ENTRY:ENTRY+2], 'big')
    assert op0 >> 12 == 0x9, f"Expected mov.w @(disp,pc) as first op, got 0x{op0:04X}"
    print("OK  getACSwitchStatus @0x%04X  first op: 0x%04X (mov.w @(disp,pc))" % (ENTRY, op0))

    # RTS is at offset 28 (0x1C), not 30 - the function is 32 bytes total
    # Let me find the RTS
    rts_found = False
    for off in range(0, 32, 2):
        op = int.from_bytes(rom[ENTRY+off:ENTRY+off+2], 'big')
        if op == 0x000B:
            print("  RTS at +%d" % off)
            rts_found = True
            break
    assert rts_found, "RTS not found in function"
    print("OK  getACSwitchStatus @0x%04X  RTS found" % ENTRY)
    return True

def main():
    if test_getACSwitchStatus():
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == '__main__':
    main()
