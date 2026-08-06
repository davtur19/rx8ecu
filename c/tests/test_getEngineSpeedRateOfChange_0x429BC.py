#!/usr/bin/env python3
"""test_getEngineSpeedRateOfChange_0x429BC.py

Differential test for ROM 0x429BC (60E0FC00.bin) - lift
c/getEngineSpeedRateOfChange_0x429BC.c.

Runs the ACTUAL ROM bytes of 0x429BC in tools/sh2emu.py over seeded RAM
states (the oracle) and compares the full post-call RAM overlay (byte-exact,
task-stack window 0xFFFFDE00..DF00 skipped) plus the return register r0
against a Python reference model that mirrors the C lift line-for-line.

Entry/range: 0x429BC IS the real entry (dispatcher slot @0x14488 of the
engineControlCalculateTiming 0x141FC table; the preceding function ends
rts+delay @0x42994; the next function 0x429EE starts exactly at the CSV end).
CSV range 0x429BC..0x429EE (50 B) CORRECT - no phantom rows.

Semantics (see lift header): computes the engine speed rate-of-change sample
that the sibling filterEngineSpeedRateOfChange (0x429EE) consumes.  It looks
up an interpolated scalar from 1D u8 table 0x69BC8 (X axis = f32@FFFFC928
engine RPM, y = u8 hold-per-rotor table), multiplies the delta between the
two raw RPM inputs (f32@FFFFC8FC - f32@FFFFC8F8) by that scalar, divides by a
normaliser f32@FFFFC910, clamps the result to >= 0.0 (ROM 0x23E4 = float
max), and writes it to f32@FFFFC8F4 (the rate-of-change "current raw rate"
read by 0x429EE).  r0 on return = the u8 byte the 1D lookup read at its final
index (the upper neighbour when the fraction is non-zero), carried byte-exact.

Run: python3 c/tests/test_getEngineSpeedRateOfChange_0x429BC.py [N]
     (N = random inputs per seed; default 100000 -> 500000 across 5 seeds)
"""
import os, random, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2, ts

ROM = os.path.join(ROOT, 'roms', 'stock', '60E0FC00.bin')
ADDR = 0x429BC

# ---- RAM addresses (see c/getEngineSpeedRateOfChange_0x429BC.c) ----
C928 = 0xFFFFC928   # f32 engine RPM (X input to the 1D lookup)
C8F8 = 0xFFFFC8F8   # f32 raw RPM A
C8FC = 0xFFFFC8FC   # f32 raw RPM B
C910 = 0xFFFFC910   # f32 scale normaliser
C8F4 = 0xFFFFC8F4   # f32 output rate-of-change
T1D = 0x69BC8        # 1D u8 table

STACK_LO = 0xFFFFDE00
STACK_HI = 0xFFFFDF00

ROM_BYTES = None


def ru16(a):
    return struct.unpack('>H', ROM_BYTES[a:a + 2])[0]


def ru8(a):
    return ROM_BYTES[a]


def rf32(a):
    return struct.unpack('>f', ROM_BYTES[a:a + 4])[0]


def ru32(a):
    return struct.unpack('>I', ROM_BYTES[a:a + 4])[0]


def lookup_index(xp, x):
    cnt = len(xp)
    i = cnt - 1
    if not (xp[i] > x):
        return cnt - 1, ts(0.0)
    if cnt == 1:
        return 0, ts(0.0)
    i -= 1
    while True:
        if not (xp[i] > x):
            break
        if i == 0:
            return 0, ts(0.0)
        i -= 1
    return i, ts(ts(x - xp[i]) / ts(xp[i + 1] - xp[i]))


def lookup1d_u8(base, x):
    """Mirror of ROM 0x2068 (1D u8 interp).  Returns (scaled float result,
    final u8 byte read)."""
    cnt = ru16(base)
    xp = [rf32(ru32(base + 4) + 4 * i) for i in range(cnt)]
    yp = ru32(base + 8)
    A = rf32(base + 0xC)
    B = rf32(base + 0x10)
    idx, frac = lookup_index(xp, ts(x))
    v = ru8(yp + idx)
    byte = v
    if frac != 0.0:
        byte = ru8(yp + idx + 1)          # upper neighbour (r0 on return)
        d = ts(float(byte) - float(v))    # fsub
        v = ts(frac * d + float(v))       # fmac
    return ts(v * A + B), byte            # fmac (single rounding)


def ref(m):
    """Line-for-line mirror of getEngineSpeedRateOfChange_0x429BC().  Returns
    (full RAM-effect dict, expected r0)."""
    m = dict(m)
    gf = lambda a: struct.unpack('>f', bytes(m.get(a + i, 0) for i in range(4)))[0]
    setf = lambda a, v: [m.__setitem__(a + i, struct.pack('>f', ts(v))[i]) for i in range(4)]

    rpm = gf(C928)
    A = gf(C8F8)
    B = gf(C8FC)
    scale = gf(C910)

    # 1D u8 lookup (jsr 0x2068): fr0 = scaled result, r0 = u8 byte
    lerp, r0 = lookup1d_u8(T1D, rpm)

    # (C8FC - C8F8) * lerp / C910  (each op single-precision)
    delta = ts(ts(B) - ts(A))
    num = ts(ts(lerp) * ts(delta))
    rate = ts(ts(num) / ts(scale))

    # clamp >= 0 (jsr 0x23E4 = float max(rate, 0.0)).  The SH-2E fcmp/gt sets T
    # only when rate > 0.0; on the fmax helper that T drives keeping `rate`,
    # and 0.0 is kept for rate <= 0.0, for -0.0 and for any NaN operand.
    if not (rate > 0.0):
        out = 0.0
    else:
        out = ts(rate)

    setf(C8F4, out)
    return m, r0


def gen_in(rng):
    """Random seeded RAM.  C928 spans the 1D axis [1..6] incl. fractional and
    clamp; A/B/scale span wide + edge values incl. NaN so fsub/fmul/fdiv and
    the clamp come out byte-exact."""
    ram = {}
    r = rng.random()
    if r < 0.5:
        c928 = float(rng.uniform(-2.0, 8.0))
    elif r < 0.75:
        c928 = float(rng.choice([0.0, 0.999, 1.0, 2.5, 5.999, 6.0, 6.5, 100.0,
                                 -100.0, 1e9]))
    elif r < 0.9:
        c928 = float('nan')
    else:
        c928 = float(rng.uniform(-1e8, 1e8))

    vals = []
    for idx in range(3):
        r = rng.random()
        if idx == 2:
            # C910 is a divisor: keep it non-zero (emulator fdiv raises on 0)
            vals.append(float(rng.choice([1.0, 2.0, 5.0, -1.0, 100.0, 1000.0])))
        elif r < 0.5:
            vals.append(float(rng.uniform(-1e5, 1e5)))
        elif r < 0.7:
            vals.append(float(rng.choice([0.0, 1.0, -1.0, 1e9, -1e9, 3.4e38])))
        elif r < 0.8:
            vals.append(float('nan'))
        else:
            vals.append(0.0)
    for a, v in ((C928, c928), (C8F8, vals[0]), (C8FC, vals[1]),
                 (C910, vals[2]), (C8F4, rng.uniform(-1e9, 1e9))):
        for i, b in enumerate(struct.pack('>f', ts(v))):
            ram[a + i] = b
    return ram


def main():
    global ROM_BYTES
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    ROM_BYTES = open(ROM, 'rb').read()
    cpu = SH2(ROM_BYTES)
    seeds = (0x429BC, 0x42A70, 0xffffC8FC, 0x69BC8, 0x14488)
    total_fails = 0
    for seed in seeds:
        rng = random.Random(seed)
        fails = 0
        for it in range(N):
            ram = gen_in(rng)
            want, want_r0 = ref(ram)
            cpu.call(ADDR, ram=ram)
            bad = []
            allk = set(k for k in want if isinstance(k, int)) | set(cpu.ram.keys())
            for k in allk:
                if STACK_LO <= k <= STACK_HI:
                    continue
                if cpu.ram.get(k, 0) != want.get(k, 0):
                    bad.append((k, cpu.ram.get(k, 0), want.get(k, 0)))
            if bad or cpu.r[0] != want_r0:
                print('MISMATCH seed=0x%X iter=%d: r0=%d want_r0=%d %s' %
                      (seed, it, cpu.r[0], want_r0,
                       {hex(k): (hex(g), hex(e)) for k, g, e in bad[:10]}))
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
    print('OK  0x429BC getEngineSpeedRateOfChange '
          '(%d random inputs across %d seeds)' % (N * len(seeds), len(seeds)))
    print('\nAll getEngineSpeedRateOfChange_0x429BC tests passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()