#!/usr/bin/env python3
"""
Verify c/knockSensorADCFault.c behaves exactly like the ROM function @0xC290,
by running the ACTUAL ROM bytes in the SH-2E emulator over every possible ADC value
and comparing to the C lift's logic.

Run from repo root:  python3 c/tests/test_knockSensorADCFault.py
"""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM  = os.path.join(ROOT, 'roms', 'stock', '60E0FC00.bin')
ADDR = 0xC290
ADC  = 0xFFFF9F0E   # knock-sensor ADC sample (RAM)
OUT  = 0xFFFFA325   # fault-code byte (RAM)

rom = open(ROM, 'rb').read()
OPEN = int.from_bytes(rom[0x6D47E:0x6D480], 'big')   # 51249
SHRT = int.from_bytes(rom[0x6D47C:0x6D47E], 'big')   # 16121


def c_lift(adc):
    if adc >= OPEN:
        return 1
    elif adc >= SHRT:
        return 0
    return 2


def main():
    cpu = SH2(rom)
    bad = 0
    for adc in range(0x10000):
        cpu.call(ADDR, ram={ADC: (adc >> 8) & 0xFF, ADC + 1: adc & 0xFF})
        emu = cpu.ram.get(OUT)
        if emu != c_lift(adc):
            bad += 1
            if bad <= 5:
                print("MISMATCH adc=%d emu=%r c=%d" % (adc, emu, c_lift(adc)))
    print("knockSensorADCFault: OPEN=%d SHORT=%d  tested=65536  mismatches=%d  %s"
          % (OPEN, SHRT, bad, "OK" if bad == 0 else "FAIL"))
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
