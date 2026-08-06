#!/usr/bin/env python3
"""test_idleLeadingTimingCorrection_0x13414.py

Differential test for ROM 0x13414 (60E0FC00.bin) — lift
c/idleLeadingTimingCorrection_0x13414.c.

Runs the ACTUAL ROM bytes of 0x13414 — including the real sub-calls 2D lookup
@0x2068 and saturate @0x2404 — in tools/sh2emu.py over seeded RAM states (the
oracle) and compares the full post-call RAM overlay (byte-exact, task-stack
window 0xFFFFDE00..DF00 skipped) plus the return register r0 against a Python
reference model.  The sub-calls are executed in a dedicated emulator instance
`cpu2` seeded with the same RAM so single-precision rounding matches the ROM.

Entry-point / range note: 0x13414 IS the real entry point (function-pointer
slot @0x14428 of the engineControlCalculateTiming dispatcher 0x141FC table;
valid prologue; preceding calc_fuel_trim_correction_map ends rts @0x13410).
CSV range 0x13414..0x13544 is CORRECT (code to rts @0x134F4, pool to 0x13542,
trailing twin 0x13544 starts exactly at the CSV end).

Key semantic facts (see the lift header): void idle leading-timing writer.
  fr2  = ts(B594 - B5A0); A718 = fr2
  desc = (B580==0) ? (B588==0 ? 0x686AC : 0x686C0)
                   : (B586==1 ? 0x686AC : 0x686C0)
  res  = 2D(desc, fr2); A710 = res
  fr15 = res if (AAC6==1 && B594 > 1500.0 &&
                 (C030 > 0.009765625 || word A424 >= 375)) else 0.0
  load gate A720: 1 if C0D8 <= 0.6, 0 if C0D8 > 0.555, else unchanged
  fr15 = saturate(fr15, -2.8, 0.7) if A720 == 1
  A708 = fr15
r0 at return = u8@A720 & 0xFF (0x2404 never writes r0).

Run: python3 c/tests/test_idleLeadingTimingCorrection_0x13414.py [N]
      (N = random inputs per seed; default 100000 -> 500000 across 5 seeds)
"""
import os, random, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2, ts

ROM = os.path.join(ROOT, 'roms', 'stock', '60E0FC00.bin')
ADDR = 0x13414

# ---- RAM addresses (see c/idleLeadingTimingCorrection_0x13414.c) ----
B594 = 0xFFFFB594   # f32 RPM
C0D8 = 0xFFFFC0D8   # f32 load
B5A0 = 0xFFFFB5A0   # f32 idle RPM target
B580 = 0xFFFFB580   # u8 lookup-select gate
B588 = 0xFFFFB588   # u8 lookup-select gate
B586 = 0xFFFFB586   # u8 lookup-select gate
AAC6 = 0xFFFFAAC6   # u8 idle gate
C030 = 0xFFFFC030   # f32 idle gate
A424 = 0xFFFFA424   # u16 idle gate
A720 = 0xFFFFA720   # u8 load gate / out
A718 = 0xFFFFA718   # f32 out (RPM error)
A710 = 0xFFFFA710   # f32 out (lookup result)
A708 = 0xFFFFA708   # f32 out (correction)

FLOAT_RW = [B594, C0D8, B5A0, C030, A718, A710, A708]
WORD_JUNK = [A424]

STACK_LO = 0xFFFFDE00      # task stack window (skipped in the compare)
STACK_HI = 0xFFFFDF00


def romf(rom, a):
    return struct.unpack('>f', rom[a:a + 4])[0]


def gf(m, a):
    return struct.unpack('>f', bytes(m.get(a + i, 0) for i in range(4)))[0]


def setf(m, a, v):
    for i, b in enumerate(struct.pack('>f', ts(v))):
        m[a + i] = b


def gw(m, a):
    return (m.get(a, 0) << 8) | m.get(a + 1, 0)


def gb(m, a):
    return m.get(a, 0)


def merge(cpu2, m):
    return {k: v for k, v in cpu2.ram.items() if not (STACK_LO <= k <= STACK_HI)}


def ref(cpu2, m, rom):
    """Line-for-line mirror of idleLeadingTimingCorrection_0x13414().
    Returns (RAM-effect dict, expected r0)."""
    m = dict(m)
    rpm = gf(m, B594)
    load = gf(m, C0D8)
    fr2 = ts(rpm - gf(m, B5A0))
    setf(m, A718, fr2)

    # ---- 2D lookup ----
    if gb(m, B580) == 0:
        desc = 0x686AC if gb(m, B588) == 0 else 0x686C0
    else:
        desc = 0x686AC if gb(m, B586) == 1 else 0x686C0
    cpu2.call(0x2068, r4=desc, fr={4: fr2}, ram=dict(m))
    m = merge(cpu2, m)
    res = cpu2.fr[0]
    setf(m, A710, res)

    # ---- idle gate -> fr15 (fcmp/gt Fm,Fn == Fn > Fm, i.e. inverted) ----
    gate = (gb(m, AAC6) == 1 and romf(rom, 0x726D4) > rpm and
            (romf(rom, 0x726D8) > gf(m, C030) or
             gw(m, A424) >= struct.unpack('>H', rom[0x726D0:0x726D2])[0]))
    fr15 = res if gate else 0.0

    # ---- load gate byte A720 (fr14 = load survives the lookup: fr0-fr5 only) ----
    fr5 = romf(rom, 0x726DC)
    if load < fr5:                            # 0.6 > load
        if load < ts(fr5 + romf(rom, 0x13530)):   # 0.555 > load
            m[A720] = 0
    else:
        m[A720] = 1
    a720 = gb(m, A720)

    # ---- saturate when the gate is set ----
    if a720 == 1:
        cpu2.call(0x2404, fr={4: fr15, 5: romf(rom, 0x726E0),
                              6: romf(rom, 0x726E4)}, ram=dict(m))
        m = merge(cpu2, m)
        fr15 = cpu2.fr[0]

    setf(m, A708, fr15)
    return m, a720 & 0xFF


def pick_f(rng):
    """Float pool: wide spans plus the gate boundaries (1500.0 RPM, 0.6/0.555
    load, 1/1024, map range) and NaN/Inf."""
    return rng.choice([
        rng.uniform(0, 10000),
        rng.uniform(1490, 1510),
        rng.uniform(0, 2),
        rng.uniform(0.4, 0.7),
        rng.uniform(-1, 1),
        rng.uniform(-200, 200),
        0.0, -0.0, 1500.0, 0.6, 0.555, 0.009765625, 1.0 / 1024.0,
        float('nan'), float('inf'), float('-inf'),
    ])


def gen_state(rng):
    """Random seeded RAM hitting every branch combination; every output word
    is junk so a missed write is caught."""
    ram = {}
    for a in FLOAT_RW:
        setf(ram, a, pick_f(rng))
    ram[B580] = rng.choice([0, 0, 1, 1, 2])
    ram[B588] = rng.choice([0, 0, 1, 1, 2])
    ram[B586] = rng.choice([0, 0, 1, 1, 2])
    ram[AAC6] = rng.choice([0, 0, 1, 1, 1, 2])
    ram[A720] = rng.choice([0, 1, 0xEE, 0xFF])
    v = rng.choice([0, 375, 374, 376, 0xFFFF, rng.randint(0, 65535)])
    ram[A424] = v >> 8
    ram[A424 + 1] = v & 0xFF
    return ram


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    rom = open(ROM, 'rb').read()
    assert romf(rom, 0x726D4) == 1500.0
    assert romf(rom, 0x726D8) == ts(0.009765625)
    assert struct.unpack('>H', rom[0x726D0:0x726D2])[0] == 375
    assert romf(rom, 0x726DC) == ts(0.6)
    # pool literal is -0.045 one-ULP off (BD3851EB, not the nearest float32)
    assert abs(romf(rom, 0x13530) - (-0.045)) < 1e-6
    assert romf(rom, 0x726E0) == ts(-2.8)
    assert romf(rom, 0x726E4) == ts(0.7)

    cpu = SH2(rom)
    cpu2 = SH2(rom)             # dedicated instance for the leaves in ref()
    seeds = (0x13414, 0x13544, 0x686AC, 0xA720, 0x726DC)
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
                print('  B594=%r C0D8=%r B5A0=%r C030=%r A424=%d '
                      'B580=%d B588=%d B586=%d AAC6=%d A720=%d' %
                      (gf(ram, B594), gf(ram, C0D8), gf(ram, B5A0),
                       gf(ram, C030), gw(ram, A424),
                       ram.get(B580, 0), ram.get(B588, 0), ram.get(B586, 0),
                       ram.get(AAC6, 0), ram.get(A720, 0)))
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
    print('OK  0x13414 idleLeadingTimingCorrection '
          '(%d random inputs across %d seeds)' % (N * len(seeds), len(seeds)))
    print('\nAll idleLeadingTimingCorrection_0x13414 tests passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()