#!/usr/bin/env python3
"""test_throttleLiftoffRelated_0x425A2.py

Differential test for ROM 0x425A2 (60E0FC00.bin) - lift
c/throttleLiftoffRelated_0x425A2.c.

Runs the ACTUAL ROM bytes of 0x425A2 in tools/sh2emu.py over seeded RAM
states (the oracle) and compares the full post-call RAM overlay (byte-exact,
task-stack window 0xFFFFDE00..DF00 skipped) plus the return register r0
against a Python reference model that mirrors the C lift line-for-line.

Entry/range: 0x425A2 IS the real entry (dispatcher slot @0x1446C of the
engineControlCalculateTiming 0x141FC table; preceding fn ends rts+delay
@0x42570; next fn 0x426C4 starts at CSV end). CSV range 0x425A2..0x426C2
(288 B) CORRECT - no phantom rows.

Semantics (see lift header): per-cycle reaction to backing off the throttle.
Derives an integer liftoff state 0..3 from the throttle-rate f32@C934 (gated
by the hard override byte @AAC6), pushes a copy of engine RPM f32@C928 to
f32@C920 when a mode byte @C93E == 2 (else clears C920 to 0.0), then writes
two interpolated lookups:
  f32@C918 = 2D u16-grid interp (jsr 0x20DC) over one of four throttle tables
             (0x69BF0/0x69C0C/0x69C28/0x69C44, rowwise state 0..3, grid u16
             x0.01, A/B linear scale), X = f32@C920, Y = state (float int);
  f32@C91C = 1D u8 interp (jsr 0x2068) over table 0x69BDC, X = f32@C928.
The four 2D tables are selected by two enable bytes @C94A / @C94D; the state
by AAC6 + threshold logic on C934 (5.0/6.5 mova literals @0x7A1AC/0x7A1B0).
The 2D and 1D interpolators (lookup_index + u16/u8 interp, f32 single-precision
rounding everywhere) are mirrored here from the ROM handlers 0x2624/0x25F4/
0x26B0.  r0 on return = the u8 byte the 1D lookup read at its final index
(the upper neighbour when the fraction is non-zero), carried byte-exact.

Run: python3 c/tests/test_throttleLiftoffRelated_0x425A2.py [N]
     (N = random inputs per seed; default 100000 -> 500000 across 5 seeds)
"""
import os, random, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2, ts

ROM = os.path.join(ROOT, 'roms', 'stock', '60E0FC00.bin')
ADDR = 0x425A2

# ---- RAM addresses (see c/throttleLiftoffRelated_0x425A2.c) ----
C934 = 0xFFFFC934   # f32 throttle rate (input)
C928 = 0xFFFFC928   # f32 engine RPM (input)
AAC6 = 0xFFFFAAC6   # u8 hard override (state = 0)
C93E = 0xFFFFC93E   # u8 RPM-copy enable (== 2 -> C920 = C928)
C94A = 0xFFFFC94A   # u8 2D-table enable A
C94D = 0xFFFFC94D   # u8 2D-table enable B
C93D = 0xFFFFC93D   # u8 liftoff state (output)
C920 = 0xFFFFC920   # f32 RPM-X for the 2D interp (output)
C918 = 0xFFFFC918   # f32 2D interp result (output)
C91C = 0xFFFFC91C   # f32 1D interp result (output)

# 2D tables selected by (C94A, C94D): (0,0) -> 0x69BF0, (0,1) -> 0x69C0C,
# (1,0) -> 0x69C28, (1,1) -> 0x69C44.  1D table: 0x69BDC.
T2D = {(0, 0): 0x69BF0, (0, 1): 0x69C0C, (1, 0): 0x69C28, (1, 1): 0x69C44}
T1D = 0x69BDC

STACK_LO = 0xFFFFDE00
STACK_HI = 0xFFFFDF00

ROM_BYTES = None   # filled in main()


def ru16(a):
    return struct.unpack('>H', ROM_BYTES[a:a + 2])[0]


def ru8(a):
    return ROM_BYTES[a]


def rf32(a):
    return struct.unpack('>f', ROM_BYTES[a:a + 4])[0]


def ru32(a):
    return struct.unpack('>I', ROM_BYTES[a:a + 4])[0]


def lookup_index(xp, x):
    """Mirror of ROM 0x2624 (axis lookup): returns (idx, frac) with frac =
    single-precision (x - xp[idx]) / (xp[idx+1] - xp[idx]); x below the first
    axis point clamps to (0, 0.0), above the last to (cnt-1, 0.0)."""
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


def interp_u16(grid, idx, frac):
    """Mirror of ROM handler 0x26D0 (u16 grid cell interp).  fsub then a
    single fused fmac: v2-v, then ts(frac*(v2-v) + v) (one rounding)."""
    v = ru16(grid + idx * 2)
    if frac == 0.0:
        return ts(float(v))
    v2 = ru16(grid + (idx + 1) * 2)
    d = ts(float(v2) - float(v))          # fsub (single rounding)
    return ts(frac * d + float(v))        # fmac (single rounding)


def lookup2d(base, x, y):
    """Mirror of ROM 0x20DC (2D interp dispatcher -> 0x25F4 handler, type 8)."""
    cnt1 = ru16(base)
    cnt2 = ru16(base + 2)
    x1 = [rf32(ru32(base + 4) + 4 * i) for i in range(cnt1)]
    x2 = [rf32(ru32(base + 8) + 4 * i) for i in range(cnt2)]
    grid = ru32(base + 12)
    A = rf32(base + 0x14)
    B = rf32(base + 0x18)
    idx1, frac1 = lookup_index(x1, ts(x))
    idx2, frac2 = lookup_index(x2, ts(y))
    stride = cnt1 * 2
    v1 = interp_u16(grid + idx2 * stride, idx1, frac1)
    if frac2 == 0.0:
        val = v1
    else:
        v2 = interp_u16(grid + (idx2 + 1) * stride, idx1, frac1)
        d = ts(v2 - v1)                    # fsub
        val = ts(frac2 * d + v1)           # fmac
    return ts(val * A + B)                 # fmac (single rounding)


def lookup1d_u8(base, x):
    """Mirror of ROM 0x2068 (1D u8 interp dispatcher -> 0x26B0 handler, type
    4).  Returns (scaled float result, final u8 byte read)."""
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
    """Line-for-line mirror of throttleLiftoffRelated_0x425A2().  Returns
    (full RAM-effect dict, expected r0)."""
    m = dict(m)
    gf = lambda a: struct.unpack('>f', bytes(m.get(a + i, 0) for i in range(4)))[0]
    setf = lambda a, v: [m.__setitem__(a + i, struct.pack('>f', ts(v))[i]) for i in range(4)]
    gb = lambda a: m.get(a, 0)

    rrate = gf(C934)
    rpm = gf(C928)
    ovr = gb(AAC6)
    rpmz = gb(C93E)
    ea = gb(C94A)
    ed = gb(C94D)

    # ---- state (u8@C93D) ----
    if ovr == 1:
        state = 0
    elif rrate > 5.0:
        state = 2 if 6.5 > rrate else 3
    else:
        state = 1
    m[C93D] = state & 0xFF                # mov.b r?,@r14 (state byte)

    # ---- RPM-X copy / clear ----
    if rpmz == 2:
        c920 = rpm
    else:
        c920 = 0.0
    setf(C920, c920)

    # ---- 2D interp over the state-selected throttle map ----
    c918 = lookup2d(T2D[(ea, ed)], c920, float(state))
    setf(C918, c918)

    # ---- 1D u8 interp over 0x69BDC, X = f32(C928) ----
    c91c, r0 = lookup1d_u8(T1D, rpm)
    setf(C91C, c91c)

    return m, r0


def gen_in(rng):
    """Random seeded RAM.  C934 spans every state boundary (5.0/6.5) and NaN;
    C928 spans the 1D axis [1..6] incl. fractional + clamped + NaN; enables
    hit every 2D-table selector; the state/RPM-enable bytes sample all
    values."""
    ram = {}
    r = rng.random()
    if r < 0.4:
        c934 = float(rng.uniform(-5.0, 10.0))
    elif r < 0.7:
        c934 = float(rng.choice([-1e9, 0.0, 4.999, 5.0, 5.001, 6.499, 6.5,
                                 6.501, 7.0, 1e9]))
    elif r < 0.85:
        c934 = float('nan')
    else:
        c934 = float(rng.uniform(-1e8, 1e8))
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

    for a, v in ((C934, c934), (C928, c928)):
        for i, b in enumerate(struct.pack('>f', ts(v))):
            ram[a + i] = b
    ram[AAC6] = rng.choice([0, 0, 0, 1])
    ram[C93E] = rng.choice([0, 1, 2, 2, 3])
    ram[C94A] = rng.choice([0, 1])
    ram[C94D] = rng.choice([0, 1])
    # output words are junk so a missed write is caught
    for a in (C93D, C920, C918, C91C):
        for i, b in enumerate(struct.pack('>f', rng.uniform(-1e9, 1e9))):
            ram[a + i] = b
    return ram


def main():
    global ROM_BYTES
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    ROM_BYTES = open(ROM, 'rb').read()
    cpu = SH2(ROM_BYTES)
    seeds = (0x425A2, 0x4268C, 0xFFFFC918, 0x69BF0, 0x1446C)
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
    print('OK  0x425A2 throttleLiftoffRelated '
          '(%d random inputs across %d seeds)' % (N * len(seeds), len(seeds)))
    print('\nAll throttleLiftoffRelated_0x425A2 tests passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()
