#!/usr/bin/env python3
"""
harness_limit_knock_retard_max.py — equivalence of
rx8_limit_knock_retard_max @0x13E6C.

Reconstructed source: samples/src/rx8_limit_knock_retard_max.c
Verified lift   : c/limitKnockRetardMax_ConditionalRPM.c (same symbol; the
                  lift documents the 60E0FC00 copy @0x13AE4 — in 60E1D400.bin
                  the body is at 0x13E6C, which is what is executed here for
                  real via tools/sh2emu.py, including the jsr'd callees
                  0x2068 table1D_lookup and 0x2404 clamp).

The function is a pure `float f(float)` — ABI argument in fr4, return in fr0 —
with four RAM input cells and NO RAM side effects, so the equivalence check
compares the returned fr0 bits:

  - emulator side: seed the four input cells in the sparse ram overlay (rpm
    f32 @0xFFFFB5B8, sensor u8 @0xFFFFB5A4, flag u8 @0xFFFFBB55, sec u8
    @0xFFFFBCA9), call the ROM entry @0x13E6C with fr4 = knock-retard arg,
    read fr0 back;
  - host side: the dedicated oracle mmap()s the pages backing the same RAM
    cells AND the ROM calibration pages (descriptors @0x6B664/0x6B678, u8
    threshold @0x79838, f32 clamp upper @0x79878, axes+cells @0x798A4/0x798B8/
    0x798C0/0x798D0) straight from the stock bin ($RX8_ROM_PATH), runs the
    reconstructed C with the same argument and prints the returned bits.

EDGE vectors cover the table-select gates (sensor == 0/1/other at every byte
boundary incl. 0x80..0xFF which the sensor==1 branch sign-extends before its
unsigned cmp/hs; flag around the threshold 5 with the zero-extended cmp/gt;
sec around the threshold 5), the table-lookup interpolation at every axis
breakpoint of both tables (+-1 ulp, mid-points, out-of-range clamps, NaN/Inf
rpm) and the clamp edges of the argument around every table result (-10/-5/0,
NaN/Inf, denormal), plus N random vectors (fixed seed 0x60E1D400).

Usage:  python3 harness_limit_knock_retard_max.py [N]  (default N = 20000)
"""
import math
import os
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROM_PATH, load_cpu, make_rng, report, run_oracle  # noqa: E402
from sh2emu import f2bits, bits2f, ts  # noqa: E402

ADDR = 0x13E6C
N_DEFAULT = 20000
SEED = 0x60E1D400

# RAM input cells (all pure inputs — the function writes no RAM).
RPM_ADDR = 0xFFFFB5B8    # f32 engine speed (table interp axis)
SENSOR_ADDR = 0xFFFFB5A4  # u8  status byte (==1 / ==0 table-select gate)
FLAG_ADDR = 0xFFFFBB55    # u8  flag byte   (sensor==0 table-select gate)
SEC_ADDR = 0xFFFFBCA9     # u8  secondary byte (sensor==1 gate vs threshold)

# ROM calibration addresses.
ROM_TABLE_A = 0x0006B678   # 1D descriptor (4 u8 cells)
ROM_TABLE_B = 0x0006B664   # 1D descriptor (5 u8 cells)
ROM_THRESHOLD = 0x00079838  # u8 table-select threshold (== 5)
ROM_CLAMP_UPPER = 0x00079878  # f32 clamp high bound (== 0.0)

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = '/tmp/rx8-recon-limit_knock_retard_max'


def build_oracle(cc='cc'):
    """Compile the reconstructed source + its dedicated oracle into a binary."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_limit_knock_retard_max.c'),
           os.path.join(SAMPLES, 'src', 'rx8_limit_knock_retard_max.c'),
           '-lm',
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def load_cal(cpu):
    """The calibration constants straight from the stock ROM bytes (compared
    by their raw big-endian bit patterns)."""
    rom = cpu.rom

    def r32(a):
        return struct.unpack_from('>I', rom, a)[0]

    if rom[ROM_THRESHOLD] != 5:
        raise RuntimeError(
            'unexpected threshold @0x%X: got %02X want 05'
            % (ROM_THRESHOLD, rom[ROM_THRESHOLD]))
    got = [rom[ROM_THRESHOLD], r32(ROM_CLAMP_UPPER)]
    if got[1] != 0x00000000:
        raise RuntimeError(
            'unexpected clamp upper @0x%X: got %08X want 00000000'
            % (ROM_CLAMP_UPPER, got[1]))
    # descriptor heads: u16 count, u8 cell type (4 = u8), u8 pad, axis ptr,
    # values ptr, scale, offset.
    desc_b = ((ROM_TABLE_B, 5), (ROM_TABLE_A, 4))
    for addr, count in desc_b:
        if rom[addr] != 0 or rom[addr + 1] != count or rom[addr + 2] != 4:
            raise RuntimeError('unexpected descriptor head @0x%X' % addr)
        scale = struct.unpack_from('>f', rom, addr + 12)[0]
        offset = struct.unpack_from('>f', rom, addr + 16)[0]
        if scale != 0.5 or offset != -64.0:
            raise RuntimeError(
                'unexpected scale/offset @0x%X: %r %r' % (addr, scale, offset))
    got += [rom[ROM_TABLE_B + 1], rom[ROM_TABLE_A + 1]]
    # table axes/cells
    axB = [struct.unpack_from('>f', rom, 0x798A4 + 4 * i)[0] for i in range(5)]
    if axB != [2000.0, 2500.0, 3000.0, 4500.0, 5000.0]:
        raise RuntimeError('unexpected table B axis: %r' % (axB,))
    if list(rom[0x798B8:0x798BD]) != [108, 108, 108, 108, 128]:
        raise RuntimeError('unexpected table B cells')
    axA = [struct.unpack_from('>f', rom, 0x798C0 + 4 * i)[0] for i in range(4)]
    if axA != [2000.0, 3000.0, 4500.0, 5000.0]:
        raise RuntimeError('unexpected table A axis: %r' % (axA,))
    if list(rom[0x798D0:0x798D4]) != [108, 118, 118, 128]:
        raise RuntimeError('unexpected table A cells')
    return got


def seed_ram(init, addr, n, val):
    """Byte-exact big-endian store of a width-`n` value in the ram overlay."""
    for i in range(n):
        init[addr + i] = (val >> (8 * (n - 1 - i))) & 0xFF


def run_emu(cpu, vec):
    """Seed the four input cells, run the ROM bytes @0x13E6C with fr4 = arg
    and return the returned fr0 bits."""
    rpm, sensor, flag, sec, arg = vec
    init = {}
    seed_ram(init, RPM_ADDR, 4, rpm)
    init[SENSOR_ADDR] = sensor
    init[FLAG_ADDR] = flag
    init[SEC_ADDR] = sec
    cpu.call(ADDR, ram=init, fr={4: bits2f(arg)})
    return f2bits(cpu.fr[0])


def gen_edges():
    """EDGE vectors.  Vector tuple: (rpm_bits, sensor, flag, sec, arg_bits)."""
    v = []

    # Byte gates around every branch boundary.  sensor==1 sign-extends sec and
    # threshold before the unsigned cmp/hs, so 0x80..0xFF always passes;
    # sensor==0 zero-extends flag before the cmp/gt vs the threshold (5).
    sensor_set = [0, 1, 2, 3, 0x7F, 0x80, 0xFF]
    flag_set = [0, 1, 2, 4, 5, 6, 7, 0x7F, 0x80, 0xFE, 0xFF]
    sec_set = [0, 1, 4, 5, 6, 0x7F, 0x80, 0xFE, 0xFF]

    # (a) table-select gates at a mid-table rpm, neutral arg.
    for s in sensor_set:
        for fl in flag_set:
            for se in sec_set:
                v.append((f2bits(2500.0), s, fl, se, f2bits(-3.0)))

    # (b) rpm axis breakpoints of both tables, +-1 ulp each side.
    for rpm in (2000.0, 2500.0, 3000.0, 4500.0, 5000.0):
        for d in (-1, 0, 1):
            u = (f2bits(rpm) + d) & 0xFFFFFFFF
            for s, fl, se in ((0, 4, 0), (1, 0, 9), (0, 0, 0), (2, 4, 0)):
                v.append((u, s, fl, se, f2bits(-3.0)))

    # (c) rpm out-of-range / non-finite rpm (high/low clamps, NaN/Inf).
    for rpm in (0.0, -0.0, 1999.0, 1999.99, 2000.01, 4999.99, 5000.01, 6000.0,
                100000.0, float('nan'), float('inf'), float('-inf')):
        for s, fl, se in ((0, 4, 0), (1, 0, 9), (0, 0, 0), (0, 6, 0)):
            v.append((f2bits(rpm), s, fl, se, f2bits(-3.0)))

    # (d) argument clamp edges around every table result (lo = -10 / -5 /
    # -7.5 / 0 etc.), across both tables and both gate paths.
    arg_edges = (float('-inf'), -20.0, -12.0, -10.0001, -10.0, -9.999,
                 -7.5001, -7.5, -7.499, -5.0001, -5.0, -4.999,
                 -0.01, -0.0, 0.0, 0.01, 2.0, 5.0, 20.0, float('inf'),
                 float('nan'), 1e-40, -1e-40)
    for arg in arg_edges:
        for s, fl, se in ((0, 4, 0), (1, 0, 9), (0, 0, 0), (0, 6, 0),
                          (0, 0, 0), (1, 0, 4)):
            v.append((f2bits(2500.0), s, fl, se, f2bits(arg)))
    return v


def gen_random(rng, n):
    """n random vectors: floats uniform in-range (15% raw bits to hit NaN/Inf/
    denormals), mode bytes uniform over the full byte range.  No overflow risk:
    rpm is only compared/interpolated against the small axis values (out-of-
    range rpm high-clamps before any fdiv) and arg is only compared."""

    def pick(lo, hi):
        if rng.random() < 0.15:
            return rng.getrandbits(32)
        return f2bits(ts(rng.uniform(lo, hi)))

    v = []
    for _ in range(n):
        v.append((pick(0.0, 9000.0),     # rpm
                  rng.getrandbits(8),    # sensor
                  rng.getrandbits(8),    # flag
                  rng.getrandbits(8),    # sec
                  pick(-30.0, 30.0)))    # arg
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

    # (a) ROM behaviour via the emulator (returned fr0 bits).
    emu = [run_emu(cpu, v) for v in vectors]

    # (b) host-C on the same vectors (floats as raw bits; the oracle maps
    # the ROM cal pages straight from the stock bin, so no cal tokens needed).
    lines = ['lkr %08X %02X %02X %02X %08X' % v for v in vectors]
    host = [int(x, 16) for x in run_oracle(oracle, lines)]

    # (c) compare the returned bits byte-for-byte.
    mismatches = []
    for i, (vec, e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            rpm, sensor, flag, sec, arg = vec
            mismatches.append(
                'vec#%d rpm=%08X sensor=%02X flag=%02X sec=%02X arg=%08X '
                'ROM=%08X C=%08X'
                % (i, rpm, sensor, flag, sec, arg, e, h))
            if len(mismatches) >= 5:
                break

    report('limit_knock_retard_max', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
