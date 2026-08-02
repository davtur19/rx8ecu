#!/usr/bin/env python3
"""test_calc_spark_advance_0x1237C.py

Differential test for ROM 0x1237C (60E1D400.bin) — lift
c/calc_spark_advance_0x1237C.c.

Runs the ACTUAL ROM bytes of 0x1237C in tools/sh2emu.py over seeded RAM states
(the oracle) and compares the full post-call RAM overlay against a Python
reference model that mirrors the C lift line-for-line.

Key semantic facts (see the lift header):
  * The old IDA name "calc_combustion_load_factor" is NOT supported — the ROM
    computes a RESULTANT SPARK ADVANCE (deg) from RPM/load/temp timing maps:
      A624 = TwoDLookup(0x69A7C, A7BC)          RPM map
      A628 = ThreeDLookup(0x69B14, LOAD, RPM)   10x7 map
      A634 = TwoDLookup(0x69A90, AA10)          temp map
      A5F8 = 0.0 - A628*A634 + A624
      A604 = (CDA0 == 0) ? 80.0 : 11.0
      (B19D == 1) ? A62C=3D(0x69B4C) : A62C=3D(0x69B68)
      A608 = min(A62C, A604)
      A630 = ThreeDLookup(0x69B30, LOAD, RPM)
      A638 = ThreeDLookup(0x69B98, RPM, AA10)
      A5F0 = max( fma(1-B188, min(A630,A604), B188*A608), A638 )
  * Helper leaves are executed in a second emulator instance (cpu2) so float
    rounding / fused-fmac behavior matches the ROM exactly: 0x2068/0x20DC
    lookups, 0x23E4 = max(fr4,fr5), 0x23F4 = min(fr4,fr5).

Run: python3 c/tests/test_calc_spark_advance_0x1237C.py [N]
     (N = random inputs per seed; default 100000 -> 500000 across 5 seeds)
"""
import os, random, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2, ts

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ADDR = 0x1237C

# ---- RAM addresses (see c/calc_spark_advance_0x1237C.c header) ----
B5B8 = 0xFFFFB5B8   # RPM   (f32 in)
C12C = 0xFFFFC12C   # load  (f32 in)
B188 = 0xFFFFB188   # rotor-sync blend weight (f32 in)
AA10 = 0xFFFFAA10   # map table input (f32 in)
A7BC = 0xFFFFA7BC   # RPM-map x input (f32 in)
CDA0 = 0xFFFFCDA0   # u8 gate in
B19D = 0xFFFFB19D   # u8 table-select in

A624 = 0xFFFFA624; A628 = 0xFFFFA628; A634 = 0xFFFFA634
A5F8 = 0xFFFFA5F8; A604 = 0xFFFFA604; A62C = 0xFFFFA62C
A608 = 0xFFFFA608; A630 = 0xFFFFA630; A638 = 0xFFFFA638
A5F0 = 0xFFFFA5F0

FLOAT_IN  = [B5B8, C12C, B188, AA10, A7BC]
FLOAT_OUT = [A624, A628, A634, A5F8, A604, A62C, A608, A630, A638, A5F0]

# ROM f32 constants used as addends/clamps
def romf(rom, a):
    return struct.unpack('>f', rom[a:a + 4])[0]
R_6D56C = romf  # 0.0   (A5F8 base addend)
R_6D570 = romf  # 80.0  (A604 clamp when CDA0 == 0)
R_6D574 = romf  # 11.0  (A604 clamp when CDA0 != 0)
R_6D578 = romf  # 0.0   (A5F0 blend addend)
R_6D57C = romf  # 0.0   (A608 addend, B19D == 1)
R_6D580 = romf  # 0.0   (A608 addend, B19D != 1)


def r32(d, a):
    return struct.unpack('>f', bytes(d.get(a + i, 0) for i in range(4)))[0]


def f32b(v):
    return list(struct.pack('>f', ts(v)))


def ref(cpu2, ram, rom):
    """Line-for-line mirror of calc_spark_advance_0x1237C().

    Lookup leaves (0x2068/0x20DC) and the min/max helpers (0x23F4/0x23E4) are
    executed in the dedicated emulator instance `cpu2` so single-precision
    rounding / fused-fmac match the ROM exactly.  Returns a full RAM-effect
    dict (int keys -> byte values).
    """
    m = dict(ram)
    rpm = r32(m, B5B8); load = r32(m, C12C)
    w   = r32(m, B188); temp = r32(m, AA10); a7bc = r32(m, A7BC)
    cda0 = m.get(CDA0, 0); b19d = m.get(B19D, 0)

    # ---- A624 / A628 / A634 maps ----
    cpu2.call(0x2068, r4=0x69A7C, fr={4: a7bc})
    for i, b in enumerate(f32b(cpu2.fr[0])): m[A624 + i] = b
    cpu2.call(0x20DC, r4=0x69B14, fr={4: load, 5: rpm})
    for i, b in enumerate(f32b(cpu2.fr[0])): m[A628 + i] = b
    cpu2.call(0x2068, r4=0x69A90, fr={4: temp})
    for i, b in enumerate(f32b(cpu2.fr[0])): m[A634 + i] = b

    # ---- A5F8 = 0.0 - (A628*A634) + A624 ----
    a5f8 = ts(ts(ts(R_6D56C(rom, 0x6D56C)) - ts(r32(m, A628) * r32(m, A634)))
              + r32(m, A624))
    for i, b in enumerate(f32b(a5f8)): m[A5F8 + i] = b

    # ---- A604 = (CDA0 == 0) ? 80.0 : 11.0 ----
    a604 = R_6D570(rom, 0x6D570) if cda0 == 0 else R_6D574(rom, 0x6D574)
    for i, b in enumerate(f32b(a604)): m[A604 + i] = b

    # ---- leading advance path (A62C / A608) ----
    if b19d == 1:
        cpu2.call(0x20DC, r4=0x69B4C, fr={4: load, 5: rpm})
        a62c = cpu2.fr[0]
        cpu2.call(0x23F4, fr={4: a62c, 5: a604})
        adv_first = cpu2.fr[0]
        a608 = ts(adv_first + R_6D57C(rom, 0x6D57C))
    else:
        cpu2.call(0x20DC, r4=0x69B68, fr={4: load, 5: rpm})
        a62c = cpu2.fr[0]
        cpu2.call(0x23F4, fr={4: a62c, 5: a604})
        adv_first = cpu2.fr[0]
        a608 = ts(adv_first + R_6D580(rom, 0x6D580))
    for i, b in enumerate(f32b(a62c)): m[A62C + i] = b
    for i, b in enumerate(f32b(a608)): m[A608 + i] = b

    # ---- A630 / A638 ----
    cpu2.call(0x20DC, r4=0x69B30, fr={4: load, 5: rpm})
    for i, b in enumerate(f32b(cpu2.fr[0])): m[A630 + i] = b
    cpu2.call(0x20DC, r4=0x69B98, fr={4: rpm, 5: temp})
    for i, b in enumerate(f32b(cpu2.fr[0])): m[A638 + i] = b

    # ---- A5F0 = max( fma(1-w, min(A630,A604), w*A608), A638 ) ----
    cpu2.call(0x23F4, fr={4: r32(m, A630), 5: a604})
    adv_lead = cpu2.fr[0]
    prod = ts(w * r32(m, A608))                       # fmul, pre-rounded addend
    blended = ts(ts(1.0 - w) * ts(R_6D578(rom, 0x6D578) + adv_lead) + prod)
    cpu2.call(0x23E4, fr={4: blended, 5: r32(m, A638)})
    for i, b in enumerate(f32b(cpu2.fr[0])): m[A5F0 + i] = b

    return m


def gen_state(rng):
    """Random seeded RAM hitting every table/branch combination."""
    ram = {}

    def setf(a, v):
        for i, b in enumerate(struct.pack('>f', float(v))):
            ram[a + i] = b

    setf(B5B8, rng.uniform(0, 10000))        # RPM  (incl. out of map range)
    setf(C12C, rng.uniform(0, 2.0))          # load (incl. out of map range)
    setf(B188, rng.uniform(-1, 2))           # blend weight (some >1 / <0)
    setf(AA10, rng.uniform(-60, 150))        # temp map input (incl. clamped)
    setf(A7BC, rng.uniform(0, 10000))        # RPM-map x input
    ram[CDA0] = rng.choice([0, 1, rng.randint(0, 255)])
    ram[B19D] = rng.choice([0, 1, rng.randint(0, 255)])
    for a in FLOAT_OUT:                      # previous outputs (overwritten)
        setf(a, rng.uniform(-200, 200))
    return ram


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    rom = open(ROM, 'rb').read()

    cpu = SH2(rom)
    cpu2 = SH2(rom)          # dedicated instance for helper calls in ref()
    seeds = (0x1237C, 0xA5F0, 0x69B98, 0xCDA0, 0xB19D)
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
                print('  rpm=%r load=%r w=%r temp=%r a7bc=%r cda0=%d b19d=%d' % (
                    r32(ram, B5B8), r32(ram, C12C), r32(ram, B188),
                    r32(ram, AA10), r32(ram, A7BC), ram[CDA0], ram[B19D]))
                print('  A5F0 got=%r want=%r' % (r32(cpu.ram, A5F0), r32(want, A5F0)))
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
    print('OK  0x1237C calc_spark_advance  (%d random inputs across %d seeds)'
          % (N * len(seeds), len(seeds)))
    print('\nAll calc_spark_advance_0x1237C tests passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()
