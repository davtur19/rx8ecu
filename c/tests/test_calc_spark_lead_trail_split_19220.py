#!/usr/bin/env python3
"""test_calc_spark_lead_trail_split_19220.py

Differential test for ROM 0x19220 (60E1D400.bin) — lift
c/calc_spark_lead_trail_split_19220.c.

Runs the ACTUAL ROM bytes of 0x19220 in tools/sh2emu.py over seeded RAM states
(the oracle) and compares the full post-call RAM overlay against a Python
reference model that mirrors the C lift line-for-line.

Key semantic facts (see the lift header):
  * A9A0 leading timing: sel==4 -> BD00; |BCFC|<=1e-5 -> -20; else the
    base-select formula terminated by the software-float helper 0x46CC
    (frexp/int-div/ldexp; emulator-observable: 0.0/Inf -> 1.0, else NaN +
    RAM32@0xFFFF7304 = 0x044D).
  * A9AC trailing timing by selector: 1 -> 0.5*ROM[0x6ED98]-50; 2 ->
    ThreeDLookup(0x69F14 TrailingA); 3 -> 0.5*ROM[0x6ED99]-50; else ->
    ThreeDLookup(0x69EF8 TrailingB).  Descriptors are ROM tables (u8 cells,
    0.5*interp-50), x-axis = load, y-axis = RPM.
  * minSplit = ThreeDLookup(0x69F30 MinSplit, x=load, y=RPM).
  * A9A8 = max(A9A0, A9AC); A9A4 = max(A9A0+ms, A9AC+ms); A9C0 = (lead>trail)?0:1.

The reference model computes the helper outputs (0x2440, 0x2500, 0x23E4, 0x46CC,
0x20DC) by calling them in a second emulator instance — the same trick the
pressure_delta_monitor test uses for its 0x23B0 filter call — so float rounding
and NaN handling match the ROM exactly.

Run: python3 c/tests/test_calc_spark_lead_trail_split_19220.py [N]
     (N = random inputs per seed; default 100000 -> 500000 across 5 seeds)
"""
import os, random, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2, ts

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ADDR = 0x19220

# ---- RAM addresses (see c/calc_spark_lead_trail_split_19220.c header) ----
B5B8 = 0xFFFFB5B8   # RPM   (f32)
C12C = 0xFFFFC12C   # load  (f32)
BCFC = 0xFFFFBCFC   # f32
BCEF = 0xFFFFBCEF   # u8 split selector
BD00 = 0xFFFFBD00; BD04 = 0xFFFFBD04; BD14 = 0xFFFFBD14; BD20 = 0xFFFFBD20
BD24 = 0xFFFFBD24; BD28 = 0xFFFFBD28; BCE4 = 0xFFFFBCE4
BC40 = 0xFFFFBC40; BB2C = 0xFFFFBB2C
A9B0 = 0xFFFFA9B0; A9B4 = 0xFFFFA9B4

A9A0 = 0xFFFFA9A0   # leading  (f32 out)
A9AC = 0xFFFFA9AC   # trailing (f32 out)
A9A8 = 0xFFFFA9A8   # f32 out
A9A4 = 0xFFFFA9A4   # f32 out
A9C0 = 0xFFFFA9C0   # u8 out
F7304 = 0xFFFF7304  # NaN/Inf fault code (u32, written only by 0x46CC NaN path)

FLOAT_IN = [B5B8, C12C, BCFC, BD00, BD04, BD14, BD20, BD24, BD28,
            BCE4, BC40, BB2C, A9B0, A9B4]
FLOAT_OUT = [A9A0, A9AC, A9A8, A9A4]


def r32(d, a):
    return struct.unpack('>f', bytes(d.get(a + i, 0) for i in range(4)))[0]


def f32b(v):
    return list(struct.pack('>f', ts(v)))


def ref(cpu2, ram, rom):
    """Line-for-line mirror of calc_spark_lead_trail_split_19220().

    Helper calls are executed in the dedicated emulator instance `cpu2` so the
    single-precision rounding / NaN / RAM-side-effect behavior matches the ROM
    exactly.  Returns a full RAM-effect dict (int keys -> byte values).
    """
    m = dict(ram)
    sel = m.get(BCEF, 0)
    rpm = r32(m, B5B8); load = r32(m, C12C); bcfc = r32(m, BCFC)

    # ---- leading A9A0 ----
    if sel == 4:
        lead = r32(m, BD00)
    else:
        cpu2.call(0x2440, fr={4: bcfc, 5: 0.0, 6: 1e-5})   # |bcfc| > 1e-5 ?
        if cpu2.r[0] == 0:
            lead = -20.0
        else:
            base = r32(m, BB2C) if r32(m, A9B4) > r32(m, A9B0) else r32(m, BC40)
            f = ts(ts(ts(r32(m, BD14) - r32(m, BCE4)) - r32(m, BD20)) - base)
            f = ts(f * ts(4.0 / ts(4.0 - float(sel))))     # 0x2500(sel,1,0)
            X = ts(ts(ts(r32(m, BD24) + r32(m, BD28)) + r32(m, BD04)) + f) - r32(m, BD14)
            cpu2.call(0x23E4, fr={4: X, 5: 0.0})           # max(X, 0)
            mm = ts(cpu2.fr[0] / bcfc)
            cpu2.call(0x46CC, fr={4: mm})
            for i in range(4):                              # 0x46CC side effect
                if cpu2.ram.get(F7304 + i) is not None:
                    m[F7304 + i] = cpu2.ram[F7304 + i]
            lead = ts(r32(m, BD00) - cpu2.fr[0])
    for i, b in enumerate(f32b(lead)):
        m[A9A0 + i] = b

    # ---- trailing A9AC ----
    if sel == 1:
        cpu2.call(0x2500, r4=rom[0x6ED98], fr={4: 0.5, 5: -50.0})
        trail = cpu2.fr[0]
    elif sel == 2:
        cpu2.call(0x20DC, r4=0x69F14, fr={4: load, 5: rpm})
        trail = cpu2.fr[0]
    elif sel == 3:
        cpu2.call(0x2500, r4=rom[0x6ED99], fr={4: 0.5, 5: -50.0})
        trail = cpu2.fr[0]
    else:
        cpu2.call(0x20DC, r4=0x69EF8, fr={4: load, 5: rpm})
        trail = cpu2.fr[0]
    for i, b in enumerate(f32b(trail)):
        m[A9AC + i] = b

    # ---- minSplit ----
    cpu2.call(0x20DC, r4=0x69F30, fr={4: load, 5: rpm})
    minsplit = cpu2.fr[0]

    # ---- A9A8 = 0x23E4(lead, trail) ; A9A4 = 0x23E4(lead+ms, trail+ms) ----
    cpu2.call(0x23E4, fr={4: lead, 5: trail})
    for i, b in enumerate(f32b(cpu2.fr[0])):
        m[A9A8 + i] = b
    cpu2.call(0x23E4, fr={4: ts(lead + minsplit), 5: ts(trail + minsplit)})
    for i, b in enumerate(f32b(cpu2.fr[0])):
        m[A9A4 + i] = b

    # ---- A9C0 = (lead > trail) ? 0 : 1 ----
    m[A9C0] = 0 if (lead > trail) else 1
    return m


def gen_state(rng):
    """Random seeded RAM hitting every selector / branch combination."""
    ram = {}

    def setf(a, v):
        for i, b in enumerate(struct.pack('>f', float(v))):
            ram[a + i] = b

    setf(B5B8, rng.uniform(0, 10000))               # RPM  (incl. out of map range)
    setf(C12C, rng.uniform(0, 2.0))                 # load (incl. out of map range)
    setf(BCFC, 0.0 if rng.random() < 0.3 else rng.uniform(1e-3, 50.0))
    for a in [BD00, BD04, BD14, BD20, BD24, BD28, BCE4, BC40, BB2C, A9B0, A9B4]:
        setf(a, rng.uniform(-100, 100))
    ram[BCEF] = rng.randint(0, 7)                   # selectors 0..7
    for a in FLOAT_OUT:                             # previous outputs (must be overwritten)
        setf(a, rng.uniform(-200, 200))
    ram[A9C0] = rng.randint(0, 1)
    for i in range(4):                              # previous fault code
        ram[F7304 + i] = rng.randint(0, 255)
    return ram


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    rom = open(ROM, 'rb').read()

    cpu = SH2(rom)
    cpu2 = SH2(rom)         # dedicated instance for the helper calls in ref()
    seeds = (0x19220, 0xA9A0, 0x6EF98, 0xBCEF, 0x46CC)
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
                print('  sel=%d rpm=%r load=%r bcfc=%r lead=%r trail=%r' % (
                    ram[BCEF], r32(ram, B5B8), r32(ram, C12C), r32(ram, BCFC),
                    r32(cpu.ram, A9A0), r32(cpu.ram, A9AC)))
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
    print('OK  0x19220 calc_spark_lead_trail_split  (%d random inputs across %d seeds)'
          % (N * len(seeds), len(seeds)))
    print('\nAll calc_spark_lead_trail_split_19220 tests passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()
