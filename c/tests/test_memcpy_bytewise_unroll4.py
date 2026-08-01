#!/usr/bin/env python3
"""
Verify memcpy_bytewise_unroll4 (0x0042B0) against the ACTUAL ROM bytes,
run in the SH-2E emulator.  This is a byte-by-byte copy with 4× unrolling.

Register usage (SH-2 calling convention BROKEN — uses r0, r1, r2 directly):
  r0 = count (bytes to copy)
  r1 = destination pointer
  r2 = source pointer

Test creates a custom caller that sets r0-r2 appropriately.

C:
  void memcpy_bytewise_unroll4(uint8_t *dst, const uint8_t *src, uint32_t count)

Run from repo root:  python3 c/tests/test_memcpy_bytewise_unroll4.py [N]
"""
import os, sys, random

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0x0042B0

def call_custom(cpu, entry, r0=0, r1=0, r2=0, r4=0, r5=0, r6=0, r7=0, r15=0xFFFFDF00, ram=None):
    """Call a function with full register setup (r0-r15)."""
    cpu.ram = dict(ram or {})
    cpu.r = [0] * 16
    cpu.r[0] = r0 & 0xFFFFFFFF
    cpu.r[1] = r1 & 0xFFFFFFFF
    cpu.r[2] = r2 & 0xFFFFFFFF
    cpu.r[4] = r4 & 0xFFFFFFFF
    cpu.r[5] = r5 & 0xFFFFFFFF
    cpu.r[6] = r6 & 0xFFFFFFFF
    cpu.r[7] = r7 & 0xFFFFFFFF
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

def test_memcpy(cpu, N):
    """Run N random memcpy tests."""
    MAX_SIZE = 64
    SRC_BASE = 0x1000
    DST_BASE = 0x2000

    for _ in range(N):
        size = random.randint(0, MAX_SIZE)
        # Create source data in RAM
        ram = {}
        src_data = [random.randint(0, 0xFF) for _ in range(size)]
        for i, b in enumerate(src_data):
            ram[SRC_BASE + i] = b
        # Initialize destination with known pattern
        for i in range(MAX_SIZE + 4):
            ram[DST_BASE + i] = 0xA5

        call_custom(cpu, ENTRY,
                     r0=size,
                     r1=DST_BASE,
                     r2=SRC_BASE,
                     ram=ram)

        # Verify destination bytes match source
        for i in range(size):
            got = cpu.ram.get(DST_BASE + i, -1)
            exp = src_data[i]
            if got != exp:
                return (size, i, got, exp)

        # Verify bytes beyond copy range are untouched (still 0xA5)
        for i in range(size, MAX_SIZE + 4):
            got = cpu.ram.get(DST_BASE + i, -1)
            if got != 0xA5:
                return (size, i, got, 'untouched(0xA5)')

    return None

def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)

    # Edge cases
    for size in [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 15, 16, 17, 31, 32, 33, 63, 64, 100]:
        ram = {}
        src_data = [random.randint(0, 0xFF) for _ in range(size)]
        for i, b in enumerate(src_data):
            ram[0x1000 + i] = b
        for i in range(150):
            ram[0x2000 + i] = 0xA5
        call_custom(cpu, ENTRY, r0=size, r1=0x2000, r2=0x1000, ram=ram)
        for i in range(size):
            if cpu.ram.get(0x2000 + i, -1) != src_data[i]:
                print("FAIL edge: size=%d, byte %d: got 0x%02X expected 0x%02X" % (size, i, cpu.ram.get(0x2000+i), src_data[i]))
                sys.exit(1)

    err = test_memcpy(cpu, N)
    if err:
        size, i, got, exp = err
        print("FAIL: size=%d, byte %d: got 0x%02X expected 0x%02X" % (size, i, got, exp))
        sys.exit(1)
    else:
        print("OK  memcpy_bytewise_unroll4 @0x%04X  (%d edge + %d random)" % (ENTRY, 18, N))
        sys.exit(0)

if __name__ == '__main__':
    main()
