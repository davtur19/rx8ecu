#!/usr/bin/env python3
"""test_writeToE2RAMArea_0x39124.py

Differential test for ROM 0x39124 (60E1D400.bin) — lift c/writeToE2RAMArea.c.

Runs the ACTUAL ROM bytes of 0x39124 in tools/sh2emu.py over seeded inputs and
compares the resulting EEPROM shadow (primary 0xFFFFC2FE + complement 0xFFFFC3FE)
against the C lift model.

Semantics (from the disassembly, verified):
   while (length != 0) {
       idx   = index & 0xFFFF;
       b     = *src++;                 // src = r5, source pointer
       length--; index++;
       primary[idx]     = b;           // 0xFFFFC2FE + idx
       complement[idx]  = ~primary[idx];// NOT of the READ-BACK byte = ~b
   }
   getSR/setSR (0x3920/0x3934) are stubbed to rts;nop (SR not observable).

Run: python3 c/tests/test_writeToE2RAMArea_0x39124.py [N]
"""
import os, random, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ADDR = 0x39124
E2_PRI = 0xFFFFC2FE
E2_COM = 0xFFFFC3FE


def stub():
    s = {}
    for a in (0x3920, 0x3934):          # getSR, setSR
        s[a] = 0x00; s[a + 1] = 0x0B; s[a + 2] = 0x00; s[a + 3] = 0x09  # rts; nop
    return s


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    rng = random.Random(0x39124)
    fails = 0

    for it in range(N):
        index = rng.randint(0, 0x80)                 # keep end within primary (no alias)
        length = rng.randint(1, 64)                 # index+length <= 0x100
        if index + length > 0xFF:
            length = 0xFF - index
        src_addr = 0xFFFFA000
        src = [rng.randint(0, 255) for _ in range(length)]
        ram = {**stub()}
        for i in range(length):
            ram[src_addr + i] = src[i]
        cpu.call(ADDR, r4=index, r5=src_addr, r6=length, ram=dict(ram))

        for i in range(length):
            j = index + i
            gd = cpu.ram.get(E2_PRI + j, 0)
            gc = cpu.ram.get(E2_COM + j, 0)
            if gd != src[i]:
                print('MISMATCH data idx=%d expect=%02X got=%02X' % (j, src[i], gd))
                fails += 1
            if gc != ((~src[i]) & 0xFF):
                print('MISMATCH comp  idx=%d expect=%02X got=%02X' % (j, (~src[i]) & 0xFF, gc))
                fails += 1
        if fails:
            print('first failing input: index=%d length=%d src=%s' % (index, length, src[:8]))
            break

    if fails:
        print('%d FAILURE(S)  writeToE2RAMArea' % fails)
        sys.exit(1)
    print('OK  0x39124 writeToE2RAMArea  (%d inputs)' % N)
    sys.exit(0)


if __name__ == '__main__':
    main()