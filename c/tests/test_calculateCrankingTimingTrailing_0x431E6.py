#!/usr/bin/env python3
"""test_calculateCrankingTimingTrailing_0x431E6.py

Differential test for ROM 0x431E6 (60E0FC00.bin) — lift
c/calculateCrankingTimingTrailing_0x431E6.c.

Runs the ACTUAL ROM bytes of 0x431E6 — including the real sub-calls
TwoDLookup @0x2068 and one of {minValue @0x23F4 + ratio @0x3E0AC} or
filters @0x23B0, all executed inside the emulator against the real ROM
descriptor @0x699E0 — in tools/sh2emu.py over seeded RAM states (the oracle)
and compares the full post-call RAM overlay (byte-exact, task-stack window
0xFFFFDE00..DF00 skipped) plus the return register r0 against a Python
reference model that mirrors the C lift line-for-line.

Entry/range: 0x431E6 IS the real entry (dispatcher slot @0x14450 of the
engineControlCalculateTiming table; valid prologue; preceding fn
calculateCrankingTimingLeading ends rts @0x431E2). CSV range 0x431E6..0x432B0
CORRECT: code to rts @0x432A8 (delay @0x432AA), next function apvVoltageRange
at 0x432B0; this fn OWNS the shared twin literal pool @0x43250..0x432AE.

Semantics (see lift header): cranking TRAILING advance driver — structural
twin of 0x43168 with outputs f32@C9A8 (temp) / f32@C9A0 (final), state
u8@FFFFC9AD, desc 0x699E0, consts +1.0 @0x7979C / @0x797A0. If the two gate
bytes u8@AAC6==1 && u8@B588==1:
  C9A8 = TwoDLookup(desc 0x699E0, x=A9FC)         9-pt u8 flat temp map *0.5 -50
  if u8@C9AD == 0:  C9A0 = ratio( twoD, minValue(+1.0,+1.0)=1.0 )   (two/1.0)
  else:             C9A0 = filters(twoD, old C9A0, 1.0, 1.0e-5)     (passthrough)
  u8@C9AD = u8@B588
else (early exit):  C9A8 = 0 ; C9A0 = 0 ; u8@C9AD = u8@B58
r0 diagnostics: 0x0007979C (state==0 path), (bits of f32@C9A0 & 0x7F800000)
on the latched path, or the failing gate byte & 0xFF on early exit.

Run: python3 c/tests/test_calculateCrankingTimingTrailing_0x431E6.py [N]
"""
import os, random, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2, ts

ROM = os.path.join(ROOT, 'roms', 'stock', '60E0FC00.bin')
ADDR = 0x431E6

# ---- RAM addresses (see c/calculateCrankingTimingTrailing_0x431E6.c) ----
AAC6 = 0xFFFFAAC6   # u8 gateway in  (==1)
B588 = 0xFFFFB588   # u8 crank gate  (==1)
A9FC = 0xFFFFA9FC   # f32 temp in
C9AD = 0xFFFFC9AD   # u8 state latch in/out
C9A8 = 0xFFFFC9A8   # f32 working out
C9A0 = 0xFFFFC9A0   # f32 final out

DESC = 0x699E0      # TwoDLookup 9-pt u8 flat temp map
CONST_P = 0x7979C   # +1.0 (state==0 min upper) -> r0 on state==0 path
FLOAT_IN  = [A9FC]
FLOAT_OUT = [C9A8, C9A0]
BYTE_IN   = [AAC6, B588, C9AD]
STACK_LO = 0xFFFFDE00
STACK_HI = 0xFFFFDF00


def r32(d, a):
    return struct.unpack('>f', bytes(d.get(a + i, 0) for i in range(4)))[0]


def f32b(v):
    return list(struct.pack('>f', ts(v)))


def wrf(m, a, v):
    for i, b in enumerate(struct.pack('>f', ts(v))):
        m[a + i] = b


def ref(cpu2, m, rom):
    m = dict(m)
    aac6 = m.get(AAC6, 0)
    b588 = m.get(B588, 0)
    a9fc = r32(m, A9FC)
    c9ad = m.get(C9AD, 0)
    final_prev = r32(m, C9A0)

    if aac6 == 1 and b588 == 1:
        cpu2.call(0x2068, r4=DESC, fr={4: a9fc})
        two = cpu2.fr[0]
        wrf(m, C9A8, two)
        if c9ad == 0:
            cpu2.call(0x23F4, fr={4: 1.0, 5: 1.0})
            c = cpu2.fr[0]
            cpu2.call(0x3E0AC, fr={4: two, 5: c})
            wrf(m, C9A0, cpu2.fr[0])
            want_r0 = 0x0007979C            # mov.l @PARAM ,r0 from the ROM unit
        else:
            cpu2.call(0x23B0, fr={4: two, 5: final_prev, 6: 1.0, 7: 1.0e-5})
            wrf(m, C9A0, cpu2.fr[0])
            want_r0 = cpu2.r[0]
        m[C9AD] = b588 & 0xFF
        return m, want_r0

    wrf(m, C9A8, 0.0)
    wrf(m, C9A0, 0.0)
    m[C9AD] = b588 & 0xFF
    want_r0 = (aac6 & 0xFF) if aac6 != 1 else (b588 & 0xFF)
    return m, want_r0


def gen_state(rng):
    ram = {}

    def setf(a, v):
        for i, b in enumerate(struct.pack('>f', float(v))):
            ram[a + i] = b

    def fuzz(a, lo, hi):
        r = rng.random()
        if r < 0.7:
            setf(a, rng.uniform(lo, hi))
        elif r < 0.85:
            setf(a, rng.choice([lo, hi, 0.0, (lo + hi) / 2.0]))
        elif r < 0.93:
            setf(a, float('nan'))
        else:
            setf(a, rng.uniform(-200, 200))

    fuzz(A9FC, -40, 120)        # temp axis -40..120
    ram[AAC6] = rng.choice([0, 1, rng.randint(2, 255)])
    ram[B588] = rng.choice([0, 1, rng.randint(2, 255)])
    ram[C9AD] = rng.choice([0, 1, rng.randint(2, 255)])
    for a in FLOAT_OUT:
        setf(a, rng.uniform(-200, 200))
    return ram


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    rom = open(ROM, 'rb').read()
    assert struct.unpack('>f', rom[0x7979C:0x797A0])[0] == 1.0
    assert struct.unpack('>f', rom[0x797A0:0x797A4])[0] == 1.0
    assert rom[DESC + 2] == 4
    n = struct.unpack('>H', rom[DESC:DESC + 2])[0]
    assert n == 9

    cpu = SH2(rom)
    cpu2 = SH2(rom)          # dedicated instance for the helper leaves in ref()
    seeds = (0x431E6, 0x43168, 0x699E0, 0xFFFFC9A0, 0xFFFFAAC6)
    total_fails = 0

    for seed in seeds:
        rng = random.Random(seed)
        fails = 0
        for it in range(N):
            ram = gen_state(rng)
            want, want_r0 = ref(cpu2, ram, rom)
            try:
                cpu.call(ADDR, ram=ram)
            except Exception as e:
                print('EMULATOR EXC seed=0x%X iter=%d: %s' % (seed, it, e))
                fails += 1
                break
            bad = []
            allk = set(k for k in want if isinstance(k, int)) | set(cpu.ram.keys())
            for k in allk:
                if STACK_LO <= k <= STACK_HI:
                    continue
                if cpu.ram.get(k, 0) != want.get(k, 0):
                    bad.append((k, cpu.ram.get(k, 0), want.get(k, 0)))
            if bad or cpu.r[0] != want_r0:
                print('MISMATCH seed=0x%X iter=%d: r0=%d want_r0=%d %s' %
                      (seed, it, cpu.r[0], want_r0,
                       {hex(k): (hex(g), hex(e)) for k, g, e in bad[:10]}))
                print('  AAC6=%d B588=%d A9FC=%r C9AD=%r C9A0_prev=%r' %
                      (ram.get(AAC6, 0), ram.get(B588, 0), r32(ram, A9FC),
                       ram.get(C9AD, 0), r32(ram, C9A0)))
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
    print('OK  0x431E6 calculateCrankingTimingTrailing '
          '(%d random inputs across %d seeds)' % (N * len(seeds), len(seeds)))
    print('\nAll calculateCrankingTimingTrailing_0x431E6 tests passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()