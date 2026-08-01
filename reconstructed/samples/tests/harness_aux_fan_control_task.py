#!/usr/bin/env python3
"""
harness_aux_fan_control_task.py — equivalence of rx8_aux_fan_control_task
@0x1AED2.

Reconstructed source: samples/src/rx8_aux_fan_control_task.c
Verified lift   : c/aux_fan_control_task.c (same address; listed in
                  c/verified_addrs.txt, verified there via
                  c/tests/test_aux_fan_control_task.py).  The ROM bytes at
                  0x1AED2 are executed for real here via tools/sh2emu.py —
                  the emulator follows the whole call chain (0x32F42 boost
                  filter wrapper, 0x2DD6E delta control, 0x2DD88 error
                  filter wrapper, 0x344FE float swap, 0x3488C hysteresis,
                  0xC2E6 flag transition, plus getSR/setSR and the 0x23B0
                  filter leaf).

The task is a void OS task with NO ABI return value: its whole effect is on
RAM.  The equivalence check compares the FULL RAM side-effect set — every
cell the task can write, bit-exactly:

  - 10 f32 cells:  C008 (boost in), BD3C (scaled delta), BD40 (delta prev),
    BD38 (error prev), C0D8/C0DC/C0E0/C108/C104/C10C (the float swap),
  - 4 u8 cells:    A384/A385/A324 (update latch) and A38C (fan flag).

The 6 f32 calibration constants (0.7 @0x78CFC, 0.5 @0x76B30, 1e-5 @0x32F64,
15.625 @0x2DDB0, 7000 @0x7A18C, 500 @0x7A190) are read from the ROM on the
emulator side and shipped inline to the oracle, which writes them into mapped
ROM pages (same pattern as harness_purge_control_state_update.py), so both
sides read byte-identical constants.

EDGE vectors sweep the hysteresis boundaries around 7000/6500 with the flag
pre-state on both sides of the transition test (0/1), NaN/inf/denormal and
sign-flipped pressures (the ROM's fcmp/gt makes a NaN pressure trip the flag
ON — see the sample header for the discrepancy this corrects vs the lift),
plus the 0x23B0 filter bootstrap (non-finite history).  N random vectors
follow (fixed seed): the four cells that feed arithmetic (c008, bc1c, bd40,
bd38) get realistic firmware magnitudes, while the six pure-copy/comparison
cells (b5b8, c104, c108, c10c, c12c, adc0) get raw random bit patterns to
exercise NaN, infinities, denormals and sign flips there.

Usage:  python3 harness_aux_fan_control_task.py [N]   (default N = 20000)
"""
import os
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402
from sh2emu import bits2f, f2bits  # noqa: E402

ADDR = 0x1AED2
SEED = 0x1AED2                  # fixed seed: the ROM address
N_DEFAULT = 20000

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = '/tmp/rx8-recon-aux_fan_control_task'

# --- RAM cells (same names/addresses as the sample and the lift) -----------
C008 = 0xFFFFC008; BC1C = 0xFFFFBC1C; BD40 = 0xFFFFBD40; BD3C = 0xFFFFBD3C
BD38 = 0xFFFFBD38; B5B8 = 0xFFFFB5B8
C104 = 0xFFFFC104; C108 = 0xFFFFC108; C10C = 0xFFFFC10C
C0D8 = 0xFFFFC0D8; C0DC = 0xFFFFC0DC; C0E0 = 0xFFFFC0E0
C12C = 0xFFFFC12C; ADC0 = 0xFFFFADC0
A38C = 0xFFFFA38C; A384 = 0xFFFFA384; A385 = 0xFFFFA385; A324 = 0xFFFFA324

# float inputs the harness seeds (ROM write order of the outputs first).
FLOAT_IN = [C008, BC1C, BD40, BD38, B5B8, C104, C108, C10C, C12C, ADC0]
FLOAT_OUT = [C008, BD3C, BD40, BD38, C0D8, C0DC, C0E0, C108, C104, C10C]
BYTE_OUT = [A384, A385, A324, A38C]

# ROM calibration-constant addresses the task reads (f32).
ROM_FLOATS = [(0x00078CFC, 'ff_filter', 0.7), (0x00076B30, 'ff_error', 0.5),
              (0x00032F64, 'eps', 1e-5), (0x0002DDB0, 'delta_scale', 15.625),
              (0x0007A18C, 'p_on', 7000.0), (0x0007A190, 'p_hy', 500.0)]


def build_oracle():
    """Compile the reconstructed source + its dedicated oracle.  The sample is
    self-contained (the 0x23B0 filter leaf is inlined), so no extra sources."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = ['cc', '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_aux_fan_control_task.c'),
           os.path.join(SAMPLES, 'src', 'rx8_aux_fan_control_task.c'),
           '-lm', '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def fbits(v):
    """Bit pattern (u32) of a Python float, as the SH-2 stores it (f2bits)."""
    return f2bits(v)


# --- interesting single-precision bit patterns -----------------------------
_PINF = 0x7F800000; _NINF = 0xFF800000
_QNAN = 0x7FC00000; _SNAN = 0x7F800001
_ZERO = 0x00000000; _NZERO = 0x80000000
_ONE = 0x3F800000; _NEGONE = 0xBF800000
_MAXF = 0x7F7FFFFF
_DEN = 0x00000001

# Hysteresis boundary pressures: p_on=7000 (0x45DAC000), p_on-p_hy=6500.
P_ON = 7000.0
P_OFF = 6500.0
PRESSURE_EDGES = [
    fbits(P_ON), fbits(P_ON + 1.0), fbits(P_ON - 1.0), fbits(P_ON - 0.01),
    fbits(P_OFF), fbits(P_OFF + 0.01), fbits(P_OFF - 0.01),
    fbits(P_OFF - 1.0), fbits(P_OFF + 1.0),
    fbits(0.0), fbits(-1.0), fbits(-0.0),
    fbits(1e6), fbits(-1e6), fbits(1e-30),
    _PINF, _NINF, _QNAN, _SNAN, _DEN, _MAXF,
]


def gen_edges():
    """Edge vectors: sweep the hysteresis + filter bootstrap + sign flips."""
    v = []
    # (1) Hysteresis: every interesting pressure x flag pre-state {0,1},
    #     all other cells neutral (0.0), so the flag cell is the only
    #     non-trivial decision.  (NaN pressure must trip the flag ON — the
    #     ROM's fcmp/gt is false for NaN, so !(7000 > p) is true.)
    for p in PRESSURE_EDGES:
        for flag in (0x00, 0x01):
            # p goes to the pressure cell (b5b8, index 4); everything else 0.
            v.append(([_ZERO] * 4 + [p] + [_ZERO] * 5, flag))
    # (2) Filter bootstrap: non-finite history (BC1C) on the boost filter
    #     and non-finite error prev (BD38) on the error filter.
    for hist in (_PINF, _NINF, _QNAN, _SNAN, _ZERO, _ONE):
        for sig in (_ZERO, _ONE, _NEGONE, _PINF, _QNAN, _DEN):
            # c008=sig, bc1c=hist, bd38=hist; pressure keeps the flag ON.
            v.append(([sig, hist, _ZERO, hist, fbits(7500.0)] +
                      [_ZERO] * 5, 0x00))
    # (3) Delta control extremes: sign flips, denormals, and inf/NaN on both
    #     operands (c008 and bd40).  Finite magnitudes are capped at 1e15 so
    #     the emulator's single-precision rounder (ts) never sees a finite
    #     double intermediate outside the f32 range (its known limitation).
    _BIG = fbits(1e15); _NBIG = fbits(-1e15)
    for a in (_BIG, _NBIG, _DEN, _ZERO, _NZERO, _PINF, _NINF, _QNAN):
        for b in (_BIG, _NBIG, _DEN, _ZERO, _PINF, _NINF, _QNAN):
            v.append(([a, _ZERO, b, _ZERO, fbits(6500.0)] +
                      [_ZERO] * 5, 0x00))
    # (4) The float swap: distinct values on the 6 source cells.
    v.append(([fbits(1.0), fbits(2.0), fbits(3.0), fbits(4.0),
               fbits(5.0), fbits(6.0), fbits(7.0), fbits(8.0),
               fbits(9.0), fbits(10.0)], 0x00))
    v.append(([_QNAN, _ONE, _PINF, _NZERO, fbits(-0.5),
               _DEN, _MAXF, _NEGONE, _SNAN, _NINF], 0x01))
    return v


def gen_random(rng, n):
    """n random vectors.  The four cells that feed arithmetic (c008, bc1c,
    bd40, bd38) get realistic firmware magnitudes — the emulator's ts() raises
    OverflowError when a finite double intermediate exceeds the f32 range, so
    raw 32-bit patterns are only used on the pure-copy / comparison cells
    (b5b8, c104, c108, c10c, c12c, adc0), which never feed a multiply."""

    def rflt():
        return fbits(rng.choice([rng.uniform(-1e4, 1e4),
                                 rng.uniform(-2, 2),
                                 rng.uniform(0, 8000),
                                 rng.uniform(-8000, 0)]))

    def raw():
        return rng.getrandbits(32)          # NaN/inf/denormal/sign-flip space

    ARITH = [C008, BC1C, BD40, BD38]
    COPY = [B5B8, C104, C108, C10C, C12C, ADC0]
    return [([rflt() if a in ARITH else raw() for a in FLOAT_IN],
             rng.randrange(256)) for _ in range(n)]


def seed_ram(v):
    """Build the emulator ram overlay (byte dict) from a (floats, flag) pair."""
    fl, flag = v
    ram = {}
    for addr, bits in zip(FLOAT_IN, fl):
        for i, b in enumerate(struct.pack('>I', bits & 0xFFFFFFFF)):
            ram[addr + i] = b
    ram[A38C] = flag & 0xFF
    return ram


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(SEED)

    # Sanity-check the ROM calibration constants (both sides must read these).
    cal = []
    for addr, name, val in ROM_FLOATS:
        if cpu.rom[addr:addr + 4] != struct.pack('>f', val):
            raise RuntimeError('unexpected ROM constant %s @0x%X: %r'
                               % (name, addr,
                                  struct.unpack('>f', cpu.rom[addr:addr + 4])))
        cal.append(f2bits(val))

    EDGE = gen_edges()
    vectors = EDGE + gen_random(rng, n)

    # (a) ROM behaviour via the emulator — full RAM side-effects.
    emu = []
    for v in vectors:
        cpu.call(ADDR, ram=seed_ram(v))
        emu.append(tuple([cpu.rd(a, 4) for a in FLOAT_OUT] +
                         [cpu.rd(a, 1) for a in BYTE_OUT]))

    # (b) host-C on the same pre-states (calibration bits shipped inline).
    cals = ' '.join('%08X' % c for c in cal)
    lines = ['aux %s %s %02X' % (cals,
                                 ' '.join('%08X' % b for b in v[0]), v[1])
             for v in vectors]
    host_raw = run_oracle(oracle, lines)
    host = [tuple(int(t, 16) for t in l.split()) for l in host_raw]

    # (c) compare every side-effect cell bit-exactly.
    mismatches = []
    for i, (v, e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            fl, flag = v
            mismatches.append(
                'vec#%d flag_pre=%02X in=(%s) ROM=%s C=%s'
                % (i, flag,
                   ' '.join('%08X' % b for b in fl),
                   ' '.join('%08X' % t for t in e),
                   ' '.join('%08X' % t for t in h)))
            if len(mismatches) >= 5:
                break

    report('aux_fan_control_task', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
