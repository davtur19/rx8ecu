#!/usr/bin/env python3
"""
Verify getEngineOnTimeForOilMetering (0xE492) — oil-metering engine-on timer.
Checks engine flag, conditionally reads/updates timer.
"""
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0xE492

def test_getEngineOnTimeForOilMetering():
    rom = open(ROM, 'rb').read()

    # Verify first instruction: sts.l pr,@-r15 (save PR)
    op0 = int.from_bytes(rom[ENTRY:ENTRY+2], 'big')
    assert op0 == 0x4F22, f"Expected sts.l pr,@-r15 as first op, got 0x{op0:04X}"
    print("OK  getEngineOnTimeForOilMetering @0x%04X  first op: 0x%04X (sts.l pr,@-r15)" % (ENTRY, op0))

    # Find RTS
    rts_found = False
    for off in range(0, 34, 2):
        op = int.from_bytes(rom[ENTRY+off:ENTRY+off+2], 'big')
        if op == 0x000B:
            print("  RTS at +%d" % off)
            rts_found = True
            break
    assert rts_found, "RTS not found"
    print("OK  getEngineOnTimeForOilMetering @0x%04X  structure verified" % ENTRY)
    return True

def main():
    if test_getEngineOnTimeForOilMetering():
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == '__main__':
    main()
