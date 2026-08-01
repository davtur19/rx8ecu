#!/usr/bin/env python3
"""
Test radiator_fan_relay_write (0x259C0) via SH-2E emulator.

Function under test (60E1D400.bin):
  radiator_fan_relay_write @0x259C0 (40 bytes) - drives the radiator fan
  relay byte RAM[0xFFFFB5AB] from bit 0 of the status byte RAM[0xFFFF9ECD],
  active-low: RAM[0xFFFFB5AB] = (RAM[0xFFFF9ECD] & 1) ? 0 : 1.
"""
import os, sys, random
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'tools'))
from sh2emu import SH2

ROM = os.path.join(os.path.dirname(__file__), '..', '..', 'roms', 'stock', '60E1D400.bin')
ADDR = 0x259C0
INP = 0xFFFF9ECD
OUT = 0xFFFFB5AB

def ref(inp):
    return 0 if (inp & 1) else 1

def main():
    cpu = SH2(open(ROM, 'rb').read())
    random.seed(20260801)
    fails = tests = 0
    inputs = list(range(256)) + [random.randrange(0, 256) for _ in range(3000)]
    for inp in inputs:
        cpu.call(ADDR, ram={INP: inp})
        got = cpu.ram[OUT]
        tests += 1
        if got != ref(inp):
            fails += 1
            print(f"  radiator_fan_relay_write FAIL inp={inp} got={got} exp={ref(inp)}")
            if fails >= 5:
                break
    print(f"radiator_fan_relay_write: {tests} tests, {fails} failures")
    print("RADIATOR_FAN_RELAY_WRITE:", "PASS" if fails == 0 else "FAIL")
    return 0 if fails == 0 else 1

if __name__ == '__main__':
    sys.exit(main())
