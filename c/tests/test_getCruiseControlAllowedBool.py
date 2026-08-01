#!/usr/bin/env python3
"""
Verify getCruiseControlAllowedBool (0x2E3AC) — cruise enable check.
Checks inhibit flags, master override, speed comparison.
"""
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0x2E3AC

def test_getCruiseControlAllowedBool():
    rom = open(ROM, 'rb').read()

    # Verify first instruction: mov.w @(disp,pc)
    op0 = int.from_bytes(rom[ENTRY:ENTRY+2], 'big')
    assert op0 >> 12 == 0x9, f"Expected mov.w @(disp,pc) as first op, got 0x{op0:04X}"
    print("OK  getCruiseControlAllowedBool @0x%04X  first op: 0x%04X (mov.w @(disp,pc))" % (ENTRY, op0))

    # Count PC-relative word loads (each is a flag address load)
    loads = 0
    for off in range(0, 100, 2):
        op = int.from_bytes(rom[ENTRY+off:ENTRY+off+2], 'big')
        if op >> 12 == 0x9:
            loads += 1
    print("  %d PC-relative word loads (flag addresses)" % loads)

    # Check for FPU instructions (fcmp/gt)
    fpu_ops = 0
    for off in range(0, 100, 2):
        op = int.from_bytes(rom[ENTRY+off:ENTRY+off+2], 'big')
        if op >> 12 == 0xF:
            fpu_ops += 1
    print("  %d FPU opcodes (float comparison)" % fpu_ops)

    # Find RTS
    rts_found = False
    for off in range(0, 102, 2):
        op = int.from_bytes(rom[ENTRY+off:ENTRY+off+2], 'big')
        if op == 0x000B:
            print("  RTS at +%d" % off)
            rts_found = True
            break
    assert rts_found, "RTS not found"

    print("OK  getCruiseControlAllowedBool @0x%04X  structure verified" % ENTRY)
    return True

def main():
    if test_getCruiseControlAllowedBool():
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == '__main__':
    main()
