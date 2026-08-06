#!/usr/bin/env python3
"""test_calc_combustion_chamber_temp_0x12938.py

Differential test for ROM 0x12938 (60E1D400.bin) — lift
c/calc_combustion_chamber_temp_0x12938.c.

Runs the ACTUAL ROM bytes of 0x12938 in tools/sh2emu.py over seeded RAM states
(the oracle) and compares the full post-call RAM overlay against a Python
reference model that mirrors the C lift line-for-line.

Entry-point note: 0x12938 IS the real entry point — the only ROM reference is
the function-pointer slot @0x14840 in the dispatcher engineControlCalculateTiming
(0x14584) dispatch table (c/engineControlCalculateTiming.c line 263).  Valid
prologue / rts+delay at 0x12A44/0x12A46; no branches into the body.

Key semantic facts (see the lift header):
  * void function — RAM side effects:
      u8@0xFFFFA66E  = (f32@C12C > 0.5f) ? 1 : ((f32@C12C > 0.45f) ? unchanged : 0)
      f32@0xFFFFA658 = output amount picked from the gates below
  * Three window-out calls on 0x2440 with (v=..., c=0.0, eps=1e-5@ROM 0x129CC):
      w1 = window(f32@A760), w2 = window(f32@A670), w3 = window(f32@CA10)
  * f32@A658 selection:
      u8@AADA == 1                -> (w2==0) ? -25.0 : -20.0
      else if w3==0 and w1==0     -> -58.5
      else                        -> (u8@A66E==1) ? -58.5 : -20.0
    ROM constants: -25.0@0x6E3E4, -20.0@0x6E3FC, -58.5@0x6E3E8,
                   -58.5@0x6E3EC, -20.0@0x6E400, 0.5@0x6E404, 0.05@0x6E408.
  * NaN semantics (see lift header): fcmp/gt clears T on NaN, so a NaN C12C
    makes the flag store 0 (both comparisons false).  The 0x2440 window leaf
    is executed in the second emulator instance cpu2 (oracle) — NaN inputs
    read as "inside the window" (w=0).

Run: python3 c/tests/test_calc_combustion_chamber_temp_0x12938.py [N]
     (N = random inputs per seed; default 100000 -> 500000 across 5 seeds)
"""
import os, random, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2, ts

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ADDR = 0x12938

# ---- RAM addresses (see c/calc_combustion_chamber_temp_0x12938.c header) ----
C12C = 0xFFFFC12C   # f32 hysteresis input (fr15)
A760 = 0xFFFFA760   # f32 chamber temp delta 1 (w1 input)
A670 = 0xFFFFA670   # f32 chamber temp delta 2 (w2 input)
CA10 = 0xFFFFCA10   # f32 knock-control output (w3 input)
AADA = 0xFFFFAADA   # u8  rotor-B enable gate (==1)
A66E = 0xFFFFA66E   # u8  knock flag (read+write)
A658 = 0xFFFFA658   # f32 combustion chamber temp output

ROM_EPS   = 0x000129CC   # f32 1e-5 (window epsilon)
ROM_6E404 = 0x0006E404   # f32 0.5 (hysteresis high threshold)
ROM_6E408 = 0x0006E408   # f32 0.05 (hysteresis band width)
ROM_6E3E4 = 0x0006E3E4   # f32 -25.0
ROM_6E3FC = 0x0006E3FC   # f32 -20.0
ROM_6E3E8 = 0x0006E3E8   # f32 -58.5
ROM_6E3EC = 0x0006E3EC   # f32 -58.5
ROM_6E400 = 0x0006E400   # f32 -20.0


def put(ram, a, n, v):
    for i in range(n):
        ram[a + i] = (v >> (8 * (n - 1 - i))) & 0xFF


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


def ref(cpu2, m, rom, eps=ROM_EPS):
    """Line-for-line mirror of calc_combustion_chamber_temp_0x12938().

    The three 0x2440 window-out calls are executed in `cpu2` (oracle) and their
    RAM merged; the hysteresis fcms mirror the emulator's fcmp/gt (NaN -> T=0).
    Returns the RAM-effect dict.
    """
    m = dict(m)

    fr15 = rdf(m, C12C)                  # fmov.s @r2,fr15 @0x12950

    # 3x window-out 0x2440 (fr4=v, fr5=0.0, fr6=eps)
    cpu2.call(0x2440, fr={4: rdf(m, A760), 5: 0.0, 6: rdfb(rom, eps)}, ram=m)
    m = dict(cpu2.ram); w1 = cpu2.r[0]
    cpu2.call(0x2440, fr={4: rdf(m, A670), 5: 0.0, 6: rdfb(rom, eps)}, ram=m)
    m = dict(cpu2.ram); w2 = cpu2.r[0]
    cpu2.call(0x2440, fr={4: rdf(m, CA10), 5: 0.0, 6: rdfb(rom, eps)}, ram=m)
    m = dict(cpu2.ram); w3 = cpu2.r[0]

    # 0x12976/0x129DE: flag hysteresis — fcmp/gt fr4,fr15 -> T=(fr15>fr4)
    #   T=(fr15>0.5)  -> store 1   (bf/s on T==0)
    #   T=(fr15>0.45) -> unchanged (bt/s skips the store-0)
    #   else          -> store 0   (NaN C12C lands here)
    half_band = ts(rdfb(rom, ROM_6E404) - rdfb(rom, ROM_6E408))   # 0.5f - 0.05f
    if fr15 > rdfb(rom, ROM_6E404):
        m[A66E] = 1
    elif fr15 > half_band:
        pass
    else:
        m[A66E] = 0

    # 0x129E8..0x12A38: output amount into f32@A658
    if m.get(AADA, 0) == 1:
        wrf(m, A658, rdfb(rom, ROM_6E3E4) if w2 == 0 else rdfb(rom, ROM_6E3FC))
    elif w3 == 0 and w1 == 0:
        wrf(m, A658, rdfb(rom, ROM_6E3E8))
    else:
        wrf(m, A658, rdfb(rom, ROM_6E3EC) if m.get(A66E, 0) == 1
            else rdfb(rom, ROM_6E400))
    return m


def gen_state(rng):
    """Random seeded RAM hitting every flag-hysteresis and output branch.

    C12C is sampled across all three hysteresis bands (flag=1 / unchanged /
    flag=0) plus NaN and the exact 0.5/0.45 boundaries; the three window inputs
    are biased toward |v|<=1e-5 (w=0) with excursions outside (w=1) and NaN;
    AADA covers 1/0/other; A66E gets 0,1,junk and the output float is junk so a
    missed write is caught.
    """
    ram = {}

    # hysteresis input (fr15)
    r = rng.random()
    if r < 0.2:
        setf(ram, C12C, rng.uniform(0.5, 2.0))          # flag -> 1
    elif r < 0.4:
        setf(ram, C12C, rng.uniform(0.45, 0.5))         # unchanged band
    elif r < 0.6:
        setf(ram, C12C, rng.uniform(-1.0, 0.45))        # flag -> 0
    elif r < 0.75:
        setf(ram, C12C, rng.choice([0.5, 0.45, 0.0, 1.0]))  # boundaries
    elif r < 0.85:
        setf(ram, C12C, float('nan'))
    else:
        setf(ram, C12C, rng.uniform(-5.0, 5.0))

    # window inputs: mostly |v|<=1e-5 (w=0), excursions (w=1), NaN
    for a in (A760, A670, CA10):
        r = rng.random()
        if r < 0.4:
            setf(ram, a, rng.uniform(-1e-5, 1e-5))
        elif r < 0.7:
            setf(ram, a, rng.uniform(-1e-4, 1e-4))
        elif r < 0.85:
            setf(ram, a, rng.choice([0.0, 1e-5, -1e-5, 1.0, -1.0]))
        elif r < 0.93:
            setf(ram, a, float('nan'))
        else:
            setf(ram, a, rng.uniform(-2.0, 2.0))

    # rotor-B enable gate
    r = rng.random()
    if r < 0.4:
        ram[AADA] = 1
    elif r < 0.8:
        ram[AADA] = 0
    else:
        ram[AADA] = rng.randint(2, 255)

    # flag byte: 0, 1, junk (also exercises the unchanged-band retain path)
    ram[A66E] = rng.choice([0, 1, 0x55, 0xFF, rng.randint(0, 255)])

    # output float: junk so a missed write is caught
    setf(ram, A658, rng.uniform(-1000.0, 1000.0))
    return ram


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    rom = open(ROM, 'rb').read()

    cpu = SH2(rom)
    cpu2 = SH2(rom)          # dedicated instance for the 0x2440 leaves in ref()
    seeds = (0x12938, 0x128C4, 0x128FE, 0xA66E, 0x6E3E4)
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
                print('  C12C=%r AADA=%d A66E=%r w1=%r w2=%r w3=%r' % (
                    rdf(ram, C12C), ram.get(AADA, 0), ram.get(A66E, 0),
                    None, None, None))
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
    print('OK  0x12938 calc_combustion_chamber_temp '
          '(%d random inputs across %d seeds)' % (N * len(seeds), len(seeds)))
    print('\nAll calc_combustion_chamber_temp_0x12938 tests passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()
