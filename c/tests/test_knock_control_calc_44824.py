#!/usr/bin/env python3
"""test_knock_control_calc_44824.py

Differential test for ROM 0x44824 (60E1D400.bin) — lift
c/knock_control_calc_44824.c.

Runs the ACTUAL ROM bytes of 0x44824 in tools/sh2emu.py over seeded RAM states
(the oracle) and compares the full post-call RAM overlay against a Python
reference model that mirrors the C lift line-for-line.

Entry-point note: 0x44824 IS the real entry point — the only ROM reference is
the function-pointer slot @0x1483C in the dispatcher engineControlCalculateTiming
(0x14584) dispatch table (c/engineControlCalculateTiming.c line 261).  Valid
prologue / rts+delay at 0x4488A/0x4488C; no branches into the body.

Key semantic facts (see the lift header):
  * void function — RAM side effects: f32@0xFFFFCA10 then f32@0xFFFFCA14
    (the latter is a reload-copy of the former).
  * Gate 1: u8@0xFFFFCAB4 must be 1.
  * Gate 2: u8@0xFFFFCAAF > u8@0x0007B3DB (1)  (cmp/hi, unsigned).
  * Passed gates:
      v  = (f32@0xFFFFAA10 - f32@0x0007B42C(-30.0)) * f32@0x0007B430(0.01)
      c  = 0x2404(v, 0.0, 1.0)                  (clamp)
      lk = 0x2068(desc@0x0006BE74, f32@0xFFFFB5B8)   (2D lookup)
      m  = 0x23F4(f32@0xFFFFCA18, lk)           (min)
      f32@0xFFFFCA10 = m * c                    (fmul)
    any gate failed -> f32@0xFFFFCA10 = 0.0
  * The leaves 0x2404 / 0x2068 / 0x23F4 are executed in the second emulator
    instance cpu2 (oracle) with their RAM merged — the same trick the coil /
    0x91FE tests use for helper calls.

Run: python3 c/tests/test_knock_control_calc_44824.py [N]
     (N = random inputs per seed; default 100000 -> 500000 across 5 seeds)
"""
import os, random, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2, ts

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ADDR = 0x44824

# ---- RAM addresses (see c/knock_control_calc_44824.c header) ----
CAB4 = 0xFFFFCAB4   # u8  enable gate (must == 1)
CAAF = 0xFFFFCAAF   # u8  rpm/knock gate (must be > ROM const 1)
AA10 = 0xFFFFAA10   # f32 temperature-ish input
B5B8 = 0xFFFFB5B8   # f32 2D lookup input (RPM-ish)
CA18 = 0xFFFFCA18   # f32 min input
CA10 = 0xFFFFCA10   # f32 output
CA14 = 0xFFFFCA14   # f32 output (copy)

ROM_7B3DB = 0x0007B3DB   # u8  1 (cmp/hi threshold)
ROM_7B42C = 0x0007B42C   # f32 -30.0
ROM_7B430 = 0x0007B430   # f32 0.01
ROM_MAP   = 0x0006BE74   # TwoDLookup descriptor (count=11,type=4,u8,0.5)


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


def ref(cpu2, m, rom, rom_map=ROM_MAP, rom_thr=ROM_7B3DB,
        rom_base=ROM_7B42C, rom_gain=ROM_7B430):
    """Line-for-line mirror of knock_control_calc_44824().

    Leaves 0x2404 / 0x2068 / 0x23F4 are executed in `cpu2` (oracle) and their
    RAM merged; the fsub/fmul are modelled with the same single-precision
    rounding (`ts`) the emulator applies.  Returns the RAM-effect dict.
    """
    m = dict(m)

    out10 = 0.0                            # fr15 = fldi0 (first delay slot)
    if m.get(CAB4, 0) == 1 and m.get(CAAF, 0) > rom[rom_thr]:
        # 0x44846..0x4487A
        fr2 = ts(rdf(m, AA10) - rdfb(rom, rom_base))   # fsub fr3,fr2
        v   = ts(fr2 * rdfb(rom, rom_gain))            # fmul fr1,fr4

        cpu2.call(0x2404, fr={4: v, 5: 0.0, 6: 1.0}, ram=m)  # clamp
        m = dict(cpu2.ram)
        c = cpu2.fr[0]

        x = rdf(m, B5B8)                     # fmov.s @r3,fr4 (delay of jsr)
        cpu2.call(0x2068, r4=rom_map, fr={4: x}, ram=m)  # 2D lookup
        m = dict(cpu2.ram)
        lk = cpu2.fr[0]

        cpu2.call(0x23F4, fr={4: rdf(m, CA18), 5: lk}, ram=m)  # min
        m = dict(cpu2.ram)
        mn = cpu2.fr[0]

        out10 = ts(mn * c)                   # fmul fr15,fr4

    wrf(m, CA10, out10)                      # fmov.s fr4/fr15,@r14
    wrf(m, CA14, rdf(m, CA10))               # reload @r14 -> 0xFFFFCA14
    return m


def gen_state(rng):
    """Random seeded RAM hitting every gate/clamp/lookup combination.

    CAB4 and CAAF biased to pass (and to fail) both gates; AA10 is sampled so
    the clamp (0..1) saturates on both sides and in the middle; B5B8 covers the
    2D-lookup axis 500..5500 plus out-of-range clamps; CA18 both below and
    above the lookup result so min() picks each side.
    """
    ram = {}

    # gate 1: ~85% pass
    if rng.random() < 0.85:
        ram[CAB4] = 1
    else:
        ram[CAB4] = rng.randint(0, 255)

    # gate 2 (u8 > 1): ~80% pass
    if rng.random() < 0.8:
        ram[CAAF] = rng.randint(2, 255)
    else:
        ram[CAAF] = rng.randint(0, 1)

    # temp input: wide enough to saturate the 0..1 clamp both ways
    r = rng.random()
    if r < 0.2:
        setf(ram, AA10, rng.uniform(-500.0, -30.0))   # -> v < 0 clamp low
    elif r < 0.4:
        setf(ram, AA10, rng.uniform(70.0, 500.0))     # -> v > 1 clamp high
    else:
        setf(ram, AA10, rng.uniform(-30.0, 70.0))     # interior of clamp
    if rng.random() < 0.05:
        setf(ram, AA10, rng.choice([-30.0, 70.0, 0.0]))

    # 2D lookup input: axis 500..5500 with clamps outside
    r = rng.random()
    if r < 0.15:
        setf(ram, B5B8, rng.uniform(0.0, 500.0))       # clamp low
    elif r < 0.3:
        setf(ram, B5B8, rng.uniform(5500.0, 8000.0))   # clamp high
    else:
        setf(ram, B5B8, rng.uniform(500.0, 5500.0))    # interior

    # min input: both below and above the lookup result
    setf(ram, CA18, rng.uniform(-10.0, 60.0))
    if rng.random() < 0.1:
        setf(ram, CA18, 0.0)

    setf(ram, CA10, rng.uniform(-1000.0, 1000.0))      # output junk
    setf(ram, CA14, rng.uniform(-1000.0, 1000.0))      # output junk
    return ram


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    rom = open(ROM, 'rb').read()

    cpu = SH2(rom)
    cpu2 = SH2(rom)          # dedicated instance for the leaves in ref()
    seeds = (0x44824, 0xCAAF, 0xAA10, 0xB5B8, 0x6BE74)
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
                print('  CAB4=%d CAAF=%d AA10=%r B5B8=%r CA18=%r' % (
                    ram.get(CAB4, 0), ram.get(CAAF, 0), rdf(ram, AA10),
                    rdf(ram, B5B8), rdf(ram, CA18)))
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
    print('OK  0x44824 knock_control_calc '
          '(%d random inputs across %d seeds)' % (N * len(seeds), len(seeds)))
    print('\nAll knock_control_calc_44824 tests passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()
