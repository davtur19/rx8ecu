#!/usr/bin/env python3
"""test_spark_advance_calc_0x16BE8.py

Differential test for ROM 0x16BE8 (60E1D400.bin) — lift
c/spark_advance_calc_0x16BE8.c.

Runs the ACTUAL ROM bytes of 0x16BE8 in tools/sh2emu.py over seeded RAM states
(the oracle) and compares the full post-call RAM overlay against a Python
reference model that mirrors the C lift line-for-line.

Entry-point note: 0x16BE8 IS the real entry point — the only ROM reference is
the function-pointer slot @0x16B80 in engine_control_main_loop's (0x16AA8)
dispatch table 0x16B64..0x16BD0.  Valid prologue / rts+delay at
0x16C86/0x16C88; no branches into the body.

Key semantic facts (see the lift header):
  * void function — RAM side effects:
      f32@0xFFFFA8DC  always written (gate-store-0 path or copy of A8E0)
      f32@0xFFFFA8E0  written only when a lookup branch fires
  * Gate: u8@0xFFFFBDD5 == 0 -> f32@A8DC = 0.0 and return (A8E0 untouched).
  * x = f32@0xFFFFAE54 is loaded on every non-gate path.
  * Branch selectors (checked in order):
      u8@B5A4 == 1 || u8@B5AC == 0  -> map family A
      u8@B5B0 == 1                  -> map family B
      u8@B5AE == 1                  -> map family C
      none fire                     -> A8E0 kept unchanged (read through)
  * u8@0xFFFFBE24 picks the exact table inside the family:
      A: 0x69BC0 (s==0) / 0x69BD4  (s!=0)
      B: 0x69BE8 (s==0) / 0x69BFC
      C: 0x69C10 (s==0) / 0x69C24
  * Each lookup is 0x2068 (TwoDLookup) executed in the second emulator
    instance cpu2 with RAM merged — the same trick the knock / coil tests use.

Run: python3 c/tests/test_spark_advance_calc_0x16BE8.py [N]
     (N = random inputs per seed; default 100000 -> 500000 across 5 seeds)
"""
import os, random, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2, ts

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ADDR = 0x16BE8

# ---- RAM addresses (see c/spark_advance_calc_0x16BE8.c header) ----
BDD5 = 0xFFFFBDD5   # u8  calc-enable gate (==0 -> store 0)
BE24 = 0xFFFFBE24   # u8  map selector 0/1
B5A4 = 0xFFFFB5A4   # u8  branch switch A (==1)
B5AC = 0xFFFFB5AC   # u8  branch switch A' (==0)
B5B0 = 0xFFFFB5B0   # u8  branch switch B (==1)
B5AE = 0xFFFFB5AE   # u8  branch switch C (==1)
AE54 = 0xFFFFAE54   # f32 lookup input (temp)
A8E0 = 0xFFFFA8E0   # f32 lookup result / previous value
A8DC = 0xFFFFA8DC   # f32 output (copy of A8E0)

MAP_A0 = 0x00069BC0  # family A, s==0
MAP_A1 = 0x00069BD4  # family A, s!=0
MAP_B0 = 0x00069BE8  # family B, s==0
MAP_B1 = 0x00069BFC  # family B, s!=0
MAP_C0 = 0x00069C10  # family C, s==0
MAP_C1 = 0x00069C24  # family C, s!=0


def put(ram, a, n, v):
    for i in range(n):
        ram[a + i] = (v >> (8 * (n - 1 - i))) & 0xFF


def setf(ram, a, v):
    for i, b in enumerate(struct.pack('>f', ts(v))):
        ram[a + i] = b


def rdf(m, a):
    return struct.unpack('>f', bytes(m.get(a + i, 0) for i in range(4)))[0]


def wrf(m, a, v):
    for i, b in enumerate(struct.pack('>f', ts(v))):
        m[a + i] = b


def ref(cpu2, m, rom):
    """Line-for-line mirror of spark_advance_calc_0x16BE8().

    The 0x2068 helper (TwoDLookup) is executed in `cpu2` (oracle) with its RAM
    merged.  Returns the RAM-effect dict.
    """
    m = dict(m)

    if m.get(BDD5, 0) == 0:
        wrf(m, A8DC, 0.0)              # gate + store0 path (A8E0 untouched)
        return m

    x = rdf(m, AE54)                 # fr4 (delay slot, all paths)
    s = m.get(BE24, 0)               # r4 descriptor selector (delay slot)

    if m.get(B5A4, 0) == 1 or m.get(B5AC, 0) == 0:
        desc = MAP_A0 if s == 0 else MAP_A1
        cpu2.call(0x2068, r4=desc, fr={4: x}, ram=m)
        m = dict(cpu2.ram)
        wrf(m, A8E0, cpu2.fr[0])
    elif m.get(B5B0, 0) == 1:
        desc = MAP_B0 if s == 0 else MAP_B1
        cpu2.call(0x2068, r4=desc, fr={4: x}, ram=m)
        m = dict(cpu2.ram)
        wrf(m, A8E0, cpu2.fr[0])
    elif m.get(B5AE, 0) == 1:
        desc = MAP_C0 if s == 0 else MAP_C1
        cpu2.call(0x2068, r4=desc, fr={4: x}, ram=m)
        m = dict(cpu2.ram)
        wrf(m, A8E0, cpu2.fr[0])
    # no selector fired -> A8E0 keeps its pre-call value

    wrf(m, A8DC, rdf(m, A8E0))       # epilogue reload-copy
    return m


def gen_state(rng):
    """Random seeded RAM hitting every branch family + the no-fire fallback.

    BDT D5/BE24 biased 50/50; each branch family gets ~1/3 of the remaining
    inputs and the no-selector case is also covered (A8E0 must then be copied
    through unchanged — its pre-call junk value is part of the check).
    """
    ram = {}

    if rng.random() < 0.4:
        ram[BDD5] = 0                     # abort path
    else:
        ram[BDD5] = rng.randint(1, 255)   # proceed path

    if rng.random() < 0.5:
        ram[BE24] = 0
    else:
        ram[BE24] = rng.randint(1, 255)

    r = rng.random()
    if r < 0.25:
        ram[B5A4] = 1; ram[B5AC] = rng.randint(0, 255)      # family A (via A4)
    elif r < 0.4:
        ram[B5A4] = rng.randint(2, 255); ram[B5AC] = 0     # family A (via AC==0)
    elif r < 0.55:
        ram[B5A4] = rng.randint(2, 255); ram[B5AC] = rng.randint(1, 255)
        ram[B5B0] = 1                                        # family B
    elif r < 0.7:
        ram[B5A4] = rng.randint(2, 255); ram[B5AC] = rng.randint(1, 255)
        ram[B5B0] = rng.randint(2, 255); ram[B5AE] = 1     # family C
    else:
        ram[B5A4] = rng.randint(2, 255); ram[B5AC] = rng.randint(1, 255)
        ram[B5B0] = rng.randint(2, 255)                    # no selector (most)
        if rng.random() < 0.2:
            ram[B5B0] = 1                                  # but sometimes B fires
            ram[B5AE] = rng.randint(2, 255)
        else:
            ram[B5AE] = rng.randint(2, 255)

    # lookup input: axis [-20..80] plus clamps on both sides + edges
    r = rng.random()
    if r < 0.15:
        setf(ram, AE54, rng.uniform(-60.0, -20.0))
    elif r < 0.3:
        setf(ram, AE54, rng.uniform(80.0, 120.0))
    else:
        setf(ram, AE54, rng.uniform(-20.0, 80.0))
    if rng.random() < 0.05:
        setf(ram, AE54, rng.choice([-20.0, 80.0, 0.0, 40.0, float('nan')]))

    setf(ram, A8E0, rng.uniform(-100.0, 100.0))   # pre-call junk (must be read)
    setf(ram, A8DC, rng.uniform(-100.0, 100.0))   # output junk
    return ram


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    rom = open(ROM, 'rb').read()

    cpu = SH2(rom)
    cpu2 = SH2(rom)          # dedicated instance for the leaves in ref()
    seeds = (0x16BE8, 0xBDD5, 0xBE24, 0xAE54, 0x2068)
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
                print('  BDD5=%d BE24=%d B5A4=%d B5AC=%d B5B0=%d B5AE=%d AE54=%r' % (
                    ram.get(BDD5, 0), ram.get(BE24, 0),
                    ram.get(B5A4, 0), ram.get(B5AC, 0),
                    ram.get(B5B0, 0), ram.get(B5AE, 0), rdf(ram, AE54)))
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
    print('OK  0x16BE8 spark_advance_calc_0x16BE8 '
          '(%d random inputs across %d seeds)' % (N * len(seeds), len(seeds)))
    print('\nAll spark_advance_calc_0x16BE8 tests passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()