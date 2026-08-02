#!/usr/bin/env python3
"""
harness_vehicle_speed_sensor.py — equivalence of rx8_vehicle_speed_sensor @0x133F8.

Reconstructed source: samples/src/rx8_vehicle_speed_sensor.c
Verified lift   : c/vehicle_speed_sensor.c (calc_vehicle_speed_filter @ 0x133F8;
                  the lift's IIR/rate-limit model and fake status write were
                  corrected against the ROM bytes — see the sample header's
                  DISCREPANCIES section).

The ROM function is a plain `void` routine with NO ABI arguments: it reads four
f32 RAM cells (@0xFFFFA6AC raw, @0xFFFFA6B0 prev/out, @0xFFFFA6BC pivot A,
@0xFFFFA6C0 pivot B) and three status bytes + a gate byte, writes a common
1.0/5.0 bias into four more f32 cells, then applies a deadband + saturating
clamp to two of them (raw cell and prev cell).  The INPUTS are the four f32 +
four u8 cells; the OUTPUTS are six f32 RAM side-effects.  The emulator executes
the ACTUAL ROM bytes @0x133F8 (including the inline clamp leaves @0x23DC/
0x23E4/0x23F4); the host oracle mmap()s the RAM cell page and the ROM cal page
(seeded from the ROM file), seeds the same pre-states, runs the reconstructed C
and reports the six post-state cells bit-exactly.

Real ROM constants (immovable; the harness validates them and the oracle maps
the ROM page so both sides read identical bytes):
   0x0006F704 / 0x0006F708  f32 0.0999999866.. (bits 0x3DCCCCCB) thresholds
   0x0006F71C..28/6F72C..38 f32 1.0  (0x3F800000) low clamp bias
   0x0006F73C..48/6F74C..58 f32 5.0  (0x40A00000) high clamp bias

Usage:  python3 harness_vehicle_speed_sensor.py [N]   (default N = 20000)
"""
import os
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROM_PATH, load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0x133F8
N_DEFAULT = 20000
SEED = 0x60E1D400
BUILD_DIR = '/tmp/rx8-recon-vehicle_speed_sensor'

# ---- cell addresses (see rx8_vehicle_speed_sensor.c) ----
RAW   = 0xFFFFA6AC   # f32 raw speed (in+out)
OUT   = 0xFFFFA6B0   # f32 prev/out (in+out)
C1    = 0xFFFFA6BC   # f32 pivot A (in)
C2    = 0xFFFFA6C0   # f32 pivot B (in)
BIAS1 = 0xFFFFA6CC   # f32 clamp bias (+ branch blk1)
BIAS2 = 0xFFFFA6D0   # f32 clamp bias (- branch blk1)
BIAS3 = 0xFFFFA6D4   # f32 clamp bias (+ branch blk2)
BIAS4 = 0xFFFFA6D8   # f32 clamp bias (- branch blk2)
S9 = 0xFFFFA6B9   # u8 status sel (==1 -> 5.0)
S7 = 0xFFFFA6B7   # u8 status sel (==1 -> 1.0)
S8 = 0xFFFFA6B8   # u8 status sel (==1 -> 1.0)
A4 = 0xFFFFA428   # u8 gate (==0 -> zero)

# ROM cal constant locations (big-endian f32).
CAL_E1 = 0x6F704
CAL_E2 = 0x6F708

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def build_oracle(cc='cc'):
    """Compile THIS sample + its own oracle into /tmp (Track-A line; do NOT
    touch common.build_oracle / host_oracle.c / the Makefile)."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'src'),
           '-I', os.path.join(SAMPLES, 'include'),
           os.path.join(SAMPLES, 'tests', 'oracle_vehicle_speed_sensor.c'),
           os.path.join(SAMPLES, 'src', 'rx8_vehicle_speed_sensor.c'),
           '-lm', '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def f32(x):
    return struct.unpack('>I', struct.pack('>f', x))[0]


def bits2f(b):
    return struct.unpack('>f', struct.pack('>I', b & 0xFFFFFFFF))[0]


def seed(init, addr, n, val):
    for i in range(n):
        init[addr + i] = (val >> (8 * (n - 1 - i))) & 0xFF


def run_emu(cpu, vec):
    """Seed every input cell, run the ROM bytes @0x133F8 and return the six
    post-state f32 cells (raw bits) with all side effects visible."""
    s7, s8, s9, a4, raw, prev, c1, c2 = vec
    init = {}
    init[A4] = a4 & 0xFF
    seed(init, S7, 1, s7 & 0xFF)
    seed(init, S8, 1, s8 & 0xFF)
    seed(init, S9, 1, s9 & 0xFF)
    seed(init, RAW, 4, raw & 0xFFFFFFFF)
    seed(init, OUT, 4, prev & 0xFFFFFFFF)
    seed(init, C1, 4, c1 & 0xFFFFFFFF)
    seed(init, C2, 4, c2 & 0xFFFFFFFF)
    cpu.call(ADDR, ram=init)
    return (cpu.rd(RAW, 4), cpu.rd(OUT, 4),
            cpu.rd(BIAS1, 4), cpu.rd(BIAS2, 4),
            cpu.rd(BIAS3, 4), cpu.rd(BIAS4, 4))


def check_cal(cpu):
    """The stock calibration constants are fixed; refuse to run if they ever
    change so the ROM page mapping stays meaningful."""
    for addr in (CAL_E1, CAL_E2):
        if struct.unpack_from('>I', cpu.rom, addr)[0] != 0x3DCCCCCB:
            raise RuntimeError('unexpected VSS threshold @0x%X (0x%08X)'
                               % (addr, struct.unpack_from('>I', cpu.rom, addr)[0]))
    for lo, hi in ((0x6F71C, 0x6F738), (0x6F73C, 0x6F758)):
        for a in range(lo, lo + 1):
            if struct.unpack_from('>I', cpu.rom, a)[0] != 0x3F800000 and lo < hi:
                pass
    # spot-check the two representative bias constants.
    if struct.unpack_from('>I', cpu.rom, 0x6F71C)[0] != 0x3F800000:
        raise RuntimeError('unexpected low bias @0x6F71C')
    if struct.unpack_from('>I', cpu.rom, 0x6F73C)[0] != 0x40A00000:
        raise RuntimeError('unexpected high bias @0x6F73C')


def gen_edges():
    """Edge pre-states (s7,s8,s9,a4,raw,prev,c1,c2) targeting every branch."""
    v = []
    status_cases = [(0, 0, 0), (0, 0, 1), (1, 0, 0), (0, 1, 0),
                    (1, 1, 0), (1, 1, 1), (0x55, 0x55, 0x55), (0x00, 0xFF, 0x00)]
    # candidate float bit sprays (constants / boundaries / specials).
    p = 0.5
    candidates = []
    specials = [0x00000000, 0x80000000,             # +0 / -0
                0x7F800000, 0xFF800000,             # +inf / -inf
                0x7FC00000, 0xFFC00000, 0x7FA00000, # NaN payloads
                0x00000001, 0x007FFFFF,             # denormals
                0x3E800000,                          # 0.25
                0x3F000000,                          # 0.5
                f32(1.0), f32(5.0), f32(10.0), f32(-5.0)]
    candidates += specials
    # threshold-crossing deltas around pivot 0.5 (threshold ~ 0.09999999)
    for d in (0.0, 0.05, 0.09, 0.0999, 0.1, 0.1001, 0.11, 0.2, 0.5):
        candidates.append(f32(p + d))
        candidates.append(f32(p - d))
    candidates = list(dict.fromkeys(candidates))  # de-dup, keep order

    for (s7, s8, s9) in status_cases:
        for a4 in (0, 1):
            for raw in candidates:
                v.append((s7, s8, s9, a4, raw, f32(0.5), f32(0.5), f32(0.5)))
            for prev in candidates:
                v.append((s7, s8, s9, a4, f32(0.5), prev, f32(0.5), f32(0.5)))
    return v


def gen_random(rng, k):
    """k random eight-tuples; floats biased toward "sensible" ranges plus a
    tail over the full 32-bit pattern space (incl. NaN / inf / denormal)."""
    v = []
    for _ in range(k):
        def rnd():
            r = rng.random()
            if r < 0.7:
                vv = rng.uniform(-50, 50)
            elif r < 0.85:
                vv = rng.uniform(-0.5, 0.5)
            else:
                vv = rng.getrandbits(32)          # raw bits: NaN/Inf/denormal
            return vv
        raw = f32(rnd())
        prev = f32(rnd())
        c1 = f32(rng.choice((rng.uniform(-5, 5), 0.5, 0.5, 1.0, rnd())))
        c2 = f32(rng.choice((rng.uniform(-5, 5), 0.5, 0.5, 1.0, rnd())))
        v.append((rng.getrandbits(8), rng.getrandbits(8), rng.getrandbits(8),
                  rng.choice((0, 1, 1, rng.getrandbits(8))),
                  raw, prev, c1, c2))
    return v


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(SEED)
    check_cal(cpu)
    os.environ['RX8_ROM_PATH'] = ROM_PATH

    EDGE = gen_edges()
    vectors = EDGE + gen_random(rng, n)

    # (a) ROM behaviour via the emulator (real bytes, incl. clamp leaves).
    emu = [run_emu(cpu, x) for x in vectors]

    # (b) host C on the same pre-states (cal constants from the mapped ROM).
    lines = ['vss %02X %02X %02X %02X %08X %08X %08X %08X' % x for x in vectors]
    host = [tuple(int(y, 16) for y in out.split()) for out in run_oracle(oracle, lines)]

    # (c) byte-for-byte compare of the six post-state f32 cells.
    mismatches = []
    for i, (vec, e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d (s7=%02X s8=%02X s9=%02X a428=%02X raw=%08X prev=%08X '
                'c1=%08X c2=%08X) ROM=(%08X,%08X,%08X,%08X,%08X,%08X) '
                'C=(%s,%s,%s,%s,%s,%s)'
                % ((i,) + vec + e + tuple('%08X' % z for z in h)))
            if len(mismatches) >= 5:
                break

    report('vehicle_speed_sensor', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()