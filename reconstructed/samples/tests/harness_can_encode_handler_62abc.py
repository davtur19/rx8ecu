#!/usr/bin/env python3
"""
harness_can_encode_handler_62abc.py — equivalence of
rx8_can_encode_handler_62abc @0x62ABC.

Reconstructed source: samples/src/rx8_can_encode_handler_62abc.c
Verified lift   : c/can_encode_handler_62ABC.c (same address; the ROM bytes
                  are executed for real here via tools/sh2emu.py).

The function is a void dispatch leaf with NO ABI return value: it reads a
per-DTC mode byte at 0xFFFF8D7C + (dtc & 0xFFFF)*2 and, for selected modes,
calls the run-sum leaf 0x648B4 (real ROM bytes in the emulator) which folds
r5 into the two 16-bit cells word@0xFFFF8E98 / word@0xFFFF8E9A.  The whole
effect is on RAM, so the equivalence check compares those two post-call
cells, not a return value:

  - emulator side: seed the mode byte and the two cell pre-states in the
    sparse ram overlay, call the ROM entry @0x62ABC, read the two cells
    back as big-endian words;
  - host side: the dedicated oracle mmap()s the page backing the mode table
    AND the cells (0xFFFF8000), seeds the same bytes, runs the reconstructed
    C (with the oracle-supplied body of the external leaf 0x648B4) and prints
    the same two words.

EDGE vectors cover every mode x (vl = r5&0xFF) combination that flips the
call decision (0x00 always calls; 0x10 gates on vl==0x20||0x11; 0x11 gates on
vl==0x20; 0x20/other never call), the dtc boundaries inside the test bound
(0x0000/0x0001/0x007F — dtc is kept <= 0x7F so the mode-table read stays
clear of the run-sum cells, a test-only bound), and distinguishable cell
pre-states to catch any cell the function forgets to (re)write; N random
pre-states follow (fixed seed = the ROM address).

Usage:  python3 harness_can_encode_handler_62abc.py [N]  (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0x62ABC
MODE_TABLE = 0xFFFF8D7C        # per-DTC mode dispatch byte table (stride 2)
RUN_SUM_1 = 0xFFFF8E98         # word: run-sum cell 1
RUN_SUM_2 = 0xFFFF8E9A         # word: run-sum cell 2

N_DEFAULT = 20000
SEED = 0x62ABC                 # fixed seed (the function's own address)

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = '/tmp/rx8-recon-can_encode_handler_62abc'

MODES = (0x00, 0x10, 0x11, 0x20, 0x21, 0x7F, 0xFF)   # dispatch-table values
VLS = (0x00, 0x01, 0x11, 0x1F, 0x20, 0x21, 0x7F, 0x80, 0xFF)  # r5&0xFF probes
PRES = ((0x0000, 0x0000), (0xFFFF, 0xFFFF), (0x1234, 0x9ABC),
        (0x00FF, 0x0100), (0x8080, 0x7F7F))          # distinguishable pre-states


def build_oracle(cc='cc'):
    """Compile the reconstructed source + its dedicated oracle into a binary."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_can_encode_handler_62abc.c'),
           os.path.join(SAMPLES, 'src', 'rx8_can_encode_handler_62abc.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def gen_edges():
    """Edge vectors (dtc, r5, mode, wa, wb): full mode x vl cross, dtc
    boundaries inside the test bound, and pre-state coverage."""
    v = []
    for mode in MODES:                       # every dispatch byte x every vl
        for vl in VLS:
            v.append((0x12, vl, mode, 0x1234, 0x9ABC))
    for dtc in (0x0000, 0x0001, 0x007F):     # dtc edges (bound <= 0x7F)
        for mode, vl in ((0x00, 0x20), (0x10, 0x11), (0x11, 0x20),
                         (0x20, 0xFF), (0xFF, 0x00)):
            v.append((dtc, vl, mode, 0x1234, 0x9ABC))
    for pre in PRES:                         # stale pre-states: any cell missed
        for mode in (0x00, 0x10, 0x11):
            v.append((0x12, 0x20, mode, pre[0], pre[1]))
    return v


def gen_random(rng, n):
    """n random vectors: dtc in the safe 0..0x7F range, full 32-bit r5, random
    mode byte and cell pre-states."""
    return [(rng.randrange(0x80), rng.getrandbits(32), rng.choice(MODES),
             rng.getrandbits(16), rng.getrandbits(16)) for _ in range(n)]


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(SEED)

    EDGE = gen_edges()
    vectors = EDGE + gen_random(rng, n)

    # (a) ROM behaviour via the emulator (RAM side-effects).
    emu = []
    for dtc, r5, mode, wa, wb in vectors:
        maddr = (MODE_TABLE + ((dtc & 0xFFFF) << 1)) & 0xFFFFFFFF
        cpu.call(ADDR, r4=dtc, r5=r5,
                 ram={maddr: mode & 0xFF,
                      RUN_SUM_1: (wa >> 8) & 0xFF, RUN_SUM_1 + 1: wa & 0xFF,
                      RUN_SUM_2: (wb >> 8) & 0xFF, RUN_SUM_2 + 1: wb & 0xFF})
        emu.append((cpu.rd(RUN_SUM_1, 2), cpu.rd(RUN_SUM_2, 2)))

    # (b) host-C on the same pre-states.
    lines = ['enc %X %08X %02X %04X %04X'
             % (dtc & 0xFFFF, r5 & 0xFFFFFFFF, mode & 0xFF, wa & 0xFFFF, wb & 0xFFFF)
             for dtc, r5, mode, wa, wb in vectors]
    host = [tuple(int(x, 16) for x in out.split())
            for out in run_oracle(oracle, lines)]

    # (c) compare the two post-state words byte-for-byte.
    mismatches = []
    for i, ((dtc, r5, mode, wa, wb), e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d dtc=%02X r5=%08X mode=%02X pre=(%04X,%04X) '
                'ROM=(%04X,%04X) C=(%04X,%04X)'
                % (i, dtc & 0xFFFF, r5 & 0xFFFFFFFF, mode & 0xFF, wa, wb,
                   e[0], e[1], h[0], h[1]))
            if len(mismatches) >= 5:
                break

    report('can_encode_handler_62ABC', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
