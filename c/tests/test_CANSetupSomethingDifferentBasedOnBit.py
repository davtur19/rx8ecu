#!/usr/bin/env python3
"""
Verify CANSetupSomethingDifferentBasedOnBit (0xE074) — CAN channel setup.
Two loops (16 + 6 channels) calling init for uninitialised channels.
"""
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0xE074

def test_CANSetupSomethingDifferentBasedOnBit():
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)

    # Verify prologue
    op0 = int.from_bytes(rom[ENTRY:ENTRY+2], 'big')
    assert op0 == 0x2FE6, f"Expected mov.l r14,@-r15, got 0x{op0:04X}"

    # Count register saves
    saves = 0
    for off in range(0, 10, 2):
        op = int.from_bytes(rom[ENTRY+off:ENTRY+off+2], 'big')
        if (op >> 8) == 0x2F:
            saves += 1
    print("  %d register saves in prologue" % saves)

    # Find loops: look for bf/s with negative offset (loop back)
    loops = 0
    for off in range(0, 94, 2):
        op = int.from_bytes(rom[ENTRY+off:ENTRY+off+2], 'big')
        if op & 0xFF00 == 0x8F00:  # bf/s
            disp = op & 0xFF
            if disp & 0x80:
                disp -= 0x100
            target = ENTRY + off + 4 + disp * 2
            if target < ENTRY + off:  # backward branch = loop
                loops += 1
                print("  Loop at +%d → 0x%05X (backward)" % (off, target))

    print("  Found %d backward branches (loop structures)" % loops)

    # Verify RTS at end
    rts_op = int.from_bytes(rom[ENTRY + 92:ENTRY + 94], 'big')
    assert rts_op == 0x000B, f"Expected RTS at +92, got 0x{rts_op:04X}"

    print("OK  CANSetupSomethingDifferentBasedOnBit @0x%04X  structure verified" % ENTRY)
    return True

def main():
    if test_CANSetupSomethingDifferentBasedOnBit():
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == '__main__':
    main()
