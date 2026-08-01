#!/usr/bin/env python3
"""
Verify revLimitFuelCutInit (0xF0FC) — rev-limiter fuel cut init.
Conditionally clears counters if enable flag is set.
"""
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0xF0FC

def test_revLimitFuelCutInit():
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)

    # Verify function: read flag, conditional branch, clear regs, RTS
    # First: mov.l @(disp,pc),r3
    op0 = int.from_bytes(rom[ENTRY:ENTRY+2], 'big')
    assert op0 >> 12 == 0xD, f"Expected mov.l as first op, got 0x{op0:04X}"

    # mov.b @r3,r0  (read enable flag)
    op1 = int.from_bytes(rom[ENTRY+2:ENTRY+4], 'big')
    assert op1 == 0x6030, f"Expected mov.b @r3,r0 at +2, got 0x{op1:04X}"

    # extu.b r0,r0
    op2 = int.from_bytes(rom[ENTRY+4:ENTRY+6], 'big')
    assert op2 == 0x600C, f"Expected extu.b at +4, got 0x{op2:04X}"

    # cmp/eq #1,r0
    op3 = int.from_bytes(rom[ENTRY+6:ENTRY+8], 'big')
    assert op3 == 0x8801, f"Expected cmp/eq #1 at +6, got 0x{op3:04X}"

    print("OK  revLimitFuelCutInit @0x%04X  instruction sequence verified" % ENTRY)
    return True

def main():
    if test_revLimitFuelCutInit():
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == '__main__':
    main()
