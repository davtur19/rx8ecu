#!/usr/bin/env python3
"""test_engine_load_estimator_0x190A6.py

Differential test for ROM 0x190A6 (60E1D400.bin) — lift
c/engine_load_estimator_0x190A6.c.

Runs the ACTUAL ROM bytes of 0x190A6 in tools/sh2emu.py over seeded RAM states
(the oracle) and compares the full post-call RAM overlay against a Python
reference model that mirrors the C lift line-for-line.

Key semantic facts (see the lift header):
  * A9D0 = old A9BC value (unconditional snapshot copy).
  * Refresh path (3-D load map): only when A9BC == 0 AND A9BE == 0 AND
    (A9B0 < 0 OR A9B4 < 0) — the fcmp/gt 0.0,x == x < 0.0 tests, so NaN falls
    through to the countdown path.  Then A9BC = ThreeDLookup_FP_16bit(desc
    0x69F4C, x = RPM, y = load), a 19x11 u16-cell surface (axis_x RPM 0..9000
    @0x6F454, axis_y load 0..1.25 @0x6F4A0, values @0x6F4CC).
  * Countdown path: if A9BC != 0 (any nonzero — extu.w + cmp/pl), A9BC -= 1.

The reference model computes the 0x213C leaf in a second emulator instance
(cpu2) — the same emulator-in-the-model trick the other lift tests use — so
single-precision rounding and the u16 truncation match the ROM exactly.

Run: python3 c/tests/test_engine_load_estimator_0x190A6.py [N]
     (N = random inputs per seed; default 100000 -> 500000 across 5 seeds)
"""
import os, random, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ADDR = 0x190A6

# ---- RAM addresses (see c/engine_load_estimator_0x190A6.c header) ----
A9BC = 0xFFFFA9BC   # u16 load-estimate counter (out)
A9BE = 0xFFFFA9BE   # u16 refresh gate
A9D0 = 0xFFFFA9D0   # u16 snapshot out (old A9BC)
A9B0 = 0xFFFFA9B0   # f32 refresh cond A
A9B4 = 0xFFFFA9B4   # f32 refresh cond B
B5B8 = 0xFFFFB5B8   # f32 RPM
C12C = 0xFFFFC12C   # f32 load

DESC = 0x69F4C      # load-estimate Map2D descriptor (ROM)
FLOAT_IN = [A9B0, A9B4, B5B8, C12C]


def r16(d, a):
    return struct.unpack('>H', bytes(d.get(a + i, 0) for i in range(2)))[0]


def r32(d, a):
    return struct.unpack('>f', bytes(d.get(a + i, 0) for i in range(4)))[0]


def w16(m, a, v):
    for i, b in enumerate(struct.pack('>H', v & 0xFFFF)):
        m[a + i] = b


def ref(cpu2, ram):
    """Line-for-line mirror of engine_load_estimator_0x190A6().

    The 0x213C ThreeDLookup_FP_16bit call is executed in the dedicated emulator
    instance `cpu2` so float rounding matches the ROM exactly.  Returns a full
    RAM-effect dict (int keys -> byte values).
    """
    m = dict(ram)
    a9bc = r16(m, A9BC)

    # 0x190B0 mov.w r3,@r4: snapshot the pre-call counter value
    w16(m, A9D0, a9bc)

    # refresh only when both counters are 0 AND (A9B0 < 0 OR A9B4 < 0);
    # fcmp/gt 0.0,x == x < 0.0, so NaN inputs fall through to countdown.
    if a9bc == 0 and r16(m, A9BE) == 0 \
            and (r32(m, A9B0) < 0.0 or r32(m, A9B4) < 0.0):
        cpu2.call(0x213C, r4=DESC, fr={4: r32(m, B5B8), 5: r32(m, C12C)})
        w16(m, A9BC, cpu2.r[0])            # 0x190EA mov.w r0,@r14 (u16 trunc)
        return m

    # 0x190EC..0x190FA countdown: extu.w + cmp/pl true for any nonzero u16
    if a9bc != 0:
        w16(m, A9BC, a9bc - 1)
    return m


def gen_state(rng):
    """Random seeded RAM hitting every branch combination."""
    ram = {}

    def setf(a, v):
        for i, b in enumerate(struct.pack('>f', float(v))):
            ram[a + i] = b

    # counters (gate/snapshot)
    w16(ram, A9BC, rng.randint(0, 0xFFFF))
    w16(ram, A9BE, rng.randint(0, 0xFFFF))
    w16(ram, A9D0, rng.randint(0, 0xFFFF))     # previous output (overwritten)
    # refresh conditions: mix of negative / non-negative / NaN
    for a in [A9B0, A9B4]:
        r = rng.random()
        if r < 0.25:
            setf(a, -rng.uniform(0, 100))
        elif r < 0.7:
            setf(a, rng.uniform(0, 100))
        elif r < 0.85:
            setf(a, 0.0)
        else:
            setf(a, float('nan'))
    # lookup inputs (incl. out of map range)
    setf(B5B8, rng.uniform(-500, 9500))
    setf(C12C, rng.uniform(-1, 2.0))
    return ram


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    rom = open(ROM, 'rb').read()

    cpu = SH2(rom)
    cpu2 = SH2(rom)         # dedicated instance for the 0x213C leaf call in ref()
    seeds = (0x190A6, 0xA9BC, 0xA9BE, 0x69F4C, 0x213C)
    total_fails = 0

    for seed in seeds:
        rng = random.Random(seed)
        fails = 0
        for it in range(N):
            ram = gen_state(rng)
            want = ref(cpu2, ram)
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
                print('  A9BC=%04x A9BE=%04x A9B0=%r A9B4=%r rpm=%r load=%r' % (
                    r16(ram, A9BC), r16(ram, A9BE), r32(ram, A9B0), r32(ram, A9B4),
                    r32(ram, B5B8), r32(ram, C12C)))
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
    print('OK  0x190A6 engine_load_estimator  (%d random inputs across %d seeds)'
          % (N * len(seeds), len(seeds)))
    print('\nAll engine_load_estimator_0x190A6 tests passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()
