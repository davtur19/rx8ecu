#!/usr/bin/env python3
"""
Verify calledLots (0xA486) — byte counter with saturation guard.

Disassembly of the ROM function (60E1D400.bin):
  1. store the index argument (low word) on the stack
  2. call dispatch 0x3920 -> 0x2054 (subsystem init/get-ptr; side effect free here)
  3. compute byte address = base_ptr + index, base_ptr = dword literal @0xA574
     = 0xFFFFA18B
  4. read the byte; if byte < 0xFF (threshold word @0xA560 = 0x00FF), increment
     it and write it back (saturation guard — no wrap past 0xFF)
  5. call dispatch 0x3920 -> 0x2064 (finalize)

Behaviour: calledLots(index) increments RAM byte[0xFFFFA18B + index] with a
saturation guard at 0xFF, and returns the index argument (r0 is left holding
the reloaded index word).

This test compares the emulator output against a Python model for a set of
edge cases plus N random (index, initial-byte) states, and exits non-zero on
any mismatch.

Run from repo root:  python3 c/tests/test_calledLots.py [N]
"""
import os, sys, random

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0xA486
# Base pointer dword literal @0xA574 and saturation threshold word @0xA560 are
# read out of the ROM so the test model always tracks the real bytes.
BASE_LIT = 0xA574
THRESH_LIT = 0xA560


def model(byte, index):
    """(new_byte, return_value) for one call with the given initial byte."""
    new = byte + 1 if byte < 0xFF else byte
    return new, index & 0xFFFFFFFF


def run_one(cpu, base, index, byte):
    r = cpu.call(ENTRY, r4=index, ram={base + index: byte})
    return r, cpu.ram.get(base + index)


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    if not os.path.exists(ROM):
        print("FAIL: ROM not found: %s" % ROM)
        sys.exit(1)
    rom = open(ROM, 'rb').read()
    base = int.from_bytes(rom[BASE_LIT:BASE_LIT + 4], 'big')
    thr = int.from_bytes(rom[THRESH_LIT:THRESH_LIT + 2], 'big')
    cpu = SH2(rom)
    rng = random.Random(0xA486)
    fails = 0

    # index bounds: keep base+index inside the high-RAM overlay (>= 0xFFFF8000)
    # so the byte slot is pure RAM, never aliasing the ROM image.
    assert 0xFFFF8000 <= base + 0xFF, "test bounds assume high-RAM slot"

    # edge cases (fresh slot, one below threshold, at threshold = saturation)
    edges = [(0, 0x00), (1, 0x00), (0x7F, 0x00), (0xFF, 0x00),
             (2, thr - 1), (3, thr), (4, 0x7F)]
    for index, start in edges:
        try:
            got_r, got_b = run_one(cpu, base, index, start)
        except Exception as e:
            print("FAIL edge idx=0x%02X start=0x%02X: emulator raised %s: %s"
                  % (index, start, type(e).__name__, e))
            fails += 1
            continue
        exp_b, exp_r = model(start, index)
        if got_r != exp_r or got_b != exp_b:
            print("FAIL edge idx=0x%02X start=0x%02X: r0=0x%08X byte=0x%02X "
                  "expected r0=0x%08X byte=0x%02X"
                  % (index, start, got_r, got_b, exp_r, exp_b))
            fails += 1

    for _ in range(N):
        index = rng.randrange(0, 0x100)
        start = rng.randrange(0x100)
        try:
            got_r, got_b = run_one(cpu, base, index, start)
        except Exception as e:
            print("FAIL random idx=0x%02X start=0x%02X: emulator raised %s: %s"
                  % (index, start, type(e).__name__, e))
            fails += 1
            continue
        exp_b, exp_r = model(start, index)
        if got_r != exp_r or got_b != exp_b:
            print("FAIL random idx=0x%02X start=0x%02X: r0=0x%08X byte=0x%02X "
                  "expected r0=0x%08X byte=0x%02X"
                  % (index, start, got_r, got_b, exp_r, exp_b))
            fails += 1

    if fails:
        print("FAIL: %d/%d states mismatched" % (fails, N + len(edges)))
        sys.exit(1)
    print("OK  calledLots @0x%04X (base=0x%08X thr=0x%04X; %d edge + %d random states)"
          % (ENTRY, base, thr, len(edges), N))
    sys.exit(0)


if __name__ == '__main__':
    main()
