#!/usr/bin/env python3
"""test_spark_timing_boundary_limiter_0x162E4.py

Differential test for ROM 0x162E4 (60E1D400.bin) — lift
c/spark_timing_boundary_limiter_0x162E4.c.

Runs the ACTUAL ROM bytes of 0x162E4 in tools/sh2emu.py over seeded RAM states
(the oracle) and compares the full post-call RAM overlay against a Python
reference model that mirrors the C lift line-for-line.

Entry-point note: 0x162E4 IS the real entry point — the only ROM reference is
the function-pointer slot @0x16BAC in engine_control_main_loop's (0x16AA8)
dispatch table 0x16B64..0x16BD0.  Valid prologue / rts+delay at
0x16462/0x16464; no branches into the body.

Key semantic facts (see the lift header):
  * void function — RAM side effects:
      u8@0xFFFFA8A0   = pass ? 1 : 0
      u16@0xFFFFA8A2  = (gate_a==1) ? satadd16(u16@A8A2, 1) : 0
      u16@0xFFFFA8A4  = (gate_b==0) ? satadd16(u16@A8A4, 1) : 0
  * Gate A: u8@0xFFFFA7C4 must be 1; Gate B: u8@0xFFFFA7C5 must be 0.
  * Counter gates: u16@A8A2 >= 312 (u16@ROM 0x76AEA) and u16@A8A4 >= 312.
  * Float gates (fcmp/gt semantics, NaN asymmetric — see lift header):
      80.0f  > f32@AA10  -> fail      (bt/s, so NaN passes through)
      60.0f  > f32@AE54  -> must hold (bf/s, so NaN fails)
      |f32@A7BC - f32@B5C0| > 37.0f   -> fail   (delta via 0x23DC)
      |f32@A8DC| > 1e-5f              -> fail   (0x2440 window-out)
      f32@A7B4 > 0.035f  -> fail
      f32@B360 > 35.0f   -> fail
      f32@A848 > f32@A850  and  f32@A84C > f32@A848   (ordering)
  * Flag gates: u8@A7C7 == 0, u8@CCD1 == 0, u8@ROM 0x76AE8 == 0.
  * The leaves 0x23DC / 0x2440 / 0x2460 are executed in the second emulator
    instance cpu2 (oracle) with their RAM merged — the same trick the knock /
    coil / 0x91FE tests use for helper calls.

Run: python3 c/tests/test_spark_timing_boundary_limiter_0x162E4.py [N]
     (N = random inputs per seed; default 100000 -> 500000 across 5 seeds)
"""
import os, random, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2, ts

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ADDR = 0x162E4

# ---- RAM addresses (see c/spark_timing_boundary_limiter_0x162E4.c header) ----
A7C4 = 0xFFFFA7C4   # u8  gate A (must == 1)
A7C5 = 0xFFFFA7C5   # u8  gate B (must == 0)
A7BC = 0xFFFFA7BC   # f32 boundary A (delta against B5C0)
B5C0 = 0xFFFFB5C0   # f32 boundary B
A848 = 0xFFFFA848   # f32 ordering middle (fr15)
A850 = 0xFFFFA850   # f32 ordering low
A84C = 0xFFFFA84C   # f32 ordering high
A8DC = 0xFFFFA8DC   # f32 delta/zero gate
A8A2 = 0xFFFFA8A2   # u16 counter A (output)
A8A4 = 0xFFFFA8A4   # u16 counter B (output)
A8A0 = 0xFFFFA8A0   # u8  pass/fail flag (output)
AA10 = 0xFFFFAA10   # f32 80.0-gate input
AE54 = 0xFFFFAE54   # f32 60.0-gate input
A7B4 = 0xFFFFA7B4   # f32 0.035-gate input
B360 = 0xFFFFB360   # f32 35.0-gate input
A7C7 = 0xFFFFA7C7   # u8  flag gate
CCD1 = 0xFFFFCCD1   # u8  flag gate

ROM_EPS   = 0x0001640C   # f32 1e-5 (window epsilon)
ROM_THR   = 0x00076AEA   # u16 312
ROM_76AEC = 0x00076AEC   # f32 80.0
ROM_76AF0 = 0x00076AF0   # f32 60.0
ROM_76AF4 = 0x00076AF4   # f32 37.0
ROM_76AF8 = 0x00076AF8   # f32 0.035
ROM_76AFC = 0x00076AFC   # f32 35.0
ROM_76AE8 = 0x00076AE8   # u8  0


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


def rdu16(m, a):
    return (m.get(a, 0) << 8) | m.get(a + 1, 0)


def rdu16b(buf, a):
    return (buf[a] << 8) | buf[a + 1]


def wrf(m, a, v):
    for i, b in enumerate(struct.pack('>f', ts(v))):
        m[a + i] = b


def ref(cpu2, m, rom, eps=ROM_EPS, thr=ROM_THR):
    """Line-for-line mirror of spark_timing_boundary_limiter_0x162E4().

    Leaves 0x23DC / 0x2440 / 0x2460 are executed in `cpu2` (oracle) and their
    RAM merged; all fcmp/gt comparisons use the same single-precision Python
    floats the emulator compares.  Returns the RAM-effect dict.
    """
    m = dict(m)

    gate_a = m.get(A7C4, 0)
    gate_b = m.get(A7C5, 0)

    # 0x23DC: delta = |f32@A7BC - f32@B5C0|   (jsr @0x16304)
    cpu2.call(0x23DC, fr={4: rdf(m, A7BC), 5: rdf(m, B5C0)}, ram=m)
    m = dict(cpu2.ram)
    delta = cpu2.fr[0]

    # 0x2440: wout = 1 if f32@A8DC outside [-1e-5, +1e-5]  (jsr @0x16318)
    cpu2.call(0x2440, fr={4: rdf(m, A8DC), 5: 0.0, 6: rdfb(rom, eps)}, ram=m)
    m = dict(cpu2.ram)
    wout = cpu2.r[0]

    fr15 = rdf(m, A848)                # fr15 loaded @0x16312

    out = 0
    if (gate_a == 1
            and rdu16(m, A8A2) >= rdu16b(rom, thr)
            and gate_b == 0
            and rdu16(m, A8A4) >= rdu16b(rom, thr)
            and not (rdfb(rom, ROM_76AEC) > rdf(m, AA10))      # bt/s (NaN passes)
            and (rdfb(rom, ROM_76AF0) > rdf(m, AE54))          # bf/s (NaN fails)
            and not (delta > rdfb(rom, ROM_76AF4))
            and not wout
            and not (rdf(m, A7B4) > rdfb(rom, ROM_76AF8))
            and not (rdf(m, B360) > rdfb(rom, ROM_76AFC))
            and fr15 > rdf(m, A850)
            and rdf(m, A84C) > fr15
            and m.get(A7C7, 0) == 0
            and m.get(CCD1, 0) == 0
            and rom[ROM_76AE8] == 0):
        out = 1

    m[A8A0] = out                      # mov.b r1/r14,@r6

    # counter A: (gate_a==1) ? satadd16(ca,1) : 0    (0x2460 @0x163E0)
    ca = rdu16(m, A8A2)
    if gate_a == 1:
        cpu2.call(0x2460, r4=ca, r5=1, ram=m)
        m = dict(cpu2.ram)
        ca = cpu2.r[0] & 0xFFFF
    else:
        ca = 0
    put(m, A8A2, 2, ca)

    # counter B: (gate_b==0) ? satadd16(cb,1) : 0    (0x2460 @0x1644C)
    cb = rdu16(m, A8A4)
    if gate_b == 0:
        cpu2.call(0x2460, r4=cb, r5=1, ram=m)
        m = dict(cpu2.ram)
        cb = cpu2.r[0] & 0xFFFF
    else:
        cb = 0
    put(m, A8A4, 2, cb)

    return m


def gen_state(rng):
    """Random seeded RAM hitting every gate and counter combination.

    Float gates are biased toward passing but each is also forced to fail
    (and to hit NaN / exact-threshold edges) so the reference must match the
    emulator on every branch combination.  30% of states are built from a fully
    passing template (perturbed ~40% of the time) so the all-gates-pass path —
    OUT=1 plus both saturating counter increments — is exercised often despite
    the 15-gate conjunction.
    """
    ram = {}

    if rng.random() < 0.3:
        # fully-passing template
        ram[A7C4] = 1
        ram[A7C5] = 0
        put(ram, A8A2, 2, rng.randint(312, 500))
        put(ram, A8A4, 2, rng.randint(312, 500))
        setf(ram, AA10, rng.uniform(80.0, 120.0))
        setf(ram, AE54, rng.uniform(0.0, 55.0))
        a = rng.uniform(60.0, 100.0)
        setf(ram, A7BC, a)
        setf(ram, B5C0, a - rng.uniform(-30.0, 30.0))
        setf(ram, A8DC, rng.choice([0.0, rng.uniform(-1e-5, 1e-5)]))
        setf(ram, A7B4, rng.uniform(0.0, 0.03))
        setf(ram, B360, rng.uniform(0.0, 30.0))
        lo = rng.uniform(0.0, 30.0)
        setf(ram, A850, lo)
        setf(ram, A848, lo + rng.uniform(1.0, 30.0))
        setf(ram, A84C, lo + rng.uniform(40.0, 80.0))
        ram[A7C7] = 0
        ram[CCD1] = 0
        ram[A8A0] = rng.randint(0, 255)
        # perturb: flip exactly one gate to fail ~40% of the time
        if rng.random() < 0.4:
            g = rng.choice(['A7C4', 'A7C5', 'cntA', 'cntB', 'AA10', 'AE54',
                            'delta', 'A8DC', 'A7B4', 'B360', 'ord1', 'ord2',
                            'A7C7', 'CCD1'])
            if g == 'A7C4':
                ram[A7C4] = rng.randint(2, 255)
            elif g == 'A7C5':
                ram[A7C5] = rng.randint(1, 255)
            elif g == 'cntA':
                put(ram, A8A2, 2, rng.randint(0, 311))
            elif g == 'cntB':
                put(ram, A8A4, 2, rng.randint(0, 311))
            elif g == 'AA10':
                setf(ram, AA10, rng.uniform(0.0, 79.0))
            elif g == 'AE54':
                setf(ram, AE54, rng.uniform(60.0, 120.0))
            elif g == 'delta':
                setf(ram, B5C0, a - rng.choice([37.5, 45.0, 80.0]))
            elif g == 'A8DC':
                setf(ram, A8DC, rng.uniform(0.0001, 0.01))
            elif g == 'A7B4':
                setf(ram, A7B4, rng.uniform(0.036, 0.1))
            elif g == 'B360':
                setf(ram, B360, rng.uniform(35.0, 70.0))
            elif g == 'ord1':
                setf(ram, A850, lo + 50.0)          # A850 > A848
            elif g == 'ord2':
                setf(ram, A84C, lo + 10.0)          # A84C < A848
            elif g == 'A7C7':
                ram[A7C7] = rng.randint(1, 255)
            elif g == 'CCD1':
                ram[CCD1] = rng.randint(1, 255)
        return ram

    # gate A: pass half the time (also picks the counter-A update path)
    if rng.random() < 0.5:
        ram[A7C4] = 1
    else:
        ram[A7C4] = rng.randint(0, 255)

    # gate B: pass half the time (also picks the counter-B update path)
    if rng.random() < 0.5:
        ram[A7C5] = 0
    else:
        ram[A7C5] = rng.randint(0, 255)

    # counters: both sides of the 312 threshold + saturation edge
    if rng.random() < 0.9:
        put(ram, A8A2, 2, rng.randint(0, 400))
    else:
        put(ram, A8A2, 2, rng.choice([311, 312, 313, 0, 0xFFFF]))
    if rng.random() < 0.9:
        put(ram, A8A4, 2, rng.randint(0, 400))
    else:
        put(ram, A8A4, 2, rng.choice([311, 312, 313, 0, 0xFFFF]))

    # 80.0-gate input
    r = rng.random()
    if r < 0.5:
        setf(ram, AA10, rng.uniform(80.0, 130.0))      # >= 80 -> pass
    elif r < 0.85:
        setf(ram, AA10, rng.uniform(0.0, 80.0))        # < 80  -> fail
    else:
        setf(ram, AA10, rng.choice([80.0, 79.99999, float('nan'), float('inf')]))

    # 60.0-gate input
    r = rng.random()
    if r < 0.5:
        setf(ram, AE54, rng.uniform(0.0, 60.0))        # < 60 -> pass
    elif r < 0.85:
        setf(ram, AE54, rng.uniform(60.0, 120.0))      # >= 60 -> fail
    else:
        setf(ram, AE54, rng.choice([60.0, 59.99999, float('nan'), float('-inf')]))

    # boundary delta: |A7BC - B5C0| <= 37.0, with exact-threshold edges
    a = rng.uniform(40.0, 120.0)
    d = rng.uniform(-45.0, 45.0)
    if rng.random() < 0.05:
        d = rng.choice([37.0, -37.0, 37.001, -37.001])
    setf(ram, A7BC, a)
    setf(ram, B5C0, a - d)

    # delta/zero gate: |A8DC| <= 1e-5
    r = rng.random()
    if r < 0.4:
        setf(ram, A8DC, 0.0)
    elif r < 0.7:
        setf(ram, A8DC, rng.uniform(-1e-5, 1e-5))
    else:
        setf(ram, A8DC, rng.choice([1e-4, -1e-4, 1.0, float('nan')]))

    # 0.035-gate input
    if rng.random() < 0.5:
        setf(ram, A7B4, rng.uniform(0.0, 0.035))
    else:
        setf(ram, A7B4, rng.uniform(0.035, 0.1))

    # 35.0-gate input
    if rng.random() < 0.5:
        setf(ram, B360, rng.uniform(0.0, 35.0))
    else:
        setf(ram, B360, rng.uniform(35.0, 70.0))

    # ordering gates: A850 < A848 < A84C (ordered mostly, scrambled otherwise)
    if rng.random() < 0.7:
        lo = rng.uniform(-20.0, 40.0)
        mid = rng.uniform(lo + 1.0, lo + 40.0)
        hi = rng.uniform(mid + 1.0, mid + 40.0)
        setf(ram, A850, lo); setf(ram, A848, mid); setf(ram, A84C, hi)
        if rng.random() < 0.1:
            setf(ram, A848, float('nan'))
    else:
        x = rng.uniform(-20.0, 120.0)
        y = rng.uniform(-20.0, 120.0)
        z = rng.uniform(-20.0, 120.0)
        setf(ram, A850, x); setf(ram, A848, y); setf(ram, A84C, z)

    # flag gates
    if rng.random() < 0.6:
        ram[A7C7] = 0
    else:
        ram[A7C7] = rng.randint(1, 255)
    if rng.random() < 0.6:
        ram[CCD1] = 0
    else:
        ram[CCD1] = rng.randint(1, 255)

    # output flag: junk so a missed write is caught
    ram[A8A0] = rng.randint(0, 255)
    return ram


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    rom = open(ROM, 'rb').read()

    cpu = SH2(rom)
    cpu2 = SH2(rom)          # dedicated instance for the leaves in ref()
    seeds = (0x162E4, 0xA7C4, 0xA8A2, 0xAA10, 0x1640C)
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
                print('  A7C4=%d A7C5=%d A8A2=%r A8A4=%r AA10=%r AE54=%r' % (
                    ram.get(A7C4, 0), ram.get(A7C5, 0), rdu16(ram, A8A2),
                    rdu16(ram, A8A4), rdf(ram, AA10), rdf(ram, AE54)))
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
    print('OK  0x162E4 spark_timing_boundary_limiter '
          '(%d random inputs across %d seeds)' % (N * len(seeds), len(seeds)))
    print('\nAll spark_timing_boundary_limiter_0x162E4 tests passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()
