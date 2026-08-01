#!/usr/bin/env python3
"""
Verify setAlternatorWarningLight (0x275BC) — alternator warning lamp.
MULTIPLE fault condition checks → sets output 0/1.
"""
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0x275BC

def test_setAlternatorWarningLight():
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)

    # Verify first instruction: mov.w @(disp,pc)
    op0 = int.from_bytes(rom[ENTRY:ENTRY+2], 'big')
    assert op0 >> 12 == 0x9, f"Expected mov.w @(disp,pc) as first op, got 0x{op0:04X}"

    # Count the number of mov.w load instructions (each loads a flag address)
    loads = 0
    for off in range(0, 70, 2):
        op = int.from_bytes(rom[ENTRY+off:ENTRY+off+2], 'big')
        if op >> 12 == 0x9:  # mov.w @(disp,pc)
            loads += 1

    print("  Found %d PC-relative word loads (address loads for flag checks)" % loads)

    # Verify RTS at end
    rts_op = int.from_bytes(rom[ENTRY + 70:ENTRY + 72], 'big')
    assert rts_op == 0x000B, f"Expected RTS at +70, got 0x{rts_op:04X}"

    print("OK  setAlternatorWarningLight @0x%04X  structure verified" % ENTRY)
    return True

def main():
    if test_setAlternatorWarningLight():
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == '__main__':
    main()
