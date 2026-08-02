#!/usr/bin/env python3
"""
harness_calc_ignition_all_rotors_13c2c.py — equivalence of
rx8_calc_ignition_all_rotors_13c2c @0x13C2C.

Reconstructed source: samples/src/rx8_calc_ignition_all_rotors_13c2c.c
Verified lift   : c/calc_ignition_all_rotors_13C2C.c (same address; the ROM
                  bytes are executed for real here via tools/sh2emu.py,
                  including the three bsr'd helpers 0x13ED2/0x13E6C/0x13EE6,
                  the generic 1-D lookup 0x2068 and the saturate leaf 0x2404).

The function is a void periodic task with NO ABI return value: its whole
effect is on RAM, so the equivalence check compares the byte-exact RAM side
effects (all cells listed in the .c header), not a return value:

  - emulator side: seed the sixteen input cells in the sparse ram overlay
    (u8 A740/A748/A749/A75C/B5A4/BB55/BCA9/C0C4/C0C5/C0C7, f32 A73C/A744/
    B5B8/A74C/A750/A754 — the last three with distinguishable stale pre-states
    so an absent write is visible), call the ROM entry @0x13C2C (the helpers
    and the table lookup run as their REAL ROM bytes), read the eight
    post-state cells back (A73C/A744/A734/A738/A750/A754/A74C as f32 bits,
    A75C as a byte);
  - host side: the dedicated oracle mmap()s the pages backing the RAM cells
    AND the two ROM pages the function dereferences (1-D descriptors @0x6B664
    ..0x6B6B4 and the calibration/table-data page @0x79838..0x7995C, seeded
    straight from the stock 60E1D400.bin), seeds the same bytes, runs the
    reconstructed C (whose only extern — rx8_table1d_lookup, the type-4 u8
    model of 0x2068 — the oracle supplies) and prints the same eight cells.

The stock ROM calibration constants are asserted before the run (the f32
@0x79878/0x7987C/0x79880/0x79888/0x79890/0x7989C/0x798A0 and the u8
@0x79838/0x7983B, plus the type==4/u8 nature of all five descriptors), so
both sides always read byte-identical constants.

EDGE vectors cover every branch: the knock-sensor-fault / knock-detected /
knock-active / ignition-enable / knock-counter (byte vs byte >= 1) / ECT-status
/ ECT-corr-enable gates across all paths (including non-bool bytes, which any
nonzero tests as true via tst), the 0x13E6C table-select matrix (B5A4/BCA9/
BB55 around the ==1 and >=5 thresholds), the light-retard detected==0 lookup
path, and the full FP edge suite (NaN, +/-inf, denormals, +/-0, 1 ulp around
every clamp boundary -10.0/0.0/2.5/12.5 and around every axis breakpoint of
the five real tables) plus distinguishable scratch pre-states; N random
vectors follow (fixed seed 0x60E1D400, bytes uniform over 0..255, floats 85%
in-range / 15% raw f32 bits).  All floats are compared bit-for-bit (raw
single-precision bits), all bytes byte-for-byte.

Usage:  python3 harness_calc_ignition_all_rotors_13c2c.py [N]  (default N = 20000)
"""
import math
import os
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROM_PATH, load_cpu, make_rng, report, run_oracle  # noqa: E402
from sh2emu import f2bits, ts  # noqa: E402

ADDR = 0x13C2C
N_DEFAULT = 20000
SEED = 0x60E1D400
BUILD_DIR = '/tmp/rx8-recon-calc_ignition_all_rotors_13c2c'

# ---- RAM cells (see rx8_calc_ignition_all_rotors_13c2c.c header) ----
A734 = 0xFFFFA734   # f32 rotor lead  (out)
A738 = 0xFFFFA738   # f32 rotor trail (out)
A73C = 0xFFFFA73C   # f32 clamp input (fr6 in) / clamp result (out)
A740 = 0xFFFFA740   # u8  ignition enable (r14; copied to A75C)
A744 = 0xFFFFA744   # f32 previous timing (fr5 in) / final timing (out)
A748 = 0xFFFFA748   # u8  knock sensor fault
A749 = 0xFFFFA749   # u8  knock detected
A74C = 0xFFFFA74C   # f32 light-retard scratch (written on detected==0 path)
A750 = 0xFFFFA750   # f32 0x13EE6 lookup1 scratch (out)
A754 = 0xFFFFA754   # f32 0x13EE6 lookup2 scratch (out)
A75C = 0xFFFFA75C   # u8  knock active (in) / r14 copy (out)
B5B8 = 0xFFFFB5B8   # f32 RPM
B5A4 = 0xFFFFB5A4   # u8  0x13E6C table-select status
BB55 = 0xFFFFBB55   # u8  0x13E6C table-select status
BCA9 = 0xFFFFBCA9   # u8  0x13E6C table-select status
C0C4 = 0xFFFFC0C4   # u8  ECT status
C0C5 = 0xFFFFC0C5   # u8  ECT corr-enable (value never changes the result)
C0C7 = 0xFFFFC0C7   # u8  knock counter (byte-vs-byte >= threshold check)

# ---- ROM calibration addresses (fixed stock values; asserted before run) ----
CAL_13E6C_UPPER = 0x00079878   # f32 0.0    (0x13E6C saturate upper)
CAL_ZERO        = 0x0007987C   # f32 0.0    (zero correction constant)
CAL_CORR_DEF1   = 0x00079880   # f32 1.0    (ECT corr-enable==0 default)
CAL_CORR_DEF2   = 0x00079888   # f32 1.0    (ECT corr-enable!=0 default)
CAL_RETARD_MAX  = 0x00079890   # f32 2.5    (max knock retard)
CAL_13ED2_LO    = 0x0007989C   # f32 -10.0  (0x13ED2 saturate lower)
CAL_13ED2_HI    = 0x000798A0   # f32 0.0    (0x13ED2 saturate upper)
CAL_13E6C_THR   = 0x00079838   # u8  5      (0x13E6C table-select threshold)
CAL_KNOCK_THR   = 0x0007983B   # u8  1      (knock-counter threshold)
DESCS = (0x6B664, 0x6B678, 0x6B68C, 0x6B6A0, 0x6B6B4)   # 1-D u8 descriptors

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def build_oracle(cc='cc'):
    """Compile the reconstructed source + its dedicated oracle into a binary."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests',
                        'oracle_calc_ignition_all_rotors_13c2c.c'),
           os.path.join(SAMPLES, 'src',
                        'rx8_calc_ignition_all_rotors_13c2c.c'),
           '-lm',
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def check_cal(cpu):
    """The stock-Rom calibration constants are fixed; refuse to run if they
    ever change so the ROM-page mapping stays meaningful."""
    rom = cpu.rom
    vals = tuple(struct.unpack_from('>f', rom, a)[0]
                 for a in (CAL_13E6C_UPPER, CAL_ZERO, CAL_CORR_DEF1,
                           CAL_CORR_DEF2, CAL_RETARD_MAX, CAL_13ED2_LO,
                           CAL_13ED2_HI))
    if vals != (0.0, 0.0, 1.0, 1.0, 2.5, -10.0, 0.0):
        raise RuntimeError('unexpected ignition calibration floats: %r' % (vals,))
    if rom[CAL_13E6C_THR] != 5 or rom[CAL_KNOCK_THR] != 1:
        raise RuntimeError('unexpected ignition calibration bytes @0x%X/0x%X'
                           % (CAL_13E6C_THR, CAL_KNOCK_THR))
    for d in DESCS:
        cnt = struct.unpack_from('>H', rom, d)[0]
        if cnt < 2 or cnt > 64 or rom[d + 2] != 4:
            raise RuntimeError('unexpected 1-D descriptor @0x%X' % d)


def seed(init, addr, n, val):
    """Byte-exact big-endian store of a width-`n` value in the ram overlay."""
    for i in range(n):
        init[addr + i] = (val >> (8 * (n - 1 - i))) & 0xFF


def run_emu(cpu, vec):
    """Seed every input cell, run the ROM bytes @0x13C2C (helpers included)
    and return the 8-tuple of post-state cells (7 f32 bit-words + A75C byte)."""
    a740, a748, a749, a75c, b5a4, bb55, bca9, c0c4, c0c5, c0c7, \
        a73c, a744, b5b8, a74c, a750, a754 = vec
    init = {}
    for a, v in ((A740, a740), (A748, a748), (A749, a749), (A75C, a75c),
                 (B5A4, b5a4), (BB55, bb55), (BCA9, bca9),
                 (C0C4, c0c4), (C0C5, c0c5), (C0C7, c0c7)):
        init[a] = v & 0xFF
    for a, v in ((A73C, a73c), (A744, a744), (B5B8, b5b8),
                 (A74C, a74c), (A750, a750), (A754, a754)):
        seed(init, a, 4, v & 0xFFFFFFFF)
    cpu.call(ADDR, ram=init)
    return (f2bits(cpu.rdf(A73C)), f2bits(cpu.rdf(A744)),
            f2bits(cpu.rdf(A734)), f2bits(cpu.rdf(A738)),
            f2bits(cpu.rdf(A750)), f2bits(cpu.rdf(A754)),
            f2bits(cpu.rdf(A74C)), cpu.rd(A75C, 1))


def gen_edges():
    """Edge vectors (16-tuple: 10 input bytes + 6 float bit-words).  Every
    tuple ends with the three scratch pre-states so an absent write is
    visible: A74C is only written on the detected==0 path, A750/A754 always."""
    v = []
    stale = (0xDECADE00, 0x12345678, 0x0BADF00D)
    a73c = f2bits(10.0)
    a744 = f2bits(-5.0)
    rpm = f2bits(3000.0)

    # (a) full flow cross-product: (fault, detected, active, ign, c0c7,
    #     c0c4, c0c5) over every branch boundary with a fixed float state
    #     (table-select bytes fixed at 0 -> table B via bb55==0).
    for fault in (0, 1, 0xFF):
        for detected in (0, 1, 0xFF):
            for active in (0, 1, 0xFF):
                for ign in (0, 1, 0xFF):
                    for c0c7 in (0, 1, 2, 0xFF):
                        for c0c4 in (0, 1, 0xFF):
                            for c0c5 in (0, 1, 0xFF):
                                v.append((fault, detected, active, ign,
                                          0, 0, 0, c0c4, c0c5, c0c7,
                                          a73c, a744, rpm) + stale)

    # (b) 0x13E6C table-select matrix on the knock-active path (fault=1,
    #     detected=1, active=1, ign=1, c0c7=1, ect off) around the ==1 /
    #     >=5 thresholds of the B5A4/BCA9/BB55 bytes.
    for b5a4 in (0, 1, 2, 0xFF):
        for bca9 in (0, 4, 5, 6, 0xFF):
            for bb55 in (0, 1, 5, 6, 0xFF):
                v.append((1, 1, 1, 1, b5a4, bb55, bca9, 0, 0, 1,
                          a73c, a744, rpm) + stale)

    # (c) FP edges on the knock-active main path: every float input slot over
    #     the special-value suite, and RPM over every axis breakpoint of the
    #     five real tables (+/- 1 ulp around 2000/7500, out of range, NaN).
    fp_special = [0.0, -0.0, 1.0, -1.0, 2.5, -2.5, 10.0, -10.0, 40.0, -40.0,
                  1e-30, -1e-30, 123.0, -99.0,
                  float('inf'), float('-inf'), float('nan')]
    rpm_edges = [1500.0, 2000.0, 2000.5, 2499.0, 2500.0, 2750.0, 3000.0,
                 3499.0, 3500.0, 4000.0, 4499.0, 4500.0, 4999.0, 5000.0,
                 6000.0, 7499.0, 7500.0, 8000.0, 0.0,
                 math.nextafter(2000.0, -math.inf),
                 math.nextafter(2000.0, math.inf),
                 math.nextafter(7500.0, -math.inf),
                 math.nextafter(7500.0, math.inf),
                 float('-inf'), float('inf'), float('nan')]
    base = (1, 1, 1, 1, 0, 0, 0, 0, 0, 1)     # fault..ign, b5a4,bb55,bca9,
                                              # c0c4,c0c5,c0c7
    for x in fp_special:
        v.append(base + (f2bits(ts(x)), a744, rpm) + stale)   # engine speed
        v.append(base + (a73c, f2bits(ts(x)), rpm) + stale)   # prev timing
        v.append(base + (a73c, a744, f2bits(ts(x))) + stale)  # RPM
        v.append(base + (a73c, a744, rpm)
                 + (f2bits(ts(x)), f2bits(ts(x)), f2bits(ts(x))))  # scratch
    for x in rpm_edges:
        v.append(base + (a73c, a744, f2bits(ts(x))) + stale)

    # (d) clamp-boundary suite on the knock-active path (2.5 is subtracted
    #     from the clamp input when C0C7 >= 1) and the ECT overwrite path
    #     (correction := prev - 1.0), +/- 1 ulp around every boundary.
    eng_edges = [math.nextafter(-10.0, -math.inf), -10.0,
                 math.nextafter(-10.0, math.inf),
                 math.nextafter(0.0, -math.inf), -0.0, 0.0,
                 math.nextafter(2.5, -math.inf), 2.5,
                 math.nextafter(2.5, math.inf),
                 math.nextafter(12.5, -math.inf), 12.5,
                 math.nextafter(12.5, math.inf)]
    prev_edges = [math.nextafter(0.0, -math.inf), -0.0, 0.0,
                  math.nextafter(1.0, -math.inf), 1.0,
                  math.nextafter(1.0, math.inf),
                  -10.0, 10.0, 20.0, -20.0]
    for x in eng_edges:
        v.append((1, 1, 1, 1, 0, 0, 0, 0, 0, 1, f2bits(ts(x)), a744, rpm)
                 + stale)
        v.append((1, 1, 1, 1, 0, 0, 0, 0, 0, 1, f2bits(ts(x)),
                  f2bits(-20.0), rpm) + stale)
    for x in prev_edges:
        v.append((1, 1, 1, 1, 0, 0, 0, 1, 0, 1, a73c, f2bits(ts(x)), rpm)
                 + stale)                                  # ECT on
        v.append((1, 1, 1, 1, 0, 0, 0, 1, 0, 1, a73c, f2bits(ts(x)),
                  f2bits(6000.0)) + stale)                 # ECT on, high RPM
    for c0c5 in (0, 1, 0xFF):                              # both arms load 1.0
        v.append((1, 1, 1, 1, 0, 0, 0, 1, c0c5, 1, a73c, f2bits(7.5), rpm)
                 + stale)
    return v


def gen_random(rng, n):
    """n random vectors: floats uniform in-range (15% raw f32 bits to hit
    NaN/Inf/denormals), all ten bytes uniform over the full byte range."""

    def pick(lo, hi):
        if rng.random() < 0.15:
            return rng.getrandbits(32)
        return f2bits(rng.uniform(lo, hi))

    return [(rng.randrange(256), rng.randrange(256), rng.randrange(256),
             rng.randrange(256), rng.randrange(256), rng.randrange(256),
             rng.randrange(256), rng.randrange(256), rng.randrange(256),
             rng.randrange(256),
             pick(-40.0, 40.0), pick(-40.0, 40.0), pick(500.0, 9000.0),
             pick(-50.0, 50.0), pick(-50.0, 50.0), pick(-50.0, 50.0))
            for _ in range(n)]


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(SEED)
    check_cal(cpu)
    # The oracle maps the ROM pages straight from the file — point it there.
    os.environ['RX8_ROM_PATH'] = ROM_PATH

    EDGE = gen_edges()
    vectors = EDGE + gen_random(rng, n)

    # (a) ROM behaviour via the emulator (the 0x13ED2/0x13E6C/0x13EE6/0x2068/
    #     0x2404 callees run as real ROM bytes; RAM side-effects compared).
    emu = [run_emu(cpu, v) for v in vectors]

    # (b) host-C on the same pre-states (cal/table bytes from the mapped ROM).
    lines = ['ign %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X '
             '%08X %08X %08X %08X %08X %08X' % v for v in vectors]
    host = [tuple(int(tok, 16) for tok in out.split())
            for out in run_oracle(oracle, lines)]

    # (c) compare the post-state cells bit-for-bit / byte-for-byte.
    mismatches = []
    for i, (vec, e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d ign=%02X fault=%02X det=%02X act=%02X '
                'b5a4=%02X bb55=%02X bca9=%02X c0c4=%02X c0c5=%02X c0c7=%02X '
                'a73c=%08X a744=%08X rpm=%08X a74c0=%08X a7500=%08X a7540=%08X '
                'ROM=(%08X %08X %08X %08X %08X %08X %08X %02X) '
                'C=(%08X %08X %08X %08X %08X %08X %08X %02X)'
                % (i, vec[0], vec[1], vec[2], vec[3], vec[4], vec[5], vec[6],
                   vec[7], vec[8], vec[9], vec[10], vec[11], vec[12],
                   vec[13], vec[14], vec[15],
                   e[0], e[1], e[2], e[3], e[4], e[5], e[6], e[7],
                   h[0], h[1], h[2], h[3], h[4], h[5], h[6], h[7]))
            if len(mismatches) >= 5:
                break

    report('calc_ignition_all_rotors_13c2c', ADDR, n, mismatches,
           edges=len(EDGE))


if __name__ == '__main__':
    main()
