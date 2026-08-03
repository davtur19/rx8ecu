#!/usr/bin/env python3
"""test_setMemInsideFUNCto1_0x3E3F0.py

Differential test for ROM 0x3E3F0 (60E0FC00.bin) — lift c/setMemInsideFUNCto1.c.

The audit flagged setMemInsideFUNCto1 as "solo stub in test_mem_accessors":
in c/tests/test_mem_accessors.py the bytes at 0x3E3F0 are REPLACED by an
rts;nop stub, so the real function body is never executed there — it is NOT
covered.  This test runs the actual ROM bytes.

Verified disassembly (60E0FC00.bin):
   0x3E3F0  mov.w 0x3E50A,r2   ; r2 = 0xC638  -> target addr 0xFFFFC638
   0x3E3F2  mov   #0x01,r3
   0x3E3F4  rts
   0x3E3F6  mov.b r3,@r2       ; delay slot: RAM8[0xFFFFC638] = 1

Run: python3 c/tests/test_setMemInsideFUNCto1_0x3E3F0.py [N]
"""
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E0FC00.bin')
ADDR = 0x3E3F0
TARGET = 0xFFFFC638


def main():
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    fails = 0
    N = 5000

    for it in range(N):
        pre = (it * 11 + 1) & 0xFF
        ram = {TARGET: pre}
        cpu.call(ADDR, ram=dict(ram))
        got = cpu.ram.get(TARGET, 0)
        if got != 1:
            print('MISMATCH iter=%d pre=%02X: RAM8[0xFFFFC638]=%02X, expected 01' % (it, pre, got))
            fails += 1
        extra = [k for k in cpu.ram if k != TARGET]
        if extra:
            print('MISMATCH iter=%d: unexpected writes at %s' % (it, [hex(k) for k in extra[:5]]))
            fails += 1

    if fails:
        print('%d FAILURE(S)  setMemInsideFUNCto1' % fails)
        sys.exit(1)
    print('OK  0x3E3F0 setMemInsideFUNCto1  (%d inputs)' % N)
    sys.exit(0)


if __name__ == '__main__':
    main()