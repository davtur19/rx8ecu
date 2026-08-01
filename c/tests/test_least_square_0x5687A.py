#!/usr/bin/env python3
"""
Verify least_square_0x5687A (0x05687A) against the ACTUAL ROM bytes, run
in the SH-2E emulator.  Compares input byte against stored reference at
0xFFFFD20B, returns 0 if equal, 1 if different.

C:
  uint32_t least_square_0x5687A(uint8_t val)

Run from repo root:  python3 c/tests/test_least_square_0x5687A.py [N]
"""
import os, sys, random

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0x05687A
REF_ADDR = 0xFFFFD20B

def test_least_square(cpu, N):
    """Test with varying RAM state (the ref byte at 0xFFFFD20B)."""
    for _ in range(N):
        ref_byte = random.randint(0, 0xFF)
        val = random.randint(0, 0xFF)
        ram = {REF_ADDR: ref_byte}
        result = cpu.call(ENTRY, r4=val, ram=ram)
        expected = 1 if val != ref_byte else 0
        if result != expected:
            return (val, ref_byte, result, expected)
    return None

def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)

    # Test all 256 values against a known ref byte
    for ref_byte in [0x00, 0x01, 0x7F, 0x80, 0xFF]:
        for val in range(256):
            ram = {REF_ADDR: ref_byte}
            result = cpu.call(ENTRY, r4=val, ram=ram)
            expected = 1 if val != ref_byte else 0
            if result != expected:
                print("FAIL: val=0x%02X ref=0x%02X → %d expected %d" % (val, ref_byte, result, expected))
                sys.exit(1)

    # Random tests
    err = test_least_square(cpu, N)
    if err:
        val, ref_byte, result, expected = err
        print("FAIL: val=0x%02X ref=0x%02X → %d expected %d" % (val, ref_byte, result, expected))
        sys.exit(1)
    else:
        print("OK  least_square_0x5687A @0x%04X  (all 256×5 + %d random)" % (ENTRY, N))
        sys.exit(0)

if __name__ == '__main__':
    main()
