#!/usr/bin/env python3
"""test_dscRelatedTiming_0x18D3C.py

Differential test for ROM 0x18D3C (60E0FC00.bin) — lift
c/dscRelatedTiming_0x18D3C.c.

Runs the ACTUAL ROM bytes of 0x18D3C — including the real sub-calls
window_out_0x2440 (@0x2440, |x|>eps guard), f32_to_byte_0x2500 (@0x2500),
max_0x23E4 (@0x23E4), checkFloatValidity_0x46CC (@0x46CC, the sqrt chain) and
ThreeDLookup @0x20DC (x3, all executed inside the emulator against the real
ROM descriptor tables) — in tools/sh2emu.py over seeded RAM states (the
oracle) and compares the full post-call RAM overlay (byte-exact, task-stack
window 0xFFFFDE00..DF00 skipped) against a Python reference model that mirrors
the C lift line-for-line.  The function leaves r0 undefined (scratch register
clobbered by every helper), so the compare is RAM-only.

Entry-point / range note: 0x18D3C IS the real entry point — the ONLY 32-bit
reference in the ROM is the function-pointer slot @0x14448 of the
engineControlCalculateTiming dispatcher (0x141FC) table, next to the derate
family (0x1441C = calculateKnockTimingDerateConditionEvents, 0x14444..;
0x1444C/0x14450 = the cranking-timing pair).  Valid prologue (mov.l r14..r9 +
4x fmov.s + sts.l pr, add #0xF0); the CSV range 0x18D3C..0x18F3C is CORRECT:
code runs to rts @0x18F26 (delay @0x18F28), literal pool @0x18F2A..0x18F3A,
next function starts exactly at the CSV end @0x18F3C.

Semantics (see the lift header): DSC-related timing derate writer:
  mode = u8@BCB3 (selector 0..n)
  A98C (f32) by selector:
    mode==4            -> BCC4
    |BCC0| > 1e-5      -> -20.0            (0x2440 guard, r0==1)
    else               -> BCC4 - sqrt(max(X,0)/BCC0), X =
        (BCE8+BCEC+BCC8) + ((BCD8-BCA8-BCE4) - base) * 4/(4-mode) - BCD8,
        base = (A9A0 > A99C) ? BAFC : BC0C   (sqrt chain @0x46CC)
  A998 (f32) by selector:
    mode==1 -> 0.5*byte@6E8DC - 50 ; mode==2 -> ThreeD(0x67D58)
    mode==3 -> 0.5*byte@6E8DD - 50 ; else     -> ThreeD(0x67D3C)
  split = ThreeD(0x67D74, load, rpm)
  A994 = max(A98C, A998)
  A990 = max(A98C + split, A998 + split)
  A9AC = (A98C > A998) ? 0 : 1   (u8)

Run: python3 c/tests/test_dscRelatedTiming_0x18D3C.py [N]
     (N = random inputs per seed; default 100000 -> 500000 across 5 seeds)
"""
import os, random, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2, ts

ROM = os.path.join(ROOT, 'roms', 'stock', '60E0FC00.bin')
ADDR = 0x18D3C

# ---- RAM addresses (see c/dscRelatedTiming_0x18D3C.c header) ----
B594 = 0xFFFFB594   # f32 in  (RPM, fr13)
C0D8 = 0xFFFFC0D8   # f32 in  (load, fr14)
BCC0 = 0xFFFFBCC0   # f32 in  (sqrt divisor / guard)
BCC4 = 0xFFFFBCC4   # f32 in  (A98C base)
BCC8 = 0xFFFFBCC8   # f32 in  (sum component)
BC0C = 0xFFFFBC0C   # f32 in  (base select default)
BAFC = 0xFFFFBAFC   # f32 in  (base select high)
BCD8 = 0xFFFFBCD8   # f32 in  (sum subtract)
BCA8 = 0xFFFFBCA8   # f32 in  (base subtract)
BCE4 = 0xFFFFBCE4   # f32 in  (base subtract)
BCE8 = 0xFFFFBCE8   # f32 in  (sum component)
BCEC = 0xFFFFBCEC   # f32 in  (sum component)
A9A0 = 0xFFFFA9A0   # f32 in  (base-select compare)
A99C = 0xFFFFA99C   # f32 in  (base-select compare)
BCB3 = 0xFFFFBCB3   # u8 in   (mode selector)

A98C = 0xFFFFA98C   # f32 out
A998 = 0xFFFFA998   # f32 out
A994 = 0xFFFFA994   # f32 out
A990 = 0xFFFFA990   # f32 out
A9AC = 0xFFFFA9AC   # u8 out

FLOAT_IN  = [B594, C0D8, BCC0, BCC4, BCC8, BC0C, BAFC, BCD8, BCA8, BCE4,
             BCE8, BCEC, A9A0, A99C]
FLOAT_OUT = [A98C, A998, A994, A990]
BYTE_OUT  = [A9AC]

EPS = 1e-5
ROM_BYTE_1 = 0x6E8DC    # mode==1 offset byte
ROM_BYTE_3 = 0x6E8DD    # mode==3 offset byte
ROM_EPS    = 0x18E84    # f32 1e-5 used by the 0x2440 guard (exact as ROM)
DESC_67D3C = 0x67D3C    # A998 "else"  map (20x18, u8, 0.5/-50)
DESC_67D58 = 0x67D58    # A998 mode==2 map
DESC_67D74 = 0x67D74    # A990/A994 split map

STACK_LO = 0xFFFFDE00    # task stack window (skipped in the compare)
STACK_HI = 0xFFFFDF00

FAULT_46CC = 0xFFFF768C  # sqrt-chain NaN/Inf fault code sink in THIS bank


def r32(d, a):
    return struct.unpack('>f', bytes(d.get(a + i, 0) for i in range(4)))[0]


def f32b(v):
    return list(struct.pack('>f', ts(v)))


def wrf(m, a, v):
    for i, b in enumerate(struct.pack('>f', ts(v))):
        m[a + i] = b


def max_0x23E4(a, b):
    """0x23E4 — returns the larger of two floats (NaN -> picks second)."""
    return ts(b if a != a or not (a > b) else a)


def ref(cpu2, m, rom):
    """Line-for-line mirror of dscRelatedTiming_0x18D3C().

    The helper leaves (0x2440, 0x2500, 0x23E4, 0x46CC, 0x20DC) are executed in
    the dedicated emulator instance `cpu2` (they read the real ROM descriptor
    tables / sqrt chain) so single-precision rounding matches the ROM exactly.
    Returns the full RAM-effect dict.  r0 is undefined at return (scratch)."""
    m = dict(m)
    mode = m.get(BCB3, 0)
    rpm = r32(m, B594); load = r32(m, C0D8)
    bcc0 = r32(m, BCC0); bcc4 = r32(m, BCC4); bcc8 = r32(m, BCC8)
    bc0c = r32(m, BC0C); bafc = r32(m, BAFC)
    bcd8 = r32(m, BCD8); bca8 = r32(m, BCA8); bce4 = r32(m, BCE4)
    bce8 = r32(m, BCE8); bcec = r32(m, BCEC)
    a9a0 = r32(m, A9A0); a99c = r32(m, A99C)

    # ---- A98C (leading derate) ----
    # 0x2440 "window-out" guard: r0 = 1 if |BCC0| > eps, 0 if |BCC0| <= eps.
    # tst r4,r4 sets T=(r4==0); bf/s -> division path when r4 != 0, so the
    # -20 default fires when the guard returns 0 (|BCC0| <= eps).
    eps = struct.unpack('>f', rom[ROM_EPS:ROM_EPS + 4])[0]  # f32 1e-5 (exact)
    if mode == 4:
        a98c = bcc4
    else:
        cpu2.call(0x2440, fr={4: bcc0, 5: 0.0, 6: eps})
        if cpu2.r[0] == 0:              # |BCC0| <= eps -> -20 default
            a98c = -20.0
        else:                           # |BCC0| > eps -> division path
            base = bafc if (a9a0 > a99c) else bc0c
            fr15 = ts(ts(ts(bcd8 - bca8) - bce4) - base)
            cpu2.call(0x2500, r4=mode, fr={4: 1.0, 5: 0.0})
            byf = cpu2.fr[0]
            fr15 = ts(fr15 * ts(4.0 / ts(4.0 - byf)))
            s = ts(ts(ts(bce8 + bcec) + bcc8) + fr15)
            s = ts(s - bcd8)
            cpu2.call(0x23E4, fr={4: s, 5: 0.0})      # max(s, 0)
            q = ts(cpu2.fr[0] / bcc0)
            cpu2.call(0x46CC, fr={4: q})              # sqrt chain
            a98c = ts(bcc4 - cpu2.fr[0])
            # 0x46CC NaN/Inf fault write (RAM32@0xFFFF768C, this bank)
            for k in range(FAULT_46CC, FAULT_46CC + 4):
                if k in cpu2.ram:
                    m[k] = cpu2.ram[k]
    wrf(m, A98C, a98c)

    # ---- A998 (trailing derate) by selector ----
    if mode == 1:
        cpu2.call(0x2500, r4=rom[ROM_BYTE_1], fr={4: 0.5, 5: -50.0})
        a998 = cpu2.fr[0]
    elif mode == 2:
        cpu2.call(0x20DC, r4=DESC_67D58, fr={4: load, 5: rpm})
        a998 = cpu2.fr[0]
    elif mode == 3:
        cpu2.call(0x2500, r4=rom[ROM_BYTE_3], fr={4: 0.5, 5: -50.0})
        a998 = cpu2.fr[0]
    else:
        cpu2.call(0x20DC, r4=DESC_67D3C, fr={4: load, 5: rpm})
        a998 = cpu2.fr[0]
    wrf(m, A998, a998)

    # ---- split lookup + clamps ----
    cpu2.call(0x20DC, r4=DESC_67D74, fr={4: load, 5: rpm})
    split = cpu2.fr[0]

    wrf(m, A994, max_0x23E4(a98c, a998))                     # 0x18EE8
    wrf(m, A990, max_0x23E4(ts(a98c + split), ts(a998 + split)))  # 0x18EF2

    # ---- A9AC flag: (A98C > A998) ? 0 : 1 ----
    m[A9AC] = 0 if (a98c > a998) else 1
    return m


def gen_state(rng):
    """Random seeded RAM hitting every table/branch combination: the f32
    inputs sample the map ranges plus out-of-range clamps, NaN and the exact
    breakpoints; BCC0 spans the eps guard both sides; BCB3 covers 0..5 and
    other values; every output word starts as junk so a missed write is
    caught."""
    ram = {}

    def setf(a, v):
        for i, b in enumerate(struct.pack('>f', float(v))):
            ram[a + i] = b

    def fuzz(a, lo, hi, zero_bias=0.0):
        r = rng.random()
        if r < 0.7:
            setf(a, rng.uniform(lo, hi))
        elif r < 0.85:
            setf(a, rng.choice([lo, hi, 0.0, (lo + hi) / 2.0]))
        elif r < 0.93:
            setf(a, float('nan'))
        else:
            setf(a, rng.uniform(-1e4, 1e4))
        if rng.random() < zero_bias:
            setf(a, 0.0)

    fuzz(B594, 0, 10000)     # RPM  (desc y 500..9000)
    fuzz(C0D8, 0, 2.0)       # load (desc x 0.0625..1.25)
    # BCC0: bias near 0 to hit the |BCC0|<=eps division path, else spread
    r = rng.random()
    if r < 0.5:
        setf(BCC0, rng.choice([0.0, 1e-7, 5e-6, 1e-5, -1e-7, -5e-6]))
    else:
        fuzz(BCC0, -2, 2)
    fuzz(BCC4, -200, 200)
    fuzz(BCC8, -200, 200)
    fuzz(BC0C, -200, 200)
    fuzz(BAFC, -200, 200)
    fuzz(BCD8, -200, 200)
    fuzz(BCA8, -200, 200)
    fuzz(BCE4, -200, 200)
    fuzz(BCE8, -200, 200)
    fuzz(BCEC, -200, 200)
    fuzz(A9A0, -200, 200)
    fuzz(A99C, -200, 200)
    # mode: special values 0..4 weighted, plus a sprinkling of high values
    r = rng.random()
    if r < 0.15:
        mode = rng.randint(5, 255)
    else:
        mode = rng.choice([0, 1, 2, 3, 4])
    ram[BCB3] = mode
    for a in FLOAT_OUT:      # previous outputs (overwritten)
        setf(a, rng.uniform(-200, 200))
    for a in BYTE_OUT:       # previous outputs (overwritten)
        ram[a] = rng.randint(0, 255)
    return ram


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    seeds = (0x18D3C, 0x67D74, 0xBCC0, 0xBCB3, 0x6E8DC)
    total_fails = 0

    for seed in seeds:
        rng = random.Random(seed)
        cpu2 = SH2(rom)          # dedicated instance for the helper leaves
        fails = 0
        for it in range(N):
            cpu2.ram = {}        # isolate the 0x46CC fault-code write
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
                if STACK_LO <= k <= STACK_HI:    # task stack area
                    continue
                if cpu.ram.get(k, 0) != want.get(k, 0):
                    bad.append((k, cpu.ram.get(k, 0), want.get(k, 0)))
            if bad:
                print('MISMATCH seed=0x%X iter=%d: %s' %
                      (seed, it, {hex(k): (hex(g), hex(e)) for k, g, e in bad[:10]}))
                print('  mode=%d BCC0=%r BCC4=%r BCC8=%r BCD8=%r' %
                      (ram.get(BCB3, 0), r32(ram, BCC0), r32(ram, BCC4),
                       r32(ram, BCC8), r32(ram, BCD8)))
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
    print('OK  0x18D3C dscRelatedTiming '
          '(%d random inputs across %d seeds)' % (N * len(seeds), len(seeds)))
    print('\nAll dscRelatedTiming_0x18D3C tests passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()
