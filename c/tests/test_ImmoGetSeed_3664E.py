#!/usr/bin/env python3
"""test_ImmoGetSeed_3664E.py

Differential test for ROM 0x3664E (60E1D400.bin) — lift c/ImmoGetSeed.c.

Recomputes the immobilizer seed from the two EEPROM key words and the
rolling code, storing the result into IMMO_SEED_OUT (0xFFFFC270):

    IMMO_SEED_OUT = calculateImmoSeed(
                        *(u32*)0xFFFFC2DC,   -- r4
                        *(u32*)0xFFFFC2E0,   -- r5
                        *(u32*)0xFFFFC278);  -- r6 (rolling code)

calculateImmoSeed (0x3675C) executes in ROM for real; the Python model
mirrors c/calculateImmoSeed.c line-for-line.  Only C270..C273 are written.

Run: python3 c/tests/test_ImmoGetSeed_3664E.py [N]
     (N = random vectors per seed; default 5000 -> 25000 across 5 seeds)
"""
import os, random, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ADDR = 0x3664E

KEY   = 0xFFFFC278
W2DC  = 0xFFFFC2DC
W2E0  = 0xFFFFC2E0
SEED  = 0xFFFFC270


def rd32(m, a):
    return ((m.get(a, 0) << 24) | (m.get(a + 1, 0) << 16) |
            (m.get(a + 2, 0) << 8) | m.get(a + 3, 0))


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


def model(ram):
    m = dict(ram)
    v = calc(rd32(m, W2DC), rd32(m, W2E0), rd32(m, KEY)) & 0xFFFFFFFF
    m[SEED] = (v >> 24) & 0xFF
    m[SEED + 1] = (v >> 16) & 0xFF
    m[SEED + 2] = (v >> 8) & 0xFF
    m[SEED + 3] = v & 0xFF
    return m


def seed_word(m, a, rng):
    for i in range(4):
        m[a + i] = rng.randint(0, 255)


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    seeds = (0x3664E, 0x3675C, 0xC278, 0xC2DC, 0x5EED)
    total = fails = 0

    for seed in seeds:
        rng = random.Random(seed)
        for _ in range(N):
            m = {}
            for a in (KEY, W2DC, W2E0):
                seed_word(m, a, rng)
            want = model(m)
            cpu.call(ADDR, ram=dict(m))
            bad = []
            allk = set(want) | set(cpu.ram.keys())
            for k in allk:
                if 0xFFFFDE00 <= k <= 0xFFFFDF00:
                    continue
                if cpu.ram.get(k, 0) != want.get(k, 0):
                    bad.append((k, cpu.ram.get(k, 0), want.get(k, 0)))
            if bad:
                fails += 1
                if fails <= 5:
                    print('MISMATCH seed=0x%X: %s' %
                          (seed, {hex(k): (hex(g), hex(e))
                                  for k, g, e in bad[:10]}))
            total += 1
        if fails >= 5:
            break

    if fails:
        print('\nFAIL ImmoGetSeed @0x3664E  (%d mismatches / %d inputs)'
              % (fails, total))
        sys.exit(1)
    print('OK  ImmoGetSeed @0x3664E  (%d inputs, 0 mismatches)' % total)
    sys.exit(0)


if __name__ == '__main__':
    main()