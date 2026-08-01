#!/usr/bin/env python3
"""
Test complement_shift_u32 (0x2440) via SH-2E emulator.

Returns 1 when |threshold - value| > adjustment (outside deadband).
Returns 0 when |threshold - value| <= adjustment (inside deadband).
"""
import os, sys, random
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'tools'))
from sh2emu import SH2

ROM = os.path.join(os.path.dirname(__file__), '..', '..', 'roms', 'stock', '60E1D400.bin')

def call_rom(threshold, value, adjustment, cpu):
    """Call ROM function at 0x2440 via emulator."""
    return cpu.call(0x2440, r4=0, ram={}, fr={4: threshold, 5: value, 6: adjustment})

def main():
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    
    tests = 0
    fails = 0
    
    # Known test cases
    cases = [
        # (threshold, value, adjustment, expected_description)
        (0.0, 0.0, 1.0, "|0| <= 1 -> inside -> 0"),
        (2.0, 0.0, 1.0, "|2| > 1 -> outside -> 1 (above)"),
        (-2.0, 0.0, 1.0, "|-2| > 1 -> outside -> 1 (below)"),
        (1.0, 0.0, 1.0, "|1| > 1 -> outside -> 1 (exact boundary)"),
        (-1.0, 0.0, 1.0, "|-1| > 1 -> outside -> 1 (exact boundary)"),
        (0.5, 0.0, 1.0, "|0.5| <= 1 -> inside -> 0"),
        (-0.5, 0.0, 1.0, "|-0.5| <= 1 -> inside -> 0"),
        (5.0, 3.0, 2.0, "|5-3|=2 -> !> 2 -> inside -> 0"),
        (5.0, 3.0, 1.5, "|5-3|=2 > 1.5 -> outside -> 1"),
        (1.0, 3.0, 1.5, "|1-3|=2 > 1.5 -> outside -> 1"),
    ]
    
    for threshold, value, adj, desc in cases:
        tests += 1
        result = call_rom(threshold, value, adj, cpu)
        expected = 1 if abs(threshold - value) > adj else 0
        if result != expected:
            print(f"FAIL: |{threshold}-{value}|={abs(threshold-value)} vs adj={adj}: "
                  f"expected {expected} got {result} ({desc})")
            fails += 1
    
    # Random verification
    random.seed(12345)
    for _ in range(500):
        threshold  = random.uniform(-100, 100)
        value      = random.uniform(-100, 100)
        adjustment = random.uniform(0, 50)
        tests += 1
        result = call_rom(threshold, value, adjustment, cpu)
        expected = 1 if abs(threshold - value) > adjustment else 0
        if result != expected:
            print(f"FAIL: threshold={threshold} value={value} adj={adjustment} -> {result} exp {expected}")
            fails += 1
    
    # Negative adjustment tests: the function returns 0 only if
    # value-adj <= threshold <= value+adj. For adj < 0:
    # value-adj > value+adj (reversed), so |threshold-value| > 0 always,
    # the function returns 1 always for non-zero adj.
    for _ in range(200):
        threshold  = random.uniform(-50, 50)
        value      = random.uniform(-50, 50)
        adjustment = -random.uniform(0.1, 20)
        tests += 1
        result = call_rom(threshold, value, adjustment, cpu)
        expected = 1  # For negative adj, value-adj > value+adj → always outside
        if result != expected:
            print(f"FAIL(neg adj): threshold={threshold} value={value} adj={adjustment} -> {result} exp {expected}")
            fails += 1
    
    print(f"complement_shift_u32: {tests} tests, {fails} failures")
    return 0 if fails == 0 else 1

if __name__ == '__main__':
    sys.exit(main())
