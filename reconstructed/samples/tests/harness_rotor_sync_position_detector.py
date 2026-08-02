#!/usr/bin/env python3
"""
harness_rotor_sync_position_detector.py — equivalence of
rx8_rotor_sync_position_detector @0x189EE.

Reconstructed source: samples/src/rx8_rotor_sync_position_detector.c
Verified lift   : c/rotor_sync_position_detector.c (same address 0x189EE,
                  522 bytes; the ROM bytes are executed for real here via
                  tools/sh2emu.py, including the bsr'd callee 0x18552 wave
                  driver and its RMW leaf 0x4BBC).

The ROM function has NO ABI return value: its whole effect is on RAM, so
equivalence is judged on RAM side-effects:

  - emulator side: seed the position pair (A8F1/A974), the state byte A98B,
    the step register A97C, the wave callee's inputs (A97D/A98A/A969/A96A/
    F746 port) plus distinguishable pre-states for every writable cell
    (A97B/A97F/A98D) and eight sentinels, drive the ROM entry @0x189EE with
    r4 = mode (sr=0xF0), then read the seven bytes + the F746 word + the
    sentinels back;
  - host side: the dedicated oracle mmap()s the pages backing the same cells,
    seeds the same bytes, runs the reconstructed C (whose omp_stepper_
    waveform_driver is modelled in the oracle from the verified callee lift
    c/omp_stepper_waveform_driver.c) and prints the same post-state.

The 12-cell + 8-sentinel compare set pins the write count and width: the
state machine's stores are all `mov.b`, the wave's port drive is the only
16-bit RMW (F746), and A97D can be written either by the state-2 copy or the
wave's mode-4 path.

EDGE vectors cover: the stage-A compare space (mode 0) around every branch
boundary of A8F1 vs A974 in both phases, every stage-B state block with the
relation/phase space (including the state-4 signed 32-bit (A8F1-2) >= A974
boundary at A8F1 = 128..200 — the lift's (int8_t) cast was wrong there), the
default states, and the tail dispatch with a step/phase/A97D/A98A/gate/port
sweep driving every wave mode the function can call (wave 1/2/3/4) plus the
no-wave state-2 copy and state-3/store-only paths.  N random pre-states
follow (fixed seed = the ROM address).

Usage:  python3 harness_rotor_sync_position_detector.py [N]  (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0x189EE
N_DEFAULT = 20000
SEED = 0x60E1D400

# ---- cell addresses (see rx8_rotor_sync_position_detector.c) ----
A8F1 = 0xFFFFA8F1   # u8 old rotor position (read)
A974 = 0xFFFFA974   # u8 new rotor position (read; also wave callee input)
A98B = 0xFFFFA98B   # u8 state byte (read/written)
A97C = 0xFFFFA97C   # u8 step register (odd/even source; wave callee r/w)
A97D = 0xFFFFA97D   # u8 rotor-sync step source (wave callee; state-2 copy)
A97B = 0xFFFFA97B   # u8 waveform byte (written)
A98A = 0xFFFFA98A   # u8 latched mode (wave callee)
A969 = 0xFFFFA969   # u8 gate flag A (wave callee)
A96A = 0xFFFFA96A   # u8 gate flag B (wave callee)
A97F = 0xFFFFA97F   # u8 waveform byte (wave callee)
A98D = 0xFFFFA98D   # u8 mode store (wave callee)
F746 = 0xFFFFF746   # u16 stepper port (wave callee RMW)

# sentinels pinning the store count and width
S1, S2, S3, S4 = 0xFFFFA97A, 0xFFFFA97E, 0xFFFFA980, 0xFFFFA989
S5, S6, S7, S8 = 0xFFFFA98C, 0xFFFFA98E, 0xFFFFF745, 0xFFFFF748
SENT = (S1, S2, S3, S4, S5, S6, S7, S8)

# vector layout: (mode, a8f1, a974, a98b, a97c, a97d, a97b, a98a, a969, a96a,
#                 a97f, a98d, f746, s1..s8)
# output (16 tokens): a98b a97b a97d a97c a97f a98a a98d f746 s1..s8
SENT_PRE = (0xA5,) * 8

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = '/tmp/rx8-recon-rotor_sync_position_detector'


def build_oracle(cc='cc'):
    """Compile the reconstructed source + its dedicated oracle into a binary."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests',
                        'oracle_rotor_sync_position_detector.c'),
           os.path.join(SAMPLES, 'src',
                        'rx8_rotor_sync_position_detector.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def seed(init, addr, n, val):
    """Byte-exact big-endian store of a width-`n` value in the ram overlay."""
    for i in range(n):
        init[addr + i] = (val >> (8 * (n - 1 - i))) & 0xFF


def run_emu(cpu, vec):
    """Seed every input cell, run the ROM bytes @0x189EE (the wave callee
    0x18552 and its 0x4BBC RMW leaf included) and return the post-state."""
    mode, a8f1, a974, a98b, a97c, a97d, a97b, a98a, a969, a96a, a97f, a98d, \
        f746, s = vec[0], vec[1], vec[2], vec[3], vec[4], vec[5], vec[6], \
        vec[7], vec[8], vec[9], vec[10], vec[11], vec[12], vec[13:]
    init = {}
    for addr, val in ((A8F1, a8f1), (A974, a974), (A98B, a98b), (A97C, a97c),
                      (A97D, a97d), (A97B, a97b), (A98A, a98a), (A969, a969),
                      (A96A, a96a), (A97F, a97f), (A98D, a98d)):
        init[addr] = val & 0xFF
    seed(init, F746, 2, f746 & 0xFFFF)
    for addr, val in zip(SENT, s):
        init[addr] = val & 0xFF
    cpu.call(ADDR, r4=mode & 0xFF, ram=init)
    return (cpu.rd(A98B, 1), cpu.rd(A97B, 1), cpu.rd(A97D, 1),
            cpu.rd(A97C, 1), cpu.rd(A97F, 1), cpu.rd(A98A, 1),
            cpu.rd(A98D, 1), cpu.rd(F746, 2),
            cpu.rd(S1, 1), cpu.rd(S2, 1), cpu.rd(S3, 1), cpu.rd(S4, 1),
            cpu.rd(S5, 1), cpu.rd(S6, 1), cpu.rd(S7, 1), cpu.rd(S8, 1))


def gen_edges():
    """Edge pre-states (mode, a8f1, a974, a98b, a97c, a97d, a97b, a98a, a969,
    a96a, a97f, a98d, f746, s1..s8) targeting every branch."""
    v = []
    S = SENT_PRE

    # ---- stage A (mode 0): full A8F1 vs A974 boundary cross, both phases.
    # Each vector runs stage A -> stage B -> tail, so every final state and
    # its wave mode is exercised here too.
    for a8f1 in (0, 1, 2, 4, 5, 59, 60, 128, 254, 255):
        for a974 in (0, 1, 2, 4, 5, 59, 60, 128, 254, 255):
            for step in (0x00, 0x01):          # even / odd phase
                v.append((0, a8f1, a974, 0x00, step, 0x00, 0x00, 0x00, 0, 0,
                          0x11, 0x22, 0xAAAA, *S))

    # ---- stage B, pre-loaded states (mode != 0 skips stage A) ----
    def sb(state, a8f1, a974, step):
        v.append((1, a8f1, a974, state, step, 0x00, 0x00, 0x00, 0, 0,
                  0x11, 0x22, 0xAAAA, *S))

    for step in (0x00, 0x01):                  # state 0
        sb(0, 5, 5, step)                      # eq -> 2+flag (even only)
        sb(0, 5, 4, step)                      # gt -> nothing
        sb(0, 4, 5, step)                      # lt -> 3 (even only)
    for step in (0x00, 0x01):                  # state 1
        sb(1, 5, 4, step)                      # gt: !odd -> 3, odd -> nothing
        sb(1, 5, 0, step)                      # gt: odd && a974==0 -> 3
        sb(1, 5, 5, step)                      # eq: a974>=5 -> 4 (!odd), nothing
        sb(1, 2, 2, step)                      # eq: a974<5 -> 2+flag (a974!=0)
        sb(1, 0, 0, step)                      # eq: a974==0 -> 2+flag (both)
        sb(1, 4, 5, step)                      # lt -> nothing
    for step in (0x00, 0x01):                  # state 2
        sb(2, 5, 4, step)                      # gt -> 0
        sb(2, 5, 5, step)                      # eq -> nothing (flag stays 0)
        sb(2, 4, 5, step)                      # lt -> 1
    for step in (0x00, 0x01):                  # state 3
        sb(3, 5, 4, step)                      # gt -> 0
        sb(3, 4, 5, step)                      # lt -> 1
        sb(3, 5, 5, step)                      # eq -> 2+flag
    sb(4, 200, 150, 0x00)                      # state 4 (!odd): (200-2)=198>=150
    sb(4, 130, 0, 0x00)                        #          128 >= 0 -> 3
    sb(4, 129, 0, 0x00)                        #          127 >= 0 -> 3
    sb(4, 255, 255, 0x00)                      #          253 >= 255 false
    sb(4, 2, 0, 0x00)                          #          0 >= 0 -> 3
    sb(4, 1, 0, 0x00)                          #          -1 >= 0 false, A8F1<5
    sb(4, 0, 0, 0x00)                          #          -2 >= 0 false, A8F1<5
    sb(4, 4, 4, 0x00)                          #          2 >= 4 false, A8F1<5
    sb(4, 6, 0, 0x00)                          #          4 >= 0 -> 3 (A8F1>=5)
    sb(4, 200, 150, 0x01)                      # odd -> nothing
    sb(5, 5, 5, 0x00)                          # default states: no action
    sb(0xFF, 200, 150, 0x01)

    # ---- tail dispatch / wave-input sweep ---------------------------------
    # final state 0 -> wave(2): mode 0, a8f1 > a974.
    for step in (0x00, 0x01, 0x06, 0x07, 0x08):
        for a974 in (0x00, 0x01, 0x3B, 0x3C, 0xFF):
            for a98a in (0x00, 0x04, 0xFF):
                for f746 in (0x0000, 0x000F, 0xFFFF):
                    v.append((0, 0xFF, a974, 0x00, step, 0x08, 0x00, a98a, 0,
                              0, 0x11, 0x22, f746, *S))

    # final state 1, a974 < 5 -> wave(1): mode 0, a8f1 = 0 < a974.
    for step in (0x00, 0x01, 0x02, 0x07, 0x08):
        for a974 in (0x01, 0x02, 0x04):
            for a97d in (0x00, 0x07, 0xFF):
                for a98a in (0x00, 0x04):
                    for a969 in (0x00, 0x01):
                        for a96a in (0x00, 0x01):
                            v.append((0, 0x00, a974, 0x00, step, a97d, 0x00,
                                      a98a, a969, a96a, 0x11, 0x22, 0x0000, *S))

    # final state 1, a974 >= 5 -> wave(3): mode 0, a8f1 = 0 < a974.
    for step in (0x00, 0x01, 0x02, 0x07, 0x08):
        for a974 in (0x05, 0x3B, 0xFF):
            for a97d in (0x00, 0x07, 0xFF):
                for a98a in (0x00, 0x04, 0xFF):
                    for f746 in (0x0000, 0x000F, 0xFFFF):
                        v.append((0, 0x00, a974, 0x00, step, a97d, 0x00, a98a,
                                  0, 0, 0x11, 0x22, f746, *S))

    # final state 2, no flag (flag==0) -> wave(4): mode 1, state 2, A8F1==A974.
    for step in (0x00, 0x01, 0x02, 0x07, 0x08):
        for a974 in (0x00, 0x01, 0x05, 0xFF):
            for a97d in (0x00, 0x01, 0x07, 0xFF):
                for a98a in (0x00, 0x04):
                    for f746 in (0x0000, 0xFFFF):
                        v.append((1, a974, a974, 0x02, step, a97d, 0x00, a98a,
                                  0, 0, 0x11, 0x22, f746, *S))

    # final state 2, flag && A974 != 0 -> wave(4): mode 0, A8F1 == A974.
    for a974 in (0x01, 0x05, 0xFF):
        for step in (0x00, 0x01, 0x07, 0x08):
            v.append((0, a974, a974, 0x00, step, 0x00, 0x00, 0x00, 0, 0,
                      0x11, 0x22, 0x0000, *S))

    # final state 2, flag && A974 == 0 -> A97D = A97C, A97B = 4 (no wave).
    for step in (0x00, 0x01, 0x07, 0x08, 0xFF):
        v.append((0, 0, 0, 0x00, step, 0x00, 0x00, 0x00, 0, 0, 0x11, 0x22,
                  0x0000, *S))

    # final state 3 -> A97B = 0x30 (no wave): mode 1, state 0, A8F1 < A974.
    for a974 in (0x00, 0x01, 0x05, 0xFF):
        for a97b in (0x00, 0x4D, 0xFF):
            v.append((1, 0x00, a974, 0x00, 0x00, 0x00, a97b, 0x00, 0, 0,
                      0x11, 0x22, 0x0000, *S))
    v.append((1, 0x05, 0x04, 0x01, 0x00, 0x00, 0x00, 0x00, 0, 0, 0x11, 0x22,
              0x0000, *S))                    # case1 gt !odd -> 3
    v.append((1, 0xFF, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0, 0, 0x11, 0x22,
              0x0000, *S))                    # case1 gt odd a974==0 -> 3

    # final state 4 (always a974 >= 5) -> wave(3): mode 1, state 1, A8F1==A974.
    for step in (0x00, 0x02, 0x06, 0x08):
        for a974 in (0x05, 0x3B, 0xFF):
            for a97d in (0x00, 0x07, 0xFF):
                for a98a in (0x00, 0x04, 0xFF):
                    for f746 in (0x0000, 0x000F, 0xFFFF):
                        v.append((1, a974, a974, 0x01, step, a97d, 0x00, a98a,
                                  0, 0, 0x11, 0x22, f746, *S))
    return v


def gen_random(rng, k):
    """k random pre-states over the full byte/word range of every input, with
    the phase/step/latched-mode/gates biased toward the hot paths."""
    v = []
    for _ in range(k):
        mode = rng.choice((0, 0, rng.randrange(256)))
        a8f1 = rng.randrange(256)
        a974 = rng.randrange(256)
        a98b = rng.choice((0, 1, 2, 3, 4, rng.randrange(256)))
        a97c = rng.choice((0, 1, 2, 3, 4, 5, 6, 7, 8, rng.randrange(256)))
        a97d = rng.choice((0, 1, 7, 8, rng.randrange(256)))
        a98a = rng.choice((0, 4, rng.randrange(256)))
        a969 = rng.choice((0, 1, rng.randrange(256)))
        a96a = rng.choice((0, 1, rng.randrange(256)))
        v.append((mode, a8f1, a974, a98b, a97c, a97d,
                  rng.randrange(256),             # a97b pre-state
                  a98a, a969, a96a,
                  rng.randrange(256),             # a97f pre-state
                  rng.randrange(256),             # a98d pre-state
                  rng.randrange(65536),           # f746 port
                  *tuple(rng.randrange(256) for _ in range(8))))
    return v


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(SEED)

    EDGE = gen_edges()
    vectors = EDGE + gen_random(rng, n)

    # (a) ROM behaviour via the emulator (RAM side-effects; the wave callee
    #     0x18552 and the 0x4BBC RMW leaf run as real ROM bytes).
    emu = [run_emu(cpu, v) for v in vectors]

    # (b) host-C on the same pre-states.
    lines = ['rsync %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X '
             '%02X %02X %04X %02X %02X %02X %02X %02X %02X %02X %02X' % v
             for v in vectors]
    host = [tuple(int(x, 16) for x in out.split())
            for out in run_oracle(oracle, lines)]

    # (c) compare the post-state tuples byte-for-byte.
    mismatches = []
    for i, (v, e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d mode=%02X A8F1=%02X A974=%02X A98B=%02X A97C=%02X '
                'A97D=%02X A97B=%02X A98A=%02X A969=%02X A96A=%02X A97F=%02X '
                'A98D=%02X F746=%04X '
                'ROM=(%02X,%02X,%02X,%02X,%02X,%02X,%02X,%04X,%02X,%02X,'
                '%02X,%02X,%02X,%02X,%02X,%02X) '
                'C=(%02X,%02X,%02X,%02X,%02X,%02X,%02X,%04X,%02X,%02X,'
                '%02X,%02X,%02X,%02X,%02X,%02X)'
                % (i, v[0], v[1], v[2], v[3], v[4], v[5], v[6], v[7], v[8],
                   v[9], v[10], v[11], v[12],
                   e[0], e[1], e[2], e[3], e[4], e[5], e[6], e[7],
                   e[8], e[9], e[10], e[11], e[12], e[13], e[14], e[15],
                   h[0], h[1], h[2], h[3], h[4], h[5], h[6], h[7],
                   h[8], h[9], h[10], h[11], h[12], h[13], h[14], h[15]))
            if len(mismatches) >= 5:
                break

    report('rotor_sync_position_detector', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
