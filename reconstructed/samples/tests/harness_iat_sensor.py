#!/usr/bin/env python3
"""
harness_iat_sensor.py — equivalence of rx8_iat_sensor @0x3C214.

Reconstructed source: samples/src/rx8_iat_sensor.c
Verified lift   : c/iat_sensor.c (iat_sensor_3C214 @ 0x3C214; the lift's
                  ADC / TwoDLookup / float description does NOT match the
                  ROM bytes — the sample header documents every difference
                  and this harness validates the byte-exact behaviour).

The ROM function is a plain `void` routine with NO ABI arguments and NO
callees (no jsr/bsr in the body): it reads 7 u8 cells (three compare-channel
inputs @0xFFFFC5EC/C5ED/C5EE, two status arm-threshold inputs @0xFFFFC5EF/
C5F0, a fault-active input @0xFFFFC5F7 and the reset-request byte
@0xFFFFD201), writes three 0/1 flags (@0xFFFFC5F4/C5F5/C5F6) and computes
two status bytes (@0xFFFFC5F8/C5F9) that CLEAR on any fault flag or reset
request, ARM on the per-status threshold / fault input, and otherwise HOLD
their pre-state.  The INPUT is therefore the 7-byte pre-state and the
OUTPUTS are the 5 RAM side-effects.

Procedure (Track-A pattern):
  1. build host oracle (system gcc; own binary, common.build_oracle untouched),
  2. edge vectors (threshold boundaries around cal 0xFA for every input,
     exhaustive flag/arm/reset/fault combinations, distinct status pre-states)
     + N random (seeded) pre-states,
  3. run the ROM bytes @0x3C214 in tools/sh2emu.py on the same vectors,
  4. run the host C on the same vectors,
  5. compare all five post-state cells byte-for-byte — 0 mismatches.

Usage:  python3 harness_iat_sensor.py [N]   (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROM_PATH, load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0x3C214
N_DEFAULT = 20000
SEED = 0x60E1D400

# ---- RAM cells the ROM function reads (inputs) / writes (outputs) -------
C5EC = 0xFFFFC5EC   # u8 compare-channel A input
C5ED = 0xFFFFC5ED   # u8 compare-channel B input
C5EE = 0xFFFFC5EE   # u8 compare-channel C input
C5EF = 0xFFFFC5EF   # u8 status-1 arm-threshold input
C5F0 = 0xFFFFC5F0   # u8 status-2 arm-threshold input
C5F7 = 0xFFFFC5F7   # u8 fault-active input
D201 = 0xFFFFD201   # u8 reset request (1 clears both status bytes)
C5F4 = 0xFFFFC5F4   # u8 output flag A
C5F5 = 0xFFFFC5F5   # u8 output flag B
C5F6 = 0xFFFFC5F6   # u8 output flag C
C5F8 = 0xFFFFC5F8   # u8 status byte 1
C5F9 = 0xFFFFC5F9   # u8 status byte 2

# ---- ROM calibration thresholds (bytes 0/1 of the table @0x7A9A8) -------
ROM_THR0 = 0x7A9A8
ROM_THR1 = 0x7A9A9

# Boundary values around the calibration threshold (0xFA in the stock bin).
BOUNDS = (0x00, 0xF9, 0xFA, 0xFB, 0xFF)
STATES = (0x00, 0x01, 0xAA, 0xFF)

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = '/tmp/rx8-recon-iat_sensor'


def build_oracle(cc='cc'):
    """Compile THIS sample + its own oracle into /tmp (same command as the
    verification line in the task; do NOT touch common.build_oracle)."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_iat_sensor.c'),
           os.path.join(SAMPLES, 'src', 'rx8_iat_sensor.c'),
           '-lm', '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def run_emu(cpu, vec):
    """Seed every input cell, run the ROM bytes @0x3C214 (no callees) and
    return the 5-tuple of post-state cells."""
    c5ec, c5ed, c5ee, c5ef, c5f0, c5f7, d201, st10, st20 = vec
    init = {C5EC: c5ec, C5ED: c5ed, C5EE: c5ee, C5EF: c5ef, C5F0: c5f0,
            C5F7: c5f7, D201: d201, C5F8: st10, C5F9: st20}
    cpu.call(ADDR, ram=init)
    return (cpu._rb(C5F4), cpu._rb(C5F5), cpu._rb(C5F6),
            cpu._rb(C5F8), cpu._rb(C5F9))


def gen_edges():
    """Edge pre-states (c5ec, c5ed, c5ee, c5ef, c5f0, c5f7, d201, st1_0, st2_0)
    targeting every branch and every 'hold last value' path."""
    v = []

    # (a) exhaustive compare-channel block: every combination of the three
    #     channel inputs around the 0xFA threshold -> all flag outputs, all
    #     clear paths, with the two status bytes at distinct pre-states.
    for c5ec in BOUNDS:
        for c5ed in BOUNDS:
            for c5ee in BOUNDS:
                for st in STATES:
                    v.append((c5ec, c5ed, c5ee, 0x00, 0x00, 0x00, 0x00, st, st))

    # (b) exhaustive arm-threshold block: c5ef/c5f0 around the threshold with
    #     all channel inputs 0 (no flags, no clear) -> the two set paths.
    for c5ef in BOUNDS:
        for c5f0 in BOUNDS:
            for st in STATES:
                v.append((0x00, 0x00, 0x00, c5ef, c5f0, 0x00, 0x00, st, st))

    # (c) reset request: 0/1/other around the flags and the status pre-states.
    for d201 in (0x00, 0x01, 0x02, 0xFF):
        for flags in ((0x00, 0x00, 0x00), (0xFA, 0x00, 0x00),
                      (0x00, 0xFA, 0x00), (0x00, 0x00, 0xFA)):
            for st in STATES:
                v.append((flags[0], flags[1], flags[2],
                          0x00, 0x00, 0x00, d201, st, st))

    # (d) fault-active input: 0/1/other with no channel flags -> the arm path.
    for c5f7 in (0x00, 0x01, 0x02, 0xFF):
        for st in STATES:
            v.append((0x00, 0x00, 0x00, 0x00, 0x00, c5f7, 0x00, st, st))

    # (e) single-cell sweeps: every input over its full byte range while the
    #     others sit at neutral values (channels at 0, thresholds at 0,
    #     reset/fault at 0, status pre-states kept distinct).
    for x in range(0x100):
        v.append((x, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xAA, 0x55))  # c5ec
        v.append((0x00, x, 0x00, 0x00, 0x00, 0x00, 0x00, 0xAA, 0x55))  # c5ed
        v.append((0x00, 0x00, x, 0x00, 0x00, 0x00, 0x00, 0xAA, 0x55))  # c5ee
        v.append((0x00, 0x00, 0x00, x, 0x00, 0x00, 0x00, 0xAA, 0x55))  # c5ef
        v.append((0x00, 0x00, 0x00, 0x00, x, 0x00, 0x00, 0xAA, 0x55))  # c5f0
        v.append((0x00, 0x00, 0x00, 0x00, 0x00, x, 0x00, 0xAA, 0x55))  # c5f7
        v.append((0x00, 0x00, 0x00, 0x00, 0x00, 0x00, x, 0xAA, 0x55))  # d201
    return v


def gen_random(rng, k):
    """k random pre-states over the full byte range of every input, biased
    toward the threshold neighbourhood and the hot clear/arm paths."""
    v = []
    for _ in range(k):
        pick = lambda: rng.choice((rng.getrandbits(8), rng.getrandbits(8),
                                   rng.choice(BOUNDS)))
        v.append((pick(), pick(), pick(), pick(), pick(),
                  rng.choice((0x00, 0x01, 0xFF, rng.getrandbits(8))),
                  rng.choice((0x00, 0x01, 0xFF, rng.getrandbits(8))),
                  rng.getrandbits(8), rng.getrandbits(8)))
    return v


def check_cal(cpu):
    """The stock-Rom calibration thresholds are fixed; refuse to run if they
    ever change so the ROM-page mapping stays meaningful."""
    if cpu.rom[ROM_THR0] != 0xFA or cpu.rom[ROM_THR1] != 0xFA:
        raise RuntimeError('unexpected IAT calibration bytes @0x%X/0x%X: %02X/%02X'
                           % (ROM_THR0, ROM_THR1,
                              cpu.rom[ROM_THR0], cpu.rom[ROM_THR1]))


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(SEED)
    check_cal(cpu)
    # The oracle maps the ROM calibration page straight from the file — point
    # it there.
    os.environ['RX8_ROM_PATH'] = ROM_PATH

    EDGE = gen_edges()
    vectors = EDGE + gen_random(rng, n)

    # (a) ROM behaviour via the emulator (side-effects of the exact bytes).
    emu = [run_emu(cpu, v) for v in vectors]

    # (b) host C on the same pre-states (cal thresholds from the mapped ROM).
    lines = ['iat %02X %02X %02X %02X %02X %02X %02X %02X %02X' % v
             for v in vectors]
    host = [tuple(int(x, 16) for x in out.split())
            for out in run_oracle(oracle, lines)]

    # (c) compare the post-state tuples byte-for-byte.
    mismatches = []
    for i, (v, e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d c5ec=%02X c5ed=%02X c5ee=%02X c5ef=%02X c5f0=%02X '
                'c5f7=%02X d201=%02X st10=%02X st20=%02X '
                'ROM=(%02X,%02X,%02X,%02X,%02X) C=(%02X,%02X,%02X,%02X,%02X)'
                % (i, v[0], v[1], v[2], v[3], v[4], v[5], v[6], v[7], v[8],
                   e[0], e[1], e[2], e[3], e[4],
                   h[0], h[1], h[2], h[3], h[4]))
            if len(mismatches) >= 5:
                break

    report('iat_sensor', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
