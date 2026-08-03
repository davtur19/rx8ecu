#!/usr/bin/env python3
"""test_seed_mixer_366B8.py

Differential test for ROM 0x366B8 (60E1D400.bin) — lift c/seed_mixer.c.

Pure function of two 32-bit words (r4 = EEPROM key word, r5 = rolling code).
Already exercised indirectly as a callee of ImmoKeyExpander_365D6 (4 calls
per invocation) and of verify_emu.py; this dedicated test sweeps the full
16-bit input space systematically plus seeded random vectors and compares
the returned r0 against a Python mirror of c/seed_mixer.c.

    x = ((r4>>8)&0xFF)<<16 | (r5&0xFF)<<8 | (r4&0xFF)
    x = (x & 0xFFE0301F) | ((x & 0x0FE0)<<9) | ((x & 0x001FC000)>>9)
    y = byte-wise two's-complement negate of x
    z = (y << 21) | (y >> 3)
    return byte-swap 0<->2 of z

Run: python3 c/tests/test_seed_mixer_366B8.py [N]
     (N = random vectors per seed; default 30000 -> 150000 across 5 seeds,
      plus a full 65536-case low-byte sweep of (r4,r5).)
"""
import os, random, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ADDR = 0x366B8


def seed_mixer(r4, r5):
    """Mirror of c/seed_mixer.c (ROM 0x366B8)."""
    x = ((r4 >> 8) & 0xFF) << 16 | ((r5 & 0xFF) << 8) | (r4 & 0xFF)
    x = (x & 0xFFE0301F) | ((x & 0x0FE0) << 9) | ((x & 0x001FC000) >> 9)
    y = (((0 - (x >> 16)) & 0xFF) << 16) | (((0 - (x >> 8)) & 0xFF) << 8) \
        | ((0 - x) & 0xFF)
    z = ((y << 21) & 0xFFFFFFFF) | (y >> 3)
    return ((z & 0xFF) << 16) | (((z >> 8) & 0xFF) << 8) | ((z >> 16) & 0xFF)


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 30000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    seeds = (0x366B8, 0x5EED, 0xC278, 0xC2DC, 0x13579)
    total = fails = 0

    # systematic sweep: all 256 low-byte combinations of r4 and r5
    # (covers the byte-rebuild path exhaustively at the byte level)
    for r4l in range(256):
        for r5l in range(256):
            r4 = (r4l << 24) | (r4l << 16) | (r4l << 8) | r4l
            r5 = (r5l << 24) | (r5l << 16) | (r5l << 8) | r5l
            want = seed_mixer(r4, r5)
            got = cpu.call(ADDR, r4=r4, r5=r5)
            if got != want:
                fails += 1
                if fails <= 5:
                    print('SWEEP MISMATCH r4=%08X r5=%08X got=%08X want=%08X'
                          % (r4, r5, got, want))
            total += 1
    if fails:
        print('\nFAIL seed_mixer @0x366B8 sweep  (%d mismatches / %d)' % (fails, total))
        sys.exit(1)

    for seed in seeds:
        rng = random.Random(seed)
        for _ in range(N):
            r4 = rng.getrandbits(32)
            r5 = rng.getrandbits(32)
            want = seed_mixer(r4, r5)
            got = cpu.call(ADDR, r4=r4, r5=r5)
            if got != want:
                fails += 1
                if fails <= 5:
                    print('MISMATCH seed=0x%X r4=%08X r5=%08X got=%08X want=%08X'
                          % (seed, r4, r5, got, want))
            total += 1
        if fails >= 5:
            break

    if fails:
        print('\nFAIL seed_mixer @0x366B8  (%d mismatches / %d inputs)' % (fails, total))
        sys.exit(1)
    print('OK  seed_mixer @0x366B8  (%d inputs, 0 mismatches)' % total)
    sys.exit(0)


if __name__ == '__main__':
    main()
