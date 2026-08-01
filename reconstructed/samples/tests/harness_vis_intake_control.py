#!/usr/bin/env python3
"""
harness_vis_intake_control.py — equivalence of rx8_vis_intake_control @0x23718.

Reconstructed source: samples/src/rx8_vis_intake_control.c
Verified lift   : c/vis_intake_control.c (same address; the ROM bytes are
                  executed for real here via tools/sh2emu.py, including the
                  jsr'd callees 0x20DC (type-8 u16-cell 3-D map read + the
                  0x2624 axis-search / 0x25F4 row-interp leaves), 0x2404
                  (clamp) and the 0x24D0 float->index leaf reached only on
                  the cmode=0 dead path).

The function is a void task with NO ABI parameters and NO return value: its
whole effect is on RAM (the 14 f32 rolling-table cells @0xFFFFB408..0xFFFFB43C
and the u8 table-index byte @0xFFFFB45C), so the equivalence check compares
RAM side-effects, not a return register:

  - emulator side: seed the two f32 lookup inputs (x @0xFFFFB5B8, y
    @0xFFFFAA40), the three Map2D selector bytes @0xFFFFB33C/D/E, the f32
    dead-path input @0xFFFFB5C8, the 14 f32 table pre-states and the
    counter-mode cal byte @0x73F68 in the sparse ram overlay (over the ROM,
    so the per-vector cmode override reaches the executing bytes exactly as
    the oracle's per-vector write into its mapped ROM page does), call the
    ROM entry @0x23718 (callees run as real ROM bytes), read the 14 table
    cells + index byte back;
  - host side: the dedicated oracle mmap()s the pages backing the RAM cells
    AND the three ROM pages (0x6A000 Map2D descriptors, 0x73000 calibration
    constants, 0x74000 axis/value grids) straight from the ROM file, seeds
    the same bytes, runs the reconstructed C and prints the same 15 cells.

EDGE vectors cover the selector-byte combinations (all four map selections
plus non-binary values, which the `== 1` tests must ignore), the 2-D lookup
axes (every breakpoint +/- ulp, 0, -0.0, denormals, max finite, NaN, +/-inf,
sign flips, out of range), distinguishable stale table pre-states (to catch
any rolling-shift cell the ROM forgets to re-write) and the cmode=0 dead
path (b5c8 around the d==0 and idx==12 boundaries); N random pre-states
follow (fixed seed = the ROM address).

Usage:  python3 harness_vis_intake_control.py [N]  (default N = 20000)
"""
import os
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROM_PATH, load_cpu, make_rng, report  # noqa: E402
from sh2emu import f2bits  # noqa: E402

ADDR = 0x23718
N_DEFAULT = 20000
SEED = 0x23718                    # the ROM address doubles as the RNG seed
BUILD_DIR = '/tmp/rx8-recon-vis_intake_control'

# ---- RAM cells (see rx8_vis_intake_control.c) ----
X_ADDR = 0xFFFFB5B8               # f32 x (boost) for the 2-D lookup
Y_ADDR = 0xFFFFAA40               # f32 y (rpm/other) for the 2-D lookup
SEL_C_ADDR = 0xFFFFB33C           # u8  table selector ==1 -> 0x6AC60
SEL_D_ADDR = 0xFFFFB33D           # u8  table selector ==1 -> 0x6AC7C
SEL_E_ADDR = 0xFFFFB33E           # u8  table selector ==1 -> 0x6AC98
TABLE_ADDR = 0xFFFFB408           # 14 f32 rolling-history cells
IDX_ADDR = 0xFFFFB45C             # u8  table index (0 in stock ROM)
DP_ADDR = 0xFFFFB5C8              # f32 dead-path input

# ---- ROM calibration cells (stock values asserted before the run) ----
ROM_CMODE_ADDR = 0x73F68          # u8  1 = counter-mode (table idx = 0)
ROM_CLAMP_ADDR = 0x73F6C          # f32 84.0 (clamp high)
ROM_DP_SC_ADDR = 0x73F74          # f32 2.0  (dead-path scale)
ROM_DP_OF_ADDR = 0x73F78          # f32 2.0  (dead-path offset)

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def seed_ram(init, addr, n, val):
    """Byte-exact big-endian store of a width-`n` value in the ram overlay."""
    for i in range(n):
        init[addr + i] = (val >> (8 * (n - 1 - i))) & 0xFF


def build_oracle(cc='cc'):
    """Compile the reconstructed source + its dedicated oracle into a binary."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_vis_intake_control.c'),
           os.path.join(SAMPLES, 'src', 'rx8_vis_intake_control.c'),
           '-lm',                  # fmaf() lives in libm
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def check_cal(cpu):
    """The stock-ROM calibration cells are fixed; refuse to run if they ever
    change so the ROM-page mapping stays meaningful."""
    if (cpu.rom[ROM_CMODE_ADDR] != 0x01
            or struct.unpack_from('>f', cpu.rom, ROM_CLAMP_ADDR)[0] != 84.0
            or struct.unpack_from('>f', cpu.rom, ROM_DP_SC_ADDR)[0] != 2.0
            or struct.unpack_from('>f', cpu.rom, ROM_DP_OF_ADDR)[0] != 2.0):
        raise RuntimeError(
            'unexpected VIS calibration bytes @0x%X/0x%X/0x%X/0x%X'
            % (ROM_CMODE_ADDR, ROM_CLAMP_ADDR, ROM_DP_SC_ADDR, ROM_DP_OF_ADDR))


def run_emu(cpu, vec):
    """Seed every input cell (+ the per-vector cmode), run the ROM bytes
    @0x23718 (callees included) and return the 15-tuple of post-state cells:
    the 14 f32 table cells as raw big-endian bits + the u8 index byte."""
    x, y, selc, seld, sele, dp, cmode, t = (vec[0], vec[1], vec[2], vec[3],
                                            vec[4], vec[5], vec[6], vec[7:])
    init = {}
    seed_ram(init, X_ADDR, 4, x & 0xFFFFFFFF)
    seed_ram(init, Y_ADDR, 4, y & 0xFFFFFFFF)
    init[SEL_C_ADDR] = selc & 0xFF
    init[SEL_D_ADDR] = seld & 0xFF
    init[SEL_E_ADDR] = sele & 0xFF
    seed_ram(init, DP_ADDR, 4, dp & 0xFFFFFFFF)
    init[ROM_CMODE_ADDR] = cmode & 0xFF
    for i in range(14):
        seed_ram(init, TABLE_ADDR + 4 * i, 4, t[i] & 0xFFFFFFFF)
    cpu.call(ADDR, ram=init)
    return (tuple(cpu.rd(TABLE_ADDR + 4 * i, 4) for i in range(14))
            + (cpu.rd(IDX_ADDR, 1),))


def gen_edges():
    """Edge pre-states (x, y, selc, seld, sele, dp, cmode, t0..t13) targeting
    every branch: selector combinations, lookup-axis and clamp boundaries,
    NaN/+/-inf raw bits, distinguishable stale table cells and the cmode=0
    dead path."""
    v = []
    t_base = tuple(f2bits(1000.0 + 1000.0 * i) for i in range(14))

    def push(xb, yb, sel, dpb, cmode, t=None):
        v.append((xb, yb, sel[0], sel[1], sel[2], dpb, cmode) +
                 (t_base if t is None else t))

    X_BP = (0.0, 250.0, 500.0, 750.0, 1000.0, 1500.0, 2000.0, 2500.0,
            3000.0, 3500.0, 4000.0, 4500.0, 5000.0, 5500.0, 6000.0, 6500.0,
            7000.0, 7500.0, 8000.0, 8500.0, 9000.0)
    Y_BP = (0.0, 2.5, 5.0, 7.5, 10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0,
            45.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0)
    SPECIALS = (0x00000000, 0x80000000, 0x00000001, 0x007FFFFF, 0x00800000,
                0x7F7FFFFF, 0xFF7FFFFF, 0x7F800000, 0xFF800000, 0x7FC00000,
                0x7FA00000, 0xFFFFFFFF)
    SELS = ((1, 0, 0), (0, 1, 0), (0, 0, 1), (0, 0, 0),
            (1, 1, 0), (0, 1, 1), (1, 0, 1), (1, 1, 1),
            (0xFF, 0, 0), (2, 0, 0), (0, 0x80, 0), (0, 0, 0xFE))

    # (a) every selector combo x representative in/out-of-range points.
    for sel in SELS:
        for x in (500.0, 4500.0, 8750.0, -1000.0, 12000.0):
            for y in (10.0, 50.0, 99.0, 120.0):
                push(f2bits(x), f2bits(y), sel, f2bits(8.0), 1)
    # (b) all x breakpoints (+/-0.5) at two y points.
    for x in X_BP:
        for xoff in (0.0, 0.5, -0.5):
            push(f2bits(x + xoff), f2bits(50.0), (1, 0, 0), f2bits(8.0), 1)
            push(f2bits(x + xoff), f2bits(100.5), (0, 1, 0), f2bits(8.0), 1)
    # (c) all y breakpoints (+/-0.1) at two x points.
    for y in Y_BP:
        for yoff in (0.0, 0.1, -0.1):
            push(f2bits(4500.0), f2bits(y + yoff), (0, 0, 1), f2bits(8.0), 1)
            push(f2bits(-250.0), f2bits(y + yoff), (0, 0, 0), f2bits(8.0), 1)
    # (d) raw special bit patterns on x and y (NaN, +/-inf, denormals, max,
    #     -0.0, sign flips).
    for sel in ((1, 0, 0), (0, 0, 0)):
        for sp in SPECIALS:
            push(sp, f2bits(50.0), sel, f2bits(8.0), 1)
            push(f2bits(4500.0), sp, sel, f2bits(8.0), 1)
            push(sp, sp, sel, f2bits(8.0), 1)
    # (e) distinguishable stale table pre-states: pin every rolling cell.
    ramp = tuple((0x11111111 * i) & 0xFFFFFFFF for i in range(14))
    for t in ((0,) * 14, (0xFFFFFFFF,) * 14, ramp):
        push(f2bits(4500.0), f2bits(50.0), (1, 0, 0), f2bits(8.0), 1, t)
        push(f2bits(4500.0), f2bits(50.0), (0, 0, 0), f2bits(8.0), 0, t)
    # (f) cmode=0 dead path: d = dp*0.25 - 2 clamped >= 0, then
    #     idx = min(trunc(d + 0.5), 12): dp around the d==0 and idx==12 cuts.
    for dp in (0.0, -100.0, -1.0, 7.999, 8.0, 8.001, 9.99, 10.0, 10.001,
               40.0, 44.0, 53.99, 54.0, 54.001, 57.999, 58.0, 58.001, 60.0,
               100.0, 1e5, 1e30):
        for sel in ((1, 0, 0), (0, 0, 0)):
            push(f2bits(4500.0), f2bits(50.0), sel, f2bits(dp), 0)
    return v


def gen_random(rng, k):
    """k random pre-states.  x/y are drawn from in-range values plus raw float
    bits (so NaN/inf paths appear too); the selector bytes are biased to the
    legal 0/1 values; cmode is 0 a quarter of the time (dead path) with a
    finite dp."""
    v = []
    for _ in range(k):
        if rng.random() < 0.5:
            x = f2bits(rng.uniform(-1000.0, 10000.0))
        else:
            x = rng.getrandbits(32)
        if rng.random() < 0.5:
            y = f2bits(rng.uniform(-20.0, 120.0))
        else:
            y = rng.getrandbits(32)
        selc = rng.choice((0, 0, 1, rng.getrandbits(8)))
        seld = rng.choice((0, 0, 1, rng.getrandbits(8)))
        sele = rng.choice((0, 0, 1, rng.getrandbits(8)))
        cmode = rng.choice((1, 1, 1, 0))
        if cmode == 0:
            dp = f2bits(rng.uniform(-100.0, 300.0))
        else:
            dp = rng.choice((f2bits(8.0), f2bits(54.0), rng.getrandbits(32)))
        t = tuple(rng.getrandbits(32) for _ in range(14))
        v.append((x, y, selc, seld, sele, dp, cmode) + t)
    return v


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(SEED)
    check_cal(cpu)

    EDGE = gen_edges()
    vectors = EDGE + gen_random(rng, n)

    # (a) ROM behaviour via the emulator (RAM side-effects; the 0x20DC /
    #     0x2404 / 0x24D0 callees run as real ROM bytes).
    emu = [run_emu(cpu, v) for v in vectors]

    # (b) host-C on the same pre-states.  The oracle maps the ROM pages
    #     straight from the file — hand it the path as argv[1].
    lines = ['vis %08X %08X %02X %02X %02X %08X %02X %s'
             % (v[0], v[1], v[2], v[3], v[4], v[5], v[6],
                ' '.join('%08X' % t for t in v[7:])) for v in vectors]
    proc = subprocess.run([oracle, ROM_PATH],
                          input='\n'.join(lines) + '\n',
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError('host oracle failed:\n' + proc.stderr)
    host_lines = proc.stdout.splitlines()
    if len(host_lines) != len(vectors):
        raise RuntimeError('oracle produced %d outputs for %d vectors'
                           % (len(host_lines), len(vectors)))
    host = [tuple(int(x, 16) for x in out.split()) for out in host_lines]

    # (c) compare the 15 post-state cells byte-for-byte.
    mismatches = []
    for i, (v, e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d x=0x%08X y=0x%08X sel=(%02X,%02X,%02X) dp=0x%08X '
                'cmode=%02X t0=0x%08X ROM=(%s|%02X) C=(%s|%02X)'
                % (i, v[0], v[1], v[2], v[3], v[4], v[5], v[6], v[7],
                   ' '.join('%08X' % w for w in e[:14]), e[14],
                   ' '.join('%08X' % w for w in h[:14]), h[14]))
            if len(mismatches) >= 5:
                break

    report('vis_intake_control', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
