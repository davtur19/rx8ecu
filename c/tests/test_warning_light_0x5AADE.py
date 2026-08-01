#!/usr/bin/env python3
"""
Verify warning_light_0x5AADE (0x5AADE) against the ACTUAL ROM bytes, run
in the SH-2E emulator.

Side-effect leaf: reads status byte at 0xFFFFCD4C, writes warning-light
value byte to 0xFFFFD2C5:

  b = byte@0xFFFFCD4C
  v = (b & 0x60) ? 0x6D : (b & 0x1C) ? 0x69 : (b & 0x80) ? 0x68 : 0
  byte@0xFFFFD2C5 = v

C:
  void warning_light_0x5AADE(void)

NOTE: mov.w sign-extends — 0xD2C5/0xCD4C are really 0xFFFFD2C5/0xFFFFCD4C.

Run from repo root:  python3 c/tests/test_warning_light_0x5AADE.py
"""
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0x005AADE

IN_BYTE = 0xFFFFCD4C   # input  status byte
OUT_BYTE = 0xFFFFD2C5  # output warning-light value byte


def model(b):
    return 0x6D if (b & 0x60) else (0x69 if (b & 0x1C) else (0x68 if (b & 0x80) else 0))


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

    print("OK  warning_light_0x5AADE @0x%04X  (exhaustive 256)" % ENTRY)
    sys.exit(0)


if __name__ == '__main__':
    main()
