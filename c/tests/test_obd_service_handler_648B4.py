#!/usr/bin/env python3
"""
Verify obd_service_handler_648B4 (0x648B4) against the ACTUAL ROM bytes,
run in the SH-2E emulator.

Run-sum update leaf over the two redundant 16-bit cells 0xFFFF8E98 /
0xFFFF8E9A.  Each cell holds a byte b as the (value,complement) pair
enc8(b) = (b << 8) | ~b  (the 0x2420 encoder):

  b   = r4 & 0xFF
  sum = (s8(byte@0xFFFF8E98) + s8(byte@0xFFFF8E9A) - s8(b)) & 0xFF
  word@0xFFFF8E98 = enc8(sum)
  word@0xFFFF8E9A = enc8(b)

The high byte of each word is the stored value; mov.b reads are
sign-extended; enc8 only keeps the low byte of its argument.

C:
  void obd_service_handler_648B4(uint32_t r4)

Run from repo root:  python3 c/tests/test_obd_service_handler_648B4.py [N]
"""
import os, sys, random

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0x00648B4

A = 0xFFFF8E98   # word: first run-sum cell
B = 0xFFFF8E9A   # word: second run-sum cell


def s8(x):
    x &= 0xFF
    return x - 256 if x & 0x80 else x


def enc8(x):
    x &= 0xFF
    return ((x << 8) | (~x & 0xFF)) & 0xFFFF


def model(r4, wa, wb):
    """Python port of the ROM leaf.  wa/wb = current cell words."""
    ba, bb = (wa >> 8) & 0xFF, (wb >> 8) & 0xFF
    b = r4 & 0xFF
    s = (s8(ba) + s8(bb) - s8(b)) & 0xFF
    return enc8(s), enc8(b)


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)

    def run_one(r4, wa, wb):
        ram = {A: (wa >> 8) & 0xFF, A + 1: wa & 0xFF,
               B: (wb >> 8) & 0xFF, B + 1: wb & 0xFF}
        cpu.call(ENTRY, r4=r4, ram=ram)
        na = (cpu.ram.get(A, 0) << 8) | cpu.ram.get(A + 1, 0)
        nb = (cpu.ram.get(B, 0) << 8) | cpu.ram.get(B + 1, 0)
        return na, nb

    # Targeted: corner r4/bytes.
    vals = [0x00, 0x01, 0x7F, 0x80, 0xFE, 0xFF]
    for r4 in vals:
        for wa in [0x0000, 0x00FF, 0x7F80, 0x807F, 0xFFFF, 0xFF00]:
            for wb in [0x0000, 0x00FF, 0x7F80, 0x807F, 0xFFFF, 0xFF00]:
                got = run_one(r4, wa, wb)
                exp = model(r4, wa, wb)
                if got != exp:
                    print("FAIL: r4=%02X wa=%04X wb=%04X -> %s expected %s"
                          % (r4, wa, wb, got, exp))
                    sys.exit(1)

    rng = random.Random(0x648B4)
    for _ in range(N):
        r4 = rng.randint(0, 0xFFFFFFFF)
        wa, wb = rng.randint(0, 0xFFFF), rng.randint(0, 0xFFFF)
        got = run_one(r4, wa, wb)
        exp = model(r4, wa, wb)
        if got != exp:
            print("FAIL: r4=%08X wa=%04X wb=%04X -> %s expected %s"
                  % (r4, wa, wb, got, exp))
            sys.exit(1)

    print("OK  obd_service_handler_648B4 @0x%04X  (targeted + %d random)"
          % (ENTRY, N))
    sys.exit(0)


if __name__ == '__main__':
    main()
