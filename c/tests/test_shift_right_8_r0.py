#!/usr/bin/env python3
"""
Verify shift_right_8_r0 (0x00467A) against the ACTUAL ROM bytes, run
in the SH-2E emulator.  Returns r0 arithmetically right-shifted by 8.

C:
  int32_t shift_right_8_r0(int32_t val)  →  val >> 8

Note: SH-2 'shar' is ARITHMETIC shift (sign-extending). Python's >> on
signed ints is also arithmetic, so we convert to signed, shift, convert back.

Run from repo root:  python3 c/tests/test_shift_right_8_r0.py [N]
"""
import os, sys, random

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0x00467A

def call_r0(cpu, entry, r0_val, r15=0xFFFFDF00):
    """Run a function that expects its argument in r0."""
    cpu.ram = {}
    cpu.r = [0] * 16
    cpu.r[0] = r0_val & 0xFFFFFFFF
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

def ref(val):
    """Arithmetic right-shift by 8 (sign-extending).  Python >> on signed."""
    # Convert to signed 32-bit, shift, convert back to unsigned
    s = val - (1 << 32) if val & 0x80000000 else val
    s >>= 8
    return s & 0xFFFFFFFF

def test_shift_right_8_r0(cpu, N):
    """Verify shift_right_8_r0 @0x467A against Python reference."""
    for _ in range(N):
        val = random.randint(0, 0xFFFFFFFF)
        result = call_r0(cpu, ENTRY, val)
        expected = ref(val)
        if result != expected:
            return (val, result, expected)
    return None

def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)

    # Test edge cases first
    edge_cases = [
        0x00000000, 0x00000001, 0x000000FF, 0x00000100,
        0x7FFFFFFF, 0x80000000, 0xFFFFFFFF,
        0xABCDEF01, 0x12345678,
        0xFFFFFF00, 0xFFFF00FF, 0xFF00FFFF,
    ]
    for val in edge_cases:
        result = call_r0(cpu, ENTRY, val)
        expected = ref(val)
        if result != expected:
            print("FAIL EDGE: val=0x%08X → result=0x%08X expected=0x%08X" % (val, result, expected))
            sys.exit(1)

    err = test_shift_right_8_r0(cpu, N)
    if err:
        val, result, expected = err
        print("FAIL: val=0x%08X → result=0x%08X expected=0x%08X" % (val, result, expected))
        sys.exit(1)
    else:
        print("OK  shift_right_8_r0 @0x%04X  (%d edge + %d random inputs)" % (ENTRY, len(edge_cases), N))
        sys.exit(0)

if __name__ == '__main__':
    main()
