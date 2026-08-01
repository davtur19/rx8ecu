#!/usr/bin/env python3
"""
Verify shift_right_arithmetic_r0 (0x43C8) against the ACTUAL ROM bytes, run
in the SH-2E emulator.  Value in r0, shift count in r1, result in r0.

C:
  int32_t shift_right_arithmetic_r0(int32_t val, int32_t cnt)
  // cnt < 0 -> val ; cnt >= 32 -> (val<0 ? -1 : 0) ; else val >> cnt (arith)

Run from repo root:  python3 c/tests/test_shift_right_arithmetic_r0.py [N]
"""
import os, sys, random

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0x43C8

def call_r0r1(cpu, entry, r0_val, r1_val, r15=0xFFFFDF00):
    """Run a function that expects its args in r0 (value) and r1 (count)."""
    cpu.ram = {}
    cpu.r = [0] * 16
    cpu.r[0] = r0_val & 0xFFFFFFFF
    cpu.r[1] = r1_val & 0xFFFFFFFF
    cpu.r[15] = r15 & 0xFFFFFFFF
    cpu.fr = [0.0] * 16
    cpu.pr = cpu.SENT
    cpu.T = 0; cpu.macl = 0; cpu.mach = 0; cpu.gbr = 0
    cpu.fpul = 0; cpu.fpscr = 0
    cpu.pc = entry & 0xFFFFFFFF
    steps = 0
    while True:
        if cpu.pc == cpu.SENT:
            return cpu.r[0] & 0xFFFFFFFF
        steps += 1
        if steps > 500000:
            raise RuntimeError("runaway at 0x%X" % cpu.pc)
        op = cpu.rd(cpu.pc, 2)
        br = cpu._delayed(op)
        if br is None:
            cpu._exec(op, cpu.pc)
            cpu.pc = (cpu.pc + 2) & 0xFFFFFFFF
        else:
            target, take = br
            cpu._exec(cpu.rd(cpu.pc + 2, 2), cpu.pc + 2)
            cpu.pc = target if take else (cpu.pc + 4) & 0xFFFFFFFF

def ref(val, cnt):
    """Arithmetic right shift with count clamping (sign-extending)."""
    if cnt < 0: return val
    s = val - (1 << 32) if val & 0x80000000 else val
    if cnt >= 32: return 0xFFFFFFFF if s < 0 else 0
    return (s >> cnt) & 0xFFFFFFFF

def test_shift_right(cpu, N):
    for _ in range(N):
        val = random.randint(0, 0xFFFFFFFF)
        cnt = random.randint(-40, 72)
        result = call_r0r1(cpu, ENTRY, val, cnt)
        expected = ref(val, cnt)
        if result != expected:
            return (val, cnt, result, expected)
    return None

def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)

    # Negative values across all count buckets (0..8, 9..23, 24..31, >=32, <0)
    edge_cases = [
        (0x00000000, 0), (0x00000001, 1), (0xFFFFFFFF, 1),
        (0x80000000, 1), (0x80000000, 8), (0x80000000, 9),
        (0x80000000, 23), (0x80000000, 24), (0x80000000, 25),
        (0x80000000, 26), (0x80000000, 31),
        (0xFFFFFF00, 8), (0xFFFF00FF, 16), (0xFF00FFFF, 24),
        (0x80800000, 25), (0x80808080, 31),
        (0x80000000, 32), (0xFFFFFFFF, 32), (0x00000001, 33),
        (0x7FFFFFFF, 31), (0x7FFFFFFF, 32),
        (0x80000000, -1), (0x80000000, -10), (0xFFFFFFFF, -1),
    ]
    for val, cnt in edge_cases:
        result = call_r0r1(cpu, ENTRY, val, cnt)
        expected = ref(val, cnt)
        if result != expected:
            print("FAIL EDGE: val=0x%08X cnt=%d -> result=0x%08X expected=0x%08X" % (val, cnt, result, expected))
            sys.exit(1)

    err = test_shift_right(cpu, N)
    if err:
        val, cnt, result, expected = err
        print("FAIL: val=0x%08X cnt=%d -> result=0x%08X expected=0x%08X" % (val, cnt, result, expected))
        sys.exit(1)
    print("OK  shift_right_arithmetic_r0 @0x%04X  (%d edge + %d random inputs)" % (ENTRY, len(edge_cases), N))
    sys.exit(0)

if __name__ == '__main__':
    main()
