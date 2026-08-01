#!/usr/bin/env python3
"""
harness_idle_speed_control.py — equivalence of rx8_idle_speed_control @0x18054.

Reconstructed source: samples/src/rx8_idle_speed_control.c
Verified lift   : c/idle_speed_control_18054.c (same address; the ROM bytes
                  are executed for real here via tools/sh2emu.py).

The function is a void task with NO ABI return value: its whole effect is on
RAM (seven published cells + the two path-A-only writes + the check_pair
fallback flag), so the equivalence check compares RAM side-effects, not a
return value:

  - emulator side: seed the nine input cells in the sparse ram overlay
    (state @0xFFFFA428, mode @0xFFFFAAE0, AC @0xFFFFA979, running @0xFFFFA998,
    load_comp @0xFFFFA978, idle_en @0xFFFFA96C, old_status @0xFFFFA96A,
    learn @0xFFFFA970, duty u16 @0xFFFFA96E, O2 f32 @0xFFFFAA10) plus
    distinguishable sentinels (iacv-mode @0xFFFFA975, check_pair flag
    @0xFFFFC6AC), call the ROM entry @0x18054, read the ten post-state cells;
  - host side: the dedicated oracle mmap()s the pages backing the cells AND
    the ROM calibration page @0x78000, seeds the same bytes (calibration
    constants 156/500/-40.0 shipped inline from the stock bin), runs the
    reconstructed C and prints the same ten cells.

The three internal `jsr` leaves are executed for real on the emulator side
(0x3ED3C check_pair -> writes RAM[0xFFFFC6AC]=1 on its always-taken fallback
path, 0x2460 add16bitSaturate, 0x9668 osTaskScheduler); the oracle mirrors
them (see oracle_idle_speed_control.c).

EDGE vectors cover: the state/mode/ac/running matrix around all three paths,
duty boundaries around BOTH ceilings (155/156/157 and 499/500/501 plus the
0xFFFF saturation), O2 values around the -40.0 fcmp/gt boundary (incl. NaN,
+/-inf, +/-0.0), the status path with old_status 0/1 (the 0->1 transition
fires osTaskScheduler), the re-entry kick (idle_en 0->1) and distinguishable
stale pre-states; N random pre-states follow (fixed seed 0x18054).

Usage:  python3 harness_idle_speed_control.py [N]  (default N = 20000)
"""
import math
import os
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROM_PATH, make_rng, report, run_oracle  # noqa: E402
from sh2emu import SH2, f2bits, bits2f, ts  # noqa: E402

ADDR = 0x18054
N_DEFAULT = 20000
SEED = ADDR              # fixed-seed RNG, as requested (the address itself)

# input cells
STATE_ADDR = 0xFFFFA428
MODE_ADDR = 0xFFFFAAE0
AC_ADDR = 0xFFFFA979
RUNNING_ADDR = 0xFFFFA998
LOAD_COMP_ADDR = 0xFFFFA978
IDLE_EN_ADDR = 0xFFFFA96C
OLD_STATUS_ADDR = 0xFFFFA96A
LEARN_ADDR = 0xFFFFA970
DUTY_ADDR = 0xFFFFA96E      # u16
O2_ADDR = 0xFFFFAA10        # f32
# output cells
IDLE_ACTIVE_ADDR = 0xFFFFA96B
FEEDBACK_ADDR = 0xFFFFA968
AC_LATCH_ADDR = 0xFFFFA969
STATUS_ADDR = 0xFFFFA96A
IDLE_EN_OUT_ADDR = 0xFFFFA96C
LEARN_OUT_ADDR = 0xFFFFA970
IACV_MODE_ADDR = 0xFFFFA975
C6AC_ADDR = 0xFFFFC6AC

# calibration constants the ROM reads at 0x78E42/0x78E44/0x78E64
CAL_DUTY_HIGH = 0x00078E42
CAL_DUTY_LOW = 0x00078E44
CAL_O2_FUELCUT = 0x00078E64

N_DEFAULT = 20000

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = '/tmp/rx8-recon-idle_speed_control'


def build_oracle(cc='cc'):
    """Compile the reconstructed source + its dedicated oracle into a binary."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_idle_speed_control.c'),
           os.path.join(SAMPLES, 'src', 'rx8_idle_speed_control.c'),
           '-lm',
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def gen_edges():
    """Edge pre-states (state, mode, ac, running, load_comp, idle_en,
    old_status, learn, duty, o2)."""
    v = []
    # (1) the state/mode/ac/running matrix (all three paths), fixed duty/o2
    for state in (0, 1, 2, 3):
        for mode in (0, 1, 2, 0xFF):
            for ac in (0, 1):
                for running in (0, 1):
                    v.append((state, mode, ac, running, 0, 0, 0, 1,
                              100, 0.0))
    # (2) duty boundaries around both ceilings + saturation, both O2 branches
    for duty in (0, 1, 154, 155, 156, 157, 158, 498, 499, 500, 501,
                 0xFFFE, 0xFFFF):
        for o2 in (-41.0, -40.0, -39.0):
            v.append((2, 0, 0, 1, 0, 0, 0, 1, duty, o2))
    # (3) O2 fcmp/gt edges incl. non-finite and exact -40.0 neighbours
    o2s = [-40.0,
           ts(math.nextafter(-40.0, math.inf)),   # 1 ulp above
           ts(math.nextafter(-40.0, -math.inf)),  # 1 ulp below
           0.0, -0.0, 1e-30, -1e-30, 40.0,
           float('nan'), float('inf'), float('-inf')]
    for o2 in o2s:
        for duty in (155, 156, 157, 499, 500, 501):
            v.append((2, 0, 0, 1, 0, 0, 0, 1, duty, o2))
    # (4) status path (mode==0, ac==1, !running) — old_status 0 fires
    #     osTaskScheduler when the new status flips to 1
    for old_status in (0, 1):
        for load_comp in (0, 1):
            for learn in (0, 1):
                v.append((2, 0, 1, 0, load_comp, 0, old_status, learn,
                          100, 0.0))
    # (5) path A / path B with a full duty sweep (path A clears AC + sets
    #     mode flag; path B sets feedback only)
    for duty in (0, 1, 155, 156, 500, 0xFFFF):
        v.append((0, 1, 1, 0, 1, 1, 1, 1, duty, -50.0))
        v.append((1, 1, 0, 0, 1, 1, 1, 1, duty, 10.0))
    # (6) re-entry kick: idle_en 0 -> 1 with r13 becoming 1 (duty forced 0)
    for idle_en in (0, 1):
        for load_comp in (0, 1):
            v.append((2, 0, 0, 1, load_comp, idle_en, 0, 1, 0x1234, 0.0))
    # (7) distinguishable stale pre-states: catch any cell left unwritten
    for pre in (0x00, 0xFF, 0xAA, 0x01):
        v.append((pre & 3, pre & 1, pre & 1, pre & 1,
                  pre & 1, pre & 1, pre & 1, pre & 1, pre * 257,
                  ts(pre - 64.0)))
    return v


def gen_random(rng, n):
    """n random pre-states over the full byte range of every input."""
    return [(rng.randrange(256), rng.randrange(256), rng.randrange(256),
             rng.randrange(256), rng.randrange(256), rng.randrange(256),
             rng.randrange(256), rng.randrange(256), rng.randrange(65536),
             bits2f(rng.getrandbits(32)))
            for _ in range(n)]


def seed_ram(t):
    """Build the sparse emulator RAM overlay for one pre-state."""
    state, mode, ac, running, load_comp, idle_en, old_status, learn, duty, o2 = t
    ram = {STATE_ADDR: state & 0xFF, MODE_ADDR: mode & 0xFF,
           AC_ADDR: ac & 0xFF, RUNNING_ADDR: running & 0xFF,
           LOAD_COMP_ADDR: load_comp & 0xFF, IDLE_EN_ADDR: idle_en & 0xFF,
           OLD_STATUS_ADDR: old_status & 0xFF, LEARN_ADDR: learn & 0xFF,
           IACV_MODE_ADDR: 0x55,          # sentinel: only path A writes it
           C6AC_ADDR: 0x00}               # sentinel: check_pair fallback
    ram[DUTY_ADDR] = (duty >> 8) & 0xFF   # u16 stored big-endian (SH-2)
    ram[DUTY_ADDR + 1] = duty & 0xFF
    b = struct.pack('>f', ts(o2))
    for i in range(4):
        ram[O2_ADDR + i] = b[i]
    return ram


def read_out(cpu):
    """Read the ten post-state cells the function (re)writes."""
    def g(a):
        return cpu.ram.get(a, 0)
    duty = (g(DUTY_ADDR) << 8) | g(DUTY_ADDR + 1)
    return (g(IDLE_ACTIVE_ADDR), g(FEEDBACK_ADDR), g(AC_LATCH_ADDR),
            g(STATUS_ADDR), g(IDLE_EN_OUT_ADDR), duty, g(LEARN_OUT_ADDR),
            g(IACV_MODE_ADDR), g(AC_ADDR), g(C6AC_ADDR))


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    with open(ROM_PATH, 'rb') as f:
        cpu = SH2(f.read())
    oracle = build_oracle()
    rng = make_rng(SEED)

    # The calibration constants the ROM reads at 0x78E42/0x78E44/0x78E64
    # (stock: 156 / 500 / -40.0), shipped inline so both sides read the same.
    rom = cpu.rom
    cal_hi = struct.unpack_from('>H', rom, CAL_DUTY_HIGH)[0]
    cal_lo = struct.unpack_from('>H', rom, CAL_DUTY_LOW)[0]
    cal_o2 = struct.unpack_from('>f', rom, CAL_O2_FUELCUT)[0]
    if cal_hi != 156 or cal_lo != 500 or cal_o2 != -40.0:
        raise RuntimeError('unexpected ROM calibration @0x%X/%X/%X: %r/%r/%r'
                           % (CAL_DUTY_HIGH, CAL_DUTY_LOW, CAL_O2_FUELCUT,
                              cal_hi, cal_lo, cal_o2))

    os.environ['RX8_ROM'] = ROM_PATH      # oracle reads the 0x807C pair
    EDGE = gen_edges()
    vectors = EDGE + gen_random(rng, n)

    # (a) ROM behaviour via the emulator (RAM side-effects).
    emu = []
    for t in vectors:
        cpu.call(ADDR, ram=seed_ram(t))
        emu.append(read_out(cpu))

    # (b) host-C on the same pre-states (cal bytes shipped inline).
    lines = ['idle %X %X %X %X %X %X %X %X %X %08X %X %X %08X'
             % (t[0], t[1], t[2], t[3], t[4], t[5], t[6], t[7], t[8],
                f2bits(t[9]), cal_hi, cal_lo, f2bits(cal_o2))
             for t in vectors]
    host = [tuple(int(x, 16) for x in out.split())
            for out in run_oracle(oracle, lines)]

    # (c) compare the ten post-state cells byte-for-byte.
    names = ('idle_act', 'feedback', 'ac_latch', 'status', 'idle_en',
             'duty', 'learn', 'mode_flg', 'ac', 'c6ac')
    mismatches = []
    for i, (t, e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d s=%X m=%X ac=%X run=%X lc=%X ie=%X os=%X l=%X '
                'd=%X o2=%08X ROM=%s C=%s'
                % (i, t[0], t[1], t[2], t[3], t[4], t[5], t[6], t[7],
                   t[8], f2bits(t[9]),
                   ' '.join(names[j] + '=%X' % e[j] for j in range(10)),
                   ' '.join(names[j] + '=%X' % h[j] for j in range(10))))
            if len(mismatches) >= 5:
                break

    report('idle_speed_control', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
