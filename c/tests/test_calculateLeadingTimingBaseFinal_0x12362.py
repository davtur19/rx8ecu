#!/usr/bin/env python3
"""test_calculateLeadingTimingBaseFinal_0x12362.py

Differential test for ROM 0x12362 (60E0FC00.bin) — lift
c/calculateLeadingTimingBaseFinal_0x12362.c.

Runs the ACTUAL ROM bytes of 0x12362 — including the real sub-calls
saturateLow @0x23E4 and minValue @0x23F4 — in tools/sh2emu.py over seeded RAM
states (the oracle) and compares the full post-call RAM overlay (byte-exact,
task-stack window 0xFFFFDE00..DF00 skipped) plus the return register r0 against
a Python reference model that mirrors the C lift line-for-line.

Entry-point / range note: 0x12362 IS the real entry point (function-pointer
slot @0x144C0 of the engineControlCalculateTiming dispatcher 0x141FC table;
valid prologue; preceding function ends rts @0x1235E).  The CSV range
0x12362..0x12456 is CORRECT: code runs to rts @0x12452 (delay @0x12454), the
trailing twin 0x12456 starts exactly at the CSV end.

Key semantic facts (see the lift header): void leading-timing "base final"
ramp writer:
  fr5 = f32@A7AC + 10000.0f                  ; high
  flag@A65C = 1 if fr4(f32@B594) >= high ; 0 if fr4 < high-100 ; retain else
  x = f32@A640
  if u8@AAC6 == 1 && flag == 0:  x = max_0x23E4(x - 0.05f, 0.0f)
  else:                          x = min_0x23F4(x + 1.0f, 1.0f)
  f32@A640 = x
  f32@A63C = fmaf(1-x, (f32@A5F4+f32@A708)+f32@C99C, x*f32@A5EC)
             + f32@A780 - f32@A778
r0 at return = u8@AAC6 & 0xFF (mov.b/extu.b at the gateway check; the
0x23E4/0x23F4 leaves never write r0).

Run: python3 c/tests/test_calculateLeadingTimingBaseFinal_0x12362.py [N]
     (N = random inputs per seed; default 100000 -> 500000 across 5 seeds)
"""
import os, random, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2, ts

ROM = os.path.join(ROOT, 'roms', 'stock', '60E0FC00.bin')
ADDR = 0x12362

# ---- RAM addresses (see c/calculateLeadingTimingBaseFinal_0x12362.c header) ----
B594 = 0xFFFFB594   # f32 input (fr4)
A7AC = 0xFFFFA7AC   # f32 threshold base (fr5 = A7AC + 10000)
AAC6 = 0xFFFFAAC6   # u8 gateway byte (==1)
A65C = 0xFFFFA65C   # u8 hysteresis flag (read+write)
A640 = 0xFFFFA640   # f32 ramp value (read+write)
A708 = 0xFFFFA708   # f32 lerp S term 1
A5F4 = 0xFFFFA5F4   # f32 lerp S term 2
C99C = 0xFFFFC99C   # f32 lerp S term 3
A5EC = 0xFFFFA5EC   # f32 lerp x term
A780 = 0xFFFFA780   # f32 lerp addend
A778 = 0xFFFFA778   # f32 lerp subtrahend
A63C = 0xFFFFA63C   # f32 output

# Helper addresses called inline by the ROM
HELPER_MAX = 0x23E4   # saturateLow = max(fr4, fr5)
HELPER_MIN = 0x23F4   # minValue = min(fr4, fr5)

# ROM calibration constants
ROM_6E0B4 = 0x0006E0B4   # f32 10000.0 (high offset)
ROM_6E0B8 = 0x0006E0B8   # f32 100.0 (band width)
ROM_6E09C = 0x0006E09C   # f32 0.05 (ramp-down step)
ROM_6E0A0 = 0x0006E0A0   # f32 1.0 (ramp-up addend)

STACK_LO = 0xFFFFDE00    # task stack window (skipped in the compare)
STACK_HI = 0xFFFFDF00


def f32_at(rom, a):
    return struct.unpack('>f', rom[a:a + 4])[0]


def setf(m, a, v):
    for i, b in enumerate(struct.pack('>f', ts(v))):
        m[a + i] = b


def rdf(m, a):
    return struct.unpack('>f', bytes(m.get(a + i, 0) for i in range(4)))[0]


def rdfb(buf, a):
    return struct.unpack('>f', bytes(buf[a + i] for i in range(4)))[0]


def wrf(m, a, v):
    for i, b in enumerate(struct.pack('>f', ts(v))):
        m[a + i] = b


def ref(cpu2, m, rom):
    """Line-for-line mirror of calculateLeadingTimingBaseFinal_0x12362().

    The two 0x23xx leaves are executed in `cpu2` (oracle) and their fr0 result
    merged.  The hysteresis fcms and lerp fp ops mirror the emulator exactly.
    Returns (RAM-effect dict, expected r0)."""
    m = dict(m)

    fr4 = rdf(m, B594)                            # fmov.s @r2,fr4
    fr5 = ts(rdf(m, A7AC) + rdfb(rom, ROM_6E0B4)) # fadd -> high

    # flag hysteresis (fcmp/gt fr4,fr5 -> T=(fr5>fr4)); bt/s on T==1,
    # bf/s on T==0; NaN -> T=0 -> flag=1.
    if fr5 > fr4:                                # fr4 < high
        low = ts(fr5 - rdfb(rom, ROM_6E0B8))    # fsub -> low
        if low > fr4:                            # fr4 < low
            m[A65C] = 0                          # mov.b r0,@r4
        # else retain (pre-call A65C kept)
    else:
        m[A65C] = 1                              # mov.b r1,@r4

    # ramp rate-limit the per-tap value into A640
    x = rdf(m, A640)                             # fmov.s @r14,fr4 (delay)
    if m.get(AAC6, 0) == 1 and m.get(A65C, 0) == 0:
        cpu2.call(HELPER_MAX, fr={4: ts(x - rdfb(rom, ROM_6E09C)), 5: 0.0},
                  ram=m)
        v = cpu2.fr[0]
    else:
        cpu2.call(HELPER_MIN, fr={4: ts(rdfb(rom, ROM_6E0A0) + x), 5: 1.0},
                  ram=m)
        v = cpu2.fr[0]
    wrf(m, A640, v)                              # fmov.s fr0,@r14

    # lerp into f32@A63C (fmac = fused single rounding)
    x = rdf(m, A640)
    S = ts(ts(rdf(m, A5F4) + rdf(m, A708)) + rdf(m, C99C))
    comp = ts(1.0 - x)
    acc = ts(x * rdf(m, A5EC))
    acc = ts(comp * S + acc)                     # fmac (fused single rounding)
    acc = ts(acc + rdf(m, A780))
    acc = ts(acc - rdf(m, A778))
    wrf(m, A63C, acc)

    # r0 on return: mov.b/extu.b at the gateway check; leaves don't touch r0
    r0 = m.get(AAC6, 0) & 0xFF
    return m, r0


def gen_state(rng):
    """Random seeded RAM hitting every flag band, gateway/leaf branch and the
    lerp.  A7AC near 0 so high ~ 10000; B594 placed in each of the three flag
    bands plus NaN and the exact boundaries.  A640 samples the whole ramp
    dynamic range; the six lerp inputs are drawn around small magnitudes to
    exercise the fmac; AAC6 covers 1/0/other; A65C gets 0,1,junk (retain
    path); A63C is junk so a missed write is caught."""
    ram = {}

    base = rng.uniform(-2000.0, 2000.0)
    high = ts(base + 10000.0)                   # base + ROM 0x6E0B4 (10000.0)
    low = ts(high - 100.0)                      # high - ROM 0x6E0B8 (100.0)
    setf(ram, A7AC, base)

    r = rng.random()
    if r < 0.2:
        setf(ram, B594, high + rng.uniform(0.0, 2000.0))     # -> flag 1
    elif r < 0.4:
        setf(ram, B594, rng.uniform(low, high))              # retain band
    elif r < 0.6:
        setf(ram, B594, low - rng.uniform(0.0, 2000.0))     # -> flag 0
    elif r < 0.75:
        setf(ram, B594, rng.choice([high, low, 0.0, base]))
    elif r < 0.85:
        setf(ram, B594, float('nan'))
    else:
        setf(ram, B594, rng.uniform(-1e4, 1e4))

    r = rng.random()
    if r < 0.35:
        setf(ram, A640, rng.uniform(0.0, 1.0))
    elif r < 0.6:
        setf(ram, A640, rng.uniform(-2.0, 0.0))
    elif r < 0.8:
        setf(ram, A640, rng.choice([0.0, 1.0, 2.0, -1.0, 1000.0, -1000.0]))
    elif r < 0.9:
        setf(ram, A640, float('nan'))
    else:
        setf(ram, A640, rng.uniform(-1e4, 1e4))

    for a in (A708, A5F4, C99C, A5EC, A780, A778):
        r = rng.random()
        if r < 0.7:
            setf(ram, a, rng.uniform(-2.0, 2.0))
        elif r < 0.85:
            setf(ram, a, rng.choice([0.0, 1.0, -1.0, 0.5, -0.5]))
        elif r < 0.93:
            setf(ram, a, float('nan'))
        else:
            setf(ram, a, rng.uniform(-50.0, 50.0))

    r = rng.random()
    if r < 0.4:
        ram[AAC6] = 1
    elif r < 0.8:
        ram[AAC6] = 0
    else:
        ram[AAC6] = rng.randint(2, 255)

    ram[A65C] = rng.choice([0, 1, 0x55, 0xFF, rng.randint(0, 255)])

    setf(ram, A63C, rng.uniform(-1000.0, 1000.0))   # junk output word
    return ram


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    rom = open(ROM, 'rb').read()
    assert f32_at(rom, ROM_6E0B4) == 10000.0
    assert f32_at(rom, ROM_6E0B8) == 100.0
    assert f32_at(rom, ROM_6E09C) == ts(0.05)
    assert f32_at(rom, ROM_6E0A0) == 1.0

    cpu = SH2(rom)
    cpu2 = SH2(rom)          # dedicated instance for the 0x23xx leaves in ref()
    seeds = (0x12362, 0x12456, 0x144C0, 0xA640, 0x6E09C)
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
                if STACK_LO <= k <= STACK_HI:    # task stack area
                    continue
                if cpu.ram.get(k, 0) != want.get(k, 0):
                    bad.append((k, cpu.ram.get(k, 0), want.get(k, 0)))
            if bad or cpu.r[0] != want_r0:
                print('MISMATCH seed=0x%X iter=%d: r0=%d want_r0=%d %s' %
                      (seed, it, cpu.r[0], want_r0,
                       {hex(k): (hex(g), hex(e)) for k, g, e in bad[:10]}))
                print('  B594=%r A7AC=%r AAC6=%d A65C=%d A640=%r' %
                      (rdf(ram, B594), rdf(ram, A7AC), ram.get(AAC6, 0),
                       ram.get(A65C, 0), rdf(ram, A640)))
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
    print('OK  0x12362 calculateLeadingTimingBaseFinal '
          '(%d random inputs across %d seeds)' % (N * len(seeds), len(seeds)))
    print('\nAll calculateLeadingTimingBaseFinal_0x12362 tests passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()