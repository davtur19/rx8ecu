#!/usr/bin/env python3
"""
Test calc_manifold_pressure_error_clamp_10A5C (0x10A5C) via SH-2E emulator.

Algorithm:
  1. Read raw 8-bit byte from RAM[0xFFFFA5D4]
  2. Scale: raw * 0x1E0000
  3. Subtract input (r4)
  4. Add offset: 0xFFFB0000 (-0x50000)
  5. Signed wrap: if >= 0x02D00000: -= 0x02D00000; if < 0: += 0x02D00000
  6. Return result
"""
import os, sys, random
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'tools'))
from sh2emu import SH2

ROM = os.path.join(os.path.dirname(__file__), '..', '..', 'roms', 'stock', '60E1D400.bin')

def call_rom(byte_val, input_val, cpu):
    """Call ROM function at 0x10A5C via emulator."""
    return cpu.call(0x10A5C, r4=input_val, ram={0xFFFFA5D4: byte_val})

def main():
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    
    tests = 0
    fails = 0
    
    # Known test vectors from emulator ground truth
    vectors = [
        (0x00, 0x00000000, 0x02CB0000),
        (0x00, 0x00100000, 0x02BB0000),
        (0x00, 0x00500000, 0x027B0000),
        (0x00, 0x02000000, 0x00CB0000),
        (0x00, 0xFFFFFFFF, 0x02CB0001),
        (0x01, 0x00000000, 0x00190000),
        (0x01, 0x00100000, 0x00090000),
        (0x01, 0x00500000, 0x02990000),
        (0x01, 0x02000000, 0x00E90000),
        (0x01, 0xFFFFFFFF, 0x00190001),
        (0x10, 0x00000000, 0x01DB0000),
        (0x10, 0x00100000, 0x01CB0000),
        (0x10, 0x00500000, 0x018B0000),
        (0x10, 0x02000000, 0x02AB0000),
        (0x10, 0xFFFFFFFF, 0x01DB0001),
        (0x40, 0x00000000, 0x04AB0000),
        (0x40, 0x00100000, 0x049B0000),
        (0x40, 0x00500000, 0x045B0000),
        (0x40, 0x02000000, 0x02AB0000),
        (0x40, 0xFFFFFFFF, 0x04AB0001),
        (0x80, 0x00000000, 0x0C2B0000),
        (0x80, 0x00100000, 0x0C1B0000),
        (0x80, 0x00500000, 0x0BDB0000),
        (0x80, 0x02000000, 0x0A2B0000),
        (0x80, 0xFFFFFFFF, 0x0C2B0001),
        (0xFF, 0x00000000, 0x1B0D0000),
        (0xFF, 0x00100000, 0x1AFD0000),
        (0xFF, 0x00500000, 0x1ABD0000),
        (0xFF, 0x02000000, 0x190D0000),
        (0xFF, 0xFFFFFFFF, 0x1B0D0001),
    ]
    
    for byte_val, input_val, expected in vectors:
        tests += 1
        result = call_rom(byte_val, input_val, cpu)
        if result != expected:
            print(f"FAIL: byte=0x{byte_val:02X} input=0x{input_val:08X} "
                  f"expected=0x{expected:08X} got=0x{result:08X}")
            fails += 1
    
    # Random verification
    random.seed(9999)
    for _ in range(500):
        byte_val = random.randint(0, 255)
        input_val = random.randint(0, 0xFFFFFFFF)
        tests += 1
        result = call_rom(byte_val, input_val, cpu)
        
        # Compute expected using the known algorithm
        temp = (byte_val * 0x001E0000) - input_val
        temp = (temp + 0xFFFB0000) & 0xFFFFFFFF
        # Signed wrap
        if s32(temp) >= s32(0x02D00000):
            temp = (temp + 0xFD300000) & 0xFFFFFFFF  # -= 0x2D00000
        elif s32(temp) < 0:
            temp = (temp + 0x02D00000) & 0xFFFFFFFF  # += 0x2D00000
        
        if result != temp:
            print(f"FAIL(random): byte=0x{byte_val:02X} input=0x{input_val:08X} "
                  f"expected=0x{temp:08X} got=0x{result:08X}")
            fails += 1
            if fails >= 5:
                break
    
    print(f"calc_manifold_pressure_error_clamp_10A5C: {tests} tests, {fails} failures")
    return 0 if fails == 0 else 1

def s32(x):
    if x & 0x80000000:
        return x - 0x100000000
    return x

if __name__ == '__main__':
    sys.exit(main())
