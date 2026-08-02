#!/usr/bin/env python3
"""
harness_omp_stepper_waveform_driver.py — equivalence of
rx8_omp_stepper_waveform_driver @0x18552.

Reconstructed source: samples/src/rx8_omp_stepper_waveform_driver.c
Verified lift   : c/omp_stepper_waveform_driver.c (same address, verified by
                  c/tests/test_omp_stepper_waveform_driver.py over 60000 random
                  inputs; the ROM bytes are executed for real here via
                  tools/sh2emu.py, including the jsr leaves 0x42B0 / 0x2054 /
                  0x2064 / 0x4BBC).

The ROM function is a void mode-dispatch driver with NO ABI return value: its
whole effect is on RAM, so equivalence is judged on RAM side-effects, not a
return value:

  - emulator side: seed the six input bytes (step A97C, rotor-sync source
    A97D, rotor position A974, latched mode A98A, gates A969/A96A) plus
    distinguishable pre-states for the conditionally-written waveform byte
    A97F and the always-overwritten mode store A98D and the 16-bit stepper
    port F746 in the sparse ram overlay, call the ROM entry @0x18552 with the
    mode in r4 (sr=0xF0, matching the RTOS; the ROM's setSR_PARAM/setSR pairs
    leave SR exactly at its entry value) and read the six cells back;
  - host side: the dedicated oracle mmap()s the pages backing the same cells,
    seeds the same bytes, runs the reconstructed C (whose only external leaf,
    rx8_set_register_reg_bit_val @0x4BBC, is modelled in the oracle) and
    prints the same six cells.

EDGE vectors cover the full mode dispatch (0,1,2,3,4,6,5,7,255) x step x A97D
x A974 (straddling the <60 / >0 boundaries) x latched-mode (around 4) x gate
state space plus distinguishable port/pre-state combinations; N random
pre-states follow (fixed seed 0x60E1D400, matching the sibling OMP harness).

Usage:  python3 harness_omp_stepper_waveform_driver.py [N]  (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0x18552
N_DEFAULT = 20000
SEED = 0x60E1D400

STEP = 0xFFFFA97C        # u8 step register (advance source)
A97D = 0xFFFFA97D        # u8 rotor-sync step source
A974 = 0xFFFFA974        # u8 rotor position counter
A98A = 0xFFFFA98A        # u8 previously latched mode
A98D = 0xFFFFA98D        # u8 mode store (written at entry)
A97F = 0xFFFFA97F        # u8 waveform byte (conditional write)
A969 = 0xFFFFA969        # u8 gate flag A
A96A = 0xFFFFA96A        # u8 gate flag B
F746 = 0xFFFFF746        # u16 stepper drive port (read-modify-write)

# vector layout: (mode, step0, a97d0, a9740, a98a0, a9690, a96a0, a97f0,
#                 a98d0, f7460)
#         line  = 'step <mode> <10 hex tokens>'
#         output= 6 hex tokens: A97C A97D A97F A98A A98D F746
CELLS = (STEP, A97D, A97F, A98A, A98D, F746)

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = '/tmp/rx8-recon-omp_stepper_waveform_driver'


def build_oracle(cc='cc'):
    """Compile the reconstructed source + its dedicated oracle into a binary."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_omp_stepper_waveform_driver.c'),
           os.path.join(SAMPLES, 'src', 'rx8_omp_stepper_waveform_driver.c'),
           '-lm', '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def gen_edges():
    """Edge pre-states (mode, step0, a97d0, a9740, a98a0, a9690, a96a0,
    a97f0, a98d0, f7460) targeting every dispatch branch."""
    v = []
    steps = (0x00, 0x01, 0x02, 0x06, 0x07, 0x08, 0x09, 0xFE, 0xFF)
    a974s = (0x00, 0x01, 0x02, 0x3B, 0x3C, 0x3D, 0x3E, 0xFE, 0xFF)  # 59/60/61
    a98as = (0x00, 0x01, 0x03, 0x04, 0x05, 0xFF)
    # (a) mode dispatch x step x a974 x a98a (a97d fixed, gates 0/1), with
    #     distinguishable stale pre-states for every writable cell + two port
    #     extremes.
    for mode in (0, 1, 2, 3, 4, 6, 5, 7, 255):
        for step0 in steps:
            for a9740 in a974s:
                for a98a0 in a98as:
                    v.append((mode, step0, 0x05, a9740, a98a0,
                              0, 0, 0x55, 0xAA, 0xFFFF))
                    v.append((mode, step0, 0x05, a9740, a98a0,
                              1, 1, 0x00, 0x00, 0x0000))
    # (b) rotor-sync source A97D sweep (mode 1 step==8 path, modes 2/3 source
    #     paths, mode 4 even/8 paths).
    for mode in (1, 2, 3, 4):
        for a97d0 in (0x00, 0x01, 0x07, 0x08, 0xFE, 0xFF):
            for step0 in (0x00, 0x07, 0x08, 0xFF):
                v.append((mode, step0, a97d0, 0x20, 0x02,
                          0, 0, 0x55, 0xAA, 0x00FF))
    # (c) gate-flag combos (mode 1's A969 || A96A == 1 arm).
    for a9690 in (0, 1, 0xFF):
        for a96a0 in (0, 1, 0xFF):
            v.append((1, 0x01, 0x05, 0x01, 0x00,
                      a9690, a96a0, 0x55, 0xAA, 0xFFFF))
    # (d) port RMW sweep over every step pattern (mode 2 never faults the
    #     waveform so the 4-phase drive is exercised against every port).
    for step0 in steps:
        for f7460 in (0x0000, 0x0001, 0x000F, 0x00F0, 0x5555, 0xAAAA, 0xFFFF):
            v.append((2, step0, 0x05, 0x30, 0x00, 0, 0, 0x55, 0xAA, f7460))
    # (e) pre-state distinguishability for the conditionally/never-written
    #     cells A97F / A98D across the whole mode dispatch.
    for mode in (0, 1, 2, 3, 4, 6, 5, 8, 255):
        for a97f0 in (0x00, 0x55, 0xAA, 0xFF):
            for a98d0 in (0x00, 0x55, 0xAA, 0xFF):
                v.append((mode, 0x04, 0x02, 0x10, 0x02,
                          0, 0, a97f0, a98d0, 0x0000))
    return v


def gen_random(rng, n):
    """n random pre-states over the full byte range of every input (u16 port)."""
    return [tuple(rng.randrange(256) for _ in range(9)) + (rng.getrandbits(16),)
            for _ in range(n)]


def run_emu(cpu, vec):
    """Seed every input cell, run the ROM bytes @0x18552 (callees included)
    with the mode in r4 and return the 6-tuple of post-state cells."""
    mode, step0, a97d0, a9740, a98a0, a9690, a96a0, a97f0, a98d0, f7460 = vec
    cpu.call(ADDR, r4=mode & 0xFF, sr=0xF0,
             ram={STEP: step0 & 0xFF, A97D: a97d0 & 0xFF, A974: a9740 & 0xFF,
                  A98A: a98a0 & 0xFF, A969: a9690 & 0xFF, A96A: a96a0 & 0xFF,
                  A97F: a97f0 & 0xFF, A98D: a98d0 & 0xFF,
                  F746: (f7460 >> 8) & 0xFF, F746 + 1: f7460 & 0xFF})
    return (cpu.rd(STEP, 1), cpu.rd(A97D, 1), cpu.rd(A97F, 1),
            cpu.rd(A98A, 1), cpu.rd(A98D, 1), cpu.rd(F746, 2))


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(SEED)

    EDGE = gen_edges()
    vectors = EDGE + gen_random(rng, n)

    # (a) ROM behaviour via the emulator (RAM side-effects).
    emu = [run_emu(cpu, v) for v in vectors]

    # (b) host-C on the same pre-states.
    lines = ['step %02X %02X %02X %02X %02X %02X %02X %02X %02X %04X'
             % v for v in vectors]
    host = [tuple(int(x, 16) for x in out.split())
            for out in run_oracle(oracle, lines)]

    # (c) compare the post-state 6-tuples byte-for-byte (A97C/A97D/A97F/A98A/
    #     A98D u8, F746 u16).
    mismatches = []
    for i, (v, e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d mode=%02X pre=(%02X,%02X,%02X,%02X,%02X,%02X,'
                '%02X,%02X,%04X) '
                'ROM=(%02X,%02X,%02X,%02X,%02X,%04X) '
                'C=(%02X,%02X,%02X,%02X,%02X,%04X)'
                % (i, v[0], v[1], v[2], v[3], v[4], v[5], v[6], v[7], v[8],
                   v[9], e[0], e[1], e[2], e[3], e[4], e[5],
                   h[0], h[1], h[2], h[3], h[4], h[5]))
            if len(mismatches) >= 5:
                break

    report('omp_stepper_waveform_driver', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
