#!/usr/bin/env python3
"""
Verify can_encode_handler_62ABC (0x62ABC) against the ACTUAL ROM bytes,
run in the SH-2E emulator.  The emulator executes the real 0x648B4 and
0x2420 bodies too, so this covers the full call chain.

DTC mode-dispatch leaf: reads the per-DTC mode byte at
0xFFFF8D7C + (dtc & 0xFFFF)*2 and, for selected mode values, calls the
run-sum leaf 0x648B4(r5) which folds r5 into the two 16-bit cells
0xFFFF8E98 / 0xFFFF8E9A (each stored as enc8(x) = (x<<8) | ~x):

  mode = byte@(0xFFFF8D7C + (dtc & 0xFFFF) * 2)
  vl   = r5 & 0xFF

  mode == 0x00          -> run_sum(r5)
  mode == 0x10          -> run_sum(r5) iff vl == 0x20 or vl == 0x11
  mode == 0x11          -> run_sum(r5) iff vl == 0x20
  mode == 0x20 (or other) -> no write

C:
  void can_encode_handler_62ABC(uint32_t dtc, uint32_t r5)

dtc is restricted to 0..0x7F so the mode-table read (max 0xFFFF8E7A) stays
clear of the run-sum cells at 0xFFFF8E98/0xFFFF8E9A — a test-only bound,
mirroring how the DTC-table tests pin rows 0..0x14.

Run from repo root:  python3 c/tests/test_can_encode_handler_62ABC.py [N]
"""
import os, sys, random

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0x0062ABC

MODE = 0xFFFF8D7C   # per-DTC mode dispatch table (byte, stride 2)
A = 0xFFFF8E98      # word: run-sum cell 1
B = 0xFFFF8E9A      # word: run-sum cell 2


def s8(x):
    x &= 0xFF
    return x - 256 if x & 0x80 else x


def enc8(x):
    x &= 0xFF
    return ((x << 8) | (~x & 0xFF)) & 0xFFFF


def run_sum(v, wa, wb):
    """Python port of the 0x648B4 leaf."""
    ba, bb = (wa >> 8) & 0xFF, (wb >> 8) & 0xFF
    b = v & 0xFF
    s = (s8(ba) + s8(bb) - s8(b)) & 0xFF
    return enc8(s), enc8(b)


def model(dtc, v, mode, wa, wb):
    vl = v & 0xFF
    call = 0
    if mode == 0x00:
        call = 1
    elif mode == 0x10:
        call = (vl == 0x20 or vl == 0x11)
    elif mode == 0x11:
        call = (vl == 0x20)
    # mode == 0x20 or anything else: no call
    if call:
        return run_sum(v, wa, wb)
    return wa, wb


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)

    def run_one(dtc, v, mode, wa, wb):
        maddr = (MODE + ((dtc & 0xFFFF) << 1)) & 0xFFFFFFFF
        ram = {maddr: mode,
               A: (wa >> 8) & 0xFF, A + 1: wa & 0xFF,
               B: (wb >> 8) & 0xFF, B + 1: wb & 0xFF}
        cpu.call(ENTRY, r4=dtc, r5=v, ram=ram)
        na = (cpu.ram.get(A, 0) << 8) | cpu.ram.get(A + 1, 0)
        nb = (cpu.ram.get(B, 0) << 8) | cpu.ram.get(B + 1, 0)
        return na, nb

    # Targeted: every mode x {calling/non-calling v values}.
    vvals = [0x00, 0x01, 0x11, 0x1F, 0x20, 0x21, 0x7F, 0x80, 0xFF]
    for mode in (0x00, 0x10, 0x11, 0x20, 0x21, 0x7F, 0xFF):
        for v in vvals:
            wa, wb = 0x1234, 0x9ABC
            got = run_one(0x12, v, mode, wa, wb)
            exp = model(0x12, v, mode, wa, wb)
            if got != exp:
                print("FAIL: mode=%02X v=%02X -> %s expected %s" % (mode, v, got, exp))
                sys.exit(1)

    # Random.
    rng = random.Random(0x62ABC)
    modes = [0x00, 0x10, 0x11, 0x20, 0x21, 0x7F, 0xFF]
    for _ in range(N):
        dtc = rng.randint(0, 0x7F)     # mode read stays clear of run-sums
        v = rng.randint(0, 0xFFFFFFFF)
        mode = rng.choice(modes)
        wa, wb = rng.randint(0, 0xFFFF), rng.randint(0, 0xFFFF)
        got = run_one(dtc, v, mode, wa, wb)
        exp = model(dtc, v, mode, wa, wb)
        if got != exp:
            print("FAIL: dtc=%02X v=%08X mode=%02X (wa,wb)=(%04X,%04X) -> "
                  "%s expected %s" % (dtc, v, mode, wa, wb, got, exp))
            sys.exit(1)

    print("OK  can_encode_handler_62ABC @0x%04X  (targeted + %d random)"
          % (ENTRY, N))
    sys.exit(0)


if __name__ == '__main__':
    main()
