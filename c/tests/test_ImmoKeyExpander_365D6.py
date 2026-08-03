#!/usr/bin/env python3
"""test_ImmoKeyExpander_365D6.py

Differential test for ROM 0x365D6 (60E1D400.bin) — lift c/ImmoKeyExpander.c.

Derives the four expected key values from the rolling code (0xFFFFC278) and
the two EEPROM key words (0xFFFFC2E0 / 0xFFFFC2DC) using the in-ROM
seed_mixer (0x366B8), then stores each slot with its 0x01..0x04 byte prefix.

    slot0 = seed_mixer(w2E0,      key)     store @0xFFFFC24C (+0x01000000 -> C260)
    slot1 = seed_mixer(w2E0>>16,  key>>8)  store @0xFFFFC250 (+0x02000000 -> C264)
    slot2 = seed_mixer(w2DC,      key>>16) store @0xFFFFC254 (+0x03000000 -> C268)
    slot3 = seed_mixer(w2DC>>16,  key>>24) store @0xFFFFC258 (+0x04000000 -> C26C)

The whole call tree executes in the emulator (seed_mixer runs in ROM for
real); the Python model implements seed_mixer directly, mirroring
c/seed_mixer.c.  Writes C24C/C250/C254/C258 (slots) and C260/C264/C268/C26C.

Run: python3 c/tests/test_ImmoKeyExpander_365D6.py [N]
     (N = random vectors per seed; default 5000 -> 25000 across 5 seeds)
"""
import os, random, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ADDR = 0x365D6

KEY   = 0xFFFFC278
W2E0  = 0xFFFFC2E0
W2DC  = 0xFFFFC2DC
SLOT = [0xFFFFC24C, 0xFFFFC250, 0xFFFFC254, 0xFFFFC258]
EXP  = [0xFFFFC260, 0xFFFFC264, 0xFFFFC268, 0xFFFFC26C]
PREF = [0x01000000, 0x02000000, 0x03000000, 0x04000000]


def rd32(m, a):
    return ((m.get(a, 0) << 24) | (m.get(a + 1, 0) << 16) |
            (m.get(a + 2, 0) << 8) | m.get(a + 3, 0))


def seed_mixer(r4, r5):
    """Mirror of c/seed_mixer.c (ROM 0x366B8)."""
    x = ((r4 >> 8) & 0xFF) << 16 | ((r5 & 0xFF) << 8) | (r4 & 0xFF)
    x = (x & 0xFFE0301F) | ((x & 0x0FE0) << 9) | ((x & 0x001FC000) >> 9)
    y = (((0 - (x >> 16)) & 0xFF) << 16) | (((0 - (x >> 8)) & 0xFF) << 8) \
        | ((0 - x) & 0xFF)
    z = ((y << 21) & 0xFFFFFFFF) | (y >> 3)
    return ((z & 0xFF) << 16) | (((z >> 8) & 0xFF) << 8) | ((z >> 16) & 0xFF)


def model(ram):
    """Returns expected dict of written bytes."""
    m = dict(ram)
    key = rd32(m, KEY)
    w2E0 = rd32(m, W2E0)
    w2DC = rd32(m, W2DC)
    slots = [
        seed_mixer(w2E0, key),
        seed_mixer(w2E0 >> 16, key >> 8),
        seed_mixer(w2DC, key >> 16),
        seed_mixer(w2DC >> 16, key >> 24),
    ]
    for i in range(4):
        m[SLOT[i]] = (slots[i] >> 24) & 0xFF
        m[SLOT[i] + 1] = (slots[i] >> 16) & 0xFF
        m[SLOT[i] + 2] = (slots[i] >> 8) & 0xFF
        m[SLOT[i] + 3] = slots[i] & 0xFF
        v = slots[i] | PREF[i]
        m[EXP[i]] = (v >> 24) & 0xFF
        m[EXP[i] + 1] = (v >> 16) & 0xFF
        m[EXP[i] + 2] = (v >> 8) & 0xFF
        m[EXP[i] + 3] = v & 0xFF
    return m


def seed_word(m, a, rng):
    for i in range(4):
        m[a + i] = rng.randint(0, 255)


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    seeds = (0x365D6, 0x366B8, 0xC278, 0xC2DC, 0x5EED)
    total = fails = 0

    for seed in seeds:
        rng = random.Random(seed)
        for _ in range(N):
            m = {}
            for a in (KEY, W2E0, W2DC):
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
                    print('MISMATCH seed=0x%X key=%08X: %s' %
                          (seed, rd32(m, KEY),
                           {hex(k): (hex(g), hex(e))
                            for k, g, e in bad[:10]}))
            total += 1
        if fails >= 5:
            break

    if fails:
        print('\nFAIL ImmoKeyExpander @0x365D6  (%d mismatches / %d inputs)'
              % (fails, total))
        sys.exit(1)
    print('OK  ImmoKeyExpander @0x365D6  (%d inputs, 0 mismatches)' % total)
    sys.exit(0)


if __name__ == '__main__':
    main()