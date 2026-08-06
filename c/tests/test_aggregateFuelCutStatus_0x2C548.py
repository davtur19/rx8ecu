#!/usr/bin/env python3
"""test_aggregateFuelCutStatus_0x2C548.py

Differential test for ROM 0x2C548 (60E0FC00.bin) — lift
c/aggregateFuelCutStatus_0x2C548.c.

Runs the ACTUAL ROM bytes of 0x2C548 in tools/sh2emu.py over seeded RAM
states (the oracle) and compares the full post-call RAM overlay (byte-exact,
task-stack window 0xFFFFDE00..DF00 skipped) plus the return register r0
against a Python reference model that mirrors the C lift line-for-line.

Entry/range: 0x2C548 IS the real entry (dispatcher slot @0x144FC of the
engineControlCalculateTiming table; preceding fn 0x02C4E6 ends rts @0x2C544;
next fn starts exactly at CSV end 0x2C5D0). CSV range 0x2C548..0x2C5D0
CORRECT — no phantom rows.

Semantics (see lift header): out u8@FFFFBC61 = 1 if any of the four
fuel-cut condition flags u8@CC8A/CC8B/CC8C/CC8D == 1, else 0.
r0 on return = the deciding flag byte & 0xFF (==1 on every set path, or
u8@CC8D & 0xFF on the clear path).

Run: python3 c/tests/test_aggregateFuelCutStatus_0x2C548.py [N]
     (N = random inputs per seed; default 100000 -> 500000 across 5 seeds)
"""
import os, random, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E0FC00.bin')
ADDR = 0x2C548

# ---- RAM addresses (see c/aggregateFuelCutStatus_0x2C548.c) ----
CC8A = 0xFFFFCC8A   # u8 fuel_cut_flag
CC8B = 0xFFFFCC8B   # u8 fuel_cut condition 7 flag
CC8C = 0xFFFFCC8C   # u8 fuel-cut condition flag
CC8D = 0xFFFFCC8D   # u8 fuel-cut condition flag
BC61 = 0xFFFFBC61   # u8 aggregate fuel-cut status out

BYTE_IN = [CC8A, CC8B, CC8C, CC8D, BC61]
STACK_LO = 0xFFFFDE00
STACK_HI = 0xFFFFDF00


def ref(m):
    """Line-for-line mirror of aggregateFuelCutStatus_0x2C548().
    Returns (full RAM-effect dict, expected r0)."""
    m = dict(m)
    cc8a = m.get(CC8A, 0) & 0xFF
    cc8b = m.get(CC8B, 0) & 0xFF
    cc8c = m.get(CC8C, 0) & 0xFF
    cc8d = m.get(CC8D, 0) & 0xFF
    want_r0 = cc8d & 0xFF          # default: last byte compared
    if cc8a == 1 or cc8b == 1 or cc8c == 1 or cc8d == 1:
        m[BC61] = 1                # bt @0x2C57A paths; r0 = deciding flag
        if cc8a == 1:
            want_r0 = cc8a & 0xFF
        elif cc8b == 1:
            want_r0 = cc8b & 0xFF
        elif cc8c == 1:
            want_r0 = cc8c & 0xFF
        else:
            want_r0 = cc8d & 0xFF
    else:
        m[BC61] = 0                # bf @0x2C5C8; r0 = u8@CC8D & 0xFF
    return m, want_r0


def gen_state(rng):
    """Random seeded RAM hitting every gate combination (each flag 0/1/other)
    so the OR-aggregation, the clear path, and every r0 leaf are exercised."""
    def b(a):
        r = rng.random()
        if r < 0.6:
            return rng.choice([0, 1])
        elif r < 0.85:
            return int(rng.randint(2, 255))
        else:
            return rng.choice([0x7F, 0x80, 0xFF])
    ram = {a: b(a) for a in (CC8A, CC8B, CC8C, CC8D, BC61)}
    return ram


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    cpu = SH2(open(ROM, 'rb').read())
    seeds = (0x2C548, 0x2C488, 0xCC8A, 0xFFFFBC61, 0x144FC)
    total_fails = 0
    for seed in seeds:
        rng = random.Random(seed)
        fails = 0
        for it in range(N):
            ram = gen_state(rng)
            want, want_r0 = ref(ram)
            cpu.call(ADDR, ram=ram)
            bad = []
            for k in set(k for k in want if isinstance(k, int)) | set(cpu.ram.keys()):
                if STACK_LO <= k <= STACK_HI:
                    continue
                if cpu.ram.get(k, 0) != want.get(k, 0):
                    bad.append((k, cpu.ram.get(k, 0), want.get(k, 0)))
            if bad or cpu.r[0] != want_r0:
                print('MISMATCH seed=0x%X iter=%d r0=%d want_r0=%d %s' %
                      (seed, it, cpu.r[0], want_r0,
                       {hex(k): (hex(g), hex(e)) for k, g, e in bad[:10]}))
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
    print('OK  0x2C548 aggregateFuelCutStatus '
          '(%d random inputs across %d seeds)' % (N * len(seeds), len(seeds)))
    print('\nAll aggregateFuelCutStatus_0x2C548 tests passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()