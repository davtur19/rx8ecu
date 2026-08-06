#!/usr/bin/env python3
"""test_add_fuel_pressure_correction_0x126CA.py

Differential test for ROM 0x126CA (60E1D400.bin) — lift
c/add_fuel_pressure_correction_0x126CA.c.

Runs the ACTUAL ROM bytes of 0x126CA in tools/sh2emu.py over seeded RAM states
(the oracle) and compares the full post-call RAM overlay against a Python
reference model that mirrors the C lift line-for-line.

Entry-point note: 0x126CA IS the real entry point — the only ROM reference is
the function-pointer slot @0x1484C in the dispatcher engineControlCalculateTiming
(0x14584) dispatch table, right after calc_rotor_A_pressure_load (0x126EA @0x14848).
Valid leaf (rts+delay @0x126D6/0x126D8); no branches into the body.

Key semantic facts (see the lift header):
  * void function — pure f32 add (single-rounded):
      f32@0xFFFFA640 = f32@0xFFFFA654 + f32@0xFFFFA64C
      (input A64C = calc_rotor_A_pressure_load output; A654 = rotor knock-detect
       flag output; A640 = fuel-pressure correction reference).
  * No branches, no sub-calls, no NaN special-casing.

Run: python3 c/tests/test_add_fuel_pressure_correction_0x126CA.py [N]
     (N = random inputs per seed; default 100000 -> 500000 across 5 seeds)
"""
import os, random, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2, ts

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ADDR = 0x126CA

IN_A654 = 0xFFFFA654   # f32 rotor knock-detect flag output
IN_A64C = 0xFFFFA64C   # f32 rotor-A pressure-load output
OUT_A640 = 0xFFFFA640  # f32 fuel-pressure correction output


def rdf(m, a):
    return struct.unpack('>f', bytes(m.get(a + i, 0) for i in range(4)))[0]


def setf(ram, a, v):
    for i, b in enumerate(struct.pack('>f', ts(v))):
        ram[a + i] = b


def wrf(m, a, v):
    for i, b in enumerate(struct.pack('>f', ts(v))):
        m[a + i] = b


def ref(m):
    """Line-for-line mirror of add_fuel_pressure_correction_0x126CA().

    fr3 = A654 ; fr2 = A64C ; fr2 = ts(fr2 + fr3) ; A640 = fr2.
    Returns the RAM-effect dict.
    """
    m = dict(m)
    a = rdf(m, IN_A654)          # fmov.s @r2,fr3
    b = rdf(m, IN_A64C)          # fmov.s @r1,fr2
    wrf(m, OUT_A640, ts(a + b))  # fadd + fmov.s fr2,@r3
    return m


def gen_state(rng):
    """Random seeded RAM: both f32 inputs cover finite/edge/NaN/overflow ranges,
    output is junk so a missed write is caught."""
    ram = {}
    for a in (IN_A654, IN_A64C):
        r = rng.random()
        if r < 0.7:
            setf(ram, a, rng.uniform(-1e4, 1e4))
        elif r < 0.85:
            setf(ram, a, rng.choice([0.0, 1.0, -1.0, 0.5, -0.5, 3.0e38, -3.0e38]))
        elif r < 0.95:
            setf(ram, a, rng.choice([float('nan'), float('inf'), float('-inf')]))
        else:
            setf(ram, a, float('nan'))
    setf(ram, OUT_A640, rng.uniform(-1000.0, 1000.0))   # output junk
    return ram


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    rom = open(ROM, 'rb').read()

    cpu = SH2(rom)
    seeds = (0x126CA, 0x128C4, 0x128FE, 0xA640, 0x6E3DC)
    total_fails = 0

    for seed in seeds:
        rng = random.Random(seed)
        fails = 0
        for it in range(N):
            ram = gen_state(rng)
            want = ref(ram)
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
    print('OK  0x126CA add_fuel_pressure_correction '
          '(%d random inputs across %d seeds)' % (N * len(seeds), len(seeds)))
    print('\nAll add_fuel_pressure_correction_0x126CA tests passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()