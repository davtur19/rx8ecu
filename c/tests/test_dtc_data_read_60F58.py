#!/usr/bin/env python3
"""
Verify dtc_data_read_60F58 (0x060F58) against the ACTUAL ROM bytes, run
in the SH-2E emulator.  This function fills selected 16-bit words in the
DTC status region at 0xFFFFD6C8 with 0xFFFF.

The loop writes every other 16-bit word (step 4 bytes = skip 1 word):
  Base: 0xFFFFD6C8, End: 0xFFFFD6D0
  Write at 0xFFFFD6C8, then 0xFFFFD6CC  (2 writes only, not all 4 words)

C:
  void dtc_data_read_60F58(void)

Run from repo root:  python3 c/tests/test_dtc_data_read_60F58.py [N]
"""
import os, sys, random

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0x060F58

DTC_BASE = 0xFFFFD6C8
DTC_END  = 0xFFFFD6D0

def test_dtc_data_read_60F58(cpu, N):
    """Run the function N times with differing RAM state."""
    for _ in range(N):
        # Pre-fill the DTC region with random data (never 0xFF to detect writes)
        ram_in = {}
        for a in range(DTC_BASE, DTC_END):
            ram_in[a] = random.randint(0, 0xFE)
        cpu.call(ENTRY, ram=ram_in)
        # The function writes with step 4: addresses DTC_BASE and DTC_BASE+4
        # (the lower 16 bits of r5=0x0000FFFF at those addresses)
        written_addrs = [DTC_BASE, DTC_BASE + 4]  # where writes go
        for addr in written_addrs:
            lo = cpu.ram.get(addr, 0xFF)
            hi = cpu.ram.get(addr + 1, 0xFF)
            if lo != 0xFF or hi != 0xFF:
                return (addr, lo, hi)
        # Unwritten addresses should retain original values (0x00-0xFE)
        unwritten = [a for a in range(DTC_BASE, DTC_END) if a not in (DTC_BASE, DTC_BASE+1, DTC_BASE+4, DTC_BASE+5)]
        for addr in unwritten:
            orig = ram_in.get(addr, -1)
            val = cpu.ram.get(addr, -1)
            if orig >= 0 and val != orig:
                return (addr, val, orig)
    return None

def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 500
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)

    err = test_dtc_data_read_60F58(cpu, N)
    if err:
        addr, got, exp = err
        print("FAIL @0x%X: got 0x%02X expected 0x%02X" % (addr, got, exp))
        sys.exit(1)
    else:
        print("OK  dtc_data_read_60F58 @0x%04X  (%d random initial states)" % (ENTRY, N))
        sys.exit(0)

if __name__ == '__main__':
    main()
