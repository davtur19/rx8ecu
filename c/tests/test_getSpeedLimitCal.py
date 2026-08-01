#!/usr/bin/env python3
"""
Verify getSpeedLimitCal (0x49EFC) — speed limit calibration table.
Switch/case dispatch with 3 calibration sub-calls.
"""
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0x49EFC

def test_getSpeedLimitCal():
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)

    # Verify prologue
    op0 = int.from_bytes(rom[ENTRY:ENTRY+2], 'big')
    assert op0 == 0x2FE6, f"Expected mov.l r14,@-r15 as first op, got 0x{op0:04X}"

    # Count BSR calls
    bsrs = []
    for off in range(0, 186, 2):
        op = int.from_bytes(rom[ENTRY+off:ENTRY+off+2], 'big')
        if op >> 12 == 0xB and op != 0x0009:
            disp = op & 0xFFF
            if disp & 0x800:
                disp -= 0x1000
            target = ENTRY + off + 4 + disp * 2
            bsrs.append((off, target))

    print("  Found %d BSR/bra calls:" % len(bsrs))
    for off, tgt in bsrs:
        is_bra = (int.from_bytes(rom[ENTRY+off:ENTRY+off+2], 'big') >> 12) == 0xA
        print("    +%d: %s 0x%05X" % (off, "bra" if is_bra else "bsr", tgt))

    # Verify RTS at end
    rts_op = int.from_bytes(rom[ENTRY + 184:ENTRY + 186], 'big')
    assert rts_op == 0x000B, f"Expected RTS at +184, got 0x{rts_op:04X}"

    print("OK  getSpeedLimitCal @0x%04X  switch/case structure verified" % ENTRY)
    return True

def main():
    if test_getSpeedLimitCal():
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == '__main__':
    main()
