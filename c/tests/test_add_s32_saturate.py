#!/usr/bin/env python3
"""
Verify addS32Saturate (0x2304) against the ACTUAL ROM bytes, run in the
SH-2E emulator.  IDA labels this `fpu_compare_float`, but the code is a
saturating signed 32-bit add built on the SH-2 `addv` instruction
(0x354F = addv r4,r5) — no FPU anywhere.  Returns r0.

C:
  int32_t addS32Saturate(int32_t a, int32_t b)   // a=r4, b=r5, -> r0

Run from repo root:  python3 c/tests/test_add_s32_saturate.py [N]
"""
import os, sys, random

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0x2304

def ref(a, b):
    """Saturating signed 32-bit add."""
    sa = a - (1 << 32) if a & 0x80000000 else a
    sb = b - (1 << 32) if b & 0x80000000 else b
    s = sa + sb
    if s > 0x7FFFFFFF: return 0x7FFFFFFF
    if s < -0x80000000: return 0x80000000
    return s & 0xFFFFFFFF

def test_add_s32_saturate(cpu, N):
    for _ in range(N):
        a = random.randint(0, 0xFFFFFFFF)
        b = random.randint(0, 0xFFFFFFFF)
        result = cpu.call(ENTRY, r4=a, r5=b)
        expected = ref(a, b)
        if result != expected:
            return (a, b, result, expected)
    return None

def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)

    edge_cases = [
        (0x00000000, 0x00000000),
        (0x00000001, 0x00000001),
        (0x7FFFFFFF, 0x00000000),
        (0x7FFFFFFF, 0x00000001),   # positive overflow
        (0x7FFFFFFF, 0x7FFFFFFF),   # positive overflow
        (0x80000000, 0x00000000),
        (0x80000000, 0xFFFFFFFF),   # negative overflow (-2^31 + -1)
        (0xFFFFFFFF, 0xFFFFFFFF),   # negative overflow
        (0x7FFFFFFF, 0xFFFFFFFF),   # 0x7FFFFFFF + -1 = 0x7FFFFFFE
        (0x80000000, 0x80000000),   # negative overflow
        (0x40000000, 0x40000000),   # 0x80000000 exact
        (0xC0000000, 0x40000000),   # 0x00000000
        (0xABCDEF01, 0x12345678),
        (0xDEADBEEF, 0xCAFEBABE),
    ]
    for a, b in edge_cases:
        result = cpu.call(ENTRY, r4=a, r5=b)
        expected = ref(a, b)
        if result != expected:
            print("FAIL EDGE: a=0x%08X b=0x%08X -> result=0x%08X expected=0x%08X" % (a, b, result, expected))
            sys.exit(1)

    err = test_add_s32_saturate(cpu, N)
    if err:
        a, b, result, expected = err
        print("FAIL: a=0x%08X b=0x%08X -> result=0x%08X expected=0x%08X" % (a, b, result, expected))
        sys.exit(1)
    print("OK  addS32Saturate @0x%04X  (%d edge + %d random inputs)" % (ENTRY, len(edge_cases), N))
    sys.exit(0)

if __name__ == '__main__':
    main()
