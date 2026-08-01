#!/usr/bin/env python3
"""
harness_least_square.py — equivalence of rx8_least_square @0x5687A.

Reconstructed source: samples/src/rx8_least_square.c
Verified lift   : c/least_square_0x5687A.c  (IDA-ai symbol
                  `least_square_0x5687A` — a misnomer: this is NOT a
                  least-squares fit).

Despite the misleading symbol name, the leaf is a byte equality test: it
zero-extends r4 to 8 bits, reads the byte at 0xFFFFD20B
(SECURITY_STATE_1 — see docs/functions/security_access_handler.md), and
returns 1 when the two differ, 0 when equal.  It is the `state_check1`
helper of the SecurityAccess handler (SID 0x27).

RAM: the leaf reads the reference byte through a volatile pointer, so the
host oracle mmap()s the backing page and stores the vector's ref byte there,
while the emulator gets the byte via the sparse `ram` overlay at 0xFFFFD20B.

Procedure (Track-A pattern):
  1. build THIS harness's own host oracle (it compiles ONLY
     rx8_least_square.c — not the shared host_oracle.c),
  2. N random (val, ref) byte pairs + edge cases,
  3. run the ROM bytes @0x5687A in tools/sh2emu.py,
  4. run the host C on the same inputs,
  5. compare — 0 mismatches required.

Usage:  python3 harness_least_square.py [N]     (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0x5687A
REF_ADDR = 0xFFFFD20B
N_DEFAULT = 20000
SEED = ADDR          # fixed, reproducible

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORACLE_DIR = '/tmp/rx8-recon-least_square'
ORACLE = os.path.join(ORACLE_DIR, 'oracle')

# Edge vectors: (val, ref).
EDGE = [
    # val == ref  -> equal, returns 0 (taken `cmp/eq` path)
    (0x00, 0x00), (0x01, 0x01), (0x7F, 0x7F), (0x80, 0x80),
    (0xFE, 0xFE), (0xFF, 0xFF),
    # neighbours of each boundary byte -> different, returns 1
    (0x00, 0x01), (0x01, 0x00), (0xFF, 0xFE), (0xFE, 0xFF),
    (0x7F, 0x80), (0x80, 0x7F),
    # upper-bit input sets: the ROM's leading `extu.b` truncates to the low
    # 8 bits, so these must behave exactly like their low halves.
    (0x1234, 0x34), (0xABCD, 0xCD), (0xFFFFFF00, 0x00),
    (0xFFFF01FF, 0xFF),
    # arbitrary pairs
    (0xA5, 0x5A), (0x5A, 0xA5),
]


def build_oracle():
    """Compile the reconstructed source + this harness's own oracle.

    Unlike common.build_oracle() (which links the shared host_oracle.c plus
    the fixed SRC_FILES list), this compiles ONLY the file under test, so the
    oracle exercises no unrelated code.
    """
    os.makedirs(ORACLE_DIR, exist_ok=True)
    cmd = ['cc', '-O2', '-Wall', '-Wextra',
           '-I', 'include', '-I', 'src',
           'tests/oracle_least_square.c',
           'src/rx8_least_square.c',
           '-o', ORACLE]
    subprocess.run(cmd, cwd=SAMPLES, check=True)
    return ORACLE


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(SEED)

    vectors = list(EDGE) + [(rng.getrandbits(8), rng.getrandbits(8))
                            for _ in range(n)]

    # (a) ROM behaviour via the emulator (seeded RAM overlay),
    # (b) host-C on the same inputs.
    emu = [cpu.call(ADDR, r4=v, ram={REF_ADDR: r}) for v, r in vectors]
    lines = ['ls %08X %08X' % (v, r) for v, r in vectors]
    host = [int(x, 16) for x in run_oracle(oracle, lines)]

    # (c) compare.
    mismatches = []
    for i, ((v, r), e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append('vec#%d val=0x%02X ref=0x%02X ROM=0x%08X C=0x%08X'
                              % (i, v & 0xFF, r & 0xFF, e, h))
            if len(mismatches) >= 5:
                break

    report('least_square', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
