#!/usr/bin/env python3
"""
Verify obd_dtc_find_0x6443E (0x6443E) against the ACTUAL ROM bytes, run
in the SH-2E emulator.

Search leaf, takes r4 (byte key).  Seeds all 21 DTC table rows' bytes 0x06
and 0x08 plus the active row index, then compares the ROM's return:

  for i in 0..0x14:
    p = 0xFFFF8930 + i * 0x34
    if byte@p+0x06 == (r4 & 0xFF) and i != word@0xFFFF8D74:
        return s8(byte@p+0x08)
  return 0x08

C:
  int32_t obd_dtc_find_0x6443E(uint32_t r4)

Run from repo root:  python3 c/tests/test_obd_dtc_find_0x6443E.py [N]
"""
import os, sys, random

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0x006443E

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

    def run_one(r4, b06s, b08s, currow):
        ram = {CURROW: (currow >> 8) & 0xFF, CURROW + 1: currow & 0xFF}
        for i in range(ROWS):
            ram[addr(i, 0x06)] = b06s[i]
            ram[addr(i, 0x08)] = b08s[i]
        cpu.call(ENTRY, r4=r4, ram=ram)
        return cpu.r[0] & 0xFFFFFFFF

    def model(r4, b06s, b08s, currow):
        key = r4 & 0xFF
        for i in range(ROWS):
            if (b06s[i] & 0xFF) == key and i != currow:
                return s8(b08s[i]) & 0xFFFFFFFF
        return 0x08

    # Targeted: single-row hit at every index, plus current-row skip.
    for i in range(ROWS):
        b06s = [0] * ROWS
        b08s = [0] * ROWS
        b06s[i] = 0x5A
        b08s[i] = 0xC3  # s8 -> -61
        got = run_one(0x5A, b06s, b08s, (i + 1) % ROWS)
        exp = model(0x5A, b06s, b08s, (i + 1) % ROWS)
        if got != exp:
            print("FAIL: hit row %d -> 0x%X expected 0x%X" % (i, got, exp)); sys.exit(1)
        got = run_one(0x5A, b06s, b08s, i)
        exp = model(0x5A, b06s, b08s, i)
        if got != exp:
            print("FAIL: row %d current-row skip -> 0x%X expected 0x%X" % (i, got, exp)); sys.exit(1)

    # Random.
    for _ in range(N):
        r4 = random.randint(0, 0xFF)
        currow = random.randint(0, 0x14)
        b06s = [random.randint(0, 255) for _ in range(ROWS)]
        b08s = [random.randint(0, 255) for _ in range(ROWS)]
        got = run_one(r4, b06s, b08s, currow)
        exp = model(r4, b06s, b08s, currow)
        if got != exp:
            print("FAIL: r4=%02X currow=%d -> 0x%X expected 0x%X" % (r4, currow, got, exp))
            sys.exit(1)

    print("OK  obd_dtc_find_0x6443E @0x%04X  (targeted + %d random)" % (ENTRY, N))
    sys.exit(0)


if __name__ == '__main__':
    main()
