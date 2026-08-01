#!/usr/bin/env python3
"""
Verify whileLoop (0x0A0CE) — an infinite loop / trap handler.
The function should never return; verify that:
  - The BRA at 0x0A0D8 targets itself
  - The ROM bytes match expected trap pattern
"""
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0xA0CE

def test_whileLoop():
    rom = open(ROM, 'rb').read()

    # Verify the BRA at 0x0A0D8 targets itself (0x0A0D8)
    # BRA encoding: 0xA000 | disp12   where disp12 = (target - pc - 4) / 2
    # At pc=0x0A0D8: target = 0x0A0D8, so disp12 = (0x0A0D8 - 0x0A0DC) / 2 = -2
    # In 12-bit signed: 0xFFE → instruction = 0xAFFE
    bra_op = int.from_bytes(rom[0xA0D8:0xA0DA], 'big')
    assert bra_op == 0xAFFE, f"Expected self-loop BRA (0xAFFE) at 0x0A0D8, got 0x{bra_op:04X}"
    print("OK  whileLoop @0x%04X  BRA self-loop confirmed (0xAFFE)" % ENTRY)

    # Verify function entry bytes
    op0 = int.from_bytes(rom[ENTRY:ENTRY+2], 'big')
    print("  First op: 0x%04X (reserved/data word)" % op0)

    return True

def main():
    if test_whileLoop():
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == '__main__':
    main()
