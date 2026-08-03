#!/usr/bin/env python3
"""
test_sensorADCRead_68A8.py — BLOCKED (TODO): differential test of
sensorADCRead @0x68A8 (lift: c/coolant_temperature_sensor.c).

STATUS: NOT TESTABLE with the ROM emulator — hardware-bound busy-wait.

Why blocked (evidence):
  Running the real ROM bytes in tools/sh2emu.py raises
      RuntimeError: runaway at 0x6908
  i.e. the function never returns.

Analysis (disasm 0x68A8..0x69A6):
  0x68A8..0x68EA  Configure the on-chip A/D converter: writes command bytes
                  to the peripheral registers at 0xFFFFF818/0xFFFFF819,
                  0xFFFFF838/0xFFFFF839 and 0xFFFFF858/0xFFFFF859
                  (0x33 / 0x2B), clearing bit 0x20 and starting conversions.
  0x68EE..0x6902  Seed diagnostic sentinels at 0xFFFF9F27..0xFFFF9F29.
  0x6906..0x690C  LOOP: wait until (byte[0xFFFFF818] & 0x80) != 0
  0x6910..0x6918  LOOP: wait until (byte[0xFFFFF838] & 0x80) != 0
  0x691A..0x6922  LOOP: wait until (byte[0xFFFFF858] & 0x80) != 0
                  These three loops are conversion-complete polls.  The
                  function itself wrote 0x33/0x2B (bit 0x80 clear) into the
                  flag registers, so the ONLY thing that can release the
                  loops is the A/D hardware setting bit 0x80 on completion.
                  tools/sh2emu.py has no MMIO model, so the flag never
                  changes -> the emulator spins until its 500k-step runaway
                  guard trips at 0x6908.
  0x6924..0x69A6  (unreachable in the emulator) reads 17 result words from
                  0xFFFFF800..0xFFFFF83E and copies them to 0xFFFF9EE4..,
                  returning the first channel value in r0.

A correct differential test would need a mock A/D peripheral that sets the
flag bits after the start command (e.g. an MMIO hook in the emulator core) —
out of scope for this emulator-only harness.  Revisit if a hardware-model
mode is added to tools/sh2emu.py.

Exit code is intentionally non-zero: this lift is NOT verified.

Run from repo root:  python3 c/tests/test_sensorADCRead_68A8.py
"""
import sys

if __name__ == '__main__':
    print("BLOCKED sensorADCRead @0x68A8: busy-waits on hardware A/D"
          " conversion-complete flags (bit 0x80 of 0xFFFFF818/0xFFFFF838/"
          "0xFFFFF858) that the ROM emulator cannot satisfy"
          " (RuntimeError: runaway at 0x6908).")
    print("TODO sensorADCRead @0x68A8: needs an MMIO/A-D mock in the emulator;"
          " not verified.")
    sys.exit(2)