#!/usr/bin/env python3
"""
Verify obd_service_handler_632D6 (0x632D6) against the ACTUAL ROM bytes,
run in the SH-2E emulator.

Pending-flag clear leaf: if byte@0xFFFF87CC == 1, the 16-bit cell at
0xFFFF87CC is rewritten as enc8(0) = 0x00FF (value/complement encoding of 0):

  if (byte@0xFFFF87CC == 0x01)
      word@0xFFFF87CC = enc8(0x00)     ; (0 << 8) | ~0 == 0x00FF

Otherwise the cell is left untouched.  (Same family as 0x632F4 / 0x63312.)

C:
  void obd_service_handler_632D6(void)

Run from repo root:  python3 c/tests/test_obd_service_handler_632D6.py [N]
"""
import os, sys, random

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0x00632D6

FLAG = 0xFFFF87CC


def enc8(x):
    x &= 0xFF
    return ((x << 8) | (~x & 0xFF)) & 0xFFFF


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)

    def run_one(flag, pad):
        ram = {FLAG: flag, FLAG + 1: pad}
        cpu.call(ENTRY, ram=ram)
        return cpu.ram.get(FLAG, -1), cpu.ram.get(FLAG + 1, -1)

    # Exhaustive flag byte 0..255 with a few padding neighbours.
    for flag in range(256):
        for pad in (0x00, 0x01, 0xAA, 0xFF):
            got = run_one(flag, pad)
            if flag == 0x01:
                exp = ((enc8(0) >> 8) & 0xFF, enc8(0) & 0xFF)
                if got != exp:
                    print("FAIL: flag=%02X pad=%02X -> %s expected %s"
                          % (flag, pad, got, exp))
                    sys.exit(1)
            elif got != (flag, pad):
                print("FAIL: flag=%02X pad=%02X unchanged -> %s" % (flag, pad, got))
                sys.exit(1)

    rng = random.Random(0x632D6)
    for _ in range(N):
        flag = rng.randint(0, 0xFF)
        pad = rng.randint(0, 0xFF)
        got = run_one(flag, pad)
        if flag == 0x01:
            exp = ((enc8(0) >> 8) & 0xFF, enc8(0) & 0xFF)
            if got != exp:
                print("FAIL: flag=%02X pad=%02X -> %s expected %s"
                      % (flag, pad, got, exp))
                sys.exit(1)
        elif got != (flag, pad):
            print("FAIL: flag=%02X pad=%02X unchanged -> %s" % (flag, pad, got))
            sys.exit(1)

    print("OK  obd_service_handler_632D6 @0x%04X  (exhaustive + %d random)"
          % (ENTRY, N))
    sys.exit(0)


if __name__ == '__main__':
    main()
