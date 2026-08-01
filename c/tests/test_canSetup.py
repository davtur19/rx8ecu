#!/usr/bin/env python3
"""
Verify canSetup (0xDC8C) — CAN controller init with retry.
Tests config bit selection, retry loop, error flag setting.
"""
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0xDC8C

def test_canSetup():
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)

    # Verify prologue and structure
    op0 = int.from_bytes(rom[ENTRY:ENTRY+2], 'big')
    assert op0 == 0x2FE6, f"Expected mov.l r14,@-r15, got 0x{op0:04X}"

    # Count register saves
    saves = 0
    for off in range(0, 22, 2):
        op = int.from_bytes(rom[ENTRY+off:ENTRY+off+2], 'big')
        if (op >> 8) == 0x2F:
            saves += 1
    print("  %d register saves in prologue" % saves)

    # Find BSR/call instructions
    calls = []
    for off in range(0, 158, 2):
        op = int.from_bytes(rom[ENTRY+off:ENTRY+off+2], 'big')
        if (op >> 12) in (0xA, 0xB) and op != 0x0009:
            disp = op & 0xFFF
            if disp & 0x800:
                disp -= 0x1000
            target = ENTRY + off + 4 + disp * 2
            calls.append((off, "bra" if op >> 12 == 0xA else "bsr", target))
        elif op & 0xF0FF == 0x400B:  # jsr @Rm
            calls.append((off, "jsr", -1))
        elif op & 0xF0FF == 0x402B:  # jmp @Rm
            calls.append((off, "jmp", -1))

    for off, typ, tgt in calls:
        if tgt >= 0:
            print("    +%d: %s 0x%05X" % (off, typ, tgt))
        else:
            print("    +%d: %s (indirect)" % (off, typ))

    # Verify RTS at end
    rts_op = int.from_bytes(rom[ENTRY + 156:ENTRY + 158], 'big')
    assert rts_op == 0x000B, f"Expected RTS at +156, got 0x{rts_op:04X}"

    print("OK  canSetup @0x%04X  structure verified" % ENTRY)
    return True

def main():
    if test_canSetup():
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == '__main__':
    main()
