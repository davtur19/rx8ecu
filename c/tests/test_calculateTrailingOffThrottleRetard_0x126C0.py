#!/usr/bin/env python3
"""test_calculateTrailingOffThrottleRetard_0x126C0.py

Differential test for ROM 0x126C0 (60E0FC00.bin) — lift
c/calculateTrailingOffThrottleRetard_0x126C0.c.

Runs the ACTUAL ROM bytes of 0x126C0 — including the real sub-call
isNotZero_wDivideByZeroProtect @0x2440 — in tools/sh2emu.py over seeded RAM
states (the oracle) and compares the full post-call RAM overlay (byte-exact,
task-stack window 0xFFFFDE00..DF00 skipped) plus the return register r0 against
a Python reference model that mirrors the C lift line-for-line.

Entry-point / range note: 0x126C0 IS the real entry point (function-pointer
slot @0x144CC of the engineControlCalculateTiming dispatcher 0x141FC table;
valid prologue; preceding function defaultTimingMinMax ends rts @0x126BC).  The
CSV range 0x0126C0..0x0127CC is CORRECT: code runs to rts @0x127BC (delay
@0x127BE), the next function (FUN_000127cc) starts exactly at the CSV end
0x127CC.

Key semantic facts (see the lift header): int32 trailing-side off-throttle
retard writer — the +4-shifted structural twin of defaultTimingMinMax:
  s = isNotZero(f32@A754); r = isNotZero(f32@A664); t = isNotZero(f32@C8A4)
  sticky u8@A65F (hysteresis on f32@C0D8 vs 0.5 / 0.45): >0.5 -> 1;
   >0.45 -> <unchanged>; else -> 0
  f32@A658 = u8@AAC6==1 ? (r? -20.0 : -25.0)
            : t==0&&s==0 ? -69.2
            : (u8@A65F==1 ? -69.2 : -20.0)
  return r0: u8@AAC6==1 -> r&0xFF ; t==0&&s==0 -> u8@AAC6 raw ; else -> u8@A65F

Run: python3 c/tests/test_calculateTrailingOffThrottleRetard_0x126C0.py [N]
     (N = random inputs per seed; default 100000 -> 500000 across 5 seeds)
"""
import os, random, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2, ts

ROM = os.path.join(ROOT, 'roms', 'stock', '60E0FC00.bin')
ADDR = 0x126C0

# ---- RAM addresses (see c/calculateTrailingOffThrottleRetard_0x126C0.c) ----
C0D8 = 0xFFFFC0D8   # f32 latch input
A754 = 0xFFFFA754   # f32 deadband input 1
A664 = 0xFFFFA664   # f32 deadband input 2
C8A4 = 0xFFFFC8A4   # f32 deadband input 3
AAC6 = 0xFFFFAAC6   # u8 mode gate (==1)
A65F = 0xFFFFA65F   # u8 sticky off-throttle latch (prior read + write)
A658 = 0xFFFFA658   # f32 trailing retard output

HELPER_ISNOTZERO = 0x2440   # = 1 if |value| > 1e-5; NaN -> 0

# ROM calibration constants (single-precision values in the pool)
CAL_HI  = ts(0.5)               # @0x6E0C4
CAL_DEL = ts(0.05)              # @0x6E0C8
CAL_LO  = ts(CAL_HI - CAL_DEL)  # hysteresis lower bound (0.45)
N25  = ts(-25.0)
N20a = ts(-20.0)
N69a = ts(-69.2)
N69b = ts(-69.2)
N20b = ts(-20.0)

STACK_LO = 0xFFFFDE00    # task stack window (skipped in the compare)
STACK_HI = 0xFFFFDF00


def rdf(m, a):
    return struct.unpack('>f', bytes(m.get(a + i, 0) for i in range(4)))[0]

def setf(m, a, v):
    for i, b in enumerate(struct.pack('>f', ts(v))):
        m[a + i] = b

def wrf(m, a, v):
    for i, b in enumerate(struct.pack('>f', ts(v))):
        m[a + i] = b


def ref(cpu2, m):
    """Line-for-line mirror of calculateTrailingOffThrottleRetard_0x126C0().
    Returns (RAM-effect dict, expected r0)."""
    m = dict(m)

    def cmp_in(addr):
        cpu2.call(HELPER_ISNOTZERO, fr={4: rdf(m, addr), 5: 0.0, 6: 1e-5}, ram=m)
        return cpu2.r[0] & 0xFF          # 0 or 1

    s = cmp_in(A754); r = cmp_in(A664); t = cmp_in(C8A4)
    c0d8 = rdf(m, C0D8)

    # sticky off-throttle latch (f32@C0D8 vs 0.5 / ≤0.45); NaN drives it to 0
    if c0d8 > CAL_HI:
        a65f = 1
    elif c0d8 > CAL_LO:
        a65f = m.get(A65F, 0)            # unchanged (sticky prior)
    else:
        a65f = 0
    m[A65F] = a65f

    aac6 = m.get(AAC6, 0)
    if aac6 == 1:
        a658 = N20a if r != 0 else N25
        r0 = r
    elif t == 0 and s == 0:
        a658 = N69a
        r0 = aac6
    else:
        a658 = N69b if a65f == 1 else N20b
        r0 = a65f
    wrf(m, A658, a658)
    return m, r0


def gen_state(rng):
    """Random seeded RAM hitting every float shape for the 4 float inputs; the
    mode/latch bytes and the output word get junk so a missed write is caught."""
    ram = {}
    for a in (C0D8, A754, A664, C8A4):
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
    ram[A65F] = rng.randrange(256)          # sticky prior (any byte)
    setf(ram, A658, rng.uniform(-1000.0, 1000.0))   # junk output word
    return ram


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    rom = open(ROM, 'rb').read()

    cpu = SH2(rom)
    cpu2 = SH2(rom)          # dedicated instance for the @0x2440 leaf in ref()
    seeds = (0x126C0, 0x125B0, 0x144CC, 0xA658, 0x2440)
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
                print('  C0D8=%r A754=%r A664=%r C8A4=%r AAC6=%r priorA65F=%r' %
                      (rdf(ram, C0D8), rdf(ram, A754), rdf(ram, A664),
                       rdf(ram, C8A4), ram.get(AAC6), ram.get(A65F)))
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
    print('OK  0x126C0 calculateTrailingOffThrottleRetard '
          '(%d random inputs across %d seeds)' % (N * len(seeds), len(seeds)))
    print('\nAll calculateTrailingOffThrottleRetard_0x126C0 tests passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()