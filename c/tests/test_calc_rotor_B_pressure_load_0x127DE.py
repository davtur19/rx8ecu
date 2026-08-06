#!/usr/bin/env python3
"""test_calc_rotor_B_pressure_load_0x127DE.py

Differential test for ROM 0x127DE (60E1D400.bin) — lift
c/calc_rotor_B_pressure_load_0x127DE.c.

Runs the ACTUAL ROM bytes of 0x127DE in tools/sh2emu.py over seeded RAM states
(the oracle) and compares the full post-call RAM overlay against a Python
reference model that mirrors the C lift line-for-line.

Entry-point note: 0x127DE IS the real entry point — the only ROM reference is
the function-pointer slot @0x1485C in the dispatcher engineControlCalculateTiming
(0x14584) dispatch table (c/engineControlCalculateTiming.c line 270).  Valid
prologue / rts+delay at 0x128C0/0x128C2; no branches into the body.

Key semantic facts (see the lift header):
  * void function — RAM side effects:
      u8@0xFFFFA66D  = hysteresis flag on f32@B5B8 vs high = f32@A7BC+10000
                         (fr4>=high -> 1, fr4<high-100 -> 0, else retain)
      f32@0xFFFFA660 = rate-limited intermediate (max/min leaves 0x23xx)
      f32@0xFFFFA65C = rotor-B pressure-load lerp:
                         (1-x)*S + x*f32@A5F0 + f32@A794 - f32@A78C
                         S = f32@CB10 + f32@A71C + f32@A5F8
  * Same raw input (B5B8), threshold base (A7BC), threshold consts and gate
    (AADA) as the rotor-A twin 0x126EA; differs only in the per-rotor RAM
    addresses and the decay/add ROM constant addresses (0x6E410/0x6E414).
  * Two sub-calls 0x23E4 (max) / 0x23F4 (min), selected by the flag/gate; they
    are executed in the second emulator instance cpu2 (oracle).
  * NaN semantics: identical to the rotor-A twin (see lift header).

Run: python3 c/tests/test_calc_rotor_B_pressure_load_0x127DE.py [N]
     (N = random inputs per seed; default 100000 -> 500000 across 5 seeds)
"""
import os, random, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2, ts

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ADDR = 0x127DE

# ---- RAM addresses (see c/calc_rotor_B_pressure_load_0x127DE.c header) ----
B5B8 = 0xFFFFB5B8   # f32 raw input (fr4)
A7BC = 0xFFFFA7BC   # f32 threshold base (fr5 = A7BC + 10000)
AADA = 0xFFFFAADA   # u8  rotor gate (==1)
A66D = 0xFFFFA66D   # u8  flag (read+write)
A660 = 0xFFFFA660   # f32 intermediate filter output
A71C = 0xFFFFA71C   # f32 lerp S term 1
A5F8 = 0xFFFFA5F8   # f32 lerp S term 2
CB10 = 0xFFFFCB10   # f32 lerp S term 3
A5F0 = 0xFFFFA5F0   # f32 lerp x term
A794 = 0xFFFFA794   # f32 lerp addend
A78C = 0xFFFFA78C   # f32 lerp subtrahend
A65C = 0xFFFFA65C   # f32 rotor-B pressure load output

# Helper addresses called inline by the ROM
HELPER_MAX = 0x23E4   # max(fr4, fr5)
HELPER_MIN = 0x23F4   # min(fr4, fr5)

ROM_6E3F4 = 0x0006E3F4   # f32 10000.0 (high offset)
ROM_6E3F8 = 0x0006E3F8   # f32 100.0 (band width)
ROM_6E410 = 0x0006E410   # f32 0.05 (gate decay step)
ROM_6E414 = 0x0006E414   # f32 1.0 (gate-else addend)


def setf(ram, a, v):
    for i, b in enumerate(struct.pack('>f', ts(v))):
        ram[a + i] = b


def rdf(m, a):
    return struct.unpack('>f', bytes(m.get(a + i, 0) for i in range(4)))[0]


def rdfb(buf, a):
    return struct.unpack('>f', bytes(buf[a + i] for i in range(4)))[0]


def wrf(m, a, v):
    for i, b in enumerate(struct.pack('>f', ts(v))):
        m[a + i] = b


def ref(cpu2, m, rom):
    """Line-for-line mirror of calc_rotor_B_pressure_load_0x127DE().

    Identical shape to the rotor-A twin (0x126EA) — see that test header —
    with the rotor-B RAM addresses.  Returns the RAM-effect dict.
    """
    m = dict(m)

    fr4 = rdf(m, B5B8)                          # fmov.s @r2,fr4
    fr5 = ts(rdf(m, A7BC) + rdfb(rom, ROM_6E3F4))  # fadd -> high

    # flag hysteresis (fcmp/gt fr4,fr5 -> T=(fr5>fr4)); bt/s on T==1,
    # bf/s on T==0; NaN -> T=0 -> flag=1.
    if fr5 > fr4:                              # fr4 < high
        low = ts(fr5 - rdfb(rom, ROM_6E3F8))  # fsub -> low
        if low > fr4:                          # fr4 < low
            m[A66D] = 0                        # mov.b r0,@r4
        # else retain (pre-call A66D kept)
    else:
        m[A66D] = 1                            # mov.b r1,@r4

    # rate-limit intermediate into A660 (gate-path uses helper max/min)
    x = rdf(m, A660)
    if m.get(AADA, 0) == 1 and m.get(A66D, 0) == 0:
        cpu2.call(HELPER_MAX, fr={4: ts(x - rdfb(rom, ROM_6E410)), 5: 0.0},
                  ram=m)
        v = cpu2.fr[0]
    else:
        cpu2.call(HELPER_MIN, fr={4: ts(rdfb(rom, ROM_6E414) + x), 5: 1.0},
                  ram=m)
        v = cpu2.fr[0]
    wrf(m, A660, v)

    # lerp into f32@A65C
    x = rdf(m, A660)
    S = ts(ts(rdf(m, A71C) + rdf(m, A5F8)) + rdf(m, CB10))
    comp = ts(1.0 - x)
    acc = ts(x * rdf(m, A5F0))
    acc = ts(comp * S + acc)                 # fmac (fused single rounding)
    acc = ts(acc + rdf(m, A794))
    acc = ts(acc - rdf(m, A78C))
    wrf(m, A65C, acc)
    return m


def gen_state(rng):
    """Random seeded RAM hitting every flag band, gate/leaf branch and the lerp.

    Same sampler as the rotor-A twin test (see test header).
    """
    ram = {}

    # threshold base near 0 so high ~ 10000 (band width = 100)
    base = rng.uniform(-2000.0, 2000.0)
    high = ts(base + 10000.0)                   # base + ROM 0x6E3F4 (10000.0)
    low = ts(high - 100.0)                      # high - ROM 0x6E3F8 (100.0)
    setf(ram, A7BC, base)

    r = rng.random()
    if r < 0.2:
        setf(ram, B5B8, high + rng.uniform(0.0, 2000.0))      # -> flag 1
    elif r < 0.4:
        setf(ram, B5B8, rng.uniform(low, high))               # retain band
    elif r < 0.6:
        setf(ram, B5B8, low - rng.uniform(0.0, 2000.0))      # -> flag 0
    elif r < 0.75:
        setf(ram, B5B8, rng.choice([high, low, 0.0, base]))
    elif r < 0.85:
        setf(ram, B5B8, float('nan'))
    else:
        setf(ram, B5B8, rng.uniform(-1e4, 1e4))

    # intermediate filter dynamic (x ranges hidden early/late)
    r = rng.random()
    if r < 0.35:
        setf(ram, A660, rng.uniform(0.0, 1.0))
    elif r < 0.6:
        setf(ram, A660, rng.uniform(-2.0, 0.0))
    elif r < 0.8:
        setf(ram, A660, rng.choice([0.0, 1.0, 2.0, -1.0, 1000.0, -1000.0]))
    elif r < 0.9:
        setf(ram, A660, float('nan'))
    else:
        setf(ram, A660, rng.uniform(-1e4, 1e4))

    # six lerp inputs (S terms, x term, addend, subtrahend)
    for a in (A71C, A5F8, CB10, A5F0, A794, A78C):
        r = rng.random()
        if r < 0.7:
            setf(ram, a, rng.uniform(-2.0, 2.0))
        elif r < 0.85:
            setf(ram, a, rng.choice([0.0, 1.0, -1.0, 0.5, -0.5]))
        elif r < 0.93:
            setf(ram, a, float('nan'))
        else:
            setf(ram, a, rng.uniform(-50.0, 50.0))

    # rotor gate
    r = rng.random()
    if r < 0.4:
        ram[AADA] = 1
    elif r < 0.8:
        ram[AADA] = 0
    else:
        ram[AADA] = rng.randint(2, 255)

    # flag byte: pre-call junk also covers the retain band
    ram[A66D] = rng.choice([0, 1, 0x55, 0xFF, rng.randint(0, 255)])

    # output float: junk so a missed write is caught
    setf(ram, A65C, rng.uniform(-1000.0, 1000.0))
    return ram


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    rom = open(ROM, 'rb').read()

    cpu = SH2(rom)
    cpu2 = SH2(rom)          # dedicated instance for the 0x23xx leaves in ref()
    seeds = (0x127DE, 0x128C4, 0x128FE, 0xA660, 0x6E410)
    total_fails = 0

    for seed in seeds:
        rng = random.Random(seed)
        fails = 0
        for it in range(N):
            ram = gen_state(rng)
            want = ref(cpu2, ram, rom)
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
                      (seed, it, {hex(k): (hex(g), hex(e))
                                  for k, g, e in bad[:12]}))
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
    print('OK  0x127DE calc_rotor_B_pressure_load '
          '(%d random inputs across %d seeds)' % (N * len(seeds), len(seeds)))
    print('\nAll calc_rotor_B_pressure_load_0x127DE tests passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()