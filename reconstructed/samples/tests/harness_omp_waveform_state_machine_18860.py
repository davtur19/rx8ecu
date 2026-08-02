#!/usr/bin/env python3
"""
harness_omp_waveform_state_machine_18860.py — equivalence of
rx8_omp_waveform_state_machine_18860 @0x18860.

Reconstructed source: samples/src/rx8_omp_waveform_state_machine_18860.c
Verified lift   : c/omp_waveform_state_machine_18860.c (same address, in
                  c/verified_addrs.txt; the ROM bytes are executed for real
                  here via tools/sh2emu.py, including the jsr/bsr leaves
                  0x3ED3C readValue_8bit_ADDRESS_VAL, 0x18552
                  omp_stepper_waveform_driver and 0x2478 addSaturate8Bit).

The ROM function is a void 4-state machine with ONE r4 argument (the mode
byte) and NO ABI return value: its whole effect is on RAM, so equivalence is
judged on RAM side-effects, not a return value:

  - emulator side: seed the 23 input cells (state bytes, step/rotor cells,
    wave-driver inputs, both complementary port pairs, the f32 coolant temp
    and the C6AC fault flag) in the sparse ram overlay, call the ROM entry
    @0x18860 with r4 = mode (sr = 0xF0, matching the RTOS) and read the 13
    writable cells back (A981/A982/A97E/A97B/A97F/A977/A978/A97C/A97D/
    A98A/A98D/F746/C6AC);
  - host side: the dedicated oracle mmap()s the pages backing the same cells
    AND the ROM calibration page @0x78E33/0x78E34/0x78E68 (real stock bytes),
    seeds the same bytes, runs the reconstructed C and prints the same 13
    cells.

EDGE vectors cover: the mode-0 reset, the A968 gate, both port-pair validity
states and the f32 -40.0 threshold (incl. NaN/+inf/-inf), the step-drive
A97C in {4,5,other}, and the timing-adjust A977/A978 x even/odd-A97C space
with A97C==5 post-wave (the wave driver RE-reads A97C and may advance it),
A97E around 0/1/2 and distinguishable pre-states for every written cell; N
random pre-states follow (fixed seed = 0x60E1D400).

Usage:  python3 harness_omp_waveform_state_machine_18860.py [N]
        (default N = 20000)
"""
import os
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0x18860
N_DEFAULT = 20000
SEED = 0x60E1D400

A981 = 0xFFFFA981      # 4-state machine state
A982 = 0xFFFFA982      # wave-latch flag
A97E = 0xFFFFA97E      # cal byte / countdown
A97B = 0xFFFFA97B      # stepper command byte
A97F = 0xFFFFA97F      # waveform byte
A977 = 0xFFFFA977      # cal-B flag
A978 = 0xFFFFA978      # cal-A flag
A968 = 0xFFFFA968      # gate flag
A97C = 0xFFFFA97C      # step register
A97D = 0xFFFFA97D      # rotor-sync step source (wave input)
A974 = 0xFFFFA974      # rotor position
A98A = 0xFFFFA98A      # previously latched mode (wave input)
A98D = 0xFFFFA98D      # wave-mode latch
A969 = 0xFFFFA969      # gate flag A (wave input)
A96A = 0xFFFFA96A      # gate flag B (wave input)
F746 = 0xFFFFF746      # stepper drive port (u16, wave RMW)
P78 = 0xFFFF8078       # complementary port pair A byte 0
P7C = 0xFFFF807C       # complementary port pair C byte 0
AA10 = 0xFFFFAA10      # coolant temp (f32)
C6AC = 0xFFFFC6AC      # ADDRESS_VAL fault flag

ROM_CAL_A = 0x00078E33
ROM_CAL_B = 0x00078E34
ROM_CAL_T = 0x00078E68

# vector layout (matches the oracle's 23-token 'ompw' line):
#   mode a981 a982 a97e a97b a97f a977 a978 a968 a97c a97d a974 a98a a98d
#   a969 a96a f746 p78 p79 p7c p7d aa10 c6ac
# output = 13 tokens:
#   A981 A982 A97E A97B A97F A977 A978 A97C A97D A98A A98D F746 C6AC
OUT_CELLS = (A981, A982, A97E, A97B, A97F, A977, A978,
             A97C, A97D, A98A, A98D, F746, C6AC)

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = '/tmp/rx8-recon-omp_waveform_state_machine_18860'

F_NE40 = struct.unpack('>I', struct.pack('>f', -40.0))[0]   # 0xC2200000


def build_oracle(cc='cc'):
    """Compile the reconstructed source + its dedicated oracle into a binary."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests',
                        'oracle_omp_waveform_state_machine_18860.c'),
           os.path.join(SAMPLES, 'src',
                        'rx8_omp_waveform_state_machine_18860.c'),
           '-lm', '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def seed(init, addr, n, val):
    """Byte-exact big-endian store of a width-`n` value in the ram overlay."""
    for i in range(n):
        init[addr + i] = (val >> (8 * (n - 1 - i))) & 0xFF


def run_emu(cpu, v):
    """Seed every input cell, run the ROM bytes @0x18860 (callees included)
    with r4 = mode, and return the 13-tuple of post-state cells."""
    (mode, a981, a982, a97e, a97b, a97f, a977, a978, a968, a97c, a97d,
     a974, a98a, a98d, a969, a96a, f746, p78, p79, p7c, p7d, aa10, c6ac) = v
    init = {}
    init[A981] = a981 & 0xFF
    init[A982] = a982 & 0xFF
    init[A97E] = a97e & 0xFF
    init[A97B] = a97b & 0xFF
    init[A97F] = a97f & 0xFF
    init[A977] = a977 & 0xFF
    init[A978] = a978 & 0xFF
    init[A968] = a968 & 0xFF
    init[A97C] = a97c & 0xFF
    init[A97D] = a97d & 0xFF
    init[A974] = a974 & 0xFF
    init[A98A] = a98a & 0xFF
    init[A98D] = a98d & 0xFF
    init[A969] = a969 & 0xFF
    init[A96A] = a96a & 0xFF
    seed(init, F746, 2, f746 & 0xFFFF)
    init[P78] = p78 & 0xFF
    init[P78 + 1] = p79 & 0xFF
    init[P7C] = p7c & 0xFF
    init[P7C + 1] = p7d & 0xFF
    seed(init, AA10, 4, aa10 & 0xFFFFFFFF)
    init[C6AC] = c6ac & 0xFF
    cpu.call(ADDR, r4=mode & 0xFF, ram=init, sr=0xF0)
    return tuple(cpu.rd(c, 2) if c == F746 else cpu.rd(c, 1)
                 for c in OUT_CELLS)


def base(p78=0x37, p79=0xC8, p7c=0x01, p7d=0xFE):
    """A quiescent, valid-pair baseline vector (mode 1, state 2, cal-B)."""
    return (1, 2, 0, 0, 0x00, 0x5A, 1, 0, 1, 6, 6, 0x40, 0, 0x11,
            1, 0, 0x0000, p78, p79, p7c, p7d, F_NE40, 0)


def gen_edges():
    """Edge pre-states (23-tuples) targeting every branch."""
    v = []
    # (a) mode-0 reset: clears A981/A982 for every pre-state, then the
    #     step-drive block runs on the cleared state (fresh A981 == 0 read).
    for a981 in (0, 1, 2):
        for a97c in (4, 5, 6):
            t = list(base())
            t[0], t[1], t[9] = 0, a981, a97c      # mode, A981, A97C
            v.append(tuple(t))
    # (b) state-1 block (A981 pre == 1): A968 gate off.
    for a968 in (0, 0xFF):
        t = list(base())
        t[0], t[1], t[8] = 1, 1, a968             # mode, A981, A968
        v.append(tuple(t))
    # (c) state-1 block, A968 == 1: port-pair validity + value gate.
    pairs = [(0x37, 0xC8), (0x00, 0xFF), (0x80, 0x7F),       # valid
             (0x37, 0x00), (0x00, 0x00), (0xFF, 0xFF)]       # broken
    for (a, b) in pairs:
        for (c, d) in pairs:
            # P8078 broken/0 -> cal A; P8078 ok & P807C != 1 -> cal A;
            # P8078 ok & P807C == 1 -> temp split.
            t = list(base())
            t[0], t[1], t[8] = 1, 1, 1
            t[17], t[18], t[19], t[20] = a, b, c, d
            v.append(tuple(t))
    # (d) state-1 block, temp split: cal A iff temp < -40.0 (fcmp/gt
    #     -40.0 > temp); NaN/+inf -> cal B, -inf -> cal A.
    temps = (F_NE40,                                       # -40.0 (cal B)
             struct.unpack('>I', struct.pack('>f', -40.0001))[0],  # cal A
             struct.unpack('>I', struct.pack('>f', -50.0))[0],     # cal A
             struct.unpack('>I', struct.pack('>f', 30.0))[0],      # cal B
             0x7FC00000, 0x7FA00000,                     # NaN payloads
             0x7F800000, 0xFF800000,                     # +inf / -inf
             0x80000000, 0x00000000)                     # -0.0 / +0.0
    for tbits in temps:
        t = list(base())
        t[0], t[1], t[8] = 1, 1, 1
        t[21] = tbits
        v.append(tuple(t))
    # (e) step-drive block (A981 pre == 0): A97C == 5 / 4 / other with the
    #     A974 boundary at 60 and distinguishable A97F pre-states.
    for a97c in (5, 4, 0, 6, 0xFF):
        for a974 in (0, 59, 60, 61, 0xFF):
            t = list(base())
            t[0], t[1], t[9], t[11], t[4] = 1, 0, a97c, a974, 0x5A
            v.append(tuple(t))
    # (f) timing-adjust block (A981 pre == 2), gate flags.
    for a977 in (0, 1):
        for a978 in (0, 1):
            t = list(base())
            t[0], t[1], t[6], t[7] = 1, 2, a977, a978
            v.append(tuple(t))
    # (g) timing-adjust, even step: post-wave A97C == 5 with A97E around 0/1/2
    #     (pre-step 6 -> wave(1) advances to 5; pre-step 8 with A97D 6 also ->
    #     5).  A98A pre == 4 blocks the wave mode-1 A97F writes.
    for a97c in (6, 8, 4, 2):
        for a97e in (0, 1, 2, 0xFF):
            for a98a in (0, 4):
                t = list(base())
                t[0], t[1], t[6], t[9], t[3], t[10] = 1, 2, 1, a97c, 0xFF, 6
                t[2], t[12] = a97e, a98a              # A97E, A98A
                v.append(tuple(t))
    # (h) timing-adjust, odd step: A97E decrement (A97E > 0 -> A97E - 1).
    for a97c in (5, 7, 1, 3):
        for a97e in (0, 1, 0xFF):
            t = list(base())
            t[0], t[1], t[6], t[9], t[2] = 1, 2, 1, a97c, a97e
            v.append(tuple(t))
    # (i) C6AC pre-states with valid + broken pairs in every state.
    for a981 in (0, 1, 2):
        for c6ac in (0, 1):
            for (a, b) in ((0x37, 0xC8), (0x37, 0x00)):
                t = list(base())
                t[0], t[1], t[22] = 1, a981, c6ac
                t[17], t[18] = a, b
                v.append(tuple(t))
    return v


def gen_random(rng, k):
    """k random pre-states over the full byte range of every input, biased
    toward the hot paths (valid/broken pairs, temps around -40, step 0..8,
    states 0/1/2)."""
    def temp():
        if rng.random() < 0.5:
            return struct.unpack('>I', struct.pack('>f', rng.uniform(-100, 150)))[0]
        return rng.getrandbits(32)

    def pair():
        if rng.random() < 0.5:
            val = rng.getrandbits(8)
            return val, (~val) & 0xFF
        return rng.getrandbits(8), rng.getrandbits(8)

    v = []
    for _ in range(k):
        p78, p79 = pair()
        p7c, p7d = pair()
        v.append((rng.choice((0, 0, 1, 1, 2, rng.getrandbits(8))),   # mode
                  rng.choice((0, 0, 1, 1, 2, 2, 3)),                 # A981
                  rng.getrandbits(8),                                # A982
                  rng.choice((0, 1, 2, rng.getrandbits(8))),         # A97E
                  rng.getrandbits(8),                                # A97B
                  rng.getrandbits(8),                                # A97F
                  rng.choice((0, 1, rng.getrandbits(8))),            # A977
                  rng.choice((0, 1, rng.getrandbits(8))),            # A978
                  rng.choice((0, 1, rng.getrandbits(8))),            # A968
                  rng.choice((4, 5, 6, 7, 8, rng.getrandbits(8))),   # A97C
                  rng.choice((6, 7, 8, rng.getrandbits(8))),         # A97D
                  rng.choice((0, 59, 60, 61, rng.getrandbits(8))),   # A974
                  rng.choice((0, 4, rng.getrandbits(8))),            # A98A
                  rng.getrandbits(8),                                # A98D
                  rng.choice((0, 1, rng.getrandbits(8))),            # A969
                  rng.choice((0, 1, rng.getrandbits(8))),            # A96A
                  rng.getrandbits(16),                               # F746
                  p78, p79, p7c, p7d,
                  temp(),
                  rng.choice((0, 1, rng.getrandbits(8)))))           # C6AC
    return v


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(SEED)

    # The calibration constants the ROM reads (stock bin).
    cal_a = cpu.rom[ROM_CAL_A]
    cal_b = cpu.rom[ROM_CAL_B]
    cal_t = struct.unpack_from('>f', cpu.rom, ROM_CAL_T)[0]
    if (cal_a, cal_b) != (0x3C, 0x3C) or cal_t != -40.0:
        raise RuntimeError(
            'unexpected ROM calibration @0x%X/0x%X/0x%X: %02X %02X %g'
            % (ROM_CAL_A, ROM_CAL_B, ROM_CAL_T, cal_a, cal_b, cal_t))

    EDGE = gen_edges()
    vectors = EDGE + gen_random(rng, n)

    # (a) ROM behaviour via the emulator (RAM side-effects).
    emu = [run_emu(cpu, v) for v in vectors]

    # (b) host-C on the same pre-states.
    lines = ['ompw %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X '
             '%02X %02X %02X %02X %02X %04X %02X %02X %02X %02X %08X %02X'
             % v for v in vectors]
    host = [tuple(int(x, 16) for x in out.split())
            for out in run_oracle(oracle, lines)]

    # (c) compare the post-state 13-tuples byte-for-byte.
    mismatches = []
    for i, (v, e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d mode=%02X A981=%02X A968=%02X A97C=%02X A97E=%02X '
                'A977=%02X A978=%02X A974=%02X temp=0x%08X p78=%02X/%02X '
                'p7c=%02X/%02X '
                'ROM=(%02X,%02X,%02X,%02X,%02X,%02X,%02X,%02X,%02X,%02X,'
                '%02X,%04X,%02X) '
                'C=(%02X,%02X,%02X,%02X,%02X,%02X,%02X,%02X,%02X,%02X,'
                '%02X,%04X,%02X)'
                % (i, v[0], v[1], v[8], v[9], v[2], v[6], v[7], v[11],
                   v[21], v[17], v[18], v[19], v[20],
                   e[0], e[1], e[2], e[3], e[4], e[5], e[6], e[7],
                   e[8], e[9], e[10], e[11], e[12],
                   h[0], h[1], h[2], h[3], h[4], h[5], h[6], h[7],
                   h[8], h[9], h[10], h[11], h[12]))
            if len(mismatches) >= 5:
                break

    report('omp_waveform_state_machine', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
