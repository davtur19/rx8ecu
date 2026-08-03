#!/usr/bin/env python3
"""test_calculateImmoSeed_3675C.py

Differential test for ROM 0x3675C (60E1D400.bin) — lift c/calculateImmoSeed.c.

Pure function of three 32-bit words.  Already exercised as a real callee of
ImmoGetSeed_3664E (test_ImmoGetSeed_3664E.py); this dedicated test drives it
directly via cpu.call(0x3675C, r4, r5, r6) with N>=20000 seeded vectors and
compares the returned r0 against a Python mirror of the lift.

Run: python3 c/tests/test_calculateImmoSeed_3675C.py [N]
     (N = random vectors per seed; default 20000 -> 100000 across 5 seeds)
"""
import os, random, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ADDR = 0x3675C


def fold4(v):
    return ((v << 4) & 0xFFFFFFFF) + (v >> 4)


def calc(r4, r5, r6):
    """Mirror of c/calculateImmoSeed.c (ROM 0x3675C)."""
    sum16 = (r4 >> 16) + (r6 >> 16)
    sum32 = (r4 + r6) & 0xFFFFFFFF
    m1 = 0x0D * ((sum16 & 0xFFFF) >> 8)
    m2 = 0x0D * (sum16 & 0xFFFF)
    m3 = 0x0D * ((sum32 & 0xFFFF) >> 8)
    m4 = 0x0D * (sum32 & 0xFFFF)
    b0 = m2 & 0xFF
    b1 = m4 & 0xFF
    sc1 = ((((m1 & 0xFF) << 7) & 0xFFFF) >> 8) + ((m1 & 0xFF) << 7)
    sc2 = ((((b0 << 7) & 0xFFFF) >> 8) + (b0 << 7))
    sc3 = ((((m3 & 0xFF) << 7) & 0xFFFF) >> 8) + ((m3 & 0xFF) << 7)
    sc4 = ((((b1 << 7) & 0xFFFF) >> 8) + ((b1 << 7) & 0xFFFF)) & 0xFFFFFFFF
    r14 = ((r5 >> 16) ^ sc2) & 0xFFFFFFFF
    r7 = (sc3 ^ (r5 >> 8)) & 0xFFFFFFFF
    r5n = (r5 ^ sc4) & 0xFFFFFFFF
    r6n = (sc1 ^ (r5 >> 24)) & 0xFFFFFFFF
    if r5n & 1:
        bo0 = r6n & 0xFF
        bo1 = r14 & 0xFF
        bo2 = fold4(r5n & 0xFF) & 0xFF
        bo3 = fold4(r7 & 0xFF) & 0xFF
    else:
        bo0 = fold4(r14 & 0xFF) & 0xFF
        bo1 = fold4(r6n & 0xFF) & 0xFF
        bo2 = r7 & 0xFF
        bo3 = r5n & 0xFF
    return (bo0 << 24) | (bo1 << 16) | (bo2 << 8) | bo3


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    seeds = (0x3675C, 0x5EED, 0xC270, 0xC2DC, 0x13579)
    total = fails = 0

    # force both parity branches (bit0 of mixed r5) on every seed
    for seed in seeds:
        rng = random.Random(seed)
        for _ in range(N):
            r4 = rng.getrandbits(32)
            r5 = rng.getrandbits(32)
            r6 = rng.getrandbits(32)
            if _ % 2 == 0:
                r5 |= 1          # odd path
            else:
                r5 &= ~1         # even path
            want = calc(r4, r5, r6) & 0xFFFFFFFF
            got = cpu.call(ADDR, r4=r4, r5=r5, r6=r6)
            if got != want:
                fails += 1
                if fails <= 5:
                    print('MISMATCH seed=0x%X r4=%08X r5=%08X r6=%08X '
                          'got=%08X want=%08X' % (seed, r4, r5, r6, got, want))
            total += 1
        if fails >= 5:
            break

    if fails:
        print('\nFAIL calculateImmoSeed @0x3675C  (%d mismatches / %d inputs)'
              % (fails, total))
        sys.exit(1)
    print('OK  calculateImmoSeed @0x3675C  (%d inputs, 0 mismatches)' % total)
    sys.exit(0)


if __name__ == '__main__':
    main()
