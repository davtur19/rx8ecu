#!/usr/bin/env python3
"""test_calculateTrailingTimingBase_0x1202A.py

Differential test for ROM 0x1202A (60E0FC00.bin) — lift
c/calculateTrailingTimingBase_0x1202A.c.

Runs the ACTUAL ROM bytes of 0x1202A — including the real sub-calls
TwoDLookup @0x2068, ThreeDLookup @0x20DC, minValue @0x23F4 and saturateLow
@0x23E4 (all executed inside the emulator against the real ROM descriptor
tables) — in tools/sh2emu.py over seeded RAM states (the oracle) and compares
the full post-call RAM overlay (byte-exact, task-stack window 0xFFFFDE00..DF00
skipped) plus the return register r0 against a Python reference model that
mirrors the C lift line-for-line.

Entry-point / range note: 0x1202A IS the real entry point (function-pointer
slot @0x14408 of the engineControlCalculateTiming dispatcher 0x141FC table;
valid prologue; the leading twin 0x11F78 ends rts @0x12026).  The CSV range
0x1202A..0x12180 is CORRECT: code runs to rts @0x1215A (delay @0x1215C), the
next function (getIgnitionTimingInit? @0x12180) starts exactly at the CSV end.

Key semantic facts (see the lift header): void trailing-timing "base" writer
— structural twin of 0x11F78 with shifted RAM outputs and its own
descriptors/constants:
  A618 = TwoDLookup(0x67930, A7AC)                6-pt RPM map
  A61C = ThreeDLookup(0x67990, C0D8, B594)         8x7 load x RPM
  A624 = TwoDLookup(0x67944, A9FC)                 9-pt temp map
  A5F8 = 0.0 - A61C*A624 + A618
  A600 = (CC2C == 0) ? 80.0 : 11.0
  A620 = ThreeDLookup(0x679AC, C0D8, B594)         20x18 load x RPM
  A628 = ThreeDLookup(0x679DC, B594, A9FC)         4x3 RPM x temp (f32 cells)
  A5F0 = saturateLow( 0.0 + min(A620, A600), A628 )
r0 at return = 4 * x-axis index of f32@B594 on desc 0x679DC (the last helper
call is the 0x20DC lookup on the type-0 f32-cell desc; its interpolate
handler leaves r0 = ix<<2, and the 0x23E4/0x23F4 leaves never write r0).

Run: python3 c/tests/test_calculateTrailingTimingBase_0x1202A.py [N]
     (N = random inputs per seed; default 100000 -> 500000 across 5 seeds)
"""
import os, random, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2, ts

ROM = os.path.join(ROOT, 'roms', 'stock', '60E0FC00.bin')
ADDR = 0x1202A

# ---- RAM addresses (see c/calculateTrailingTimingBase_0x1202A.c header) ----
A7AC = 0xFFFFA7AC   # f32 in  (6-pt RPM map x input)
B594 = 0xFFFFB594   # f32 in  (RPM)
C0D8 = 0xFFFFC0D8   # f32 in  (load)
A9FC = 0xFFFFA9FC   # f32 in  (temp)
CC2C = 0xFFFFCC2C   # u8 gate in (clamp select)

A618 = 0xFFFFA618; A61C = 0xFFFFA61C; A624 = 0xFFFFA624
A5F8 = 0xFFFFA5F8; A600 = 0xFFFFA600; A620 = 0xFFFFA620
A628 = 0xFFFFA628; A5F0 = 0xFFFFA5F0

FLOAT_IN  = [A7AC, B594, C0D8, A9FC]
FLOAT_OUT = [A618, A61C, A624, A5F8, A600, A620, A628, A5F0]

# last 3D lookup descriptor (for the r0 = ix*4 expectation)
DESC_LAST = 0x679DC   # 4x3 RPM x temp, type-0 f32 cells

# ROM f32 constants used as addends/clamps
def romf(rom, a):
    return struct.unpack('>f', rom[a:a + 4])[0]
R_6DA64 = romf  # 0.0   (A5F8 base addend)
R_6DA68 = romf  # 80.0  (A600 clamp when CC2C == 0)
R_6DA6C = romf  # 11.0  (A600 clamp when CC2C != 0)
R_6DA70 = romf  # 0.0   (A5F0 addend)

STACK_LO = 0xFFFFDE00    # task stack window (skipped in the compare)
STACK_HI = 0xFFFFDF00


def r32(d, a):
    return struct.unpack('>f', bytes(d.get(a + i, 0) for i in range(4)))[0]


def f32b(v):
    return list(struct.pack('>f', ts(v)))


def wrf(m, a, v):
    for i, b in enumerate(struct.pack('>f', ts(v))):
        m[a + i] = b


def ax_index(axis, x):
    """Forward axis search with the ROM's clamp semantics (0x2624 backward
    search is equivalent on a strictly-ascending axis): x >= last -> n-1,
    x < first -> 0, else the interval [ax[i], ax[i+1])."""
    if not (x < axis[-1]):
        return len(axis) - 1
    if x < axis[0]:
        return 0
    for i in range(len(axis) - 1):
        if axis[i] <= x < axis[i + 1]:
            return i
    return len(axis) - 1


def ref(cpu2, m, rom):
    """Line-for-line mirror of calculateTrailingTimingBase_0x1202A().

    The lookup leaves (0x2068/0x20DC) and the min/max helpers (0x23F4/0x23E4)
    are executed in the dedicated emulator instance `cpu2` (they read the real
    ROM descriptor tables) so single-precision rounding matches the ROM
    exactly.  Returns (full RAM-effect dict, expected r0)."""
    m = dict(m)
    a7ac = r32(m, A7AC); rpm = r32(m, B594)
    c0d8 = r32(m, C0D8); a9fc = r32(m, A9FC)
    cc2c = m.get(CC2C, 0)

    # ---- lookup group 1 ----
    cpu2.call(0x2068, r4=0x67930, fr={4: a7ac})
    wrf(m, A618, cpu2.fr[0])
    cpu2.call(0x20DC, r4=0x67990, fr={4: c0d8, 5: rpm})
    wrf(m, A61C, cpu2.fr[0])
    cpu2.call(0x2068, r4=0x67944, fr={4: a9fc})
    wrf(m, A624, cpu2.fr[0])

    # ---- A5F8 = 0.0 - A61C*A624 + A618 ----
    a5f8 = ts(ts(ts(R_6DA64(rom, 0x6DA64)) - ts(r32(m, A61C) * r32(m, A624)))
              + r32(m, A618))
    wrf(m, A5F8, a5f8)

    # ---- A600 = (CC2C == 0) ? 80.0 : 11.0 ----
    a600 = R_6DA68(rom, 0x6DA68) if cc2c == 0 else R_6DA6C(rom, 0x6DA6C)
    wrf(m, A600, a600)

    # ---- lookup group 2 ----
    cpu2.call(0x20DC, r4=0x679AC, fr={4: c0d8, 5: rpm})
    wrf(m, A620, cpu2.fr[0])
    cpu2.call(0x20DC, r4=0x679DC, fr={4: rpm, 5: a9fc})
    wrf(m, A628, cpu2.fr[0])

    # ---- A5F0 = saturateLow( 0.0 + min(A620, A600), A628 ) ----
    cpu2.call(0x23F4, fr={4: r32(m, A620), 5: a600})
    vmin = cpu2.fr[0]
    cpu2.call(0x23E4, fr={4: ts(R_6DA70(rom, 0x6DA70) + vmin), 5: r32(m, A628)})
    wrf(m, A5F0, cpu2.fr[0])

    # ---- r0 on return = 4 * ix(B594 on desc 0x679DC's X axis) ----
    n = struct.unpack('>H', rom[DESC_LAST:DESC_LAST + 2])[0]
    axp = struct.unpack('>I', rom[DESC_LAST + 4:DESC_LAST + 8])[0]
    axis = [struct.unpack('>f', rom[axp + 4 * i:axp + 4 * i + 4])[0]
            for i in range(n)]
    r0 = 4 * ax_index(axis, rpm)
    return m, r0


def gen_state(rng):
    """Random seeded RAM hitting every table/branch combination: the four f32
    inputs sample their map ranges plus out-of-range clamps, NaN and the exact
    breakpoints; CC2C covers 0/1/other; every output word starts as junk so a
    missed write is caught."""
    ram = {}

    def setf(a, v):
        for i, b in enumerate(struct.pack('>f', float(v))):
            ram[a + i] = b

    def fuzz(a, lo, hi):
        r = rng.random()
        if r < 0.7:
            setf(a, rng.uniform(lo, hi))
        elif r < 0.85:
            setf(a, rng.choice([lo, hi, 0.0, (lo + hi) / 2.0]))
        elif r < 0.93:
            setf(a, float('nan'))
        else:
            setf(a, rng.uniform(-1e4, 1e4))

    fuzz(B594, 0, 10000)     # RPM  (desc2 y 800..2000, desc4 x 1300..2500)
    fuzz(C0D8, 0, 2.0)       # load (desc2 x 0.0625..0.5, desc4 x ..1.25)
    fuzz(A9FC, -60, 150)     # temp (axis -40..120)
    fuzz(A7AC, 0, 10000)     # 6-pt RPM map x (axis 700..1900)
    ram[CC2C] = rng.choice([0, 1, rng.randint(2, 255)])
    for a in FLOAT_OUT:      # previous outputs (overwritten)
        setf(a, rng.uniform(-200, 200))
    return ram


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    rom = open(ROM, 'rb').read()
    assert struct.unpack('>f', rom[0x6DA64:0x6DA68])[0] == 0.0
    assert struct.unpack('>f', rom[0x6DA68:0x6DA6C])[0] == 80.0
    assert struct.unpack('>f', rom[0x6DA6C:0x6DA70])[0] == 11.0
    assert struct.unpack('>f', rom[0x6DA70:0x6DA74])[0] == 0.0

    cpu = SH2(rom)
    cpu2 = SH2(rom)          # dedicated instance for the helper leaves in ref()
    seeds = (0x1202A, 0x11F78, 0x679DC, 0xB594, 0x6DA6C)
    total_fails = 0

    for seed in seeds:
        rng = random.Random(seed)
        fails = 0
        for it in range(N):
            ram = gen_state(rng)
            want, want_r0 = ref(cpu2, ram, rom)
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
                print('  A7AC=%r B594=%r C0D8=%r A9FC=%r CC2C=%d' %
                      (r32(ram, A7AC), r32(ram, B594), r32(ram, C0D8),
                       r32(ram, A9FC), ram.get(CC2C, 0)))
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
    print('OK  0x1202A calculateTrailingTimingBase '
          '(%d random inputs across %d seeds)' % (N * len(seeds), len(seeds)))
    print('\nAll calculateTrailingTimingBase_0x1202A tests passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()
