#!/usr/bin/env python3
"""test_calculateTrailingDerateRetard_0x12576.py

Differential test for ROM 0x12576 (60E0FC00.bin) — lift
c/calculateTrailingDerateRetard_0x12576.c.

Runs the ACTUAL ROM bytes of 0x12576 — including the real sub-call
saturateLow @0x23E4 — in tools/sh2emu.py over seeded RAM states (the oracle)
and compares the full post-call RAM overlay (byte-exact, task-stack window
0xFFFFDE00..DF00 skipped) plus the return register r0 against a Python
reference model that mirrors the C lift line-for-line.

Entry-point / range note: 0x12576 IS the real entry point (function-pointer
slot @0x144D0 of the engineControlCalculateTiming dispatcher 0x141FC table;
valid prologue; preceding function calculateLeadingDerateRetard ends rts
@0x12572).  The CSV range 0x12576..0x125B0 is CORRECT: code runs to rts
@0x125AC (delay @0x125AE), defaultTimingMinMax starts exactly at 0x125B0.

Key semantic facts (see the lift header): void trailing-timing derate-retard
writer — structural twin of 0x1253C with +4-shifted RAM addresses:
  x = f32@A728 - f32@A6A0
  x = x - max_0x23E4(f32@A754, f32@C8A4)     (NaN sig -> C8A4 reference)
  x = x + f32@A5E8 + f32@B2E8 - f32@A664
  f32@A654 = x
r0 at return: 0 — neither this function nor the 0x23E4 leaf ever writes r0
(the harness CPU starts with r0=0).

Run: python3 c/tests/test_calculateTrailingDerateRetard_0x12576.py [N]
     (N = random inputs per seed; default 100000 -> 500000 across 5 seeds)
"""
import os, random, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2, ts

ROM = os.path.join(ROOT, 'roms', 'stock', '60E0FC00.bin')
ADDR = 0x12576

# ---- RAM addresses (see c/calculateTrailingDerateRetard_0x12576.c header) ----
A6A0 = 0xFFFFA6A0   # f32 diff minuend base
A728 = 0xFFFFA728   # f32 diff minuend
C8A4 = 0xFFFFC8A4   # f32 leaf lower/limit
A754 = 0xFFFFA754   # f32 leaf sig
A5E8 = 0xFFFFA5E8   # f32 addend 1
B2E8 = 0xFFFFB2E8   # f32 addend 2
A664 = 0xFFFFA664   # f32 subtrahend
A654 = 0xFFFFA654   # f32 output

HELPER_MAX = 0x23E4   # saturateLow = max(fr4, fr5); NaN fr4 -> fr5

STACK_LO = 0xFFFFDE00    # task stack window (skipped in the compare)
STACK_HI = 0xFFFFDF00


def f32_at(rom, a):
    return struct.unpack('>f', rom[a:a + 4])[0]


def setf(m, a, v):
    for i, b in enumerate(struct.pack('>f', ts(v))):
        m[a + i] = b


def rdf(m, a):
    return struct.unpack('>f', bytes(m.get(a + i, 0) for i in range(4)))[0]


def wrf(m, a, v):
    for i, b in enumerate(struct.pack('>f', ts(v))):
        m[a + i] = b


def ref(cpu2, m):
    """Line-for-line mirror of calculateTrailingDerateRetard_0x12576().

    The 0x23E4 leaf is executed in `cpu2` (oracle) and its fr0 result merged;
    the fadd/fsub chain mirrors the emulator's single-precision rounding.
    Returns (RAM-effect dict, expected r0)."""
    m = dict(m)

    # x = f32@A728 - f32@A6A0  (fsub fr3,fr2)
    x = ts(rdf(m, A728) - rdf(m, A6A0))

    # x -= saturateLow(f32@A754, f32@C8A4)   (jsr @0x23E4 -> fr0, fsub fr0,fr12)
    cpu2.call(HELPER_MAX, fr={4: rdf(m, A754), 5: rdf(m, C8A4)}, ram=m)
    x = ts(x - cpu2.fr[0])

    # x += f32@A5E8 ; x += f32@B2E8 ; x -= f32@A664
    x = ts(x + rdf(m, A5E8))
    x = ts(x + rdf(m, B2E8))
    x = ts(x - rdf(m, A664))

    wrf(m, A654, x)                          # fmov.s fr12,@r3
    return m, 0                              # r0 untouched -> 0


def gen_state(rng):
    """Random seeded RAM hitting every float shape (finite spans, boundaries,
    denormals, infinities, NaN) for all 7 inputs; the output word is junk so
    a missed write is caught."""
    ram = {}
    for a in (A6A0, A728, C8A4, A754, A5E8, B2E8, A664):
        r = rng.random()
        if r < 0.6:
            setf(ram, a, rng.uniform(-40.0, 40.0))
        elif r < 0.75:
            setf(ram, a, rng.choice([0.0, -0.0, 1.0, -1.0, 100.0, -100.0,
                                     1e-6, -1e-6, 3.4e38, -3.4e38, 1e-40]))
        elif r < 0.85:
            setf(ram, a, float('nan'))
        elif r < 0.93:
            setf(ram, a, float('inf') if rng.random() < 0.5 else float('-inf'))
        else:
            setf(ram, a, rng.uniform(-2000.0, 2000.0))
    setf(ram, A654, rng.uniform(-1000.0, 1000.0))   # junk output word
    return ram


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    rom = open(ROM, 'rb').read()

    cpu = SH2(rom)
    cpu2 = SH2(rom)          # dedicated instance for the 0x23E4 leaf in ref()
    seeds = (0x12576, 0x1253C, 0x144D0, 0xA654, 0x23E4)
    total_fails = 0

    for seed in seeds:
        rng = random.Random(seed)
        fails = 0
        for it in range(N):
            ram = gen_state(rng)
            want, want_r0 = ref(cpu2, ram)
            try:
                cpu.call(ADDR, ram=ram)
            except Exception as e:
                print('EMULATOR EXC seed=0x%X iter=%d: %s' % (seed, it, e))
                fails += 1
                break
            bad = []
            allk = set(k for k in want if isinstance(k, int)) | set(cpu.ram.keys())
            for k in allk:
                if STACK_LO <= k <= STACK_HI:    # task stack area
                    continue
                if cpu.ram.get(k, 0) != want.get(k, 0):
                    bad.append((k, cpu.ram.get(k, 0), want.get(k, 0)))
            if bad or cpu.r[0] != want_r0:
                print('MISMATCH seed=0x%X iter=%d: r0=%d want_r0=%d %s' %
                      (seed, it, cpu.r[0], want_r0,
                       {hex(k): (hex(g), hex(e)) for k, g, e in bad[:10]}))
                print('  A6A0=%r A728=%r C8A4=%r A754=%r A5E8=%r B2E8=%r A664=%r' %
                      (rdf(ram, A6A0), rdf(ram, A728), rdf(ram, C8A4),
                       rdf(ram, A754), rdf(ram, A5E8), rdf(ram, B2E8),
                       rdf(ram, A664)))
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
    print('OK  0x12576 calculateTrailingDerateRetard '
          '(%d random inputs across %d seeds)' % (N * len(seeds), len(seeds)))
    print('\nAll calculateTrailingDerateRetard_0x12576 tests passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()