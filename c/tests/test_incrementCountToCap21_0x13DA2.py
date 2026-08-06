#!/usr/bin/env python3
"""test_incrementCountToCap21_0x13DA2.py

Differential test for ROM 0x13DA2 (60E0FC00.bin) — lift
c/incrementCountToCap21_0x13DA2.c.

Runs the ACTUAL ROM bytes of 0x13DA2 in tools/sh2emu.py over seeded RAM states
oracle) and compares the full post-call RAM overlay (byte-exact) plus the
return register r0 against a Python reference model that mirrors the C lift.

Semantics: reads u8@0xFFFFA758; if it is < 0x15 (21) it stores back
addSaturate8Bit@0x2478(v, 1) = min(v+1, 0xFF); otherwise no write. r0 on the
non-increment path keeps its entry value (the model uses the emulator default
initial r0 = 0), and on the increment path r0 == the stored value.

Run: python3 c/tests/test_incrementCountToCap21_0x13DA2.py [N]
"""
import os, random, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E0FC00.bin')
ADDR = 0x13DA2
CNT = 0xFFFFA758
CAP = 0x15

STACK_LO = 0xFFFFDE00
STACK_HI = 0xFFFFDF00


def add_sat(a, b):
    r = (a & 0xFF) + (b & 0xFF)
    return 0xFF if r >= 0xFF else r


def ref(m):
    m = dict(m)
    v = m.get(CNT, 0) & 0xFF
    ini = 0
    if v < CAP:
        nv = add_sat(v, 1)
        m[CNT] = nv & 0xFF
        return m, nv & 0xFF
    return m, ini


def gen_state(rng):
    # esp.: counter near/over the cap, plus junk that must stay untouched
    return {CNT: rng.choice([0, 1, 5, 0x14, 0x15, 0x16, 0x7F, 0xFE, 0xFF]),
            0xFFFFA759: rng.randrange(0, 256),
            0xFFFFA757: rng.randrange(0, 256),
            0xFFFFA5D0: rng.randrange(0, 256)}


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    rom = open(ROM, 'rb').read()

    cpu = SH2(rom)
    seeds = (0x13DA2, 0x2478, 0xA758, 0x13E00, 0x141FC)
    total_fails = 0

    for seed in seeds:
        rng = random.Random(seed)
        fails = 0
        for _ in range(N):
            ram = gen_state(rng)
            want, want_r0 = ref(ram)
            try:
                cpu.call(ADDR, ram=ram)
            except Exception as e:
                print('EMULATOR EXC seed=0x%X: %s' % (seed, e))
                fails += 1
                break
            bad = []
            allk = set(want.keys()) | set(cpu.ram.keys())
            for k in allk:
                if STACK_LO <= k <= STACK_HI:
                    continue
                if cpu.ram.get(k, 0) != want.get(k, 0):
                    bad.append((k, cpu.ram.get(k, 0), want.get(k, 0)))
            if bad or cpu.r[0] != want_r0:
                print('MISMATCH seed=0x%X r0=%d want_r0=%d %s' %
                      (seed, cpu.r[0], want_r0,
                       {hex(k): (hex(g), hex(e)) for k, g, e in bad[:8]}))
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
    print('OK  0x13DA2 incrementCountToCap21 '
          '(%d random inputs across %d seeds)' % (N * len(seeds), len(seeds)))
    print('\nAll incrementCountToCap21 tests passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()