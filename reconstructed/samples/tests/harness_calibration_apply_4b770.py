#!/usr/bin/env python3
"""
harness_calibration_apply_4b770.py — equivalence of
rx8_calibration_apply_4b770 @0x4B770.

Reconstructed source: samples/src/rx8_calibration_apply_4b770.c
Verified lift   : c/calibration_apply_4B770.c

The ROM function is a plain ABI-clean void leaf: it reads three on-chip-RAM
status bytes (0xFFFFD201, 0xFFFFCE00, 0xFFFFCE01) and writes one calibration
flag byte RAM[0xFFFFCDFD]:

    flag = (b201 != 1 && bCE00 == 0 && bCE01 == 0) ? 1 : 0

No arguments are passed and nothing is returned through a register — the
observable effect is the RAM write, so the harness drives the emulator with
the standard `cpu.call()` (seeding the three input bytes via the ram= overlay)
and compares the side-effected flag byte against the host C's mmap-backed RAM
(same MAP_FIXED trick as tests/host_oracle.c).

Procedure (Track-A pattern):
  1. build the host oracle (system gcc; -O2, -Wall, -Wextra),
  2. edge vectors (full cross-product of interesting byte values, covering
     every branch: b201 == 1 vs not, and each CE byte 0 vs nonzero, incl.
     the 8-bit extremes 0x00/0x01/0x02/0x7F/0x80/0xFF) + N random byte triples,
  3. run the ROM bytes @0x4B770 in tools/sh2emu.py on the same vectors,
  4. run the host C on the same vectors,
  5. compare the flag byte — 0 mismatches required.

Usage:  python3 harness_calibration_apply_4b770.py [N]   (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0x4B770
IN_B201 = 0xFFFFD201            # input byte 0
IN_CE00 = 0xFFFFCE00            # input byte 1
IN_CE01 = 0xFFFFCE01            # input byte 2
OUT_FLAG = 0xFFFFCDFD           # calibration flag byte
N_DEFAULT = 20000

# Edge vectors: cross-product of interesting values.  Covers every branch of
# the && short-circuit (b201 == 1 vs !=1; each CE byte 0 vs nonzero), the
# byte boundaries 0x7F/0x80 and the 8-bit extremes 0x00/0xFF.
EDGE = [(a, b, c)
        for a in (0x00, 0x01, 0x02, 0x7F, 0x80, 0xFF)
        for b in (0x00, 0x01, 0x02, 0x7F, 0x80, 0xFF)
        for c in (0x00, 0x01, 0x02, 0x7F, 0x80, 0xFF)]

# This harness' own build dir (kept separate from the shared host_oracle build).
SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = '/tmp/rx8-recon-calibration_apply_4b770'


def build_oracle(cc='cc'):
    """Compile this harness' own oracle (oracle_calibration_apply_4b770.c +
    the reconstructed source) into the task-mandated build dir."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_calibration_apply_4b770.c'),
           os.path.join(SAMPLES, 'src', 'rx8_calibration_apply_4b770.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(0x60E1D400)

    vectors = list(EDGE) + [(rng.randrange(0, 256), rng.randrange(0, 256),
                             rng.randrange(0, 256)) for _ in range(n)]

    # (a) ROM behaviour via the emulator: seed the three status bytes in the
    # RAM overlay, then read back the flag byte the function wrote.
    emu = []
    for b201, bce00, bce01 in vectors:
        cpu.call(ADDR, ram={IN_B201: b201, IN_CE00: bce00, IN_CE01: bce01})
        emu.append(cpu.ram[OUT_FLAG])

    # (b) host C on the same inputs (bytes shipped as raw hex).
    lines = ['cal %02X %02X %02X' % (b201, bce00, bce01)
             for b201, bce00, bce01 in vectors]
    host = [int(x, 16) for x in run_oracle(oracle, lines)]

    # (c) compare the flag byte.
    mismatches = []
    for k, ((b201, bce00, bce01), e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d in=(0x%02X,0x%02X,0x%02X) ROM=0x%02X C=0x%02X'
                % (k, b201, bce00, bce01, e, h))
            if len(mismatches) >= 5:
                break

    report('calibration_apply_4B770', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
