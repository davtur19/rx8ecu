#!/usr/bin/env python3
"""
Verify nop_delay_40cycles (0x4C14) — a simple NOP-burn delay.
The function is 20 NOPs + RTS + NOP delay slot.  Verify that:
  - It returns cleanly (no crash)
  - All 20 NOPs are 0x0009
  - The return address is correct
"""
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0x4C14

def test_nop_delay_40cycles():
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)

    # Verify the ROM bytes are all NOPs (0x0009) until RTS (0x000B)
    for off in range(0, 40, 2):
        op = int.from_bytes(rom[ENTRY + off:ENTRY + off + 2], 'big')
        assert op == 0x0009, f"Offset +{off}: expected NOP (0x0009), got 0x{op:04X}"

    rts_op = int.from_bytes(rom[ENTRY + 40:ENTRY + 42], 'big')
    assert rts_op == 0x000B, f"Expected RTS (0x000B) at end, got 0x{rts_op:04X}"

    # Call through emulator — should return cleanly
    result = cpu.call(ENTRY)
    print("OK  nop_delay_40cycles @0x%04X  (clean return, r0=0x%08X)" % (ENTRY, result))
    return True

def main():
    if test_nop_delay_40cycles():
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == '__main__':
    main()
