#!/usr/bin/env python3
"""
harness_omp_rotor_overshoot_detector.py — equivalence of
rx8_omp_rotor_overshoot_detector @0x18CC0.

Reconstructed source: samples/src/rx8_omp_rotor_overshoot_detector.c
Verified lift   : c/omp_rotor_overshoot_detector_18CC0.c (same address, in
                  c/verified_addrs.txt; the ROM bytes are executed for real
                  here via tools/sh2emu.py, including the two jsr leaves
                  0x3ED3C / 0x2478).

The ROM function is a void single-pass RTOS companion task with NO ABI return
value: its whole effect is on RAM, so equivalence is judged on RAM
side-effects, not a return value:

  - emulator side: seed the ten gate/flag/counter bytes plus the idle/off
    port pair 0x807A/0x807B and the C6AC fault flag in the sparse ram
    overlay, call the ROM entry @0x18CC0 (sr=0xF0, matching the RTOS) and
    read the seven writable cells back;
  - host side: the dedicated oracle mmap()s the pages backing the same cells
    AND the ROM calibration table @0x78E38 (real stock bytes 01 3E 7D),
    seeds the same bytes, runs the reconstructed C and prints the same seven
    cells.

EDGE vectors cover the full gate (A969) x ramp (A975) x fault (A976) x port
(A974-straddles-both-bands) state space with valid + broken port pairs, the
debounce-counter thresholds around CAL39 (62) / CAL3A (125), distinguishable
latch pre-states (A990/A991 are only ever latched, never cleared) and the
C6AC pre-state (the port leaf only raises it); N random pre-states follow
(fixed seed = the ROM address).

Usage:  python3 harness_omp_rotor_overshoot_detector.py [N]  (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0x18CC0
A969 = 0xFFFFA969        # rotor-sync dispatch flag (gate)
A974 = 0xFFFFA974        # position target (captured at entry)
A975 = 0xFFFFA975        # OMP ramp value (gate)
A976 = 0xFFFFA976        # OMP fault-inoperative flag
A990 = 0xFFFFA990        # over-shoot latch
A991 = 0xFFFFA991        # under-shoot latch
A992 = 0xFFFFA992        # over-shoot trigger
A993 = 0xFFFFA993        # under-shoot trigger
A994 = 0xFFFFA994        # over-shoot debounce counter
A995 = 0xFFFFA995        # under-shoot debounce counter
P7A = 0xFFFF807A         # idle/off port byte 0 (complementary u16)
C6AC = 0xFFFFC6AC        # ADDRESS_VAL fault flag (leaf 0x3F050 via 0x3ED3C)
ROM_CAL_ADDR = 0x00078E38  # 3 calibration bytes the function reads

N_DEFAULT = 20000
SEED = 0x18CC0

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = '/tmp/rx8-recon-omp_rotor_overshoot_detector'

# vector layout: (c6ac0, a969, a975, a976, a974, a990, a991, a992, a993,
#                 a994, a995, p7a, p7b) — cal bytes are shipped separately,
#         line  = 'omp <cal> <13 input bytes>'
#         output= 7 hex bytes: A990 A991 A992 A993 A994 A995 C6AC
CELLS = (A990, A991, A992, A993, A994, A995, C6AC)


def build_oracle(cc='cc'):
    """Compile the reconstructed source + its dedicated oracle into a binary."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_omp_rotor_overshoot_detector.c'),
           os.path.join(SAMPLES, 'src', 'rx8_omp_rotor_overshoot_detector.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def gen_edges():
    """Edge pre-states (c6ac0, a969, a975, a976, a974, a990, a991, a992, a993,
    a994, a995, p7a, p7b)."""
    v = []
    # full gate x ramp x fault x port state space, A974 straddling BOTH bands
    # (CAL38 = 0x01: fault band top = min(port+1, 255); healthy band = max(port-1,0))
    for a969 in (0, 1, 2, 0xFF):
        for a975 in (0, 1, 0xFF):
            for a976 in (0, 1, 0xFF):
                for pv in (0x00, 0x01, 0x02, 0x36, 0x37, 0x38, 0x7F, 0x80, 0xFE, 0xFF):
                    sat8 = min(pv + 1, 255)
                    band = (pv - 1) if pv > 1 else 0
                    for a974 in (0x00, 0x01, sat8 - 1, sat8, sat8 + 1,
                                 band - 1, band, band + 1, 0xFE, 0xFF):
                        # quiescent pre-state + a hot one (triggers set,
                        # latches set, counters at threshold)
                        v.append((0, a969, a975, a976, a974 & 0xFF, 0, 0, 0, 0,
                                  0, 0, pv, (~pv) & 0xFF))
                        v.append((1, a969, a975, a976, a974 & 0xFF, 1, 1, 1, 1,
                                  62, 125, pv, (~pv) & 0xFF))
    # debounce-counter thresholds with the gate forced open
    for a994 in (0, 61, 62, 63, 254, 255):
        for a995 in (0, 124, 125, 126, 254, 255):
            v.append((0, 1, 0, 1, 0x00, 0, 0, 1, 1, a994, a995,
                      0x37, (~0x37) & 0xFF))
    # broken port pair (complement mismatch): C6AC raised every tick, no gate
    for a969 in (0, 1):
        for a975 in (0, 1):
            for a976 in (0, 1):
                v.append((0, a969, a975, a976, 0x00, 0, 0, 0, 0, 0, 0, 0x37, 0x00))
                v.append((1, a969, a975, a976, 0xFF, 1, 1, 1, 1, 62, 125, 0x37, 0xFF))
    return v


def gen_random(rng, n):
    """n random pre-states over the full byte range of every input."""
    return [tuple(rng.randrange(256) for _ in range(13)) for _ in range(n)]


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(SEED)

    # The 3 calibration bytes the ROM reads at 0x78E38..0x78E3A (stock bin).
    cal = list(cpu.rom[ROM_CAL_ADDR:ROM_CAL_ADDR + 3])
    if cal != [0x01, 0x3E, 0x7D]:
        raise RuntimeError(
            'unexpected ROM calibration @0x%X: %s' % (ROM_CAL_ADDR,
                                                      ' '.join('%02X' % b for b in cal)))

    EDGE = gen_edges()
    vectors = EDGE + gen_random(rng, n)

    # (a) ROM behaviour via the emulator (RAM side-effects).
    emu = []
    for c6ac0, a969, a975, a976, a974, a990, a991, a992, a993, a994, a995, p7a, p7b in vectors:
        cpu.call(ADDR, ram={C6AC: c6ac0 & 0xFF, A969: a969 & 0xFF, A975: a975 & 0xFF,
                            A976: a976 & 0xFF, A974: a974 & 0xFF, A990: a990 & 0xFF,
                            A991: a991 & 0xFF, A992: a992 & 0xFF, A993: a993 & 0xFF,
                            A994: a994 & 0xFF, A995: a995 & 0xFF, P7A: p7a & 0xFF,
                            P7A + 1: p7b & 0xFF}, sr=0xF0)
        emu.append(tuple(cpu.rd(c, 1) for c in CELLS))

    # (b) host-C on the same pre-states (ROM calibration bytes shipped inline).
    caltok = ' '.join('%02X' % b for b in cal)
    lines = ['omp %s %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X'
             % (caltok, a969, a975, a976, a974, a990, a991, a992, a993,
                a994, a995, p7a, p7b, c6ac0)
             for c6ac0, a969, a975, a976, a974, a990, a991, a992, a993, a994, a995, p7a, p7b
             in vectors]
    host = [tuple(int(x, 16) for x in out.split())
            for out in run_oracle(oracle, lines)]

    # (c) compare the post-state 7-tuples byte-for-byte.
    mismatches = []
    for i, ((c6ac0, a969, a975, a976, a974, a990, a991, a992, a993, a994, a995, p7a, p7b), e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d A969=%02X A975=%02X A976=%02X A974=%02X '
                'pre=(%02X,%02X,%02X,%02X,%02X,%02X) port=%02X/%02X c6ac=%02X '
                'ROM=(%02X,%02X,%02X,%02X,%02X,%02X,%02X) '
                'C=(%02X,%02X,%02X,%02X,%02X,%02X,%02X)'
                % (i, a969, a975, a976, a974,
                   a990, a991, a992, a993, a994, a995, p7a, p7b, c6ac0,
                   e[0], e[1], e[2], e[3], e[4], e[5], e[6],
                   h[0], h[1], h[2], h[3], h[4], h[5], h[6]))
            if len(mismatches) >= 5:
                break

    report('omp_rotor_overshoot_detector', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
