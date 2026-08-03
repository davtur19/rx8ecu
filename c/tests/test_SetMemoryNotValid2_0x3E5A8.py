#!/usr/bin/env python3
"""test_SetMemoryNotValid2_0x3E5A8.py

Differential test for ROM 0x3E5A8 (60E0FC00.bin) — lift c/SetMemoryNotValid2.c.

The audit flagged SetMemoryNotValid2 as "solo stub in test_mem_accessors":
in c/tests/test_mem_accessors.py the bytes at 0x3E5A8 are REPLACED by an
rts;nop stub, so the real function body is never executed there — it is NOT
covered.  This test runs the actual ROM bytes.

Verified disassembly (60E0FC00.bin):
   0x3E5A8  mov.w 0x3E6B8,r2   ; r2 = 0xC639  -> target addr 0xFFFFC639
   0x3E5AA  mov   #0x01,r3
   0x3E5AC  rts
   0x3E5AE  mov.b r3,@r2       ; delay slot: RAM8[0xFFFFC639] = 1

NOTE (lift correction): the C lift documents MEM_INVALID_ADDR as 0xFFFFC63A,
but the literal pool at 0x3E6B8 holds 0xC639, i.e. the real write target is
0xFFFFC639.  The lift constant is off by one.

Run: python3 c/tests/test_SetMemoryNotValid2_0x3E5A8.py [N]
"""
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E0FC00.bin')
ADDR = 0x3E5A8
TARGET = 0xFFFFC639          # real write target (from literal pool 0x3E6B8)


def main():
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    fails = 0
    N = 5000

    for it in range(N):
        # function takes no arguments; pre-fill target with junk
        pre = (it * 7 + 3) & 0xFF
        ram = {TARGET: pre}
        cpu.call(ADDR, ram=dict(ram))
        got = cpu.ram.get(TARGET, 0)
        if got != 1:
            print('MISMATCH iter=%d pre=%02X: RAM8[0xFFFFC639]=%02X, expected 01' % (it, pre, got))
            fails += 1
        # any other RAM byte must be untouched
        extra = [k for k in cpu.ram if k != TARGET]
        if extra:
            print('MISMATCH iter=%d: unexpected writes at %s' % (it, [hex(k) for k in extra[:5]]))
            fails += 1

    if fails:
        print('%d FAILURE(S)  SetMemoryNotValid2' % fails)
        sys.exit(1)
    print('OK  0x3E5A8 SetMemoryNotValid2  (%d inputs)' % N)
    sys.exit(0)


if __name__ == '__main__':
    main()