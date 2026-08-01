#!/usr/bin/env python3
"""
Verify getFromGPIO (0x70D0) — GPIO port read with parametric routing.
Complex function with GPIO manipulation and conditional output routing.
"""
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0x70D0

def test_getFromGPIO():
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)

    # Verify prologue
    op0 = int.from_bytes(rom[ENTRY:ENTRY+2], 'big')
    assert op0 == 0x2FE6, f"Expected mov.l r14,@-r15 as first op, got 0x{op0:04X}"

    # Count register saves
    saves = 0
    for off in range(0, 14, 2):
        op = int.from_bytes(rom[ENTRY+off:ENTRY+off+2], 'big')
        if (op >> 8) == 0x2F:
            saves += 1
    print("  %d register saves in prologue" % saves)

    # Count BSR/bra calls
    calls = []
    for off in range(0, 168, 2):
        op = int.from_bytes(rom[ENTRY+off:ENTRY+off+2], 'big')
        if (op >> 12) in (0xA, 0xB) and op != 0x0009:
            disp = op & 0xFFF
            if disp & 0x800:
                disp -= 0x1000
            target = ENTRY + off + 4 + disp * 2
            calls.append((off, "bra" if op >> 12 == 0xA else "bsr", target))
        elif op & 0xF0FF == 0x400B:  # jsr @Rm
            calls.append((off, "jsr @r...", -1))
        elif op & 0xF0FF == 0x402B:  # jmp @Rm
            calls.append((off, "jmp @r...", -1))

    for off, typ, tgt in calls:
        if tgt >= 0:
            print("    +%d: %s 0x%05X" % (off, typ, tgt))
        else:
            print("    +%d: %s (indirect)" % (off, typ))

    # Verify RTS at end
    rts_op = int.from_bytes(rom[ENTRY + 166:ENTRY + 168], 'big')
    assert rts_op == 0x000B, f"Expected RTS at +166, got 0x{rts_op:04X}"

    print("OK  getFromGPIO @0x%04X  structure verified" % ENTRY)
    return True

def main():
    if test_getFromGPIO():
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == '__main__':
    main()
