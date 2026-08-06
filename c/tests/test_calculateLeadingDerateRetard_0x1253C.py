#!/usr/bin/env python3
"""test_calculateLeadingDerateRetard_0x1253C.py

Differential test for ROM 0x1253C (60E0FC00.bin) — lift
c/calculateLeadingDerateRetard_0x1253C.c.

Runs the ACTUAL ROM bytes of 0x1253C — including the real sub-call
saturateLow @0x23E4 — in tools/sh2emu.py over seeded RAM states (the oracle)
and compares the full post-call RAM overlay (byte-exact, task-stack window
0xFFFFDE00..DF00 skipped) plus the return register r0 against a Python
reference model that mirrors the C lift line-for-line.

Entry-point / range note: 0x1253C IS the real entry point (function-pointer
slot @0x144BC of the engineControlCalculateTiming dispatcher 0x141FC table;
valid prologue; preceding function calculateTrailingTimingBaseFinal ends rts
@0x12538).  The CSV range 0x1253C..0x12576 is CORRECT: code runs to rts
@0x12572 (delay @0x12574), the trailing twin 0x12576 starts exactly at the
CSV end.

Key semantic facts (see the lift header): void leading-timing derate-retard
writer, single-precision at every step:
  x = f32@A724 - f32@A69C
  x = x - max_0x23E4(f32@A750, f32@C8A0)     (NaN sig -> C8A0 reference)
  x = x + f32@A5E4 + f32@B2E4 - f32@A660
  f32@A644 = x
r0 at return: 0 — neither this function nor the 0x23E4 leaf ever writes r0
(the harness CPU starts with r0=0).

Run: python3 c/tests/test_calculateLeadingDerateRetard_0x1253C.py [N]
     (N = random inputs per seed; default 100000 -> 500000 across 5 seeds)
"""
import os, random, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2, ts

ROM = os.path.join(ROOT, 'roms', 'stock', '60E0FC00.bin')
ADDR = 0x1253C

# ---- RAM addresses (see c/calculateLeadingDerateRetard_0x1253C.c header) ----
A69C = 0xFFFFA69C   # f32 diff minuend base
A724 = 0xFFFFA724   # f32 diff minuend
C8A0 = 0xFFFFC8A0   # f32 leaf lower/limit
A750 = 0xFFFFA750   # f32 leaf sig
A5E4 = 0xFFFFA5E4   # f32 addend 1
B2E4 = 0xFFFFB2E4   # f32 addend 2
A660 = 0xFFFFA660   # f32 subtrahend
A644 = 0xFFFFA644   # f32 output

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
    """Line-for-line mirror of calculateLeadingDerateRetard_0x1253C().

    The 0x23E4 leaf is executed in `cpu2` (oracle) and its fr0 result merged;
    the fadd/fsub chain mirrors the emulator's single-precision rounding.
    Returns (RAM-effect dict, expected r0)."""
    m = dict(m)

    # x = f32@A724 - f32@A69C  (fsub fr3,fr2)
    x = ts(rdf(m, A724) - rdf(m, A69C))

    # x -= saturateLow(f32@A750, f32@C8A0)   (jsr @0x23E4 -> fr0, fsub fr0,fr12)
    cpu2.call(HELPER_MAX, fr={4: rdf(m, A750), 5: rdf(m, C8A0)}, ram=m)
    x = ts(x - cpu2.fr[0])

    # x += f32@A5E4 ; x += f32@B2E4 ; x -= f32@A660
    x = ts(x + rdf(m, A5E4))
    x = ts(x + rdf(m, B2E4))
    x = ts(x - rdf(m, A660))

    wrf(m, A644, x)                          # fmov.s fr12,@r3
    return m, 0                              # r0 untouched -> 0


def gen_state(rng):
    """Random seeded RAM hitting every float shape (finite spans, boundaries,
    denormals, infinities, NaN) for all 7 inputs; the output word is junk so
    a missed write is caught."""
    ram = {}
    for a in (A69C, A724, C8A0, A750, A5E4, B2E4, A660):
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
    setf(ram, A644, rng.uniform(-1000.0, 1000.0))   # junk output word
    return ram


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    rom = open(ROM, 'rb').read()

    cpu = SH2(rom)
    cpu2 = SH2(rom)          # dedicated instance for the 0x23E4 leaf in ref()
    seeds = (0x1253C, 0x12576, 0x144BC, 0xA644, 0x23E4)
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
                print('  A69C=%r A724=%r C8A0=%r A750=%r A5E4=%r B2E4=%r A660=%r' %
                      (rdf(ram, A69C), rdf(ram, A724), rdf(ram, C8A0),
                       rdf(ram, A750), rdf(ram, A5E4), rdf(ram, B2E4),
                       rdf(ram, A660)))
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
    print('OK  0x1253C calculateLeadingDerateRetard '
          '(%d random inputs across %d seeds)' % (N * len(seeds), len(seeds)))
    print('\nAll calculateLeadingDerateRetard_0x1253C tests passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()