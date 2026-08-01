#!/usr/bin/env python3
"""
Verify CAN_TableLookup_583E4 (0x583E4) — memory scan / match accumulator.
Scans 36 entries, checks signature+filter, accumulates matched data.
"""
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0x583E4

def test_CAN_TableLookup_583E4():
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)

    # Verify first instruction: mov.l r14,@-r15 (prologue)
    op0 = int.from_bytes(rom[ENTRY:ENTRY+2], 'big')
    assert op0 == 0x2FE6, f"Expected mov.l r14,@-r15 as first op, got 0x{op0:04X}"

    # Count register saves
    saves = 0
    for off in range(0, 24, 2):
        op = int.from_bytes(rom[ENTRY+off:ENTRY+off+2], 'big')
        if (op >> 8) == 0x2F:
            saves += 1
    print("  %d register saves in prologue" % saves)

    # Verify function size matches expected 100 bytes
    # Check for RTS at offset 0x60 (96)
    rts_op = int.from_bytes(rom[ENTRY+96:ENTRY+98], 'big')
    assert rts_op == 0x000B, f"Expected RTS at +96, got 0x{rts_op:04X}"

    print("OK  CAN_TableLookup_583E4 @0x%04X  size/opcodes verified" % ENTRY)
    return True

def main():
    if test_CAN_TableLookup_583E4():
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == '__main__':
    main()
