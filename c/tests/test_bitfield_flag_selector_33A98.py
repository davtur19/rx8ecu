#!/usr/bin/env python3
"""
Verify bitfield_flag_selector_33A98 (0x33A98) against the ACTUAL ROM bytes,
run in the SH-2E emulator.

Side-effect leaf: reads status byte at 0xFFFFCD4E, writes select code into
the top nibble of byte@0xFFFFC05C:

  b = byte@0xFFFFCD4E
  v = (b & 0x40) ? 0 : (b & 0x20) ? 1 : (b & 0x80) ? 2 : 3
  byte@0xFFFFC05C = v << 4

C:
  void bitfield_flag_selector_33A98(void)

NOTE: mov.w sign-extends 0xCD4E → input is 0xFFFFCD4E.

Run from repo root:  python3 c/tests/test_bitfield_flag_selector_33A98.py
"""
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0x0033A98

IN_BYTE = 0xFFFFCD4E   # input  status byte
OUT_BYTE = 0xFFFFC05C  # output select code byte


def model(b):
    v = 0 if (b & 0x40) else (1 if (b & 0x20) else (2 if (b & 0x80) else 3))
    return (v << 4) & 0xFF


def main():
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)

    for b in range(256):
        cpu.call(ENTRY, ram={IN_BYTE: b})
        got = cpu.ram.get(OUT_BYTE, -1)
        exp = model(b)
        if got != exp:
            print("FAIL: in=0x%02X -> out=0x%02X expected 0x%02X" % (b, got, exp))
            sys.exit(1)

    print("OK  bitfield_flag_selector_33A98 @0x%04X  (exhaustive 256)" % ENTRY)
    sys.exit(0)


if __name__ == '__main__':
    main()
