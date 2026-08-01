#!/usr/bin/env python3
"""
harness_dtc_data_read_60f58.py — equivalence of rx8_dtc_data_read_60f58 @0x60F58.

Reconstructed source: samples/src/rx8_dtc_data_read_60f58.c
Verified lift   : c/dtc_data_read_60F58.c

This leaf is a pure RAM side-effect: it fills the two DTC status halfwords
0xFFFFD6C8 and 0xFFFFD6CC with 0xFFFF, with NO arguments and no return value.
Equivalence therefore compares the RAM bytes after the call, not a return
value (Track-A RAM pattern, cf. harness_purge_flow_counter_init.py):

  - emulator side: seed a 12-byte window (0xFFFFD6C6..0xFFFFD6D1) in the
    sparse `ram` overlay, call the ROM entry @0x60F58, read the bytes back;
  - host side: the oracle mmap()s the backing page (MAP_FIXED, same trick as
    host_oracle.c), seeds the same bytes, runs the reconstructed C, reads
    them back.

The window deliberately includes four sentinel bytes that must survive
untouched (0xFFFFD6C6/0xFFFFD6C7 in front, 0xFFFFD6D0/0xFFFFD6D1 behind)
plus the two odd halfwords inside the 8-byte window (0xFFFFD6CA, 0xFFFFD6CE)
that the ROM does NOT touch (its `add #0x04,r4` walks the pointer in 4-byte
steps).  That pins the store width and stride exactly and catches any
over/under-run or a wrong stride in the reconstructed source.

NOTE on the lift: c/dtc_data_read_60F58.c claims a 4×uint16 / 8-byte fill and
its C loop writes FOUR halfwords (0xFFFFD6C8..0xFFFFD6CF).  The ROM bytes
only write TWO (0xFFFFD6C8 and 0xFFFFD6CC) — the odd halfwords keep their
pre-state.  This harness would flag the lift's loop as a mismatch; the
reconstructed source follows the ROM.

Usage:  python3 harness_dtc_data_read_60f58.py [N]  (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0x60F58
N_DEFAULT = 20000

# 12-byte window: sentinel front (2) + 8-byte DTC window + sentinel back (2).
WIN_BASE = 0xFFFFD6C6
WIN_LEN = 12
ADDRS = tuple(WIN_BASE + i for i in range(WIN_LEN))
# Indexes of the two halfwords the ROM fills (bytes c8/c9 and cc/cd).
TARGETS = (2, 3, 6, 7)

EDGE = [
    (0x00,) * WIN_LEN,                    # already zero
    (0xFF,) * WIN_LEN,                    # all ones (idempotent)
    (0x00, 0x00, 0x11, 0x11, 0x22, 0x22, 0x33, 0x33, 0x44, 0x44, 0x00, 0x00),
    (0x5A,) * WIN_LEN,                    # bit pattern, uniform
    (0xA5,) * WIN_LEN,
    (0x00, 0x00, 0x00, 0x00, 0xFF, 0xFF, 0x00, 0x00, 0xFF, 0xFF, 0x00, 0x00),
    (0xDE, 0xAD, 0xBE, 0xEF, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07),
    (0x80,) * WIN_LEN,                    # sign bit
    (0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xFF, 0xFF),
]

# Expected post-state of a vector: the four target bytes become 0xFF,
# everything else keeps its pre-state.
def expected(pre):
    return tuple(0xFF if i in TARGETS else v for i, v in enumerate(pre))


def build_oracle():
    """Compile the reconstructed source + its own oracle into /tmp.

    (Recipe: this harness compiles its OWN oracle — only the file under test,
    not common.build_oracle's shared SRC_FILES bundle.)"""
    samples = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = '/tmp/rx8-recon-dtc_data_read_60f58'
    os.makedirs(out, exist_ok=True)
    oracle = os.path.join(out, 'oracle')
    cmd = ['cc', '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(samples, 'include'),
           '-I', os.path.join(samples, 'src'),
           os.path.join(samples, 'tests', 'oracle_dtc_data_read_60f58.c'),
           os.path.join(samples, 'src', 'rx8_dtc_data_read_60f58.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(ADDR)

    vectors = list(EDGE) + [tuple(rng.randint(0, 255) for _ in range(WIN_LEN))
                            for _ in range(n)]

    # (a) ROM behaviour via the emulator: seed the window, call the actual
    #     ROM bytes @0x60F58, read the twelve bytes back.
    emu = []
    for v in vectors:
        ram = dict(zip(ADDRS, v))
        cpu.call(ADDR, ram=ram)
        emu.append(tuple(cpu.ram.get(a, 0) for a in ADDRS))

    # (b) host-C on the same vectors (oracle mmap-seeds and reads back).
    lines = [' '.join('%02X' % b for b in v) for v in vectors]
    host = [tuple(int(x, 16) for x in out.split())
            for out in run_oracle(oracle, lines)]

    # (c) compare the full post-state byte-for-byte (side effects included).
    mismatches = []
    for i, (v, e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            exp = expected(v)
            mismatches.append(
                'vec#%d pre=%s expected=%s ROM=%s C=%s'
                % (i, ' '.join('%02X' % b for b in v),
                   ' '.join('%02X' % b for b in exp),
                   ' '.join('%02X' % b for b in e),
                   ' '.join('%02X' % b for b in h)))
            if len(mismatches) >= 5:
                break

    report('dtc_data_read_60f58', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
