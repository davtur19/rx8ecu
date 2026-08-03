#!/usr/bin/env python3
"""test_setImmoLight_263C8.py

Differential test for ROM 0x263C8 (60E1D400.bin) — lift c/setImmoLight.c.

Drives the immobilizer warning lamp: a 16-bit GPIO register addressed via a
sign-extended mov.w literal as 0xFFFFF754 (the emulator's sparse RAM key).
on==1 sets bits 0x40 then 0x20 (via reg16SetClear @0x4BBC); on!=1 clears
0x20 then 0x40.  The SR save/restore helpers (0x2054/0x2064) only touch SR
and stack slots (0xFFFFDE00..0xFFFFDF00), which are excluded from the
comparison.

Model: v = u16(0xFFFFF754); if (on & 0xFF) == 1: v |= 0x60 else v &= ~0x60.

Run: python3 c/tests/test_setImmoLight_263C8.py [N]
     (N = random inputs per seed; default 5000 -> 25000 across 5 seeds)
"""
import os, random, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ADDR = 0x263C8
LAMP = 0xFFFFF754   # 16-bit lamp GPIO register (sign-extended literal 0xF754)


def rd16(m, a):
    return ((m.get(a, 0) & 0xFF) << 8) | (m.get(a + 1, 0) & 0xFF)


def wr16(m, a, v):
    m[a] = (v >> 8) & 0xFF
    m[a + 1] = v & 0xFF


def model(ram, on):
    """Mirror of setImmoLight(): only the lamp register is read/written."""
    m = dict(ram)
    v = rd16(m, LAMP)
    if (on & 0xFF) == 1:
        v |= 0x40
        v |= 0x20
    else:
        v &= ~0x20
        v &= ~0x40
    wr16(m, LAMP, v & 0xFFFF)
    return m


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    seeds = (0x263C8, 0xF754, 0x40, 0x20, 0x5EED)
    total = fails = 0

    for seed in seeds:
        rng = random.Random(seed)
        for _ in range(N):
            on = rng.choice([0, 1, 0xFF, rng.randint(0, 255), rng.randint(0, 1)])
            init = rng.choice([0x0000, 0x0020, 0x0040, 0x0060,
                               rng.randint(0, 0xFFFF)])
            ram = {LAMP: (init >> 8) & 0xFF, LAMP + 1: init & 0xFF}
            want = model(ram, on)
            cpu.call(ADDR, r4=on, ram=dict(ram))
            bad = []
            allk = set(want) | set(cpu.ram.keys())
            for k in allk:
                if 0xFFFFDE00 <= k <= 0xFFFFDF00:   # task stack area
                    continue
                if cpu.ram.get(k, 0) != want.get(k, 0):
                    bad.append((k, cpu.ram.get(k, 0), want.get(k, 0)))
            if bad:
                fails += 1
                if fails <= 5:
                    print('MISMATCH seed=0x%X on=%d init=%04X: %s' %
                          (seed, on, init,
                           {hex(k): (hex(g), hex(e)) for k, g, e in bad[:8]}))
            total += 1
        if fails >= 5:
            break

    if fails:
        print('\nFAIL setImmoLight @0x263C8  (%d mismatches / %d inputs)'
              % (fails, total))
        sys.exit(1)
    print('OK  setImmoLight @0x263C8  (%d inputs, 0 mismatches)' % total)
    sys.exit(0)


if __name__ == '__main__':
    main()
