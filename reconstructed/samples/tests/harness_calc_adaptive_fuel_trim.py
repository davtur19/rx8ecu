#!/usr/bin/env python3
"""
harness_calc_adaptive_fuel_trim.py — equivalence of
rx8_calc_adaptive_fuel_trim @0x1379C.

Reconstructed source: samples/src/rx8_calc_adaptive_fuel_trim.c
Verified lift   : c/calc_adaptive_fuel_trim.c (same address; the ROM bytes are
                  executed for real here via tools/sh2emu.py, including the
                  jsr'd callees 0x2068 table1D_lookup, 0x2624 axis search,
                  0x26B0 u8 interpolate and 0x2404 clamp).

The function is a void periodic task with NO ABI return value: its whole effect
is on RAM (error f32 @0xFFFFA728, trim f32 @0xFFFFA720, status u8 @0xFFFFA730,
final f32 @0xFFFFA718), so the equivalence check compares RAM side-effects, not
a return value:

  - emulator side: seed the ten input cells in the sparse ram overlay (rpm
    @0xFFFFB5B8, coolant @0xFFFFC12C, lambda @0xFFFFB5C4, enable @0xFFFFB5A4,
    table select A @0xFFFFB5AC, table select B @0xFFFFB5AA, closed loop
    @0xFFFFAADA, coolant status @0xFFFFC084, rpm raw @0xFFFFA424, status
    pre-state @0xFFFFA730), call the ROM entry @0x1379C, read the four
    side-effected cells back;
  - host side: the dedicated oracle mmap()s the pages backing the same RAM
    cells AND the ROM calibration pages (descriptors @0x6A868/0x6A87C, constants
    @0x72C5C..0x72C74, axes @0x72C88/0x72CB8, cells @0x72CAC/0x72CDC,
    hysteresis @0x138B8) straight from the stock bin ($RX8_ROM_PATH), runs the
    reconstructed C and prints the same four cells.

EDGE vectors cover the two table-select gates (enable/select/flag at every
branch boundary incl. non-bool bytes), the closed-loop gate, the rpm threshold
around 1500.0 (1 ulp both sides, NaN, +/-inf), the coolant-status threshold
around 0.009765625 (1 ulp both sides, NaN), the rpm_raw gate around 375
(374/375/376/0/65535), the coolant hysteresis boundaries (0.6 and the f32
sum 0.6 + -0.045, 1 ulp both sides, NaN, +/-inf) for every status pre-state,
the table-lookup interpolation at every axis breakpoint plus out-of-range
clamps and NaN/Inf error, and lambda == rpm (error == 0.0); N random vectors
follow (fixed seed 0x60E1D400).

NOTE on FP overflow: tools/sh2emu.ts() packs through struct, which raises
OverflowError for doubles beyond the f32 range, so the error fsub
(rpm - lambda) whose difference would saturate to +/-inf on the real SH-2E
cannot be emulated.  The generators keep such vectors out (sub_safe) while
still placing NaN/Inf/denormal/zero edge bits in every float slot.

Usage:  python3 harness_calc_adaptive_fuel_trim.py [N]  (default N = 20000)
"""
import math
import os
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROM_PATH, load_cpu, make_rng, report, run_oracle  # noqa: E402
from sh2emu import f2bits, bits2f, ts  # noqa: E402

ADDR = 0x1379C
N_DEFAULT = 20000
SEED = 0x60E1D400

# RAM input/output cells.
RPM_ADDR = 0xFFFFB5B8
LAM_ADDR = 0xFFFFB5C4
COOL_ADDR = 0xFFFFC12C
COOLST_ADDR = 0xFFFFC084
EN_ADDR = 0xFFFFB5A4
SEL_ADDR = 0xFFFFB5AC
FLAG_ADDR = 0xFFFFB5AA
CL_ADDR = 0xFFFFAADA
RPMRAW_ADDR = 0xFFFFA424
STAT_ADDR = 0xFFFFA730
ERR_ADDR = 0xFFFFA728
TRIM_ADDR = 0xFFFFA720
LEAD_ADDR = 0xFFFFA718

# ROM calibration addresses.
ROM_THR_ADDR = 0x00072C60    # f32 1500.0 rpm threshold
ROM_CST_ADDR = 0x00072C64    # f32 0.009765625 coolant-status threshold
ROM_RRT_ADDR = 0x00072C5C    # u16 375 rpm_raw threshold
ROM_HI_ADDR = 0x00072C68     # f32 0.6 status ON threshold
ROM_HY_ADDR = 0x000138B8     # f32 -0.045 hysteresis
ROM_CLO_ADDR = 0x00072C6C    # f32 -2.8 clamp low
ROM_CHI_ADDR = 0x00072C70    # f32 0.7 clamp high

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = '/tmp/rx8-recon-calc_adaptive_fuel_trim'


def build_oracle(cc='cc'):
    """Compile the reconstructed source + its dedicated oracle into a binary."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_calc_adaptive_fuel_trim.c'),
           os.path.join(SAMPLES, 'src', 'rx8_calc_adaptive_fuel_trim.c'),
           '-lm',
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def load_cal(cpu):
    """The calibration constants straight from the stock ROM bytes (compared
    by their raw big-endian bit patterns; note the -0.045 hysteresis constant
    is stored one ulp from f32(-0.045), as 0xBD3851EB)."""
    rom = cpu.rom
    exp = ((ROM_THR_ADDR, 0x44BB8000), (ROM_CST_ADDR, 0x3C200000),
           (ROM_RRT_ADDR, 0x0177), (ROM_HI_ADDR, 0x3F19999A),
           (ROM_HY_ADDR, 0xBD3851EB), (ROM_CLO_ADDR, 0xC0333333),
           (ROM_CHI_ADDR, 0x3F333333))
    got = []
    for addr, want in exp:
        if addr == ROM_RRT_ADDR:
            val = struct.unpack_from('>H', rom, addr)[0]
        else:
            val = struct.unpack_from('>I', rom, addr)[0]
        got.append(val)
        if val != want:
            raise RuntimeError(
                'unexpected ROM calibration @0x%X: got %08X want %08X'
                % (addr, val, want))
    return got


def seed_ram(init, addr, n, val):
    """Byte-exact big-endian store of a width-`n` value in the ram overlay."""
    for i in range(n):
        init[addr + i] = (val >> (8 * (n - 1 - i))) & 0xFF


def run_emu(cpu, vec):
    """Seed the ten input cells, run the ROM bytes @0x1379C and return the four
    side-effected cells: (error_bits, trim_bits, status, final_bits)."""
    rpm, cool, lam, en, sel, flag, cl, coolst, rpmraw, prev = vec
    init = {}
    seed_ram(init, RPM_ADDR, 4, rpm)
    seed_ram(init, LAM_ADDR, 4, lam)
    seed_ram(init, COOL_ADDR, 4, cool)
    seed_ram(init, COOLST_ADDR, 4, coolst)
    init[EN_ADDR] = en
    init[SEL_ADDR] = sel
    init[FLAG_ADDR] = flag
    init[CL_ADDR] = cl
    seed_ram(init, RPMRAW_ADDR, 2, rpmraw)
    init[STAT_ADDR] = prev
    cpu.call(ADDR, ram=init)
    return (f2bits(cpu.rdf(ERR_ADDR)),
            f2bits(cpu.rdf(TRIM_ADDR)),
            cpu.rd(STAT_ADDR, 1),
            f2bits(cpu.rdf(LEAD_ADDR)))


F32_MAX = 3.4028234663852886e38   # largest finite IEEE-754 single


def sub_safe(a_bits, b_bits):
    """True when the ROM's error fsub (rpm - lambda) stays inside the f32 pack
    range, i.e. tools/sh2emu.ts() cannot raise OverflowError on it (the
    emulator packs through struct, which rejects doubles > f32 max; the real
    SH-2E FPU would saturate to +/-inf instead).  NaN/Inf inputs are always
    safe (they propagate, they never overflow)."""
    a = bits2f(a_bits)
    b = bits2f(b_bits)
    if math.isnan(a) or math.isnan(b) or math.isinf(a) or math.isinf(b):
        return True
    return abs(a - b) <= F32_MAX


def gen_edges():
    """EDGE vectors.  Vector tuple: (rpm_bits, cool_bits, lam_bits, en, sel,
    flag, cl, coolst_bits, rpmraw, prev)."""
    v = []
    hy_rom = bits2f(0xBD3851EB)          # ROM hysteresis constant (0x138B8)
    f555 = ts(ts(0.6) + hy_rom)
    hi = ts(0.6)
    c_lo = hi - 0.0  # f32 0.6
    # f32 neighbours of the hysteresis boundaries and the thresholds.
    def near(x, d):
        u = struct.unpack('>I', struct.pack('>f', x))[0] + d
        return struct.unpack('>f', struct.pack('>I', u))[0]
    c_hi = near(hi, 1)       # f32 just above 0.6
    c_lo = near(hi, -1)      # f32 just below 0.6
    f555_hi = near(f555, 1)
    f555_lo = near(f555, -1)
    g = ts(0.009765625)
    g_hi = near(g, 1)
    g_lo = near(g, -1)
    r1500 = ts(1500.0)
    r_hi = near(r1500, 1)
    r_lo = near(r1500, -1)

    cool_edges = [c_lo, c_hi, hi, f555, f555_hi, f555_lo,
                  ts(0.61), ts(-0.0), ts(100.0), float('nan'),
                  float('inf'), float('-inf')]
    coolst_edges = [g, g_hi, g_lo, ts(0.0), ts(100.0), float('nan')]
    rpm_edges = [r1500, r_hi, r_lo, ts(1499.0), ts(2000.0), ts(0.0),
                 ts(-0.0), float('nan'), float('inf'), float('-inf')]
    lam_edges = [ts(1.0), r1500, ts(0.0), float('nan'),
                 float('inf'), float('-inf')]

    # (a) table-select gates + closed loop at every branch boundary.
    for en in (0, 1, 2, 0xFF):
        for sel in (0, 1, 2, 0xFF):
            for flag in (0, 1, 2, 0xFF):
                for cl in (0, 1, 2, 0xFF):
                    v.append((f2bits(2000.0), f2bits(80.0), f2bits(1.0),
                              en, sel, flag, cl, f2bits(100.0), 500, 1))
    # (b) rpm / coolant-status / rpm_raw gates around every boundary.
    for cl in (0, 1, 255):
        for rpm in rpm_edges:
            v.append((f2bits(rpm), f2bits(80.0), f2bits(1.0),
                      0, 0, 0, cl, f2bits(0.0), 375, 1))
        for coolst in coolst_edges:
            for rpmraw in (0, 374, 375, 376, 65535):
                v.append((f2bits(1000.0), f2bits(80.0), f2bits(1.0),
                          0, 0, 0, cl, f2bits(coolst), rpmraw, 1))
    # (c) coolant hysteresis: every boundary, every pre-state.
    for cool in cool_edges:
        for prev in (0, 1, 2, 0xFF):
            v.append((f2bits(1000.0), f2bits(cool), f2bits(1.0),
                      0, 0, 0, 1, f2bits(100.0), 500, prev))
    # (d) table lookup: axis breakpoints, clamps, NaN/Inf error, error == 0.
    for err in (-100.0, -75.0, -50.0, -25.0, 0.0, 25.0, 50.0, 75.0, 100.0,
                100.00001, -100.00001, float('nan'), float('inf'),
                float('-inf')):
        for en, sel, flag in ((0, 0, 0), (1, 0, 1), (0, 255, 0)):
            v.append((f2bits(1500.0 + err), f2bits(80.0), f2bits(1500.0),
                      en, sel, flag, 1, f2bits(0.0), 375, 1))
    # (e) lambda == rpm -> error == 0.0; extreme finite values.
    v.append((f2bits(1234.0), f2bits(80.0), f2bits(1234.0),
              0, 0, 0, 1, f2bits(0.0), 375, 1))
    v.append((f2bits(-1e30), f2bits(80.0), f2bits(1e30),
              0, 0, 0, 1, f2bits(0.0), 375, 0))
    v.append((f2bits(1e30), f2bits(80.0), f2bits(-1e30),
              1, 1, 1, 1, f2bits(0.0), 0, 1))
    return v


def gen_random(rng, n):
    """n random vectors: floats uniform in-range (15% raw bits to hit NaN/Inf/
    denormals), mode bytes uniform over the full byte range.  When a random
    draw would push the error fsub (rpm - lambda) out of f32 range (which the
    emulator's single-precision pack cannot represent), lambda is redrawn so
    the vector stays emulator-runnable."""

    def pick(lo, hi):
        if rng.random() < 0.15:
            return rng.getrandbits(32)
        return f2bits(ts(rng.uniform(lo, hi)))

    v = []
    for _ in range(n):
        rpm = pick(0.0, 9000.0)
        lam = pick(-5.0, 5.0)
        if not sub_safe(rpm, lam):
            lam = f2bits(ts(1.0))
        v.append((rpm,
                  pick(-50.0, 150.0),        # coolant
                  lam,
                  rng.getrandbits(8),        # en
                  rng.getrandbits(8),        # sel
                  rng.getrandbits(8),        # flag
                  rng.getrandbits(8),        # cl
                  pick(-1.0, 100.0),         # coolant status
                  rng.getrandbits(16),       # rpm raw
                  rng.getrandbits(8)))       # status pre-state
    return v


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(SEED)
    load_cal(cpu)
    os.environ['RX8_ROM_PATH'] = ROM_PATH

    EDGE = gen_edges()
    vectors = EDGE + gen_random(rng, n)

    # (a) ROM behaviour via the emulator (RAM side-effects).
    emu = [run_emu(cpu, v) for v in vectors]

    # (b) host-C on the same pre-states (floats as raw bits; the oracle maps
    # the ROM cal pages straight from the stock bin, so no cal tokens needed).
    lines = ['atr %08X %08X %08X %02X %02X %02X %02X %08X %04X %02X'
             % (v[0], v[1], v[2], v[3], v[4], v[5], v[6], v[7], v[8], v[9])
             for v in vectors]
    host = [tuple(int(x, 16) for x in out.split())
            for out in run_oracle(oracle, lines)]

    # (c) compare the post-state tuples byte-for-byte.
    mismatches = []
    for i, (vec, e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            rpm, cool, lam, en, sel, flag, cl, coolst, rpmraw, prev = vec
            mismatches.append(
                'vec#%d rpm=%08X cool=%08X lam=%08X en=%02X sel=%02X '
                'flag=%02X cl=%02X coolst=%08X rpmraw=%04X prev=%02X '
                'ROM=(%08X,%08X,%02X,%08X) C=(%08X,%08X,%02X,%08X)'
                % (i, rpm, cool, lam, en, sel, flag, cl, coolst, rpmraw, prev,
                   e[0], e[1], e[2], e[3], h[0], h[1], h[2], h[3]))
            if len(mismatches) >= 5:
                break

    report('calc_adaptive_fuel_trim', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
