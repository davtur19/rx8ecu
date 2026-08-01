#!/usr/bin/env python3
"""
Verify div32_unsigned (0x00409C) against the ACTUAL ROM bytes, run
in the SH-2E emulator.

div32_unsigned implements 32-bit unsigned division using the SH-2E's
div0u/div1/rotcl step-by-step algorithm (fully unrolled, 32 iterations).
The quotient is returned in r0.

C:
  uint32_t div32_unsigned(uint32_t divisor, uint32_t dividend)

SH-2E register convention (broken — uses r0, r1 directly):
  r0 = divisor
  r1 = dividend

On divisor == 0: writes 0x44E to 0xFFFF7304 and returns 0.

Run from repo root:  python3 c/tests/test_div32_unsigned.py [N]
"""
import os, sys, random

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0x00409C


def call_div(cpu, entry, r0_val, r1_val):
    """Run a division function with r0 and r1 set (reuse SH2 internals)."""
    cpu.ram = {}
    cpu.r = [0] * 16
    cpu.r[0] = r0_val & 0xFFFFFFFF
    cpu.r[1] = r1_val & 0xFFFFFFFF
    cpu.r[15] = 0xFFFFDF00
    cpu.fr = [0.0] * 16
    cpu.pr = cpu.SENT
    cpu.T = 0
    cpu.macl = 0; cpu.mach = 0; cpu.gbr = 0
    cpu.sr = 0xF0; cpu.vbr = 0; cpu.ssr = 0; cpu.spc = 0
    cpu.fpul = 0; cpu.fpscr = 0
    cpu._Q = 0; cpu._M = 0
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


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)

    # Edge cases: (divisor, dividend, expected)
    edge_cases = [
        (1, 0, 0),
        (1, 1, 1),
        (2, 5, 2),
        (5, 17, 3),
        (7, 100, 14),
        (0xFFFFFFFF, 0xFFFFFFFF, 1),
        (0xFFFFFFFF, 0xFFFFFFFE, 0),
        (0x80000000, 0xFFFFFFFF, 1),
        (0x00010000, 0xFFFFFFFF, 0xFFFF),
        (0x00000010, 0xFFFFFFFF, 0x0FFFFFFF),
        (0x10000, 0x12345678, 0x1234),
        (0x100, 0x12345678, 0x123456),
        (0x7FFFFFFF, 0x7FFFFFFF, 1),
        (0x7FFFFFFF, 0x80000000, 1),
        (0x80000000, 0x80000000, 1),
        (3, 0, 0),
        (10, 0, 0),
        (2, 1, 0),
        (2, 3, 1),
    ]
    for divisor, dividend, expected in edge_cases:
        if divisor == 0:
            continue
        result = call_div(cpu, ENTRY, divisor, dividend)
        if result != expected:
            print("FAIL EDGE: 0x%08X / 0x%08X -> 0x%08X expected 0x%08X" % (
                divisor, dividend, result, expected))
            sys.exit(1)

    # Division by zero: ROM writes diag code 0x44E to 0xFFFF7304, returns 0.
    result = call_div(cpu, ENTRY, 0, 100)
    if result != 0:
        print("FAIL: division by zero returned 0x%08X (expected 0)" % result)
        sys.exit(1)
    diag = (cpu.ram.get(0xFFFF7304, 0) << 24) | (cpu.ram.get(0xFFFF7305, 0) << 16) \
         | (cpu.ram.get(0xFFFF7306, 0) << 8) | cpu.ram.get(0xFFFF7307, 0)
    if diag != 0x44E:
        print("FAIL: division by zero wrote 0x%08X to 0xFFFF7304 (expected 0x44E)" % diag)
        sys.exit(1)

    # Random tests: compare ROM behavior against Python reference (unsigned floor)
    for _ in range(N):
        divisor = random.randint(0, 0xFFFFFFFF)
        dividend = random.randint(0, 0xFFFFFFFF)
        if divisor == 0:
            continue
        result = call_div(cpu, ENTRY, divisor, dividend)
        expected = dividend // divisor
        if result != expected:
            print("FAIL: 0x%08X / 0x%08X -> 0x%08X expected 0x%08X" % (
                divisor, dividend, result, expected))
            sys.exit(1)

    print("OK  div32_unsigned @0x%04X  (%d edge + %d random, excl div0)" % (ENTRY, len(edge_cases), N))
    sys.exit(0)


if __name__ == '__main__':
    main()
