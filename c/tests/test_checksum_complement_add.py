#!/usr/bin/env python3
"""
Verify checksum_complement_add (0x2034) against the ACTUAL ROM bytes, run
in the SH-2E emulator.  Computes the residual of a 32-bit redundant-storage
cell:  (~value - (value>>16)) & 0xFFFF.  Returns 0 when the pair is valid.

C:
  uint16_t checksum_complement_add(uint32_t value)

ROM: 0x2034  (7 instructions, 14 bytes)
  mov.l @r4,r3   ; r3 = *r4  (0x2034)
  mov r3,r0      ; r0 = r3
  shlr16 r3      ; r3 >>= 16
  not r0,r0      ; r0 = ~r0
  sub r3,r0      ; r0 = r0 - r3
  rts
  extu.w r0,r0   ; (delay) r0 &= 0xFFFF

Run from repo root:  python3 c/tests/test_checksum_complement_add.py [N]
"""
import os, sys, random

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0x2034

def ref(val):
    """Python reference for checksum_complement_add."""
    # r0 = ~val (32-bit), r3 = val >> 16, r0 = r0 - r3, r0 &= 0xFFFF
    return ((~val & 0xFFFFFFFF) - (val >> 16)) & 0xFFFF

def test_checksum_complement_add(cpu, N):
    """Verify checksum_complement_add @0x2034 against Python reference."""
    for _ in range(N):
        val = random.randint(0, 0xFFFFFFFF)
        # The function reads *r4 (a 32-bit value from memory)
        # So we pass a POINTER to the value, and place the value at that address
        # In the SH2 calling convention, r4 is the pointer
        result = cpu.call(ENTRY, r4=0x2000, ram={0x2000: (val >> 24) & 0xFF,
                                                 0x2001: (val >> 16) & 0xFF,
                                                 0x2002: (val >> 8) & 0xFF,
                                                 0x2003: val & 0xFF})
        expected = ref(val)
        if result != expected:
            return (val, result, expected)
    return None

def test_edge_cases(cpu):
    """Test known edge cases including encoded valid pairs."""
    edges = [
        # (value, expected_residual)
        (0x00000000, 0xFFFF),
        (0xFFFFFFFF, 0x0001),
        (0x1234ABCD, 0x41FE),
        (0x7FFFFFFF, 0x8001),
        (0x80000000, 0x7FFF),
        (0xAAAA5555, 0x0000),  # happens to produce 0
    ]
    # Also test: every valid (data << 16) | ~data pair should yield 0
    for data16 in [0x0000, 0x0001, 0x7FFF, 0x8000, 0xFFFF, 0x1234, 0xABCD]:
        encoded = ((data16 & 0xFFFF) << 16) | ((~data16) & 0xFFFF)
        edges.append((encoded, 0x0000))
    
    for val, exp in edges:
        result = cpu.call(ENTRY, r4=0x2000, ram={0x2000: (val >> 24) & 0xFF,
                                                 0x2001: (val >> 16) & 0xFF,
                                                 0x2002: (val >> 8) & 0xFF,
                                                 0x2003: val & 0xFF})
        if result != exp:
            return (val, result, exp)
    return None

def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    
    err = test_edge_cases(cpu)
    if err:
        val, result, expected = err
        print("FAIL (edge): val=0x%08X → result=0x%04X expected=0x%04X" % (val, result, expected))
        sys.exit(1)
    
    err = test_checksum_complement_add(cpu, N)
    if err:
        val, result, expected = err
        print("FAIL: val=0x%08X → result=0x%04X expected=0x%04X" % (val, result, expected))
        sys.exit(1)
    else:
        print("OK  checksum_complement_add @0x%04X  (%d random inputs + %d edge cases)" % (ENTRY, N, 6+6))
        sys.exit(0)

if __name__ == '__main__':
    main()
