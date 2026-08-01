#!/usr/bin/env python3
"""
Verify math_min_max_49ED0 (0x49ED0) against the ACTUAL ROM bytes, run
in the SH-2E emulator.

Flag-setter leaf: reads a 16-bit word at RAM 0xFFFFF76C, tests bit 0x100
and writes a 0/1 flag byte to both 0xFFFFCD48 and 0xFFFFCD49.
Returns the flag in r0.

C:
  uint32_t math_min_max_49ED0(void)  // no args; reads 0xFFFFF76C itself

Model:
  v  = (word & 0x100) ? 1 : 0
  byte@0xFFFFCD48 = v; byte@0xFFFFCD49 = v; return v

NOTE: the disassembler prints the mov.w literals as 0xCD49/0xCD48/0xF76C,
but mov.w @(disp,PC) SIGN-EXTENDS (bit 15 set) → real addresses are
0xFFFFCD49/0xFFFFCD48/0xFFFFF76C.

Run from repo root:  python3 c/tests/test_math_min_max_49ED0.py [N]
"""
import os, sys, random

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0x0049ED0

IN_WORD = 0xFFFFF76C  # input  word address (seeded in ram overlay)
OUT_A = 0xFFFFCD48    # output byte A
OUT_B = 0xFFFFCD49    # output byte B


def call_fn(cpu, word):
    """Run the function with word@0xF76C set (big-endian 16-bit)."""
    return cpu.call(ENTRY, ram={
        IN_WORD:     (word >> 8) & 0xFF,   # hi byte
        IN_WORD + 1: word & 0xFF,          # lo byte
    })


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)

    def check(word):
        result = call_fn(cpu, word)
        expected = 1 if (word & 0x0100) else 0
        if result != expected:
            print("FAIL: word 0x%04X -> r0 0x%X expected %d" % (word, result, expected))
            sys.exit(1)
        a = cpu.ram.get(OUT_A, -1)
        b = cpu.ram.get(OUT_B, -1)
        if a != expected or b != expected:
            print("FAIL: word 0x%04X -> 0xCD48=0x%02X 0xCD49=0x%02X expected both 0x%02X" % (
                word, a, b, expected))
            sys.exit(1)

    # Edge cases: bit-0x100 off / on, boundaries, sign bit, all ones.
    for word in [0x0000, 0x0001, 0x00FF, 0x0100, 0x0101, 0x01FF, 0x02FF,
                 0x8000, 0x80FF, 0xFFFF, 0x7F00, 0xFEFF, 0xFF00, 0xFF01]:
        check(word)

    # Random tests.
    for _ in range(N):
        check(random.randint(0, 0xFFFF))

    print("OK  math_min_max_49ED0 @0x%04X  (%d edge + %d random)" % (ENTRY, 14, N))
    sys.exit(0)


if __name__ == '__main__':
    main()
