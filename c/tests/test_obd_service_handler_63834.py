#!/usr/bin/env python3
"""
Verify obd_service_handler_63834 (0x63834) against the ACTUAL ROM bytes,
run in the SH-2E emulator.

Mode-1 status read leaf over the 21-entry DTC context table
(base 0xFFFF87D8, 16-byte stride, code word @+0, type byte @+6):

  cur = word@0xFFFF8928 & 0xFFFF
  for i in 0..20:
      p = 0xFFFF87D8 + i*16
      if word@p == (r4 & 0xFFFF) and i != cur:
          return s8(byte@p+0x06)     ; sign-extended (mov.b)
  return 0

C:
  int32_t obd_service_handler_63834(uint32_t r4)

Run from repo root:  python3 c/tests/test_obd_service_handler_63834.py [N]
"""
import os, sys, random

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0x0063834

BASE = 0xFFFF87D8
CUR = 0xFFFF8928
COUNT = 21


def s8(x):
    x &= 0xFF
    return x - 256 if x & 0x80 else x


def model(dtc, cur, entries):
    """entries: dict idx -> (code, type6).  Python port of the ROM scan."""
    for i in range(COUNT):
        if i not in entries:
            continue
        code, t6 = entries[i]
        if code == (dtc & 0xFFFF) and i != (cur & 0xFFFF):
            return s8(t6)
    return 0


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)

    def run_one(dtc, cur, entries):
        ram = {CUR: (cur >> 8) & 0xFF, CUR + 1: cur & 0xFF}
        for i, (code, t6) in entries.items():
            p = BASE + i * 16
            ram[p] = (code >> 8) & 0xFF
            ram[p + 1] = code & 0xFF
            ram[p + 6] = t6
        return cpu.call(ENTRY, r4=dtc, ram=ram)

    # Targeted: single-entry table, exact code match in each row, current
    # index == match row (must be skipped) and != match row (must return).
    for row in range(COUNT):
        for t6 in (0x00, 0x01, 0x7F, 0x80, 0xFF):
            # current index skips this row -> 0
            got = run_one(0x1234, row, {row: (0x1234, t6)})
            if got != 0:
                print("FAIL: row=%d skipped, type=%02X -> %d expected 0"
                      % (row, t6, got))
                sys.exit(1)
            # current index elsewhere -> returns s8(type)
            other = (row + 1) % COUNT
            got = run_one(0x1234, other, {row: (0x1234, t6)})
            if got != (s8(t6) & 0xFFFFFFFF):
                print("FAIL: row=%d match, type=%02X -> %d expected %d"
                      % (row, t6, got, s8(t6) & 0xFFFFFFFF))
                sys.exit(1)

    # Random: sparse random tables, random dtc/cur.
    rng = random.Random(0x63834)
    for _ in range(N):
        dtc = rng.randint(0, 0xFFFF)
        cur = rng.randint(0, 0xFFFF)
        entries = {}
        for i in rng.sample(range(COUNT), rng.randint(0, 6)):
            entries[i] = (rng.randint(0, 0xFFFF), rng.randint(0, 0xFF))
        got = run_one(dtc, cur, entries)
        exp = model(dtc, cur, entries) & 0xFFFFFFFF
        if got != exp:
            print("FAIL: dtc=%04X cur=%04X entries=%s -> %d expected %d"
                  % (dtc, cur, entries, got, exp))
            sys.exit(1)

    print("OK  obd_service_handler_63834 @0x%04X  (targeted + %d random)"
          % (ENTRY, N))
    sys.exit(0)


if __name__ == '__main__':
    main()
