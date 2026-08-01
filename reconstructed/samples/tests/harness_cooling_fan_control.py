#!/usr/bin/env python3
"""
harness_cooling_fan_control.py — equivalence of
rx8_cooling_fan_control @0x17DCC.

Reconstructed source: samples/src/rx8_cooling_fan_control.c
Verified lift   : c/cooling_fan_control.c (same address; verified bit-exact vs
                  the ROM via tools/sh2emu.py in the c/ tree).  Here the ACTUAL
                  ROM bytes @0x17DCC are executed, including the four leaf
                  calls (0x2440 complement_shift_u32, 0x2478 addSaturate8Bit,
                  0x3ED3C readValue_8bit, 0x3EE58 updateMemoryAtAddress_8bit)
                  which run natively in the emulator.

The function is a void leaf whose whole effect is on RAM, so equivalence is
judged on the RAM side-effects (compared byte-for-byte, ROM order):

  - RAM[0xFFFFA95C] fan-enable latch      (always rewritten with (u8)valid)
  - RAM[0xFFFFA93B] fan speed counter     (iff latch==0 && valid!=0)
  - RAM[0xFFFF8076..77] redundant u8 cell (iff the rising-edge path runs)
  - RAM[0xFFFFC6AC] redundancy error flag (set to 1 iff the rising-edge path
                                           read a corrupt cell — the 0x3F050
                                           side effect of readValue_8bit)

The coolant sensor float and the ROM eps literal are seeded as raw 32-bit
patterns on both sides; the oracle maps the ROM page @0x17EC0 (MAP_FIXED) and
writes the very bytes the emulator reads, so the C and the ROM see identical
constants (same pattern as oracle_purge_control_state_update.c).

EDGE vectors cover the sensor-validity boundaries (±eps, 0, denormals, NaN,
±inf), the fan-enable latch on/off and the valid/corrupt cell combinations;
N random pre-states follow (fixed seed, biased so the rising-edge path is hit
often).

Usage:  python3 harness_cooling_fan_control.py [N]   (default N = 20000)
"""
import os
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0x17DCC
N_DEFAULT = 20000
SEED = 0x17DCC

COOLANT_ADDR = 0xFFFFA73C   # f32 coolant temperature sensor
FAN_EN_ADDR  = 0xFFFFA95C   # u8 fan-enable latch
FAN_CNT_ADDR = 0xFFFFA93B   # u8 fan speed counter
CELL_ADDR    = 0xFFFF8076   # u16 redundant cell (value, ~value)
ERR_FLAG_ADDR = 0xFFFFC6AC  # u8 redundancy error flag
ROM_EPS_ADDR  = 0x00017EC0  # f32 deadband literal (1e-5)

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = '/tmp/rx8-recon-cooling_fan_control'


def fbits(x):
    """float -> raw 32-bit pattern (host-agnostic)."""
    return struct.unpack('>I', struct.pack('>f', x))[0]


def gen_edges():
    """Edge pre-states (coolant_bits, fan_en, fan_cnt, cell_hi, cell_lo, err)."""
    v = []
    # Sensor-validity boundaries: 0, ±eps, just outside/inside eps, denormals,
    # tiny/large magnitudes, ±inf and NaN (NaN must yield valid == 0).
    coolants = [0.0, 1e-5, -1e-5, 2e-5, -2e-5, 0.5e-5, -0.5e-5,
                1e-30, -1e-30, 1e-45, -1e-45, 1.0, -1.0, 1e6, -1e6,
                3.4e38, -3.4e38, float('inf'), float('-inf'), float('nan')]
    for c in coolants:
        cb = fbits(c)
        for en in (0x00, 0x01, 0xFF):
            for cnt in (0x00, 0x01, 0xFE, 0xFF):
                v.append((cb, en, cnt, 0x55, 0xAA, 0x00))
    # Valid + corrupt redundant cells around the rising-edge counter bump.
    cells = [(0x00, 0xFF), (0x01, 0xFE), (0xFF, 0x00), (0x55, 0xAA),
             (0x00, 0x00), (0x55, 0x55), (0x80, 0x7F), (0x80, 0x80)]
    for hi, lo in cells:
        for en in (0x00, 0x01):
            for err in (0x00, 0x01, 0xFF):
                v.append((fbits(2.0), en, 0x7F, hi, lo, err))
    return v


def gen_random(rng, n):
    """n random pre-states; biased toward latch==0 (rising edge) and valid
    cells so the counter/cell/error-flag side-effects are exercised heavily."""
    v = []
    for _ in range(n):
        cb = rng.getrandbits(32)          # any f32 bit pattern (NaN, inf, ...)
        p = rng.random()
        en = 0 if p < 0.5 else (1 if p < 0.75 else rng.randrange(256))
        cnt = rng.randrange(256)
        hi = rng.randrange(256)
        lo = (~hi) & 0xFF if rng.random() < 0.25 else rng.randrange(256)
        err = rng.randrange(256)
        v.append((cb, en, cnt, hi, lo, err))
    return v


def build_oracle(cc='cc'):
    """Compile the reconstructed source + its dedicated oracle into a binary."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_cooling_fan_control.c'),
           os.path.join(SAMPLES, 'src', 'rx8_cooling_fan_control.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(SEED)

    # The f32 deadband literal the ROM reads at 0x17EC0 (stock bin: 1e-5).
    eps_bits = struct.unpack('>I', cpu.rom[ROM_EPS_ADDR:ROM_EPS_ADDR + 4])[0]
    if eps_bits != 0x3727C5AC:
        raise RuntimeError('unexpected eps literal @0x%X: %08X'
                           % (ROM_EPS_ADDR, eps_bits))

    EDGE = gen_edges()
    vectors = EDGE + gen_random(rng, n)

    # (a) ROM behaviour via the emulator (whole call chain runs natively,
    # incl. the four leaf calls); read the four side-effected cells back.
    emu = []
    for cb, en, cnt, hi, lo, err in vectors:
        cpu.call(ADDR, ram={COOLANT_ADDR + 0: (cb >> 24) & 0xFF,
                            COOLANT_ADDR + 1: (cb >> 16) & 0xFF,
                            COOLANT_ADDR + 2: (cb >> 8) & 0xFF,
                            COOLANT_ADDR + 3: cb & 0xFF,
                            FAN_EN_ADDR: en & 0xFF,
                            FAN_CNT_ADDR: cnt & 0xFF,
                            CELL_ADDR: hi & 0xFF,
                            CELL_ADDR + 1: lo & 0xFF,
                            ERR_FLAG_ADDR: err & 0xFF})
        emu.append('%02X %02X %02X %02X %02X' % (
            cpu.ram.get(FAN_EN_ADDR, 0) & 0xFF,
            cpu.ram.get(FAN_CNT_ADDR, 0) & 0xFF,
            cpu.ram.get(CELL_ADDR, 0) & 0xFF,
            cpu.ram.get(CELL_ADDR + 1, 0) & 0xFF,
            cpu.ram.get(ERR_FLAG_ADDR, 0) & 0xFF))

    # (b) host C on the same pre-states (eps + coolant as raw f32 bits).
    lines = ['fan %08X %08X %02X %02X %02X %02X %02X'
             % (eps_bits, cb, en, cnt, hi, lo, err)
             for cb, en, cnt, hi, lo, err in vectors]
    host = run_oracle(oracle, lines)

    # (c) compare the side-effected RAM byte-for-byte.
    mismatches = []
    for i, ((cb, en, cnt, hi, lo, err), e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d coolant=%08X en=%02X cnt=%02X cell=(%02X,%02X) err=%02X '
                'ROM=[%s] C=[%s]' % (i, cb, en, cnt, hi, lo, err, e, h))
            if len(mismatches) >= 5:
                break

    report('cooling_fan_control', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
