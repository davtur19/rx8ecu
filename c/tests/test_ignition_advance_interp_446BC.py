#!/usr/bin/env python3
"""test_ignition_advance_interp_446BC.py

Differential test for ROM 0x446BC (60E1D400.bin) — lift
c/ignition_advance_interp_446BC.c.

Runs the ACTUAL ROM bytes of 0x446BC in tools/sh2emu.py over seeded RAM states
(the oracle) and compares the full post-call RAM overlay against a Python
reference model that mirrors the C lift line-for-line.

Entry-point note: 0x446BC IS the real entry point — the only ROM reference is
the function-pointer slot @0x1482C in the dispatcher engineControlCalculateTiming
(0x14584) dispatch table (c/engineControlCalculateTiming.c line 257).  Valid
prologue / rts+delay at 0x44744/0x44746; no branches into the body.

Key semantic facts (see the lift header):
  * void function — the only RAM side effect is f32@0xFFFFCA28.
  * Gate: u8@0xFFFFCAB4 must be 1, else no write at all.
  * fr4 = f32@0xFFFFCA40;  fr5 = 20.0 (ROM f32 @0x0007B410).
      fr5 > fr4  -> advance path
      fr5 <= fr4 -> f32@0xFFFFCA28 = fr5 (20.0)
    advance path, fr4 > 0.0:
      v   = 0x2500(u8@0xFFFFCAAD, 1.0, 0.0)              (= (float)idx)
      lut = 0x20DC(desc@0x0006BF34, f32@0xFFFFCA90, v)   (3D lookup)
      r   = lut * f32@0xFFFFCA44 + f32@0xFFFFCA60        (fmac)
      r   = r - f32@0xFFFFCA84                           (fsub)
      f32@0xFFFFCA28 = r
    else (fr4 <= 0.0): f32@0xFFFFCA28 = 0.0.
  * The leaves 0x2500 and 0x20DC are executed in the second emulator instance
    cpu2 (oracle) with their RAM merged — the same trick the coil/0x91FE tests
    use for helper calls — so float conversion, bilinear interp and every RAM
    side effect match the ROM exactly.

Run: python3 c/tests/test_ignition_advance_interp_446BC.py [N]
     (N = random inputs per seed; default 100000 -> 500000 across 5 seeds)
"""
import os, random, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2, ts

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ADDR = 0x446BC

# ---- RAM addresses (see c/ignition_advance_interp_446BC.c header) ----
CAB4 = 0xFFFFCAB4   # u8  enable gate (must == 1)
CA40 = 0xFFFFCA40   # f32 fr4 input
CA28 = 0xFFFFCA28   # f32 output
CAAD = 0xFFFFCAAD   # u8  3D lookup y index
CA90 = 0xFFFFCA90   # f32 3D lookup x input
CA60 = 0xFFFFCA60   # f32 fmac addend
CA44 = 0xFFFFCA44   # f32 fmac multiply
CA84 = 0xFFFFCA84   # f32 fsub subtrahend

ROM_7B410 = 0x0007B410   # f32 20.0 (upper gate threshold)
ROM_MAP   = 0x0006BF34   # ThreeDLookup descriptor (count_x=7,count_y=4,u16,0.02)


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


def ref(cpu2, m, rom, rom_map=ROM_MAP, rom_thresh=ROM_7B410):
    """Line-for-line mirror of ignition_advance_interp_446BC().

    Leaves 0x2500 / 0x20DC are executed in `cpu2` (oracle) and their RAM
    merged; the fmac/fsub blend is modelled with the same single-precision
    rounding (`ts`) the emulator applies.  Returns the RAM-effect dict.
    """
    m = dict(m)
    if m.get(CAB4, 0) != 1:                # mov.b @r2 ; cmp/eq #1 ; bf/s
        return m                           # early return: no RAM write

    fr4 = rdf(m, CA40)                     # fmov.s @r3,fr4 (delay slot)
    fr5 = rdfb(rom, rom_thresh)            # fmov.s @r0,fr5 (20.0)
    if not (fr5 > fr4):                    # fcmp/gt fr4,fr5 ; bt/s 0x44708
        wrf(m, CA28, fr5)                  # bra 0x44740 delay: fmov.s fr5,@r14
        return m

    if not (fr4 > 0.0):                    # fldi0 fr3 ; fcmp/gt fr3,fr4 ; bf/s
        wrf(m, CA28, 0.0)                  # 0x4473E: fmov.s fr15,@r14 (fr15=0.0)
        return m

    idx = m.get(CAAD, 0)                   # mov.b @r1,r4 (delay slot of jsr)
    cpu2.call(0x2500, r4=idx, fr={4: 1.0, 5: 0.0}, ram=m)
    m = dict(cpu2.ram)
    v = cpu2.fr[0]                         # = (float)idx

    x = rdf(m, CA90)                       # fmov.s @r2,fr4 (delay slot of jsr)
    cpu2.call(0x20DC, r4=rom_map, fr={4: x, 5: v}, ram=m)
    m = dict(cpu2.ram)
    lut = cpu2.fr[0]

    fr3 = rdf(m, CA60)                     # fmov.s @r3,fr3 (0xFFFFCA60)
    fr2 = rdf(m, CA44)                     # fmov.s @r2,fr2 (0xFFFFCA44)
    fr3 = ts(lut * fr2 + fr3)              # fmac fr0,fr2,fr3
    fr2 = rdf(m, CA84)                     # fmov.s @r1,fr2 (0xFFFFCA84)
    fr3 = ts(fr3 - fr2)                    # fsub fr2,fr3
    wrf(m, CA28, fr3)                      # bra 0x44740 delay: fmov.s fr3,@r14
    return m


def gen_state(rng):
    """Random seeded RAM hitting every gate/zone combination.

    CAB4 biased toward 1 so both the early-return and the compute path run;
    fr4 (CA40) sampled so all three zones of the 20.0 / 0.0 thresholds are hit;
    the 3D-lookup x (CA90) covers the axis 0..6 plus out-of-range clamps; the
    blend words are free-floating f32.
    """
    ram = {}

    # enable gate: ~80% pass
    if rng.random() < 0.8:
        ram[CAB4] = 1
    else:
        ram[CAB4] = rng.randint(0, 255)

    # fr4: force the fr5>fr4 / fr4>0 boundaries frequently
    r = rng.random()
    if r < 0.25:
        setf(ram, CA40, rng.uniform(20.0, 40.0))       # fr4 >= 20 (store 20)
    elif r < 0.5:
        setf(ram, CA40, rng.uniform(-20.0, 0.0))       # fr4 <= 0 (store 0)
    else:
        setf(ram, CA40, rng.uniform(0.0, 20.0))        # advance path
    if rng.random() < 0.06:                            # exact edge floats
        setf(ram, CA40, rng.choice([20.0, 0.0, -0.0, 20.000001, -0.000001]))

    # y index: biased toward the realistic small range, sometimes full byte
    if rng.random() < 0.7:
        ram[CAAD] = rng.randint(0, 6)
    else:
        ram[CAAD] = rng.randint(0, 255)

    # 3D lookup x: axis 0..6, with out-of-range clamps either side
    r = rng.random()
    if r < 0.15:
        setf(ram, CA90, rng.uniform(-4.0, 0.0))        # clamp low
    elif r < 0.3:
        setf(ram, CA90, rng.uniform(6.0, 12.0))        # clamp high
    else:
        setf(ram, CA90, rng.uniform(0.0, 6.0))         # bilinear interior

    setf(ram, CA60, rng.uniform(-50.0, 50.0))          # fmac addend
    setf(ram, CA44, rng.uniform(-50.0, 50.0))          # fmac multiply
    setf(ram, CA84, rng.uniform(-50.0, 50.0))          # fsub subtrahend
    if rng.random() < 0.1:
        setf(ram, CA60, 0.0)
    if rng.random() < 0.1:
        setf(ram, CA44, 0.0)

    setf(ram, CA28, rng.uniform(-1000.0, 1000.0))      # output junk
    return ram


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    rom = open(ROM, 'rb').read()

    cpu = SH2(rom)
    cpu2 = SH2(rom)          # dedicated instance for the leaves in ref()
    seeds = (0x446BC, 0xCA40, 0xCA90, 0x6BF34, 0xCA28)
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
                print('  CAB4=%d CA40=%r CAAD=%d CA90=%r CA60=%r CA44=%r '
                      'CA84=%r' % (
                          ram.get(CAB4, 0), rdf(ram, CA40), ram.get(CAAD, 0),
                          rdf(ram, CA90), rdf(ram, CA60), rdf(ram, CA44),
                          rdf(ram, CA84)))
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
    print('OK  0x446BC ignition_advance_interp '
          '(%d random inputs across %d seeds)' % (N * len(seeds), len(seeds)))
    print('\nAll ignition_advance_interp_446BC tests passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()
