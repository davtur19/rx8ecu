#!/usr/bin/env python3
"""test_defaultTimingMinMax_0x125B0.py

Differential test for ROM 0x125B0 (60E0FC00.bin) — lift
c/defaultTimingMinMax_0x125B0.c.

Runs the ACTUAL ROM bytes of 0x125B0 — including the real sub-call
isNotZero_wDivideByZeroProtect @0x2440 — in tools/sh2emu.py over seeded RAM
states (the oracle) and compares the full post-call RAM overlay (byte-exact,
task-stack window 0xFFFFDE00..DF00 skipped) plus the return register r0 against
a Python reference model that mirrors the C lift line-for-line.

Entry-point / range note: 0x125B0 IS the real entry point (function-pointer
slot @0x144B8 of the engineControlCalculateTiming dispatcher 0x141FC table;
valid prologue; preceding function calculateTrailingDerateRetard ends rts
@0x125AC).  The CSV range 0x0125B0..0x0126C0 is CORRECT: code runs to rts
@0x126BC (delay @0x126BE), the trailing twin starts exactly at the CSV end
0x126C0.

Key semantic facts (see the lift header): int32 leading-side default-timing
min/max derate writer:
  s = isNotZero(f32@A750); r = isNotZero(f32@A660); t = isNotZero(f32@C8A0)
     (isNotZero @0x2440 = 1 if |x| > 1e-5, NaN -> 0)
  sticky u8@A65E (hysteresis on f32@C0D8 vs 0.5 / 0.45): >0.5 -> 1;
   >0.45 -> <unchanged>; else -> 0
  f32@A648 = u8@AAC6==1 ? (r? -20.0 : -25.0)
            : t==0&&s==0 ? -58.5
            : (u8@A656==1 ? -58.5 : -20.0)
  return r0: u8@AAC6==1 -> r&0xFF ; t==0&&s==0 -> u8@AAC6 raw ; else -> u8@A65E
r0 at return is the function's own result register, computed per the trace.

Run: python3 c/tests/test_defaultTimingMinMax_0x125B0.py [N]
     (N = random inputs per seed; default 100000 -> 500000 across 5 seeds)
"""
import os, random, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2, ts

ROM = os.path.join(ROOT, 'roms', 'stock', '60E0FC00.bin')
ADDR = 0x125B0

# ---- RAM addresses (see c/defaultTimingMinMax_0x125B0.c header) ----
C0D8 = 0xFFFFC0D8   # f32 latch input
A750 = 0xFFFFA750   # f32 deadband input 1
A660 = 0xFFFFA660   # f32 deadband input 2
C8A0 = 0xFFFFC8A0   # f32 deadband input 3
AAC6 = 0xFFFFAAC6   # u8 mode gate (==1)
A65E = 0xFFFFA65E   # u8 sticky off-throttle latch (prior read + write)
A648 = 0xFFFFA648   # f32 default timing derate output

HELPER_ISNOTZERO = 0x2440   # = 1 if |value| > 1e-5; NaN -> 0

# ROM calibration constants (single-precision values in the pool)
CAL_HI  = ts(0.5)               # @0x6E0C4
CAL_DEL = ts(0.05)              # @0x6E0C8
CAL_LO  = ts(CAL_HI - CAL_DEL)  # hysteresis lower bound (0.45)
N25  = ts(-25.0)
N20a = ts(-20.0)
N58a = ts(-58.5)
N58b = ts(-58.5)
N20b = ts(-20.0)

STACK_LO = 0xFFFFDE00    # task stack window (skipped in the compare)
STACK_HI = 0xFFFFDF00


def f32_at(rom, a):
    return struct.unpack('>f', rom[a:a + 4])[0]


def setf(m, a, v):
    for i, b in enumerate(struct.pack('>f', ts(v))):
        m[a + i] = b


def rdf(m, a):
    return struct.unpack('>f', bytes(m.get(a + i, 0) for i in range(4)))[0]


def wrf(m, a, v):
    for i, b in enumerate(struct.pack('>f', ts(v))):
        m[a + i] = b


def ref(cpu2, m):
    """Line-for-line mirror of defaultTimingMinMax_0x125B0().

    The @0x2440 leaf is executed in `cpu2` (oracle) and its r0 result merged;
    every fcmp / fsub mirrors the emulator's single-precision rounding.
    Returns (RAM-effect dict, expected r0)."""
    m = dict(m)

    def cmp_in(addr):
        cpu2.call(HELPER_ISNOTZERO, fr={4: rdf(m, addr), 5: 0.0, 6: 1e-5}, ram=m)
        return cpu2.r[0] & 0xFF          # 0 or 1

    s = cmp_in(A750); r = cmp_in(A660); t = cmp_in(C8A0)
    c0d8 = rdf(m, C0D8)

    # sticky latch (f32@C0D8 vs 0.5 / ≤0.45); NaN drives it to 0
    if c0d8 > CAL_HI:
        a65e = 1
    elif c0d8 > CAL_LO:
        a65e = m.get(A65E, 0)            # unchanged (sticky prior)
    else:
        a65e = 0
    m[A65E] = a65e

    aac6 = m.get(AAC6, 0)
    if aac6 == 1:
        a648 = N20a if r != 0 else N25
        r0 = r
    elif t == 0 and s == 0:
        a648 = N58a
        r0 = aac6
    else:
        a648 = N58b if a65e == 1 else N20b
        r0 = a65e
    wrf(m, A648, a648)
    return m, r0


def gen_state(rng):
    """Random seeded RAM hitting every float shape (finite spans, boundaries,
    denormals, infinities, NaN) for the 4 float inputs; the mode/latch bytes and
    the output word get junk so a missed write is caught."""
    ram = {}
    for a in (C0D8, A750, A660, C8A0):
        r = rng.random()
        if r < 0.6:
            setf(ram, a, rng.uniform(-40.0, 40.0))
        elif r < 0.75:
            setf(ram, a, rng.choice([0.0, -0.0, 1.0, -1.0, 100.0, -100.0,
                                     1e-6, -1e-6, 3.4e38, -3.4e38, 1e-40]))
        elif r < 0.85:
            setf(ram, a, float('nan'))
        elif r < 0.93:
            setf(ram, a, float('inf') if rng.random() < 0.5 else float('-inf'))
        else:
            setf(ram, a, rng.uniform(-2000.0, 2000.0))
    ram[AAC6] = rng.randrange(256)          # mode byte (any value)
    ram[A65E] = rng.randrange(256)          # sticky prior (any byte)
    setf(ram, A648, rng.uniform(-1000.0, 1000.0))   # junk output word
    return ram


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    rom = open(ROM, 'rb').read()

    cpu = SH2(rom)
    cpu2 = SH2(rom)          # dedicated instance for the @0x2440 leaf in ref()
    seeds = (0x125B0, 0x126C0, 0x144B8, 0xA648, 0x2440)
    total_fails = 0

    for seed in seeds:
        rng = random.Random(seed)
        fails = 0
        for it in range(N):
            ram = gen_state(rng)
            want, want_r0 = ref(cpu2, ram)
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
                print('  C0D8=%r A750=%r A660=%r C8A0=%r AAC6=%r priorA65E=%r' %
                      (rdf(ram, C0D8), rdf(ram, A750), rdf(ram, A660),
                       rdf(ram, C8A0), ram.get(AAC6), ram.get(A65E)))
                fails += 1
                if fails >= 3:
                    break
        print('  seed 0x%X: %d inputs, fails=%d' % (seed, N, fails))
        total_fails += fails
        if total_fails:
            break

    if total_fails:
        print('\n%d FAILURES(S)' % total_fails)
        sys.exit(1)
    print('OK  0x125B0 defaultTimingMinMax '
          '(%d random inputs across %d seeds)' % (N * len(seeds), len(seeds)))
    print('\nAll defaultTimingMinMax_0x125B0 tests passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()