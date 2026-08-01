#!/usr/bin/env python3
"""
Verify calibration_apply_4B770 (0x4B770) against the ACTUAL ROM bytes, run
in the SH-2E emulator.

Side-effect leaf: reads three input bytes, writes one flag byte:

  b201  = byte@0xFFFFD201
  bCE00 = byte@0xFFFFCE00
  bCE01 = byte@0xFFFFCE01
  v = (b201 != 1 && bCE00 == 0 && bCE01 == 0) ? 1 : 0
  byte@0xFFFFCDFD = v

C:
  void calibration_apply_4B770(void)

NOTE: mov.w sign-extends — 0xD201/0xCE00/0xCE01/0xCDFD are really
0xFFFFD201/0xFFFFCE00/0xFFFFCE01/0xFFFFCDFD.

Run from repo root:  python3 c/tests/test_calibration_apply_4B770.py [N]
"""
import os, sys, random

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0x004B770

IN_B201 = 0xFFFFD201   # input byte 0
IN_CE00 = 0xFFFFCE00   # input byte 1
IN_CE01 = 0xFFFFCE01   # input byte 2
OUT = 0xFFFFCDFD       # output flag byte


def model(b201, bce00, bce01):
    return 1 if (b201 != 1 and bce00 == 0 and bce01 == 0) else 0


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)

    # Targeted: all combos of interesting values (covers every branch).
    interesting = [0x00, 0x01, 0x02, 0x80, 0xFF]
    for b201 in interesting:
        for bce00 in interesting:
            for bce01 in interesting:
                cpu.call(ENTRY, ram={IN_B201: b201, IN_CE00: bce00, IN_CE01: bce01})
                got = cpu.ram.get(OUT, -1)
                exp = model(b201, bce00, bce01)
                if got != exp:
                    print("FAIL: in=(%02X,%02X,%02X) -> out=0x%02X expected 0x%02X" % (
                        b201, bce00, bce01, got, exp))
                    sys.exit(1)

    # Random.
    for _ in range(N):
        b201, bce00, bce01 = (random.randint(0, 255) for _ in range(3))
        cpu.call(ENTRY, ram={IN_B201: b201, IN_CE00: bce00, IN_CE01: bce01})
        got = cpu.ram.get(OUT, -1)
        exp = model(b201, bce00, bce01)
        if got != exp:
            print("FAIL: in=(%02X,%02X,%02X) -> out=0x%02X expected 0x%02X" % (
                b201, bce00, bce01, got, exp))
            sys.exit(1)

    print("OK  calibration_apply_4B770 @0x%04X  (%d targeted + %d random)" % (
        ENTRY, len(interesting) ** 3, N))
    sys.exit(0)


if __name__ == '__main__':
    main()
