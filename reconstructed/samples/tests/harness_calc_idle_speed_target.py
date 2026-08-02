#!/usr/bin/env python3
"""
harness_calc_idle_speed_target.py — equivalence of
rx8_calc_idle_speed_target @0x12F5E.

Reconstructed source: samples/src/rx8_calc_idle_speed_target.c
Verified lift   : c/calc_idle_speed_target.c (same address; the ROM bytes are
                  executed for real here via tools/sh2emu.py, including the
                  jsr'd callees 0x3ED0C sensor_range_check and 0x23E4 fpu_max).

The function is a void periodic task with NO ABI return value: its whole effect
is on RAM (idle target f32 @0xFFFFA678, increment flag u8 @0xFFFFA68F,
adaptive accumulator f32 @0xFFFFA680, rotor state flags @0xFFFFA6A9/0xFFFFA6AA),
so the equivalence check compares RAM side-effects, not a return value:

  - emulator side: seed the thirteen input cells in the sparse ram overlay
    (rotor A @0xFFFFA444, rotor B @0xFFFFA445, rpm @0xFFFFA424, engine flag
    @0xFFFFC600, closed loop @0xFFFFAADA, coolant main @0xFFFFC12C, coolant
    alt @0xFFFFC128, inc flag @0xFFFFA68F, state flag A @0xFFFFA6A9, state
    flag B @0xFFFFA6AA, adaptive @0xFFFFA680, adapt refs @0xFFFFA670/74),
    call the ROM entry @0x12F5E, read the five side-effected cells back;
  - host side: the dedicated oracle mmap()s the pages backing the same cells
    AND the ROM calibration pages (0x72BBB inc value, 0x72BC0 idle RPM
    threshold, 0x3EF78/0x3EF7C sensor_range_check range constants), seeds the
    same bytes, runs the reconstructed C and prints the same five cells.

EDGE vectors cover the three enable gates (engine/rpm/closed-loop, at every
branch boundary incl. 0x8000/0xFFFF rpm and non-bool mode bytes), every
sensor_range_check path (b == 0 with a == 0/+/- , normal division, sign
flips), the full FP edge suite for every float input (NaN, +/-inf, denormals,
+/-0, near-max), the rotor-gate logic (both flags/rotors, all combinations of
1 vs nonzero), the inc-flag decrement (0/1/0xFF pre-states) and the adaptive
max/zero paths (refs around 0, NaN refs); N random vectors follow (fixed seed
0x60E1D400).  The stock ROM constants are asserted before the run.

NOTE on FP overflow: tools/sh2emu.ts() packs through struct, which raises
OverflowError for doubles beyond the f32 range, so a coolant fsub/fdiv whose
quotient would saturate to +/-inf on the real SH-2E cannot be emulated.  The
generators keep such vectors out (fdiv_safe) while still placing NaN/Inf/
denormal/zero edge bits in every float slot.

Usage:  python3 harness_calc_idle_speed_target.py [N]  (default N = 20000)
"""
import math
import os
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402
from sh2emu import f2bits, bits2f, ts  # noqa: E402

ADDR = 0x12F5E
N_DEFAULT = 20000
SEED = 0x60E1D400
BUILD_DIR = '/tmp/rx8-recon-calc_idle_speed_target'

# RAM input/output cells.
RA_ADDR = 0xFFFFA444
RB_ADDR = 0xFFFFA445
RPM_ADDR = 0xFFFFA424
ENG_ADDR = 0xFFFFC600
CL_ADDR = 0xFFFFAADA
CM_ADDR = 0xFFFFC12C
CA_ADDR = 0xFFFFC128
TGT_ADDR = 0xFFFFA678
INC_ADDR = 0xFFFFA68F
FA_ADDR = 0xFFFFA6A9
FB_ADDR = 0xFFFFA6AA
AD_ADDR = 0xFFFFA680
V1_ADDR = 0xFFFFA670
V2_ADDR = 0xFFFFA674

# ROM calibration addresses.
ROM_THR_ADDR = 0x00072BC0    # u16 idle RPM threshold (2500)
ROM_INC_ADDR = 0x00072BBB    # u8  inc-flag reload value (0xFF)
ROM_POS_ADDR = 0x0003EF78    # f32 +3.402823e38 (0x7F7FFFFC)
ROM_NEG_ADDR = 0x0003EF7C    # f32 -3.402823e38 (0xFF7FFFFC)

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def build_oracle(cc='cc'):
    """Compile the reconstructed source + its dedicated oracle into a binary."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests',
                        'oracle_calc_idle_speed_target.c'),
           os.path.join(SAMPLES, 'src', 'rx8_calc_idle_speed_target.c'),
           '-lm',
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def load_cal(cpu):
    """The calibration constants straight from the stock ROM bytes."""
    thr = struct.unpack_from('>H', cpu.rom, ROM_THR_ADDR)[0]
    inc = cpu.rom[ROM_INC_ADDR]
    pos = struct.unpack_from('>I', cpu.rom, ROM_POS_ADDR)[0]
    neg = struct.unpack_from('>I', cpu.rom, ROM_NEG_ADDR)[0]
    if (thr, inc, pos, neg) != (2500, 0xFF, 0x7F7FFFFC, 0xFF7FFFFC):
        raise RuntimeError(
            'unexpected ROM calibration @0x%X/0x%X/0x%X/0x%X: '
            '%04X %02X %08X %08X' % (ROM_THR_ADDR, ROM_INC_ADDR,
                                     ROM_POS_ADDR, ROM_NEG_ADDR,
                                     thr, inc, pos, neg))
    return thr, inc


def seed_ram(init, addr, n, val):
    """Byte-exact big-endian store of a width-`n` value in the ram overlay."""
    for i in range(n):
        init[addr + i] = (val >> (8 * (n - 1 - i))) & 0xFF


def run_emu(cpu, vec):
    """Seed the 13 input cells, run the ROM bytes @0x12F5E and return the five
    side-effected cells: (tgt_bits, inc, ad_bits, fa, fb)."""
    rpm, ra, rb, eng, cl, cm, ca, inc0, fa0, fb0, ad, v1, v2 = vec
    init = {}
    seed_ram(init, RPM_ADDR, 2, rpm)
    init[RA_ADDR] = ra
    init[RB_ADDR] = rb
    init[ENG_ADDR] = eng
    init[CL_ADDR] = cl
    seed_ram(init, CM_ADDR, 4, cm)
    seed_ram(init, CA_ADDR, 4, ca)
    init[INC_ADDR] = inc0
    init[FA_ADDR] = fa0
    init[FB_ADDR] = fb0
    seed_ram(init, AD_ADDR, 4, ad)
    seed_ram(init, V1_ADDR, 4, v1)
    seed_ram(init, V2_ADDR, 4, v2)
    cpu.call(ADDR, ram=init)
    return (f2bits(cpu.rdf(TGT_ADDR)),
            cpu.rd(INC_ADDR, 1),
            f2bits(cpu.rdf(AD_ADDR)),
            cpu.rd(FA_ADDR, 1),
            cpu.rd(FB_ADDR, 1))


F32_MAX = 3.4028234663852886e38   # largest finite IEEE-754 single


def fdiv_safe(ca_bits, cm_bits):
    """True when the ROM's fsub (ca-cm) and fdiv ((ca-cm)/cm) stay inside the
    f32 pack range, i.e. tools/sh2emu.ts() cannot raise OverflowError on them
    (the emulator packs through struct, which rejects doubles > f32 max; the
    real SH-2E FPU would saturate to +/-inf instead).  NaN/Inf inputs are
    always safe (they propagate, they never overflow)."""
    cmf = bits2f(cm_bits)
    caf = bits2f(ca_bits)
    if math.isnan(cmf) or math.isinf(cmf) or math.isnan(caf) or math.isinf(caf):
        return True
    diff = caf - cmf                       # exact in double
    if abs(diff) > F32_MAX:
        return False                       # the fsub itself would overflow
    if cmf == 0.0:
        return True                        # no division (range-constant path)
    return abs(diff / cmf) <= F32_MAX


def gen_edges():
    """EDGE vectors.  Vector tuple: (rpm, ra, rb, eng, cl, cm_bits, ca_bits,
    inc0, fa0, fb0, ad_bits, v1_bits, v2_bits).  Every raw-bit FP edge is
    placed in each float slot; where the edge lands in the divisor slot (cm)
    the numerator (ca) is paired to it so the fsub/fdiv stay in f32 range."""
    v = []
    # (a) enable gates: engine flag / rpm / closed-loop at every boundary.
    for eng in (0, 1, 2, 0xFF):
        for rpm in (0, 1, 2499, 2500, 2501, 0x7FFF, 0x8000, 0xFFFF):
            for cl in (0, 1, 2, 0xFF):
                v.append((rpm, 0, 0, eng, cl, f2bits(80.0), f2bits(90.0),
                          0, 0, 0, f2bits(5.0), f2bits(-1.0), f2bits(-1.0)))
    # (b) sensor_range_check paths (b==0 with a==0/+/-; normal div; signs).
    for cm, ca in ((0.0, 0.0), (0.0, 5.0), (0.0, -5.0), (0.0, 1e-30),
                   (0.0, -1e-30), (-0.0, 1.0), (-0.0, -1.0), (80.0, 90.0),
                   (80.0, 70.0), (1.0, 0.0), (-1.0, 2.0), (2.0, -1.0),
                   (1e-30, 80.0), (-1e-30, 2.0)):
        for eng, cl in ((0, 0), (1, 0), (0, 1)):
            v.append((2500, 0, 0, eng, cl, f2bits(cm), f2bits(ca),
                      0, 0, 0, f2bits(5.0), f2bits(-1.0), f2bits(-1.0)))
    # (c) raw FP edge bits applied to every float slot (cm, ca, ad, v1; v2=+1).
    for bits in (0x7FC00000, 0x7F800001, 0x7F800000, 0xFF800000,
                 0x7F7FFFFF, 0xFF7FFFFF, 0x7F7FFFFC, 0xFF7FFFFC,
                 0x00000001, 0x80000001, 0x00000000, 0x80000000,
                 0x3F800000, 0xBF800000, 0x40000000):
        for slot in range(4):
            cm = bits if slot == 0 else f2bits(80.0)
            if slot == 0:
                # divisor gets the raw bits: pair ca so fsub/fdiv stay in range.
                ca = bits if not fdiv_safe(f2bits(90.0), bits) else f2bits(90.0)
            elif slot == 1:
                ca = bits
            else:
                ca = f2bits(90.0)
            ad = bits if slot == 2 else f2bits(5.0)
            v1 = bits if slot == 3 else f2bits(-1.0)
            v.append((2500, 0, 0, 0, 0, cm, ca, 1, 0, 0, ad, v1,
                      f2bits(1.0)))
    # (d) rotor-gate + inc-flag logic.
    for fa, fb in ((0, 0), (1, 0), (0, 1), (1, 1), (2, 0), (0, 2),
                   (0xFF, 1), (1, 0xFF), (0xFF, 0xFF)):
        for ra, rb in ((0, 0), (0, 1), (1, 0), (1, 1), (0x80, 0), (0, 0x80),
                       (0xFF, 0xFF)):
            for inc0 in (0, 1, 2, 0x7F, 0x80, 0xFF):
                v.append((2500, ra, rb, 0, 0, f2bits(80.0), f2bits(90.0),
                          inc0, fa, fb, f2bits(5.0),
                          f2bits(-1.0), f2bits(-1.0)))
    # (e) adaptive max path (inc != 0) and zero-check path (refs around 0).
    for ad, v1, v2 in ((5.0, -1.0, -1.0), (0.0, -1.0, -1.0),
                       (-5.0, -1.0, -1.0), (0.5, 0.0, 0.0),
                       (-0.5, 0.0, 0.0), (3.0, 1e30, -1e30),
                       (float('nan'), 0.0, 0.0), (5.0, float('nan'), 1.0),
                       (5.0, 1.0, float('nan')), (5.0, 1e30, 1e30),
                       (-3.0, -0.0, -0.0), (2.0, 0.0, 1.0),
                       (2.0, 1.0, 0.0), (1.0, 1.0, 1.0)):
        v.append((2500, 0, 0, 0, 0, f2bits(80.0), f2bits(90.0),
                  1, 0, 0, f2bits(ad), f2bits(v1), f2bits(v2)))
    return v


def gen_random(rng, n):
    """n random pre-states.  Floats: 15% raw bits (NaN/inf/denormals), rest
    uniform in-range; mode bytes uniform over the full byte range.  When a
    random draw would push the coolant fsub/fdiv out of f32 range (which the
    emulator's single-precision pack cannot represent), the two temperatures
    are collapsed to the same value so the vector stays emulator-runnable."""

    def pick(lo, hi):
        if rng.random() < 0.15:
            return rng.getrandbits(32)
        return f2bits(rng.uniform(lo, hi))

    v = []
    for _ in range(n):
        cm = pick(-40.0, 130.0)
        ca = pick(-40.0, 130.0)
        if not fdiv_safe(ca, cm):
            ca = cm                       # keep the emulator inside f32 range
        v.append((rng.getrandbits(16),    # rpm
                  rng.getrandbits(8),     # ra
                  rng.getrandbits(8),     # rb
                  rng.getrandbits(8),     # eng
                  rng.getrandbits(8),     # cl
                  cm,
                  ca,
                  rng.getrandbits(8),     # inc0
                  rng.getrandbits(8),     # fa
                  rng.getrandbits(8),     # fb
                  pick(-500.0, 5000.0),   # ad
                  pick(-1e3, 1e3),        # v1
                  pick(-1e3, 1e3)))       # v2
    return v


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(SEED)
    thr, inc_cal = load_cal(cpu)

    EDGE = gen_edges()
    vectors = EDGE + gen_random(rng, n)

    # (a) ROM behaviour via the emulator (RAM side-effects).
    emu = [run_emu(cpu, v) for v in vectors]

    # (b) host-C on the same pre-states (floats as raw bits; the oracle maps
    # the ROM cal pages straight from the stock bin, so no cal tokens needed).
    lines = ['ids %04X %02X %02X %02X %02X %08X %08X %02X %02X %02X %08X %08X %08X'
             % (v[0], v[1], v[2], v[3], v[4], v[5], v[6], v[7], v[8], v[9],
                v[10], v[11], v[12]) for v in vectors]
    host = [tuple(int(x, 16) for x in out.split())
            for out in run_oracle(oracle, lines)]

    # (c) compare the post-state tuples byte-for-byte.
    mismatches = []
    for i, (vec, e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            rpm, ra, rb, eng, cl, cm, ca, inc0, fa0, fb0, ad, v1, v2 = vec
            mismatches.append(
                'vec#%d rpm=%04X ra=%02X rb=%02X eng=%02X cl=%02X '
                'cm=%08X ca=%08X inc0=%02X fa0=%02X fb0=%02X ad=%08X '
                'v1=%08X v2=%08X ROM=(%08X,%02X,%08X,%02X,%02X) '
                'C=(%08X,%02X,%08X,%02X,%02X)'
                % (i, rpm, ra, rb, eng, cl, cm, ca, inc0, fa0, fb0, ad,
                   v1, v2, e[0], e[1], e[2], e[3], e[4],
                   h[0], h[1], h[2], h[3], h[4]))
            if len(mismatches) >= 5:
                break

    report('calc_idle_speed_target', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
