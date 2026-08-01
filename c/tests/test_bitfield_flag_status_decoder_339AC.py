#!/usr/bin/env python3
"""
Verify bitfield_flag_status_decoder_339AC (0x339AC) against the ACTUAL ROM
bytes, run in the SH-2E emulator.

Side-effect leaf: reads status byte at 0xFFFFCD4E, writes decoded status
code byte to 0xFFFFC04D:

  b = byte@0xFFFFCD4E
  v = (b & 0x60) ? 0x08 : (b & 0x80) ? 0x02 : 0
  byte@0xFFFFC04D = v

C:
  void bitfield_flag_status_decoder_339AC(void)

NOTE: mov.w sign-extends 0xCD4E → input is 0xFFFFCD4E.

Run from repo root:  python3 c/tests/test_bitfield_flag_status_decoder_339AC.py
"""
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0x00339AC

IN_BYTE = 0xFFFFCD4E   # input  status byte
OUT_BYTE = 0xFFFFC04D  # output status code byte


def model(b):
    return 0x08 if (b & 0x60) else (0x02 if (b & 0x80) else 0)


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

    print("OK  bitfield_flag_status_decoder_339AC @0x%04X  (exhaustive 256)" % ENTRY)
    sys.exit(0)


if __name__ == '__main__':
    main()
