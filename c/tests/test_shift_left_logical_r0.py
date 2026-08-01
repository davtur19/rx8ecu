#!/usr/bin/env python3
"""
Verify shift_left_logical_r0 (0x4308) against the ACTUAL ROM bytes, run in
the SH-2E emulator.  Value in r0, shift count in r1, result in r0.

C:
  uint32_t shift_left_logical_r0(uint32_t val, int32_t cnt)
  // cnt < 0 -> val ; cnt >= 32 -> 0 ; else val << cnt

Run from repo root:  python3 c/tests/test_shift_left_logical_r0.py [N]
"""
import os, sys, random

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0x4308

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
    """Logical left shift with count clamping."""
    if cnt < 0: return val
    if cnt >= 32: return 0
    return (val << cnt) & 0xFFFFFFFF

def test_shift_left(cpu, N):
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

    edge_cases = [
        (0x00000000, 0), (0x00000001, 1), (0x00000001, 31),
        (0x80000000, 1), (0x7FFFFFFF, 31), (0xFFFFFFFF, 0),
        (0x000000FF, 8), (0x000000FF, 24), (0x000000FF, 31),
        (0x12345678, 16), (0xABCDEF01, 28), (0xABCDEF01, 31),
        (0x00000001, 32), (0x00000001, 33), (0xFFFFFFFF, 64),
        (0x00000001, -1), (0x00000001, -10), (0xFFFFFFFF, -1),
    ]
    for val, cnt in edge_cases:
        result = call_r0r1(cpu, ENTRY, val, cnt)
        expected = ref(val, cnt)
        if result != expected:
            print("FAIL EDGE: val=0x%08X cnt=%d -> result=0x%08X expected=0x%08X" % (val, cnt, result, expected))
            sys.exit(1)

    err = test_shift_left(cpu, N)
    if err:
        val, cnt, result, expected = err
        print("FAIL: val=0x%08X cnt=%d -> result=0x%08X expected=0x%08X" % (val, cnt, result, expected))
        sys.exit(1)
    print("OK  shift_left_logical_r0 @0x%04X  (%d edge + %d random inputs)" % (ENTRY, len(edge_cases), N))
    sys.exit(0)

if __name__ == '__main__':
    main()
