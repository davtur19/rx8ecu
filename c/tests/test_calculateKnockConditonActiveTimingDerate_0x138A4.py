#!/usr/bin/env python3
"""test_calculateKnockConditonActiveTimingDerate_0x138A4.py

Differential test for ROM 0x138A4 (60E0FC00.bin) — lift
c/calculateKnockConditonActiveTimingDerate_0x138A4.c.

Runs the ACTUAL ROM bytes of 0x138A4 — including the real sub-calls
limitKnockRetardMax_CalValue @0x13B4A, limitKnockRetardMax_ConditonalRPM
@0x13AE4, saturateBetweenKnockRetardMinMaxTables @0x13B5E and the 2D lookup
@0x2068 they embed — in tools/sh2emu.py over seeded RAM states (the oracle)
and compares the full post-call RAM overlay (byte-exact, task-stack window
0xFFFFDE00..DF00 skipped) plus the return register r0 against a Python
reference model.  The sub-calls are executed in a dedicated emulator instance
`cpu2` seeded with the same RAM so rounding matches the ROM exactly.

Entry-point / range note: 0x138A4 IS the real entry point (function-pointer
slot @0x1441C of the engineControlCalculateTiming dispatcher 0x141FC table;
valid prologue; preceding updateKnockMaxRAM ends rts @0x138A0).  CSV range
0x138A4..0x139B4 is CORRECT (code to rts @0x13970, pool to 0x139B2, next fn @0x139B4).

Key semantic facts (see the lift header): void knock-derate writer.
  fr15 <- f32@A734 ; fr4 <- f32@A72C
  u8@A738==0                         -> fr15=0, fr4=0
  elif u8@A739==0:   fr15 = 2D(RPM@B594, desc 0x693E0); f32@A73C=fr15; fr4=0
  elif u8@A74C==0:   fr15 = 0 (if u8@A730==1)
  else:              fr4 -= 2.5 (if u8@A730==1 and u8@C073>=ROM78547==1)
                     fr15 -= 1.0 (if u8@A730==1 and u8@C070==1)
  f32@A72C = 13B4A(fr4)   f32@A734 = 13AE4(fr15)
  f32@A724 = f32@A728 = 13B5E(f32@A734+f32@A72C)
  u8@A74C  = u8@A730
r0 at return = r0 left by the last sub-call (bsr 0x13B5E; its final 0x2404
leaf is pure-FPU so r0 is the index*4 of the last 2D lookup @0x69408).

Run: python3 c/tests/test_calculateKnockConditonActiveTimingDerate_0x138A4.py [N]
      (N = random inputs per seed; default 100000 -> 500000 across 5 seeds)
"""
import os, random, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2, ts

ROM = os.path.join(ROOT, 'roms', 'stock', '60E0FC00.bin')
ADDR = 0x138A4

# ---- RAM addresses (see c/calculateKnockConditonActiveTimingDerate_0x138A4.c) ----
A734 = 0xFFFFA734   # f32 in / out (retard 2)
A72C = 0xFFFFA72C   # f32 in / out (retard 1)
A73C = 0xFFFFA73C   # f32 out (path A739==0 lookup)
A724 = 0xFFFFA724   # f32 out (saturated)
A728 = 0xFFFFA728   # f32 out (twin)
A730 = 0xFFFFA730   # u8 gate / out (stored -> A74C)
A738 = 0xFFFFA738   # u8 gate
A739 = 0xFFFFA739   # u8 gate
A74C = 0xFFFFA74C   # u8 gate / out
B594 = 0xFFFFB594   # f32 RPM (2D x)
C073 = 0xFFFFC073   # u8 gate (A730==1)
C070 = 0xFFFFC070   # u8 gate (A730==1)
A740 = 0xFFFFA740   # f32 (written by sub-call 0x13B5E)
A744 = 0xFFFFA744   # f32 (written by sub-call 0x13B5E)

FLOAT_RW = [A734, A72C, A73C, A724, A728, A740, A744, B594]
BYTE_GATES = [A730, A738, A739, A74C, C073, C070]

STACK_LO = 0xFFFFDE00      # task stack window (skipped in the compare)
STACK_HI = 0xFFFFDF00


def romf(rom, a):
    return struct.unpack('>f', rom[a:a + 4])[0]


def gf(m, a):
    return struct.unpack('>f', bytes(m.get(a + i, 0) for i in range(4)))[0]


def setf(m, a, v):
    for i, b in enumerate(struct.pack('>f', ts(v))):
        m[a + i] = b


def gb(m, a):
    return m.get(a, 0)


def merge(cpu2, m):
    """Take cpu2's RAM back into the reference state, dropping the task stack."""
    return {k: v for k, v in cpu2.ram.items() if not (STACK_LO <= k <= STACK_HI)}


def ref(cpu2, m, rom):
    """Line-for-line mirror of calculateKnockConditonActiveTimingDerate_0x138A4().
    Returns (RAM-effect dict, expected r0)."""
    m = dict(m)
    a72c = gf(m, A72C)
    a734 = gf(m, A734)
    a730 = gb(m, A730)
    fr4 = a72c            # fr6 <- f32@A72C ; fr4 <- fr6
    fr15 = a734           # fr5 <- f32@A734 ; fr15 <- fr5

    # ---- fan-in selection ----
    if gb(m, A738) == 0:
        fr15 = 0.0; fr4 = 0.0
    elif gb(m, A739) == 0:
        cpu2.call(0x2068, r4=0x693E0, fr={4: gf(m, B594)}, ram=dict(m))
        m = merge(cpu2, m)
        fr15 = cpu2.fr[0]
        setf(m, A73C, fr15)
        fr4 = 0.0
    elif gb(m, A74C) == 0:
        if a730 == 1:
            fr15 = romf(rom, 0x78588)          # 0.0
            fr4 = 0.0
    else:
        if a730 == 1:
            if gb(m, C073) >= rom[0x78547]:    # cal byte 78547 == 1
                fr4 = ts(fr4 - romf(rom, 0x7859C))   # -2.5
            if gb(m, C070) == 1:
                fr15 = ts(fr15 - romf(rom, 0x78594)) # -1.0

    # ---- bsr 0x13B4A (fr4): clamp into [785A8, 785AC] -> A72C ----
    cpu2.call(0x13B4A, fr={4: fr4}, ram=dict(m))
    m = merge(cpu2, m)
    a72c_n = cpu2.fr[0]
    setf(m, A72C, a72c_n)

    # ---- bsr 0x13AE4 (fr4 = fr15): clamp(fr15, 2D(B594), 78584) -> A734 ----
    cpu2.call(0x13AE4, fr={4: fr15}, ram=dict(m))
    m = merge(cpu2, m)
    a734_n = cpu2.fr[0]
    setf(m, A734, a734_n)

    # ---- bsr 0x13B5E (fr4 = A734 + A72C): clamp -> A724/A728 ----
    fr4_final = ts(a734_n + a72c_n)
    cpu2.call(0x13B5E, fr={4: fr4_final}, ram=dict(m))
    r0 = cpu2.r[0]
    m = merge(cpu2, m)          # includes A740/A744 writes
    out = cpu2.fr[0]
    setf(m, A724, out)
    setf(m, A728, out)

    m[A74C] = a730 & 0xFF       # mov.b r14,@A74C (low byte)
    return m, r0


def pick_f(rng):
    """Float pool: wide spans plus map/edge values and NaN/Inf."""
    return rng.choice([
        rng.uniform(-400, 400),
        rng.uniform(1500, 8000),
        rng.uniform(-200, 200),
        0.0, -0.0, 5.0, -5.0, 1e-6, -1e-6, 3.4e38, -3.4e38,
        float('nan'), float('inf'), float('-inf'),
    ])


def gen_state(rng):
    """Random seeded RAM hitting every branch combination; every output word
    is junk so a missed write is caught."""
    ram = {}
    for a in FLOAT_RW:
        setf(ram, a, pick_f(rng))
    # bytes: bias so all gate combos are covered
    ram[A730] = rng.choice([0, 1, 1, 1, 2, 0xFF])
    ram[A738] = rng.choice([0, 0, 1, 1, 1, 2])
    ram[A739] = rng.choice([0, 0, 1, 1, 1, 2])
    ram[A74C] = rng.choice([0, 0, 1, 1, 2])
    ram[C073] = rng.choice([0, 0, 1, 1, 2])
    ram[C070] = rng.choice([0, 0, 1, 1, 2])
    return ram


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    rom = open(ROM, 'rb').read()
    # sanity on the ROM constants used by our reference
    assert romf(rom, 0x78588) == 0.0
    assert romf(rom, 0x7858C) == 1.0
    assert romf(rom, 0x78594) == 1.0
    assert romf(rom, 0x7859C) == 2.5
    assert rom[0x78547] == 1

    cpu = SH2(rom)
    cpu2 = SH2(rom)             # dedicated instance for the sub-calls in ref()
    seeds = (0x138A4, 0x13B5E, 0x693E0, 0xA72C, 0x7859C)
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
                print('  A734=%r A72C=%r B594=%r A730=%d A738=%d A739=%d '
                      'A74C=%d C073=%d C070=%d' %
                      (gf(ram, A734), gf(ram, A72C), gf(ram, B594),
                       ram.get(A730, 0), ram.get(A738, 0), ram.get(A739, 0),
                       ram.get(A74C, 0), ram.get(C073, 0), ram.get(C070, 0)))
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
    print('OK  0x138A4 calculateKnockConditonActiveTimingDerate '
          '(%d random inputs across %d seeds)' % (N * len(seeds), len(seeds)))
    print('\nAll calculateKnockConditonActiveTimingDerate_0x138A4 tests passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()