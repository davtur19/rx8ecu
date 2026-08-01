#!/usr/bin/env python3
"""
Verify obd_dtc_find_0x643D4 (0x643D4) against the ACTUAL ROM bytes, run
in the SH-2E emulator.

Search leaf, takes r4 (16-bit key).  Seeds all 21 DTC table rows' words and
byte-0x06 fields plus the active row index, then compares the ROM's return:

  for i in 0..0x14:
    p = 0xFFFF8930 + i * 0x34
    if word@p == (r4 & 0xFFFF) and i != word@0xFFFF8D74:
        return s8(byte@p+0x06)
  return 0

C:
  int32_t obd_dtc_find_0x643D4(uint32_t r4)

Run from repo root:  python3 c/tests/test_obd_dtc_find_0x643D4.py [N]
"""
import os, sys, random

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0x00643D4

BASE = 0xFFFF8930
STRIDE = 0x34
ROWS = 0x15
CURROW = 0xFFFF8D74


def s8(x):
    x &= 0xFF
    return x - 256 if x & 0x80 else x


def addr(row, off):
    return (BASE + row * STRIDE + off) & 0xFFFFFFFF


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)

    def run_one(r4, words, b06s, currow):
        ram = {CURROW: (currow >> 8) & 0xFF, CURROW + 1: currow & 0xFF}
        for i in range(ROWS):
            w = words[i]
            ram[addr(i, 0)] = (w >> 8) & 0xFF
            ram[addr(i, 1)] = w & 0xFF
            ram[addr(i, 0x06)] = b06s[i]
        cpu.call(ENTRY, r4=r4, ram=ram)
        return cpu.r[0] & 0xFFFFFFFF

    def model(r4, words, b06s, currow):
        key = r4 & 0xFFFF
        for i in range(ROWS):
            if (words[i] & 0xFFFF) == key and i != currow:
                return s8(b06s[i]) & 0xFFFFFFFF
        return 0

    # Targeted: single-row hit at every index, plus current-row skip.
    for i in range(ROWS):
        words = [0] * ROWS
        b06s = [0] * ROWS
        words[i] = 0x1234
        b06s[i] = 0xAB
        # hit row i, currow elsewhere -> s8(0xAB) = -85
        got = run_one(0x1234, words, b06s, (i + 1) % ROWS)
        exp = model(0x1234, words, b06s, (i + 1) % ROWS)
        if got != exp:
            print("FAIL: hit row %d -> 0x%X expected 0x%X" % (i, got, exp)); sys.exit(1)
        # same row is current row -> skipped -> 0
        got = run_one(0x1234, words, b06s, i)
        exp = model(0x1234, words, b06s, i)
        if got != exp:
            print("FAIL: row %d current-row skip -> 0x%X expected 0x%X" % (i, got, exp)); sys.exit(1)

    # Random.
    for _ in range(N):
        r4 = random.randint(0, 0xFFFF)
        currow = random.randint(0, 0x14)
        words = [random.randint(0, 0xFFFF) for _ in range(ROWS)]
        b06s = [random.randint(0, 255) for _ in range(ROWS)]
        got = run_one(r4, words, b06s, currow)
        exp = model(r4, words, b06s, currow)
        if got != exp:
            print("FAIL: r4=%04X currow=%d -> 0x%X expected 0x%X" % (r4, currow, got, exp))
            sys.exit(1)

    print("OK  obd_dtc_find_0x643D4 @0x%04X  (targeted + %d random)" % (ENTRY, N))
    sys.exit(0)


if __name__ == '__main__':
    main()
