#!/usr/bin/env python3
"""
harness_calc_decel_fuel_cut_445aa.py — equivalence of
rx8_calc_decel_fuel_cut_445aa @0x445AA.

Reconstructed source: samples/src/rx8_calc_decel_fuel_cut_445aa.c
Verified lift   : c/calc_decel_fuel_cut_445AA.c (same address; the ROM bytes
                  are executed for real here via tools/sh2emu.py, including
                  the jsr'd leaf addSaturate8Bit @0x2478).

The function is a void fuel-cut task with NO ABI return value: its whole
effect is two RAM byte writes — the fuel-cut flag @0xFFFFCAB5 and the
hysteresis accumulator @0xFFFFCAAC — so the equivalence check compares RAM
side-effects, not a return value:

  - emulator side: seed the three f32 inputs (throttle @0xFFFFCA30, speed
    @0xFFFFCA38, threshold @0xFFFFCA88) and the six byte inputs (override
    @0xFFFFCABB, decel enable @0xFFFFCAB9, mode @0xFFFFCAB4, accumulator
    @0xFFFFCAAC, permission #2 @0xFFFFCAB8, secondary-cut @0xFFFFCAB6) in the
    sparse ram overlay, call the ROM entry @0x445AA, read the two output
    bytes back;
  - host side: the dedicated oracle mmap()s the page backing the RAM cells AND
    the ROM calibration page (0x7B3DC/0x7B3DD flags, 0x7B418/0x7B41C f32),
    seeds the same bytes (calibration values shipped inline, taken from the
    stock 60E1D400.bin) and prints the two output bytes.

The calibration constants are asserted against the stock ROM before the run
(f_en == 1, cdis == 0, tclosed == 0.01, t50 == 50.0), so emulator and oracle
read byte-identical constants.  The decision path depends on them in the
obvious way: with the stock f_en == 1 the `den == 1` gate forces no cut, and
with cdis == 0 the cut gate equals (cab8 == 1).

EDGE vectors cover: the fuel-cut decision around both thresholds (th vs thr88
and vs t50, 1 ulp around every boundary, 0/-0, NaN, +/-inf), the acc
hysteresis boundary, the caldec gate (cab8 around its ==1 test), the three
gate flags (override / decel-enable / mode around their ==1 tests, non-bool
bytes too), the speed threshold (tclosed == 0.01 +/- 1 ulp) and the
accumulator write rules (sc 0/!=0 x fuel_cut 0/1 x acc pre-states); N random
pre-states follow (fixed seed = 0x60E1D400).

Usage:  python3 harness_calc_decel_fuel_cut_445aa.py [N]  (default N = 20000)
"""
import math
import os
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402
from sh2emu import f2bits, bits2f, ts  # noqa: E402

ADDR = 0x445AA
N_DEFAULT = 20000
SEED = 0x60E1D400
BUILD_DIR = '/tmp/rx8-recon-calc_decel_fuel_cut_445aa'

# ---- RAM cells (see rx8_calc_decel_fuel_cut_445aa.c) ----
TH_ADDR = 0xFFFFCA30       # f32 throttle position
SPD_ADDR = 0xFFFFCA38      # f32 engine speed / over-run input
THR_ADDR = 0xFFFFCA88      # f32 throttle-position threshold
OVR_ADDR = 0xFFFFCABB      # u8 override flag
DEN_ADDR = 0xFFFFCAB9      # u8 decel-fuel-cut enable
MODE_ADDR = 0xFFFFCAB4     # u8 fuel-cut mode
ACC_ADDR = 0xFFFFCAAC      # u8 hysteresis accumulator (in/out)
CAB8_ADDR = 0xFFFFCAB8     # u8 decel permission flag #2
SC_ADDR = 0xFFFFCAB6       # u8 secondary-cut flag
FLAG_ADDR = 0xFFFFCAB5     # u8 fuel-cut flag (output)

# ---- ROM calibration cells ----
C_FEN_ADDR = 0x7B3DC       # u8 feature enable    (== 0x01)
C_CDIS_ADDR = 0x7B3DD      # u8 feature disable   (== 0x00)
C_TCLOSED_ADDR = 0x7B418   # f32 throttle-closed  (== 0.01)
C_T50_ADDR = 0x7B41C       # f32 secondary RPM    (== 50.0)

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def seed_ram(init, addr, n, val):
    """Byte-exact big-endian store of a width-`n` value in the ram overlay."""
    for i in range(n):
        init[addr + i] = (val >> (8 * (n - 1 - i))) & 0xFF


def run_emu(cpu, vec):
    """Seed the nine input cells, run the ROM bytes @0x445AA (the real
    0x2478 leaf included) and return the two output bytes."""
    th, spd, thr88, ovr, den, mode, acc, cab8, sc = vec
    init = {}
    seed_ram(init, TH_ADDR, 4, th & 0xFFFFFFFF)
    seed_ram(init, SPD_ADDR, 4, spd & 0xFFFFFFFF)
    seed_ram(init, THR_ADDR, 4, thr88 & 0xFFFFFFFF)
    init[OVR_ADDR] = ovr & 0xFF
    init[DEN_ADDR] = den & 0xFF
    init[MODE_ADDR] = mode & 0xFF
    init[ACC_ADDR] = acc & 0xFF
    init[CAB8_ADDR] = cab8 & 0xFF
    init[SC_ADDR] = sc & 0xFF
    cpu.call(ADDR, ram=init)
    return (cpu.rd(FLAG_ADDR, 1), cpu.rd(ACC_ADDR, 1))


def load_cal(cpu):
    """The four calibration constants straight from the stock ROM bytes."""
    fen = cpu.rom[C_FEN_ADDR]
    cdis = cpu.rom[C_CDIS_ADDR]
    tclosed = struct.unpack_from('>f', cpu.rom, C_TCLOSED_ADDR)[0]
    t50 = struct.unpack_from('>f', cpu.rom, C_T50_ADDR)[0]
    if (fen, cdis, ts(tclosed), ts(t50)) != (1, 0, ts(0.01), ts(50.0)):
        raise RuntimeError('unexpected ROM calibration @0x%X/0x%X/0x%X/0x%X: '
                           '%r %r %r %r' % (C_FEN_ADDR, C_CDIS_ADDR,
                                            C_TCLOSED_ADDR, C_T50_ADDR,
                                            fen, cdis, tclosed, t50))
    return (f2bits(tclosed), f2bits(t50), fen, cdis)


def gen_edges():
    """EDGE vectors.  Tuple: (th, spd, thr88, ovr, den, mode, acc, cab8, sc)
    with the three floats as raw IEEE-754 single bits."""
    v = []

    def np(lo, hi):
        return math.nextafter(lo, hi)

    # (a) decision sweep: th vs thr88 (RAM) and vs t50 (cal 50.0), with the
    # accumulator at its ==0 boundary; speed well past tclosed, mode==1,
    # gates clear, cab8==1 (so caldec == 1 and the cut gate is observable).
    for thr88 in (0.0, 20.0, 49.99, 50.0, 60.0, 90.0, float('nan')):
        th_set = [thr88,
                  np(thr88, -math.inf) if not math.isnan(thr88) else float('nan'),
                  np(thr88, math.inf) if not math.isnan(thr88) else float('nan')]
        th_set += (0.0, -0.0, 49.999, 50.0, 50.001, 89.999, 90.0001, 100.0,
                   float('nan'), float('inf'), float('-inf'))
        for th in th_set:
            for acc in (0, 1, 2, 127, 254, 255):
                v.append((f2bits(th), f2bits(60.0), f2bits(thr88),
                          0, 0, 1, acc, 1, 1))
    # (b) caldec gate: cab8 around its ==1 test (th >= thr88, acc == 0 so the
    # cut gate always passes and fuel_cut == caldec == (cab8 == 1)).
    for cab8 in (0, 1, 2, 0x7F, 0xFF):
        v.append((f2bits(100.0), f2bits(60.0), f2bits(10.0), 0, 0, 1, 0, cab8, 1))
    # (c) the three gate flags around their ==1 tests (non-bool bytes too),
    # with inputs that would otherwise cut (th=100, thr88=10, acc=0, cab8=1).
    for ovr in (0, 1, 2, 0xFF):
        for den in (0, 1, 2, 0xFF):
            for mode in (0, 1, 2, 0xFF):
                v.append((f2bits(100.0), f2bits(60.0), f2bits(10.0),
                          ovr, den, mode, 0, 1, 1))
    # (d) speed around the tclosed threshold (0.01): the `tclosed > spd` gate.
    for spd in (0.0, 0.005, 0.0099999998, 0.01, 0.010000001, 0.02, 60.0,
                float('nan'), float('inf'), float('-inf')):
        v.append((f2bits(100.0), f2bits(spd), f2bits(10.0), 0, 0, 1, 0, 1, 1))
    # (e) accumulator write rules: sc 0/!=0 x fuel-cut outcome x acc pre-state.
    for sc in (0, 1, 2, 0xFF):
        for acc in (0, 1, 254, 255):
            # fuel_cut == 1 path (decision passes, cab8 == 1)
            v.append((f2bits(100.0), f2bits(60.0), f2bits(10.0),
                      0, 0, 1, acc, 1, sc))
            # fuel_cut == 0 path (cab8 == 0 -> caldec == 0)
            v.append((f2bits(100.0), f2bits(60.0), f2bits(10.0),
                      0, 0, 1, acc, 0, sc))
            # gate path (den == 1 -> fuel_cut == 0 regardless)
            v.append((f2bits(100.0), f2bits(60.0), f2bits(10.0),
                      0, 1, 1, acc, 1, sc))
    return v


def gen_random(rng, n):
    """n random pre-states: floats uniform in-range (15% raw bits to hit
    NaN/Inf/denormals), gate/flag bytes biased toward their ==1 hot values
    plus the full byte range."""

    def pick(lo, hi):
        if rng.random() < 0.15:
            return bits2f(rng.getrandbits(32))
        return ts(rng.uniform(lo, hi))

    v = []
    for _ in range(n):
        mode = rng.choice((0, 1, 1, 1, 2, 0xFF, rng.getrandbits(8)))
        ovr = rng.choice((0, 0, 0, 1, rng.getrandbits(8)))
        den = rng.choice((0, 0, 0, 1, rng.getrandbits(8)))
        cab8 = rng.choice((0, 0, 1, 1, rng.getrandbits(8)))
        sc = rng.choice((0, 0, 1, rng.getrandbits(8)))
        acc = rng.choice((0, 0, 1, rng.getrandbits(8)))
        v.append((f2bits(pick(-20.0, 120.0)),
                  f2bits(pick(-5.0, 100.0)),
                  f2bits(pick(-5.0, 120.0)),
                  ovr, den, mode, acc, cab8, sc))
    return v


def build_oracle(cc='cc'):
    """Compile the reconstructed source + its dedicated oracle into a binary."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests',
                        'oracle_calc_decel_fuel_cut_445aa.c'),
           os.path.join(SAMPLES, 'src',
                        'rx8_calc_decel_fuel_cut_445aa.c'),
           '-lm',
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(SEED)
    tclosed, t50, fen, cdis = load_cal(cpu)

    EDGE = gen_edges()
    vectors = EDGE + gen_random(rng, n)

    # (a) ROM behaviour via the emulator (RAM side-effects at 0xFFFFCAB5 /
    # 0xFFFFCAAC; the 0x2478 leaf runs as real ROM bytes).
    emu = [run_emu(cpu, v) for v in vectors]

    # (b) host-C on the same pre-states (stock cal bytes shipped inline).
    caltok = '%02X %02X %08X %08X' % (fen, cdis, tclosed, t50)
    lines = ['dcl %s %08X %08X %08X %02X %02X %02X %02X %02X %02X'
             % (caltok, v[0], v[1], v[2], v[3], v[4], v[5], v[6], v[7], v[8])
             for v in vectors]
    host = [tuple(int(x, 16) for x in out.split())
            for out in run_oracle(oracle, lines)]

    # (c) compare the post-state tuples byte-for-byte.
    mismatches = []
    for i, (v, e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d th=%08X(%.9g) spd=%08X thr88=%08X ovr=%02X den=%02X '
                'mode=%02X acc=%02X cab8=%02X sc=%02X ROM=(%02X,%02X) '
                'C=(%02X,%02X)'
                % (i, v[0], bits2f(v[0]), v[1], v[2], v[3], v[4], v[5], v[6],
                   v[7], v[8],
                   e[0], e[1], h[0], h[1]))
            if len(mismatches) >= 5:
                break

    report('calc_decel_fuel_cut_445aa', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
