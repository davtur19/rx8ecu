#!/usr/bin/env python3
"""test_getEngineLimitTimingDerates_0x12CE8.py

Differential test for ROM 0x12CE8 (60E0FC00.bin) — lift
c/getEngineLimitTimingDerates_0x12CE8.c.

Runs the ACTUAL ROM bytes of 0x12CE8 in tools/sh2emu.py over seeded RAM states
(the oracle) and compares the full post-call RAM overlay (byte-exact) plus the
return register r0 against a Python reference model that mirrors the C lift
line-for-line.

Entry-point note: 0x12CE8 IS the real entry point — the function-pointer slot
@0x14444 in the dispatcher engineControlCalculateTiming (0x141FC) dispatch
table.  Valid entry (opens with a mov.l literal load; preceding
somethingEngineLoadCalc ends rts @0x12CE0).  The CSV range 0x12CE8..0x12D30
is CORRECT (code to rts @0x12D00 + delay store @0x12D02, literal pool
0x12D04..0x12D2E, next function at 0x12D30).

Key semantic facts (see the lift header): scale two limit-timing derate floats
by a factor read from ROM literal address 0x0007266C (stock value 1.0f), each
via an exact single-precision fmul:
  factor = f32@0x0007266C
  f32@0xFFFFA660 = factor * f32@0xFFFFA674
  f32@0xFFFFA664 = factor * f32@0xFFFFA678
r0 after return = 0 (no integer register is touched); fr0 = f32@A664.
The ROOM address 0x7266C sits below ROM length, but the opaque ROM-as-RAM
read is honored by the emulator, so the harness treats it as an input float.

Run: python3 c/tests/test_getEngineLimitTimingDerates_0x12CE8.py [N]
     (N = random inputs per seed; default 100000 -> 500000 across 5 seeds)
"""
import os, random, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2, ts

ROM = os.path.join(ROOT, 'roms', 'stock', '60E0FC00.bin')
ADDR = 0x12CE8

FACTOR_ADDR = 0x0007266C   # ROM-as-input float factor (stock 1.0f)
A674 = 0xFFFFA674   # f32 limit lead derate input
A678 = 0xFFFFA678   # f32 limit trail derate input
A660 = 0xFFFFA660   # f32 scaled lead output
A664 = 0xFFFFA664   # f32 scaled trail output

STACK_LO = 0xFFFFDE00    # task stack window (skipped in the compare)
STACK_HI = 0xFFFFDF00


def setf(m, a, v):
    for i, b in enumerate(struct.pack('>f', ts(v))):
        m[a + i] = b


def rdf(m, a):
    return struct.unpack('>f', bytes(m.get(a + i, 0) for i in range(4)))[0]


def wrf(m, a, v):
    for i, b in enumerate(struct.pack('>f', ts(v))):
        m[a + i] = b


def ref(m):
    """Mirror of getEngineLimitTimingDerates_0x12CE8().  Returns (RAM-effect
    dict, expected r0)."""
    m = dict(m)
    factor = rdf(m, FACTOR_ADDR)
    d = ts(factor * rdf(m, A674))      # fmul fr2,fr3 -> fmov.s fr2,@A660
    wrf(m, A660, d)
    d2 = ts(factor * rdf(m, A678))     # fmul fr1,foot -> fmov.s fr0,@A664 (delay)
    wrf(m, A664, d2)
    return m, 0                        # r0 untouched -> 0


def gen_state(rng):
    """Random seeded RAM hitting every float shape (finite spans, boundaries,
    denormals, infinities, NaN) for the factor and the two derate inputs; the
    two output words are junk so a missed write is caught."""
    ram = {}

    def pick():
        r = rng.random()
        if r < 0.6:
            return rng.uniform(-40.0, 40.0)
        if r < 0.72:
            return rng.choice([0.0, -0.0, 1.0, -1.0, 100.0, -100.0,
                               1e-6, 3.4e38, 1e-40])
        if r < 0.84:
            return float('nan')
        if r < 0.92:
            return float('inf') if rng.random() < 0.5 else float('-inf')
        return rng.uniform(-2000.0, 2000.0)

    setf(ram, FACTOR_ADDR, pick())     # factor (stock 1.0)
    setf(ram, A674, pick())
    setf(ram, A678, pick())
    setf(ram, A660, rng.uniform(-1000.0, 1000.0))  # junk outputs
    setf(ram, A664, rng.uniform(-1000.0, 1000.0))
    return ram


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    rom = open(ROM, 'rb').read()

    cpu = SH2(rom)
    seeds = (0x12CE8, 0x12D30, 0x14444, 0xA660, 0xA664)
    total_fails = 0

    for seed in seeds:
        rng = random.Random(seed)
        fails = 0
        for it in range(N):
            ram = gen_state(rng)
            want, want_r0 = ref(ram)
            try:
                cpu.call(ADDR, ram=ram)
            except Exception as e:
                print('EMULATOR EXC seed=0x%X iter=%d: %s' % (seed, it, e))
                fails += 1
                break
            bad = []
            allk = set(k for k in want if isinstance(k, int)) | set(cpu.ram.keys())
            for k in allk:
                if STACK_LO <= k <= STACK_HI:    # task stack area
                    continue
                if cpu.ram.get(k, 0) != want.get(k, 0):
                    bad.append((k, cpu.ram.get(k, 0), want.get(k, 0)))
            if bad or cpu.r[0] != want_r0:
                print('MISMATCH seed=0x%X iter=%d: r0=%d want_r0=%d %s' %
                      (seed, it, cpu.r[0], want_r0,
                       {hex(k): (hex(g), hex(e)) for k, g, e in bad[:10]}))
                print('  factor=%r A674=%r A678=%r' %
                      (rdf(ram, FACTOR_ADDR), rdf(ram, A674), rdf(ram, A678)))
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
    print('OK  0x12CE8 getEngineLimitTimingDerates '
          '(%d random inputs across %d seeds)' % (N * len(seeds), len(seeds)))
    print('\nAll getEngineLimitTimingDerates_0x12CE8 tests passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()