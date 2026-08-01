#!/usr/bin/env python3
"""
Verify the request-queue leaves (0x69602 store / 0x69694 clear) against the
ACTUAL ROM bytes, run in the SH-2E emulator.

  0x69602  store(r4, r5):
            b = r4 & 0xFF
            long@(0xFFFFDE40 + b*4) = (uint32)(r5 * 0x0FA0) + long@0xFFFFF430
            byte@(0xFFFFDE38 + b)   = 1
  0x69694  clear(r4):
            byte@(0xFFFFDE38 + (r4 & 0xFF)) = 0

C:
  void req_queue_store_69602(uint32_t r4, uint32_t r5)
  void req_queue_clear_69694(uint32_t r4)

Run from repo root:  python3 c/tests/test_req_queue_69602.py [N]
"""
import os, sys, random

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
STORE = 0x0069602
CLEAR = 0x0069694

FLAGS = 0xFFFFDE38
VALUES = 0xFFFFDE40
BASE = 0xFFFFF430


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 4000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)

    def long_at(a):
        return ((cpu.ram.get(a, 0) << 24) | (cpu.ram.get(a + 1, 0) << 16) |
                (cpu.ram.get(a + 2, 0) << 8) | cpu.ram.get(a + 3, 0)) & 0xFFFFFFFF

    # ---- store: all 256 indices, varied base + r5 ----
    for b in range(256):
        basev = random.randint(0, 0xFFFFFFFF)
        r5 = random.randint(0, 0xFFFFFFFF)
        ram = {}
        for i in range(4):
            ram[BASE + i] = (basev >> (24 - 8 * i)) & 0xFF
        ram[FLAGS + b] = 0
        cpu.call(STORE, r4=b, r5=r5, ram=ram)
        va = VALUES + b * 4
        exp = ((r5 & 0xFFFFFFFF) * 0x0FA0 + basev) & 0xFFFFFFFF
        got = long_at(va)
        if got != exp:
            print("FAIL store: b=%d r5=%08X base=%08X got %08X expected %08X"
                  % (b, r5, basev, got, exp)); sys.exit(1)
        if cpu.ram.get(FLAGS + b, -1) != 1:
            print("FAIL store flag: b=%d" % b); sys.exit(1)

    # ---- clear: all 256 indices ----
    for b in range(256):
        ram = {FLAGS + b: 1}
        cpu.call(CLEAR, r4=b, ram=ram)
        if cpu.ram.get(FLAGS + b, -1) != 0:
            print("FAIL clear: b=%d" % b); sys.exit(1)

    # ---- random store/clear interleaved ----
    for _ in range(N):
        b = random.randint(0, 255)
        if random.random() < 0.5:
            basev = random.randint(0, 0xFFFFFFFF)
            r5 = random.randint(0, 0xFFFFFFFF)
            ram = {FLAGS + b: 0}
            for i in range(4):
                ram[BASE + i] = (basev >> (24 - 8 * i)) & 0xFF
            cpu.call(STORE, r4=b, r5=r5, ram=ram)
            exp = ((r5 & 0xFFFFFFFF) * 0x0FA0 + basev) & 0xFFFFFFFF
            got = long_at(VALUES + b * 4)
            if got != exp or cpu.ram.get(FLAGS + b) != 1:
                print("FAIL random store: b=%d" % b); sys.exit(1)
        else:
            ram = {FLAGS + b: random.randint(0, 255)}
            cpu.call(CLEAR, r4=b, ram=ram)
            if cpu.ram.get(FLAGS + b) != 0:
                print("FAIL random clear: b=%d" % b); sys.exit(1)

    print("OK  req_queue 0x69602/0x69694  (all 256 indices + %d random)" % N)
    sys.exit(0)


if __name__ == '__main__':
    main()
