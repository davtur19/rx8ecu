#!/usr/bin/env python3
"""
Verify knockFunctionInit (0xC31C) — knock detection subsystem init.
Calls atu2_tior2c_waveform_init, knockRelatedInit, then sets registers.
"""
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0xC31C

def test_knockFunctionInit():
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)

    # Verify BSR calls to sub-functions
    # bsr 0xC346 at offset 2
    bsr1 = int.from_bytes(rom[ENTRY+2:ENTRY+4], 'big')
    # bsr 0xC3C8 at offset 6
    bsr2 = int.from_bytes(rom[ENTRY+6:ENTRY+8], 'big')

    # Verify we have BSR instructions (0xBnnn)
    assert bsr1 >> 12 == 0xB, f"Expected BSR at +2, got 0x{bsr1:04X}"
    assert bsr2 >> 12 == 0xB, f"Expected BSR at +6, got 0x{bsr2:04X}"

    # Verify RTS at end
    rts_op = int.from_bytes(rom[ENTRY+38:ENTRY+40], 'big')
    assert rts_op == 0x000B, f"Expected RTS at +38, got 0x{rts_op:04X}"

    # Verify there's a mov.b r4,@r2 in the delay slot of RTS
    delay_op = int.from_bytes(rom[ENTRY+40:ENTRY+42], 'big')
    assert delay_op == 0x2240, f"Expected mov.b r4,@r2 in delay slot, got 0x{delay_op:04X}"

    print("OK  knockFunctionInit @0x%04X  structure verified" % ENTRY)
    return True

def main():
    if test_knockFunctionInit():
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == '__main__':
    main()
