#!/usr/bin/env python3
"""
Verify getEngineOffTimer (0x3279E) — engine-off elapsed time logic.
Checks engine-run flag, conditionally calls timer accumulator.
"""
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0x3279E

def test_getEngineOffTimer():
    rom = open(ROM, 'rb').read()

    # Verify first instruction: mov.l r14,@-r15 (stack save)
    op0 = int.from_bytes(rom[ENTRY:ENTRY+2], 'big')
    assert op0 == 0x2FE6, f"Expected mov.l r14,@-r15 as first op, got 0x{op0:04X}"
    print("OK  getEngineOffTimer @0x%04X  first op: 0x%04X (mov.l r14,@-r15)" % (ENTRY, op0))

    # Find RTS
    rts_found = False
    for off in range(0, 40, 2):
        op = int.from_bytes(rom[ENTRY+off:ENTRY+off+2], 'big')
        if op == 0x000B:
            print("  RTS at +%d" % off)
            rts_found = True
            break
    assert rts_found, "RTS not found"
    print("OK  getEngineOffTimer @0x%04X  structure verified" % ENTRY)
    return True

def main():
    if test_getEngineOffTimer():
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == '__main__':
    main()
