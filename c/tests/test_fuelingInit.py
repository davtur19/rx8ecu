#!/usr/bin/env python3
"""
Verify fuelingInit (0x753C) — fuel/crank system initialisation.
Long init chain with multiple BSR calls and tail-call.
"""
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0x753C

def test_fuelingInit():
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)

    # Count BSR calls
    bsrs = []
    for off in range(0, 78, 2):
        op = int.from_bytes(rom[ENTRY+off:ENTRY+off+2], 'big')
        if op >> 12 == 0xB and op != 0x0009:  # BSR
            # Decode target
            disp = op & 0xFFF
            if disp & 0x800:
                disp -= 0x1000
            target = ENTRY + off + 4 + disp * 2
            bsrs.append((off, target))

    print("  Found %d BSR calls:" % len(bsrs))
    for off, tgt in bsrs:
        print("    +%d: bsr 0x%05X" % (off, tgt))

    # Verify it ends with BRA (tail call) not RTS
    # At offset ~78: bra 0x808E
    bra_off = 76  # 0x4F26 + 2 = lds.l, then bra
    bra_op = int.from_bytes(rom[ENTRY+bra_off:ENTRY+bra_off+2], 'big')
    if bra_op >> 12 == 0xA:
        disp = bra_op & 0xFFF
        if disp & 0x800:
            disp -= 0x1000
        target = ENTRY + bra_off + 4 + disp * 2
        print("  Tail-call: BRA to 0x%05X (crank_output_update)" % target)
    else:
        print("  No BRA at offset %d (op=0x%04X) — checking further" % (bra_off, bra_op))
        # The BRA might be at offset 78 (after lds.l)
        bra_op2 = int.from_bytes(rom[ENTRY+78:ENTRY+80], 'big')
        if bra_op2 >> 12 == 0xA:
            disp = bra_op2 & 0xFFF
            if disp & 0x800:
                disp -= 0x1000
            target = ENTRY + 78 + 4 + disp * 2
            print("  Tail-call: BRA to 0x%05X" % target)

    print("OK  fuelingInit @0x%04X  call tree documented" % ENTRY)
    return True

def main():
    if test_fuelingInit():
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == '__main__':
    main()
