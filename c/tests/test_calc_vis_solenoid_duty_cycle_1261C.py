#!/usr/bin/env python3
"""test_calc_vis_solenoid_duty_cycle_1261C.py

Differential test for ROM 0x1261C (60E1D400.bin) — lift
c/calc_vis_solenoid_duty_cycle_1261C.c.

Runs the ACTUAL ROM bytes of 0x1261C — including the verified leaves 0x2440
(complement_shift_u32) and 0x2404 (fpu_compare_and_select / clamp) — in
tools/sh2emu.py over seeded RAM states (the oracle), and compares the full
post-call RAM overlay against a Python reference model that mirrors the C lift
line-for-line.

Key semantic facts (see the lift header):
  * r1 = complement_shift_u32(A794, 0, 1e-5)  (1 if |A794| > 1e-5)
    r2 = complement_shift_u32(BCE4, 0, 1e-5)  (1 if |BCE4| > 1e-5)
  * closed-loop idle path (AADA==1, r1==0, rpm < 2000, CE58==1):
    duty = 10.0 (ROM 0x6E40C)
  * normal path (BC36==0, A9B8 > 0, (ROM8@0x6E3D5==0 || r2==0)):
    duty = RAM[A9A4]  (spark lead/trail split + minSplit from 0x19220)
  * else: duty = RAM[A648]
  * RAM[A644] = clamp(duty, RAM[A668], 65.0)  via 0x2404

The reference model computes the helper outputs (0x2440, 0x2404) by calling
them in a second emulator instance (cpu2) — the same trick the
calc_spark_lead_trail_split_19220 test uses — so float rounding and NaN
handling match the ROM exactly.

The function parks a byte on the task stack (0xFFFFDEE8) — inside the
0xFFFFDE00..0xFFFFDF00 region that is skipped by the full-RAM diff.

Run: python3 c/tests/test_calc_vis_solenoid_duty_cycle_1261C.py [N]
     (N = random inputs per seed; default 100000 -> 500000 across 5 seeds)
"""
import os, random, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2, ts

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ADDR = 0x1261C

# ---- RAM addresses (see c/calc_vis_solenoid_duty_cycle_1261C.c header) ----
B5B8 = 0xFFFFB5B8   # rpm    (f32)
A794 = 0xFFFFA794   # target (f32)
BCE4 = 0xFFFFBCE4   # error  (f32)
AADA = 0xFFFFAADA   # u8 closed-loop active
CE58 = 0xFFFFCE58   # u8 idle/overrun flag
BC36 = 0xFFFFBC36   # u8 fuel cut active
A9B8 = 0xFFFFA9B8   # f32 lambda/air-charge status
A9A4 = 0xFFFFA9A4   # f32 alternate reference (spark split + minSplit)
A648 = 0xFFFFA648   # f32 default reference
A668 = 0xFFFFA668   # f32 clamp low
A644 = 0xFFFFA644   # f32 duty-cycle output

FLOAT_IN  = [B5B8, A794, BCE4, A9B8, A9A4, A648, A668]
U8_IN     = [AADA, CE58, BC36]
FLOAT_OUT = [A644]

ROM_CAL_ENABLE = 0x6E3D5   # u8 cal enable (stock 0)
ROM_CLAMP_HIGH = 65.0      # f32 @0x6E424
ROM_IDLE_DUTY  = 10.0      # f32 @0x6E40C


def r32(d, a):
    return struct.unpack('>f', bytes(d.get(a + i, 0) for i in range(4)))[0]


def f32b(v):
    return list(struct.pack('>f', ts(v)))


def ref(cpu2, ram, rom):
    """Line-for-line mirror of calc_vis_solenoid_duty_cycle_1261C().

    Helper calls are executed in the dedicated emulator instance `cpu2` so the
    single-precision rounding / NaN behavior matches the ROM exactly.
    Returns a full RAM-effect dict (int keys -> byte values).
    """
    m = dict(ram)
    rpm = r32(m, B5B8); target = r32(m, A794); error = r32(m, BCE4)

    # r1/r2 = |.| > 1e-5 deadband tests via real 0x2440
    cpu2.call(0x2440, fr={4: target, 5: 0.0, 6: 1e-5})
    r1 = cpu2.r[0]
    cpu2.call(0x2440, fr={4: error, 5: 0.0, 6: 1e-5})
    r2 = cpu2.r[0]

    if (m.get(AADA, 0) == 1 and r1 == 0 and rpm < 2000.0
            and m.get(CE58, 0) == 1):
        duty = ROM_IDLE_DUTY                       # 10.0 @0x6E40C
    elif (m.get(BC36, 0) == 0 and r32(m, A9B8) > 0.0
            and (rom[ROM_CAL_ENABLE] == 0 or r2 == 0)):
        duty = r32(m, A9A4)                        # spark split + minSplit
    else:
        duty = r32(m, A648)                        # default reference

    # clamp via real 0x2404 (max(lo, min(val, hi)))
    cpu2.call(0x2404, fr={4: duty, 5: r32(m, A668), 6: ROM_CLAMP_HIGH})
    for i, b in enumerate(f32b(cpu2.fr[0])):
        m[A644 + i] = b
    return m


def gen_state(rng):
    """Random seeded RAM hitting every branch combination."""
    ram = {}

    def setf(a, v):
        for i, b in enumerate(struct.pack('>f', float(v))):
            ram[a + i] = b

    setf(B5B8, rng.uniform(0, 9000))                # rpm (incl. both sides of 2000)
    setf(A794, 0.0 if rng.random() < 0.3 else rng.uniform(-20, 20))
    setf(BCE4, 0.0 if rng.random() < 0.3 else rng.uniform(-20, 20))
    setf(A9B8, rng.uniform(-5, 5))
    setf(A9A4, rng.uniform(-50, 50))                # alternate reference
    setf(A648, rng.uniform(-50, 50))                # default reference
    setf(A668, rng.uniform(-50, 50))                # clamp low
    for a in U8_IN:
        ram[a] = rng.randint(0, 1)
    for a in FLOAT_OUT:                             # previous output (must be overwritten)
        setf(a, rng.uniform(-200, 200))
    return ram


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    rom = open(ROM, 'rb').read()

    cpu = SH2(rom)
    cpu2 = SH2(rom)         # dedicated instance for the helper calls in ref()
    seeds = (0x1261C, 0xA644, 0xBCE4, 0x6E40C, 0x2404)
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
                      (seed, it, {hex(k): (hex(g), hex(e)) for k, g, e in bad[:12]}))
                print('  rpm=%r target=%r error=%r A9B8=%r A9A4=%r A648=%r A668=%r'
                      % (r32(ram, B5B8), r32(ram, A794), r32(ram, BCE4),
                         r32(ram, A9B8), r32(ram, A9A4), r32(ram, A648), r32(ram, A668)))
                print('  AADA=%d CE58=%d BC36=%d duty=%r' %
                      (ram.get(AADA, 0), ram.get(CE58, 0), ram.get(BC36, 0),
                       r32(cpu.ram, A644)))
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
    print('OK  0x1261C calc_vis_solenoid_duty_cycle  (%d random inputs across %d seeds)'
          % (N * len(seeds), len(seeds)))
    print('\nAll calc_vis_solenoid_duty_cycle_1261C tests passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()
