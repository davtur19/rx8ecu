#!/usr/bin/env python3
"""
harness_battery_voltage_monitor.py — equivalence of rx8_battery_voltage_monitor
                                      @0x26766.

Reconstructed source: samples/src/rx8_battery_voltage_monitor.c
Verified lift   : c/battery_voltage_monitor.c  (speculative description — the
                  ROM bytes win where the two disagree; documented in the
                  reconstructed source header).

The function is a VOID task with no ABI return value: the whole effect is on
RAM, so the equivalence check compares the four post-state RAM cells
byte-for-byte:

   RAM8  [0xFFFFB6B6]  charging-fault byte ov = (bat <= 10.0) ? 1 : 0
   RAM16 [0xFFFFB67A]  compensation word    312 (skip) | decremented (dec)
   RAM16 [0xFFFFB6AC]  counter A  saturating +1 (or cleared if tps==0)
   RAM16 [0xFFFFB6AE]  counter B  saturating +1 (or cleared if ov==0)

  - emulator side: seed the sparse RAM overlay (bat f32 @0xFFFFB600, the TPS
    byte @0xFFFFA428, intermediate f32 @0xFFFFB6C4, reference f32
    @0xFFFFB6C8, plus pre-states of the four written cells), call the REAL ROM
    bytes @0x26766 (the saturating-u16-add leaf @0x2460 runs as real ROM),
    read the four cells back;
  - host side: the dedicated oracle mmap()s the pages backing the cells AND
    the ROM calibration page @0x751A2..0x751C4 straight from the ROM file,
    seeds the same bytes, runs the reconstructed C and prints the same cells.

EDGE vectors cover the battery threshold at 10.0 and every f32 guard
(16.973 / 10.938) +/- 1 ulp, NaN/±inf/denormal of each float cell, the TPS
byte (0/1/2/0xFF), the ov byte (0/1/2/0xFF), the counter thresholds around
63/62/0xFFFF (saturating boundary) and the compensation word around
0/1/0xFFFF; N random pre-states follow (fixed seed = the ROM address).

Usage:  python3 harness_battery_voltage_monitor.py [N]  (default N = 20000)
"""
import os
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROM_PATH, load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0x26766
N_DEFAULT = 20000
SEED = 0x26766
BUILD_DIR = os.environ.get('RX8_RECON_BVM_BUILD_DIR',
                           '/tmp/rx8-recon-battery_voltage_monitor')

# ---- cell addresses (see rx8_battery_voltage_monitor.c) ----
BAT_ADDR   = 0xFFFFB600      # f32 battery voltage (V)
TPS_ADDR   = 0xFFFFA428      # u8 TPS / engine-state byte
OV_ADDR    = 0xFFFFB6B6      # u8 charging-fault byte
CMP_ADDR   = 0xFFFFB67A      # u16 compensation word
INT_ADDR   = 0xFFFFB6C4      # f32 ADC-processing intermediate
REF_ADDR   = 0xFFFFB6C8      # f32 reference voltage
CNTA_ADDR  = 0xFFFFB6AC      # u16 counter A
CNTB_ADDR  = 0xFFFFB6AE      # u16 counter B

# ---- ROM calibration cells (validated again) ----
ROM_CAL_HI   = 0x751B0       # f32 10.0
ROM_CAL_LO   = 0x751B4       # f32 1.0 (dead)
ROM_CAL_CRIT = 0x751C0       # f32 16.973
ROM_CAL_UW   = 0x751C4       # f32 10.938
ROM_CAL_ACC_A = 0x751A2      # u16 63
ROM_CAL_ACC_B = 0x751A4      # u16 63
ROM_CAL_LOAD  = 0x751A8      # u16 312

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def build_oracle(cc='cc'):
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_battery_voltage_monitor.c'),
           os.path.join(SAMPLES, 'src', 'rx8_battery_voltage_monitor.c'),
           '-lm', '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def seed(init, addr, n, val):
    for i in range(n):
        init[addr + i] = (val >> (8 * (n - 1 - i))) & 0xFF


def run_emu(cpu, vec):
    bat, tps, ov0, cmp0, intermed, ref, cntA0, cntB0 = vec
    init = {}
    seed(init, BAT_ADDR, 4, bat & 0xFFFFFFFF)
    init[TPS_ADDR] = tps & 0xFF
    init[OV_ADDR] = ov0 & 0xFF
    seed(init, CMP_ADDR, 2, cmp0 & 0xFFFF)
    seed(init, INT_ADDR, 4, intermed & 0xFFFFFFFF)
    seed(init, REF_ADDR, 4, ref & 0xFFFFFFFF)
    seed(init, CNTA_ADDR, 2, cntA0 & 0xFFFF)
    seed(init, CNTB_ADDR, 2, cntB0 & 0xFFFF)
    cpu.call(ADDR, ram=init)
    return (cpu.rd(OV_ADDR, 1), cpu.rd(CMP_ADDR, 2),
            cpu.rd(CNTA_ADDR, 2), cpu.rd(CNTB_ADDR, 2))


# f32 edge bit patterns: 0/+denorm -0, +/-1, thresholds (10/16.973/10.938)
# with +/-1 ulp, +-inf, NaN payloads, huge +/- magnitudes.
F32_EDGES = (
    0x00000000, 0x00000001, 0x007FFFFF, 0x00800000, 0x3F800000,
    0x411F0000, 0x411FFFFF,                   # ~9.99 (below 10.0)
    0x41200000, 0x41201000, 0x41201001,       # 10.0 and ulp
    0x41800000, 0x4187C8B3, 0x4187C8B4, 0x4187C8B5,   # 16.97 ulp
    0x41880000,                               # 17.0
    0x412F020B, 0x412F020C, 0x412F020D,       # 10.938 ulp
    0x42C80000, 0x43160000, 0x437A0000,       # 100 / 150 / 250
    0x7F800000, 0xFF800000,                   # +inf / -inf
    0x7FC00000, 0xFFFFBFFF,                   # NaN  (qnan / snan)
    0x80000000, 0xC3480000,                   # -0.0 / -200.0
    0x4E6E6B28, 0xCE6E6B28)                   # +1e9 / -1e9


def gen_edges():
    v = []
    # (a) battery-value threshold around 10.0 (bat <= 10 -> ov=1) with the
    #     counter / float guard driven well inside.
    for bat in F32_EDGES:
        # int passes through the two f32 gates and the tps/ov byte tests.
        for tps in (0x00, 0x01):
            v.append((bat, tps, 0x01, 0x0005, 0x41900000, 0x41400000,
                      0x0040, 0x0040))
    # (b) intermediate / reference guards (succeed -> may reach dec path).
    for intermed in (0x41870000, 0x41880000, 0x41900000, 0x7FC00000,
                     0xFF800000, 0x00000000):
        for ref in (0x41400000, 0x41500000, 0x7FA00000, 0x7F800000):
            v.append((0x43160000, 0x01, 0x01, 0x0005, intermed, ref,
                      0x0040, 0x0040))
    # (c) TPS/ov byte polarity -> counter clears (tps==0 clears A, ov==0
    #     clears B).
    for cnt in (0x0000, 0x0001, 0x003E, 0x003F, 0x0040, 0x7FFF, 0x8000,
                0xFFFE, 0xFFFF):
        v.append((0x43160000, 0x00, 0x01, 0x0000, 0x41900000, 0x41400000,
                  cnt, cnt))
        v.append((0x43160000, 0x01, 0x00, 0x0000, 0x41900000, 0x41400000,
                  cnt, cnt))
    # (d) counter-A threshold boundary (tps==1 requires [A]>=63 to reach dec).
    for cntA in (0x003E, 0x003F, 0x0040, 0xFFFE, 0xFFFF):
        v.append((0x43160000, 0x01, 0x01, 0x0005, 0x41900000, 0x41400000,
                  cntA, 0x0040))
    # (e) counter-B threshold boundary / dec gate (ov==1: cntB>=63 -> dec).
    for cntB in (0x003E, 0x003F, 0x0040, 0xFFFF):
        v.append((0x43160000, 0x01, 0x01, 0x0005, 0x41900000, 0x41400000,
                  0x0040, cntB))
    # (f) compensation-word decrement boundaries on the dec path.
    for cmp0 in (0x0000, 0x0001, 0x0002, 0x7FFF, 0x8000, 0xFFFF):
        v.append((0x43160000, 0x01, 0x01, cmp0, 0x41900000, 0x41400000,
                  0x0040, 0x0040))
    return v


def gen_random(rng, k):
    v = []
    for _ in range(k):
        def rb():
            if rng.random() < 0.5:
                return struct.unpack('>I', struct.pack(
                    '>f', rng.uniform(0, 20)))[0]
            return rng.getrandbits(32)
        v.append((rb(),
                  rng.choice((0, 0, 1, 2, 0xFF)),
                  rng.choice((0, 0, 1, 2, 0xFF)),
                  rng.getrandbits(16),
                  rb(), rb(),
                  rng.choice((0x003E, 0x003F, 0x0040, rng.getrandbits(16))),
                  rng.choice((0x003E, 0x003F, 0x0040, rng.getrandbits(16)))))
    return v


def check_cal(cpu):
    import struct as st
    def f16(a):
        return st.unpack_from('>H', cpu.rom, a)[0]
    def f32(a):
        return st.unpack_from('>I', cpu.rom, a)[0]
    if (f32(ROM_CAL_HI) != 0x41200000            # 10.0
            or f32(ROM_CAL_LO) != 0x3F800000     # 1.0
            or f32(ROM_CAL_CRIT) != 0x4187C8B4   # 16.97299...
            or f32(ROM_CAL_UW) != 0x412F020C     # 10.93799...
            or f16(ROM_CAL_ACC_A) != 63
            or f16(ROM_CAL_ACC_B) != 63
            or f16(ROM_CAL_LOAD) != 312):
        raise RuntimeError('unexpected battery-monitor calibration bytes')


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(SEED)
    check_cal(cpu)
    os.environ['RX8_ROM_PATH'] = ROM_PATH

    EDGE = gen_edges()
    vectors = EDGE + gen_random(rng, n)

    emu = [run_emu(cpu, v) for v in vectors]

    lines = ['bvm %08X %02X %02X %04X %08X %08X %04X %04X' % v
             for v in vectors]
    host = [tuple(int(x, 16) for x in out.split())
            for out in run_oracle(oracle, lines)]

    mismatches = []
    for i, (v, e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d bat=0x%08X tps=%02X ov0=%02X cmp0=%04X '
                'int=0x%08X ref=0x%08X cntA0=%04X cntB0=%04X '
                'ROM=(%02X,%04X,%04X,%04X) C=(%02X,%04X,%04X,%04X)'
                % (i, v[0], v[1], v[2], v[3], v[4], v[5], v[6], v[7],
                   e[0], e[1], e[2], e[3], h[0], h[1], h[2], h[3]))
            if len(mismatches) >= 5:
                break

    report('battery_voltage_monitor', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()