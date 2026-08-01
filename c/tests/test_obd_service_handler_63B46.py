#!/usr/bin/env python3
"""
Verify obd_service_handler_63B46 (0x63B46) against the ACTUAL ROM bytes,
run in the SH-2E emulator.

Debounce-state writer leaf.  Addresses the DTC context-table row selected by
the "current DTC index" word @0xFFFF8928 (base 0xFFFF87D8, 16-byte stride)
and folds r4 into the row's bytes at +0x0D and +0x0E:

  idx = word@0xFFFF8928 & 0xFFFF
  p   = 0xFFFF87D8 + idx*16
  byte@p+0x0E = (s8(byte@p+0x0E) + s8(byte@p+0x0D) - r4) & 0xFF
  byte@p+0x0D = r4 & 0xFF

Returns r0 = r4.

C:
  uint32_t obd_service_handler_63B46(uint32_t r4)

Rows restricted to 0..0x14 (realistic table size: 21 * 16 == 0x150 bytes,
0xFFFF87D8..0xFFFF8928).  Run from repo root:
  python3 c/tests/test_obd_service_handler_63B46.py [N]
"""
import os, sys, random

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0x0063B46

BASE = 0xFFFF87D8
CUR = 0xFFFF8928


def s8(x):
    x &= 0xFF
    return x - 256 if x & 0x80 else x


def model(r4, idx, b0d, b0e):
    return ((s8(b0e) + s8(b0d) - r4) & 0xFF, r4 & 0xFF)


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)

    def run_one(r4, idx, b0d, b0e):
        p = BASE + (idx & 0xFFFF) * 16
        ram = {CUR: (idx >> 8) & 0xFF, CUR + 1: idx & 0xFF,
               p + 0x0D: b0d, p + 0x0E: b0e}
        r = cpu.call(ENTRY, r4=r4, ram=ram)
        return r, cpu.ram.get(p + 0x0D), cpu.ram.get(p + 0x0E)

    # Targeted: corner values on each realistic row.
    vals = [0x00, 0x01, 0x7F, 0x80, 0xFE, 0xFF]
    for idx in range(0x15):
        for r4 in vals:
            for b0d in vals:
                for b0e in vals:
                    got = run_one(r4, idx, b0d, b0e)
                    ne, nd = model(r4, idx, b0d, b0e)
                    exp = (r4 & 0xFFFFFFFF, nd, ne)
                    if got != exp:
                        print("FAIL: r4=%02X idx=%d (b0d,b0e)=(%02X,%02X) -> "
                              "%s expected %s" % (r4, idx, b0d, b0e, got, exp))
                        sys.exit(1)

    # Random: full 32-bit r4, realistic row index.
    rng = random.Random(0x63B46)
    for _ in range(N):
        r4 = rng.randint(0, 0xFFFFFFFF)
        idx = rng.randint(0, 0x14)
        b0d, b0e = rng.randint(0, 0xFF), rng.randint(0, 0xFF)
        got = run_one(r4, idx, b0d, b0e)
        ne, nd = model(r4, idx, b0d, b0e)
        exp = (r4 & 0xFFFFFFFF, nd, ne)
        if got != exp:
            print("FAIL: r4=%08X idx=%d (b0d,b0e)=(%02X,%02X) -> %s expected %s"
                  % (r4, idx, b0d, b0e, got, exp))
            sys.exit(1)

    print("OK  obd_service_handler_63B46 @0x%04X  (targeted + %d random)"
          % (ENTRY, N))
    sys.exit(0)


if __name__ == '__main__':
    main()
