#!/usr/bin/env python3
"""test_getCoolantDerate_0x13A30.py — differential test for ROM 0x13E30.

Runs the ACTUAL ROM bytes of 0x13E30 (including its sub-calls f32_to_byte
@0x2500, coolant lookups @0x13E98/@0x13F60, guarded div @0x3E0AC, clamp
@0x2404) over seeded RAM states (the oracle) in tools/sh2emu.py, and compares
a full post-call RAM overlay (byte-exact, task-stack window 0xFFFFDE00..DF00
skipped) against a Python reference model that mirrors the C lift
c/getCoolantBasedTimingDerate_0x13A30.c.  Sub-call leaves are themselves run
by a dedicated emulator instance (cpu2) so their byte-exact results / RAM
side-effects come from the ROM — same pattern as the isNotZero leaf test.

0x13E30 is the real entry (unique slot @0x14438 of the 0x141FC dispatcher
table); code runs to rts delay @0x13E96; CSV end 0x13E98 = start of sub-fn
floatArrayToByteArrayLookup1.  Range OK.

Semantics: writes coolant-based per-side timing derate cells:
  v=(float)byte@A758 ; c1=lookup1(v) ; c2=lookup2(v) ; A76C=c1 ; A770=c2
  x = clamp( guarded_div(f32@A9FC-727E4 , 727E8-727E4), 0, 1 )
  A750 = x*c1 ; A754 = x*c2
Void RAM-writer.
Run: python3 c/tests/test_getCoolRefix_0x13A30.py [N]
"""
import os, random, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2, ts

ROM = os.path.join(ROOT, 'roms', 'stock', '60E0FC00.bin')
ADDR = 0x13E30

A758 = 0xFFFFA758; A76C = 0xFFFFA76C; A770 = 0xFFFFA770
A750 = 0xFFFFA750; A754 = 0xFFFFA754; A9FC = 0xFFFFA9FC
A774 = 0xFFFFA774; A775 = 0xFFFFA775
R727E4 = 0x000727E4; R727E8 = 0x000727E8
STACK_LO = 0xFFFFDE00; STACK_HI = 0xFFFFDF00


def f32_at(rom, a):
    return struct.unpack('>f', rom[a:a + 4])[0]


def rdf(m, a):
    return struct.unpack('>f', bytes(m.get(a + i, 0) for i in range(4)))[0]


def wrf(m, a, v):
    for i, b in enumerate(struct.pack('>f', ts(v))):
        m[a + i] = b


def rdb(m, a):
    return m.get(a, 0)


def gen_state(rng):
    ram = {}
    ram[A758] = rng.randrange(256)
    wrf(ram, A9FC, rng.uniform(-50.0, 200.0))
    if rng.random() < 0.25:
        wrf(ram, A9FC, rng.choice([0.0, 100.0, 3.4e38, 1e-40]))
    wrf(ram, A76C, 1.0); wrf(ram, A770, 2.0)
    wrf(ram, A750, 3.0); wrf(ram, A754, 4.0)
    ram[A774] = 0xAA; ram[A775] = 0xBB
    return ram


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    cpu2 = SH2(rom)
    r727e4 = f32_at(rom, R727E4); r727e8 = f32_at(rom, R727E8)

    def ref(m):
        m = dict(m)
        def go(addr, fr=None, r4=0, r5=0, r6=0):
            cp = dict(m)
            cpu2.call(addr, r4=r4, r5=r5, r6=r6, fr=fr, ram=cp)
            for k, v in cpu2.ram.items():
                if cp.get(k, 0) != v:
                    m[k] = v
            return cpu2.fr[0], cpu2.r[0]

        v, _ = go(0x2500, r4=rdb(m, A758), fr={4: 1.0, 5: 0.0})
        c1, _ = go(0x13E98, fr={4: v})
        c2, _ = go(0x13F60, fr={4: v})
        wrf(m, A76C, c1); wrf(m, A770, c2)
        n = ts(ts(rdf(m, A9FC)) - ts(r727e4))
        d = ts(ts(r727e8) - ts(r727e4))
        ratio, _ = go(0x3E0AC, fr={4: n, 5: d})
        x, _ = go(0x2404, fr={4: ratio, 5: 0.0, 6: 1.0})
        wrf(m, A750, ts(x * c1))
        wrf(m, A754, ts(x * c2))
        return m

    seeds = (0x13E30, 0x13E98, 0x13F60, 0x3E0AC, 0x2500)
    total_fails = 0
    for seed in seeds:
        rng = random.Random(seed)
        fails = 0
        for it in range(N):
            ram = gen_state(rng)
            want = ref(ram)
            try:
                cpu.call(ADDR, ram=dict(ram))
            except Exception as e:
                print('EMULATOR EXC seed=0x%X iter=%d: %s' % (seed, it, e))
                fails += 1
                break
            bad = {}
            for k in set(want) | set(cpu.ram.keys()):
                if STACK_LO <= k <= STACK_HI:
                    continue
                if cpu.ram.get(k, 0) != want.get(k, 0):
                    bad[k] = (cpu.ram.get(k, 0), want.get(k, 0))
            if bad:
                print('MISMATCH seed=0x%X iter=%d %s' %
                      (seed, it, {hex(k): (hex(a), hex(b)) for k, (a, b) in bad.items()}))
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
    print('OK  0x13E30 getCoolantBasedTimingDerate (%d random inputs across %d seeds)' %
          (N * len(seeds), len(seeds)))
    print('\nAll getCoolantBasedTimingDerate_0x13E30 tests passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()