#!/usr/bin/env python3
"""test_load_blend_factor_limiter_0x16A30.py

Differential test for ROM 0x16A30 (60E1D400.bin) — lift
c/load_blend_factor_limiter_0x16A30.c.

Runs the ACTUAL ROM bytes of 0x16A30 in tools/sh2emu.py over seeded RAM states
(the oracle) and compares the full post-call RAM overlay against a Python
reference model that mirrors the C lift line-for-line.

Key semantic facts (see the lift header):
  * Selector RAM8@0xFFFFB5A4:  ==1 -> blend = TwoDLookup(0x69EAC, RAM[AA14])
                               else -> blend = ThreeDLookup(0x69EC0, RAM[AA14],
                                                            RAM[AA1C])
    The lookup helpers are the ROM byte leaves 0x2068 (u8 1-D) and 0x20DC
    (u8 2-D) — called through a second emulator instance so their single
    precision rounding and clamp behavior match the ROM exactly.
  * Limiter: if blend < RAM[A8D8] + 20.0 -> RAM[A8D4] = blend; then
    RAM[A8D8] = RAM[A8D4] (always).

Run: python3 c/tests/test_load_blend_factor_limiter_0x16A30.py [N]
     (N = random inputs per seed; default 100000 -> 500000 across 5 seeds)
"""
import os, random, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2, ts

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ADDR = 0x16A30
DESC_2D = 0x69EAC     # 1-D 9x u8, x = coolant temp -40..100
DESC_3D = 0x69EC0    # 3-D 9x3 u8

# ---- RAM addresses (see c/load_blend_factor_limiter_0x16A30.c header) ----
B5A4 = 0xFFFFB5A4   # u8 selector
AA14 = 0xFFFFAA14   # f32 x input
AA1C = 0xFFFFAA1C   # f32 y input
A8D4 = 0xFFFFA8D4   # f32 blend out
A8D8 = 0xFFFFA8D8   # f32 lagged word

FLOAT_IN = [AA14, AA1C, A8D8]
FLOAT_OUT = [A8D4, A8D8]


def r32(d, a):
    return struct.unpack('>f', bytes(d.get(a + i, 0) for i in range(4)))[0]


def f32b(v):
    return list(struct.pack('>f', ts(v)))


def ref(cpu2, ram):
    """Line-for-line mirror of load_blend_factor_limiter_0x16A30().

    The lookup helpers are executed in the dedicated emulator instance `cpu2`
    so the fp rounding / clamp / NaN behavior matches the ROM exactly. Returns
    a full RAM-effect dict (int keys -> byte values).
    """
    m = dict(ram)
    sel = m.get(B5A4, 0)
    x = r32(m, AA14); y = r32(m, AA1C)

    if sel == 1:
        cpu2.call(0x2068, r4=DESC_2D, fr={4: x})     # TwoDLookup
        blend = cpu2.fr[0]
    else:
        cpu2.call(0x20DC, r4=DESC_3D, fr={4: x, 5: y})   # ThreeDLookup
        blend = cpu2.fr[0]

    if blend < ts(r32(m, A8D8) + 20.0):
        for i, b in enumerate(f32b(blend)):
            m[A8D4 + i] = b
    # A8D8 = A8D4 always
    for i, b in enumerate(f32b(r32(m, A8D4))):
        m[A8D8 + i] = b
    return m


def setf(ram, a, v):
    for i, b in enumerate(struct.pack('>f', ts(v))):
        ram[a + i] = b


def gen_state(rng):
    """Random seeded RAM hitting every select/blend/limit-combination."""
    ram = {}
    # coolant temp x on -80..140 (out of map range too), y on -40..40
    setf(ram, AA14, rng.uniform(-80, 140))
    setf(ram, AA1C, rng.uniform(-40, 40))
    ram[B5A4] = rng.randrange(0, 255)   # pick ==1 / !=1
    # prior limiter words: include near/below -20 so the conditional store is hit
    setf(ram, A8D8, rng.choice([rng.uniform(-60, 120), 0.0, 30.0, -25.0]))
    setf(ram, A8D4, rng.uniform(-60, 120))
    if rng.random() < 0.3:               # force a compact limiter
        setf(ram, A8D4, 0.05)
        setf(ram, A8D8, 0.05)
    return ram


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    rom = open(ROM, 'rb').read()

    cpu = SH2(rom)
    cpu2 = SH2(rom)         # dedicated instance for the helper calls in ref()
    seeds = (0x16A30, 0xA8D4, 0x69EC0, 0xAA14, 0xB5A4)
    total_fails = 0

    for seed in seeds:
        rng = random.Random(seed)
        fails = 0
        for it in range(N):
            ram = gen_state(rng)
            want = ref(cpu2, ram)
            try:
                cpu.call(ADDR, ram=ram)
            except Exception as e:
                print('EMULATOR EXC seed=0x%X iter=%d: %s' % (seed, it, e))
                fails += 1
                break
            bad = []
            allk = set(k for k in want if isinstance(k, int)) | set(cpu.ram.keys())
            for k in allk:
                if 0xFFFFDE00 <= k <= 0xFFFFDF00:   # task stack area
                    continue
                if cpu.ram.get(k, 0) != want.get(k, 0):
                    bad.append((k, cpu.ram.get(k, 0), want.get(k, 0)))
            if bad:
                print('MISMATCH seed=0x%X iter=%d: %s' %
                      (seed, it, {hex(k): (hex(g), hex(e)) for k, g, e in bad[:12]}))
                print('  sel=%d x=%r y=%r a8d8=%r' % (
                    ram[B5A4], r32(ram, AA14), r32(ram, AA1C), r32(ram, A8D8)))
                print('  a8d4=%r want_a8d4=%r a8d8=%r want_a8d8=%r' % (
                    r32(cpu.ram, A8D4), r32(want, A8D4),
                    r32(cpu.ram, A8D8), r32(want, A8D8)))
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
    print('OK  0x16A30 load_blend_factor_limiter  (%d random inputs across %d seeds)'
          % (N * len(seeds), len(seeds)))
    print('\nAll load_blend_factor_limiter_0x16A30 tests passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()