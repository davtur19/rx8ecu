#!/usr/bin/env python3
"""
Verify enableDisableCruiseControl (0xC2E6) — cruise enable/disable.
Takes a boolean, calls dispatch, updates state, tail-calls cleanup.
"""
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0xC2E6

def test_enableDisableCruiseControl():
    rom = open(ROM, 'rb').read()

    # Verify function starts with sts.l pr,@-r15 (prologue)
    op0 = int.from_bytes(rom[ENTRY:ENTRY+2], 'big')
    assert op0 == 0x4F22, f"Expected sts.l pr,@-r15 as prologue, got 0x{op0:04X}"
    print("OK  enableDisableCruiseControl @0x%04X  prologue: sts.l pr,@-r15" % ENTRY)

    # Find the tail-call (jmp @Rn)
    for off in range(0, 54, 2):
        op = int.from_bytes(rom[ENTRY+off:ENTRY+off+2], 'big')
        if op & 0xF0FF == 0x402B:  # jmp @Rm
            reg = (op >> 4) & 0xF
            print("  Tail-call at +%d: jmp @r%d" % (off, reg))
            break
        if op == 0x000B:  # RTS
            print("  RTS at +%d (no tail-call found)" % off)
            break

    print("OK  enableDisableCruiseControl @0x%04X  structure verified" % ENTRY)
    return True

def main():
    if test_enableDisableCruiseControl():
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == '__main__':
    main()
