#!/usr/bin/env python3
"""
Verify complement_shift_u16 (0x2430) against the ACTUAL ROM bytes, run
in the SH-2E emulator.  This packs a 16-bit value with its ones' complement
into a 32-bit word (redundant storage encoding).

C:
  uint32_t complement_shift_u16(uint16_t val)
ROM: return ((val & 0xFFFF) << 16) | (~val & 0xFFFF)

Run from repo root:  python3 c/tests/test_complement_shift_u16.py [N]
"""
import os, sys, random

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0x2430

def ref(val):
    """Pure-Python reference for complement_shift_u16."""
    return ((val & 0xFFFF) << 16) | ((~val) & 0xFFFF)

def test_complement_shift_u16(cpu, N):
    """Verify complement_shift_u16 @0x2430 against Python reference."""
    for _ in range(N):
        val = random.randint(0, 0xFFFF)
        result = cpu.call(ENTRY, r4=val)
        expected = ref(val)
        if result != expected:
            return (val, result, expected)
    return None

def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    
    err = test_complement_shift_u16(cpu, N)
    if err:
        val, result, expected = err
        print("FAIL: val=0x%04X → result=0x%08X expected=0x%08X" % (val, result, expected))
        sys.exit(1)
    else:
        print("OK  complement_shift_u16 @0x%04X  (%d random inputs)" % (ENTRY, N))
        sys.exit(0)

if __name__ == '__main__':
    main()
