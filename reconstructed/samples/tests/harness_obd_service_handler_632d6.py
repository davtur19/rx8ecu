#!/usr/bin/env python3
"""
harness_obd_service_handler_632d6.py — equivalence of
rx8_obd_service_handler_632d6 @0x632D6.

Reconstructed source: samples/src/rx8_obd_service_handler_632d6.c
Verified lift   : c/obd_service_handler_632D6.c

OBD pending-flag clear leaf.  It takes no arguments and its return value is not
meaningful (the lift returns void); ALL observable behaviour is a RAM side
effect on the 16-bit cell at 0xFFFF87CC:

    if (byte@0xFFFF87CC == 0x01)          # flag byte == 1
        word@0xFFFF87CC = enc8(0) == 0x00FF

so this harness compares the side-effected RAM (both bytes of the cell) between
the emulated ROM and the host C, exactly like host_oracle.c does for the
index-table helpers.  The SH-2E is big-endian: byte@0xFFFF87CC is the HIGH byte
of the 16-bit cell, so both sides exchange the cell as the uint16_t WORD value
(flag<<8)|pad — that keeps every comparison endian-independent.

Procedure (Track-A pattern):
  1. build the host oracle (system gcc; -O2, -Wall, -Wextra),
  2. edge vectors: exhaustive flag byte 0x00..0xFF with 4 neighbour pads
     (covers the ==1 trigger, both endpoints and all non-trigger values) +
     N random (flag, pad) pairs,
  3. run the ROM bytes @0x632D6 in tools/sh2emu.py on the same vectors,
  4. run the host C on the same vectors,
  5. compare the resulting cell WORD — 0 mismatches required.

Usage:  python3 harness_obd_service_handler_632d6.py [N]   (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0x632D6
N_DEFAULT = 20000

FLAG = 0xFFFF87CC

# This harness' own build dir (kept separate from the shared host_oracle build).
SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = '/tmp/rx8-recon-obd_service_handler_632d6'

# Edge vectors: every flag byte against 4 neighbour pads.  flag==1 is the only
# trigger (cell rewritten to enc8(0) == 0x00FF); 0x00/0xFF/0x80 are the
# boundary/max cases, the rest must leave the cell untouched.
EDGE = [(f, p) for f in range(0x100) for p in (0x00, 0x01, 0xAA, 0xFF)]


def build_oracle(cc='cc'):
    """Compile this harness' own oracle (oracle_obd_service_handler_632d6.c +
    the source)."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests',
                        'oracle_obd_service_handler_632d6.c'),
           os.path.join(SAMPLES, 'src', 'rx8_obd_service_handler_632d6.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(0x632D6)

    vectors = list(EDGE) + [(rng.randrange(0, 0x100), rng.randrange(0, 0x100))
                            for _ in range(n)]

    # (a) ROM behaviour via the emulator: seed byte@FLAG / byte@FLAG+1, read
    # back the whole 16-bit cell (big-endian word value) after the call.
    emu = []
    for flag, pad in vectors:
        cpu.call(ADDR, ram={FLAG: flag, FLAG + 1: pad})
        word = (cpu.ram[FLAG] << 8) | cpu.ram[FLAG + 1]
        emu.append(word)

    # (b) host C on the same inputs.
    lines = ['obd %02X %02X' % (f, p) for f, p in vectors]
    host = [int(x, 16) for x in run_oracle(oracle, lines)]

    # (c) compare the side-effected RAM cell.
    mismatches = []
    for i, ((flag, pad), e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d flag=%02X pad=%02X ROM=0x%04X C=0x%04X'
                % (i, flag, pad, e, h))
            if len(mismatches) >= 5:
                break

    report('obd_service_handler_632d6', ADDR, n, mismatches,
           edges=len(EDGE))


if __name__ == '__main__':
    main()
