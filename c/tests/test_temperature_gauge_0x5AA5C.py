#!/usr/bin/env python3
"""
Verify temperature_gauge_0x5AA5C (0x5AA5C) against the ACTUAL ROM bytes,
run in the SH-2E emulator.

Side-effect leaf: reads status byte at 0xFFFFCD4C, writes gauge value byte
to 0xFFFFD2C4:

  b = byte@0xFFFFCD4C
  v = (b & 0x7C) ? 7 : (b & 0x80) ? 6 : 0     // bits 0x40|0x20|0x10|0x08|0x04
  byte@0xFFFFD2C4 = v

C:
  void temperature_gauge_0x5AA5C(void)

NOTE: mov.w sign-extends — 0xD2C4/0xCD4C are really 0xFFFFD2C4/0xFFFFCD4C.

Run from repo root:  python3 c/tests/test_temperature_gauge_0x5AA5C.py
"""
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0x005AA5C

IN_BYTE = 0xFFFFCD4C   # input  status byte
OUT_BYTE = 0xFFFFD2C4  # output gauge value byte


def model(b):
    return 7 if (b & 0x7C) else (6 if (b & 0x80) else 0)


def main():
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)

    # Exhaustive: all 256 input byte values.
    for b in range(256):
        cpu.call(ENTRY, ram={IN_BYTE: b})
        got = cpu.ram.get(OUT_BYTE, -1)
        exp = model(b)
        if got != exp:
            print("FAIL: in=0x%02X -> out=0x%02X expected 0x%02X" % (b, got, exp))
            sys.exit(1)

    print("OK  temperature_gauge_0x5AA5C @0x%04X  (exhaustive 256)" % ENTRY)
    sys.exit(0)


if __name__ == '__main__':
    main()
