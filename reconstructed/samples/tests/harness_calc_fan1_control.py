#!/usr/bin/env python3
"""
harness_calc_fan1_control.py — equivalence of rx8_calc_fan1_control @0x303A6.

Reconstructed source: samples/src/rx8_calc_fan1_control.c
Verified lift   : c/calc_fan1_control.c (same address; the ROM bytes are
                  executed for real here via tools/sh2emu.py).

The ROM function is a leaf with NO ABI return value: its whole effect is on
RAM (three u8 cells — fan 1 relay @0xFFFFBE16, fan 2 relay @0xFFFFBE17 and
the fan-enable latch @0xFFFFBE0D), so the equivalence check compares RAM
side-effects, not a return value:

  - emulator side: seed the f32 temperature @0xFFFFAA10, the three output
    pre-states and the 13 fan-enable status cells in the sparse ram overlay,
    call the ROM entry @0x303A6, read the three cells back;
  - host side: the dedicated oracle mmap()s the pages backing the cells AND
    the ROM calibration table @0x7793C, seeds the same bytes (calibration
    floats shipped inline as raw bits), runs the reconstructed C and prints
    the same three cells.

EDGE vectors cover the hysteresis thresholds (0, 94-ulp, 94, 94+ulp, 97-ulp,
97, 97+ulp, hot/cold extremes, NaN, +/-inf) with distinguishable pre-states,
an exhaustive sweep of the six entry-tree status cells, and an exhaustive
sweep of the seven branch-tree cells behind it (with the entry chain forced
cold so the whole latch state machine is exercised); N random vectors follow
with full-byte status cells and raw random float temps (fixed seed).

Usage:  python3 harness_calc_fan1_control.py [N]  (default N = 20000)
"""
import os
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import make_rng, report, run_oracle  # noqa: E402
from sh2emu import SH2, f2bits  # noqa: E402

ADDR = 0x303A6
FAN_TEMP_ADDR = 0xFFFFAA10        # f32 temperature input
FAN1_OUT_ADDR = 0xFFFFBE16        # u8 fan 1 relay command
FAN2_OUT_ADDR = 0xFFFFBE17        # u8 fan 2 relay command
FAN_EN_ADDR = 0xFFFFBE0D          # u8 fan enable latch

# 13 fan-enable status cells, in vector order.
STATUS_CELLS = [0xFFFFB13D, 0xFFFFAAE0, 0xFFFFBE0C, 0xFFFFCD06, 0xFFFFA96A,
                0xFFFFBFF5, 0xFFFFBDD4, 0xFFFFBDD6, 0xFFFFD07C, 0xFFFFD0E4,
                0xFFFFD2A0, 0xFFFFD2A5, 0xFFFFD29F]

# Hysteresis calibration floats the ROM reads (raw bits).
CAL_ADDRS = (0x0007793C, 0x00077940, 0x00077944, 0x00077948)  # T1_ON, T1_HY, T2_ON, T2_HY
CAL_EXPECT = (0x42C20000, 0x40400000, 0x42C20000, 0x40400000)  # 97.0, 3.0, 97.0, 3.0

N_DEFAULT = 20000
SEED = 0x303A6

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = '/tmp/rx8-recon-calc_fan1_control'


def build_oracle(cc='cc'):
    """Compile the reconstructed source + its dedicated oracle into a binary."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_calc_fan1_control.c'),
           os.path.join(SAMPLES, 'src', 'rx8_calc_fan1_control.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def f_bits(v):
    """Exact single-precision bits of a Python float."""
    return f2bits(v)


def gen_edges():
    """Edge vectors: (t_bits, be16, be17, be0d, s0..s12)."""
    v = []
    pre_both = [(0, 0, 0), (1, 1, 1), (1, 0, 1), (0, 1, 0)]

    # (a) temperature edges: both relays hot/cold/held + NaN/Inf behaviour,
    #     with distinguishable pre-states to catch the "hold" paths.
    temps = [0.0, -40.0, 20.0, 93.999, 94.0, 94.001, 96.999, 97.0, 97.001,
             100.0, 120.0, -1e30, 1e30, float('nan'), float('inf'),
             float('-inf')]
    for t in temps:
        tb = f_bits(t)
        for pre in pre_both:
            v.append((tb, pre[0], pre[1], pre[2]) + (0,) * 13)

    # (b) exhaustive sweep of the six entry-tree status cells
    #     (B13D, AAE0, BE0C, CD06, A96A, BFF5) with be16=be17=0: the
    #     five-cell AND chain decides loc0 -> loc2 vs loc0 -> loc1.
    entry_idx = (0, 1, 2, 3, 4, 5)
    for m in range(1 << len(entry_idx)):
        s = [0] * 13
        for j, i in enumerate(entry_idx):
            s[i] = (m >> j) & 1
        v.append((f_bits(50.0), 0, 0, 0) + tuple(s))

    # (c) entry via be17==1 && B13D==1 (and the split where B13D==0).
    for b13d in (0, 1):
        v.append((f_bits(50.0), 0, 1, 0) + (b13d,) + (0,) * 12)

    # (d) exhaustive sweep of the branch-tree cells behind the entry
    #     (BDD4, BDD6, D07C, D0E4, D2A0, D2A5, D29F) with the entry chain
    #     forced cold (AAE0=1 -> loc0 -> loc1) so the whole latch state
    #     machine runs to every leaf.
    tree_idx = (6, 7, 8, 9, 10, 11, 12)
    for m in range(1 << len(tree_idx)):
        s = [0] * 13
        s[1] = 1                    # AAE0 = 1: five-chain false, loc0 -> loc1
        for j, i in enumerate(tree_idx):
            s[i] = (m >> j) & 1
        v.append((f_bits(50.0), 0, 0, 0) + tuple(s))

    return v


def gen_random(rng, n):
    """n random vectors: full-byte status cells, random pre-states, and a mix
    of plausible temps and raw random float bits (NaN/Inf/sign-flips)."""
    v = []
    for _ in range(n):
        if rng.random() < 0.5:
            tb = rng.getrandbits(32)            # raw float bits
        else:
            tb = f_bits(rng.uniform(-50.0, 150.0))
        pre = (rng.randrange(256), rng.randrange(256), rng.randrange(256))
        s = tuple(rng.randrange(256) for _ in range(13))
        v.append((tb, pre[0], pre[1], pre[2]) + s)
    return v


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    rom = open(os.path.join(SAMPLES, '..', '..', 'roms', 'stock', '60E1D400.bin'),
               'rb').read()
    cpu = SH2(rom)
    oracle = build_oracle()
    rng = make_rng(SEED)

    # The 4 calibration floats the ROM reads at 0x7793C..0x77948 (stock bin).
    cal = tuple(struct.unpack_from('>I', rom, a)[0] for a in CAL_ADDRS)
    if cal != CAL_EXPECT:
        raise RuntimeError('unexpected ROM calibration @0x%X: %s'
                           % (CAL_ADDRS[0],
                              ' '.join('%08X' % b for b in cal)))

    EDGE = gen_edges()
    vectors = EDGE + gen_random(rng, n)

    # (a) ROM behaviour via the emulator (RAM side-effects).
    emu = []
    for tb, be16, be17, be0d, *s in vectors:
        ram = {FAN1_OUT_ADDR: be16, FAN2_OUT_ADDR: be17, FAN_EN_ADDR: be0d}
        for i, b in enumerate(struct.pack('>I', tb)):
            ram[FAN_TEMP_ADDR + i] = b
        for c, val in zip(STATUS_CELLS, s):
            ram[c] = val
        cpu.call(ADDR, ram=ram)
        emu.append((cpu.rd(FAN1_OUT_ADDR, 1), cpu.rd(FAN2_OUT_ADDR, 1),
                    cpu.rd(FAN_EN_ADDR, 1)))

    # (b) host-C on the same inputs (calibration floats shipped inline).
    caltok = ' '.join('%08X' % b for b in cal)
    lines = ['fan1 %s %08X %02X %02X %02X %s'
             % (caltok, tb, be16, be17, be0d,
                ' '.join('%02X' % x for x in s))
             for tb, be16, be17, be0d, *s in vectors]
    host = [tuple(int(x, 16) for x in out.split())
            for out in run_oracle(oracle, lines)]

    # (c) compare the post-state triples byte-for-byte.
    mismatches = []
    for i, ((tb, be16, be17, be0d, *s), e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d t=0x%08X pre=(%02X,%02X,%02X) status=%s '
                'ROM=(%02X,%02X,%02X) C=(%02X,%02X,%02X)'
                % (i, tb, be16, be17, be0d,
                   ' '.join('%02X' % x for x in s),
                   e[0], e[1], e[2], h[0], h[1], h[2]))
            if len(mismatches) >= 5:
                break

    report('calc_fan1_control', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
