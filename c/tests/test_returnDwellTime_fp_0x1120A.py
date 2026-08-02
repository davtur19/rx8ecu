#!/usr/bin/env python3
"""test_returnDwellTime_fp_0x1120A.py

Differential test for ROM 0x1120A (60E1D400.bin) — lift
c/returnDwellTime_fp_0x1120A.c.

The function is a tiny pure read->return leaf:
    r0 = (uint32_t)(*(volatile u16*)0xFFFFA0D4) * 16
It reads the u16 dwell value from RAM 0xFFFFA0D4, zero-extends to u32 and
returns `value << 2 << 2` (two shll2 => *16) in r0.

Despite the "_fp" (float-point) suffix, the code returns a plain unsigned 32-bit
integer in r0 — no FPU instructions, no float literals.  The coil-output
dispatcher (FUN @0x11010, dispatch site 0x110D8..0x110DC) adds this integer to
outputPerRotorIgnitionDwell (0x11218) before its own fixed-point math.

Since the leaf performs NO RAM writes, the full-RAM overlay diff is trivially
constant; the meaningful check is the RETURN VALUE r0 returned by the emulator's
call(), compared against the C model mirrored below.

Run: python3 c/tests/test_returnDwellTime_fp_0x1120A.py [N]
     (N = random inputs per seed; default 100000 -> 500000 across 5 seeds)
"""
import os, random, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ADDR = 0x1120A

A0D4 = 0xFFFFA0D4   # u16 dwell value (input, read-only)


def model(v):
    """Mirror of returnDwellTime_fp_0x1120A(): return u16 * 16."""
    v &= 0xFFFF
    return (v << 2 << 2) & 0xFFFFFFFF


def gen_state(rng):
    """Random seeded u16 input at 0xFFFFA0D4."""
    ram = {}
    for i in range(2):
        ram[A0D4 + i] = rng.randint(0, 255)
    return ram


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    rom = open(ROM, 'rb').read()

    cpu = SH2(rom)
    seeds = (0x1120A, 0xA0D4, 0x94C8, 0x10F84, 0x11218)
    total_fails = 0

    for seed in seeds:
        rng = random.Random(seed)
        fails = 0
        for it in range(N):
            ram = gen_state(rng)
            u16 = (ram.get(A0D4, 0) << 8) | ram.get(A0D4 + 1, 0)   # big-endian read
            want = model(u16)
            try:
                got = cpu.call(ADDR, ram=ram)
            except Exception as e:
                print('EMULATOR EXC seed=0x%X iter=%d: %s' % (seed, it, e))
                fails += 1
                break
            got &= 0xFFFFFFFF
            # full-RAM diff (function writes nothing; the only written region is
            # the call stack, which is skipped like the other lift tests)
            bad = []
            for k, v in cpu.ram.items():
                if 0xFFFFDE00 <= k <= 0xFFFFDF00:   # task stack area
                    continue
                if ram.get(k, 0) != v:
                    bad.append((k, v, ram.get(k, 0)))
            if bad:
                print('RAM MISMATCH seed=0x%X iter=%d: %s' %
                      (seed, it, {hex(k): (hex(g), hex(e)) for k, g, e in bad[:12]}))
                fails += 1
                if fails >= 3:
                    break
            if got != want:
                print('MISMATCH seed=0x%X iter=%d: u16=0x%04x got=0x%x want=0x%x' %
                      (seed, it, u16, got, want))
                fails += 1
                if fails >= 3:
                    break
        print('  seed 0x%X: %d inputs, fails=%d' % (seed, N, fails))
        total_fails += fails
        if total_fails:
            break

    if total_fails:
        print('\n%d FAILURE(S)' % total_fails)
        sys.exit(1)
    print('OK  0x1120A returnDwellTime_fp  (r0 return: %d random inputs across %d seeds)'
          % (N * len(seeds), len(seeds)))
    print('\nAll returnDwellTime_fp_0x1120A tests passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()