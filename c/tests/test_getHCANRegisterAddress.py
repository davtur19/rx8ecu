#!/usr/bin/env python3
"""
Verify getHCANRegisterAddress (0xD198) — HCAN register addr calculator.
  If idx==0: return base
  Else:      return base + 0x200

Test all index values 0..255 with a known base.
"""
import os, sys, random

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0xD198

def ref(base, idx):
    return base if idx == 0 else base + 0x200

def test_getHCANRegisterAddress():
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)

    # Test boundary values
    for idx in [0, 1, 2, 0x7F, 0xFF]:
        base = 0x12345678
        result = cpu.call(ENTRY, r4=idx, r5=base)
        expected = ref(base, idx)
        if result != expected:
            print("FAIL: idx=%d → result=0x%08X expected=0x%08X" % (idx, result, expected))
            return False
        print("OK  idx=%d → 0x%08X" % (idx, result))

    # Random tests
    for _ in range(100):
        idx = random.randint(0, 255)
        base = random.randint(0, 0xFFFFF000)
        result = cpu.call(ENTRY, r4=idx, r5=base)
        expected = ref(base, idx)
        if result != expected:
            print("FAIL: random: idx=%d base=0x%08X → result=0x%08X expected=0x%08X" % (idx, base, result, expected))
            return False

    print("OK  getHCANRegisterAddress @0x%04X  (all tests)" % ENTRY)
    return True

def main():
    if test_getHCANRegisterAddress():
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == '__main__':
    main()
