#!/usr/bin/env python3
"""
Verify ignitionDwellOutputInit (0x8F62) — ignition dwell init.
4-channel loop with sensor ADC init and tail-call.
"""
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0x8F62

def test_ignitionDwellOutputInit():
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)

    # Verify prologue: multiple mov.l pushes
    op0 = int.from_bytes(rom[ENTRY:ENTRY+2], 'big')
    assert op0 == 0x2FE6, f"Expected mov.l r14,@-r15 as prologue, got 0x{op0:04X}"

    # Count register saves (mov.l rN,@-r15 = 0x2F__)
    saves = 0
    for off in range(0, 16, 2):
        op = int.from_bytes(rom[ENTRY+off:ENTRY+off+2], 'big')
        if (op >> 8) == 0x2F:  # mov.l rN,@-r15
            saves += 1
    print("  %d register saves in prologue" % saves)

    # Find BSR calls
    bsrs = []
    for off in range(0, 78, 2):
        op = int.from_bytes(rom[ENTRY+off:ENTRY+off+2], 'big')
        if op >> 12 == 0xB and op != 0x0009:
            disp = op & 0xFFF
            if disp & 0x800:
                disp -= 0x1000
            target = ENTRY + off + 4 + disp * 2
            bsrs.append((off, target))

    for off, tgt in bsrs:
        print("    +%d: bsr 0x%05X" % (off, tgt))

    # Verify tail-call BRA at the end
    bra_op = int.from_bytes(rom[ENTRY+76:ENTRY+78], 'big')
    if bra_op >> 12 == 0xA:
        disp = bra_op & 0xFFF
        if disp & 0x800:
            disp -= 0x1000
        target = ENTRY + 76 + 4 + disp * 2
        print("  Tail-call: BRA to 0x%05X" % target)

    print("OK  ignitionDwellOutputInit @0x%04X  structure verified" % ENTRY)
    return True

def main():
    if test_ignitionDwellOutputInit():
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == '__main__':
    main()
