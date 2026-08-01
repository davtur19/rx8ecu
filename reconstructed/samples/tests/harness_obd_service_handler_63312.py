#!/usr/bin/env python3
"""
harness_obd_service_handler_63312.py — equivalence of
rx8_obd_service_handler_63312 @0x63312.

Reconstructed source: samples/src/rx8_obd_service_handler_63312.c
Verified lift   : c/obd_service_handler_63312.c  (OBD pending-flag clear
                  leaf, side-effect only: if byte@0xFFFF87D0 == 1 the 16-bit
                  cell at 0xFFFF87D0 is rewritten as enc8(0) = 0x00FF,
                  otherwise untouched).

The ROM function is entered through the normal ABI path (no arguments, so
cpu.call()'s r4-r7 seeding is irrelevant) but it only READS/WRITES RAM —
there is no meaningful register result.  Equivalence is therefore judged on
the RAM side-effect: the two bytes of the cell at 0xFFFF87D0, compared in
ROM (big-endian) order.

The cell is a uint16_t VALUE whose high byte is the flag byte (byte@0xFFFF87D0,
big-endian ROM semantics; see the lift and the oracle).  The emulator stores
it as two raw big-endian bytes in its sparse RAM overlay, the host oracle
stores the same VALUE with native host endianness and re-reads it as a value,
so both sides print the cell bytes in ROM order.

Because 0xFFFF87D0 lies in an address range the host can mmap() with
MAP_FIXED, the oracle maps the backing page, seeds the identical initial
cell value, runs the reconstructed C, and reports the resulting bytes.

Procedure (Track-A pattern):
  1. build host oracle (system gcc),
  2. edge vectors (exhaustive: every flag byte 0x00..0xFF against several
     neighbour-byte values, incl. the trigger 0x01 and the 0x00/0xFF edges)
     + N random (flag, pad) pairs,
  3. run the ROM bytes @0x63312 in tools/sh2emu.py on the same vectors,
  4. run the host C on the same vectors,
  5. compare the side-effected RAM bytes — 0 mismatches required.

Usage:  python3 harness_obd_service_handler_63312.py [N]   (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0x63312
N_DEFAULT = 20000

# Cell address (byte@FLAG = pending flag, byte@FLAG+1 = neighbour/pad).
FLAG = 0xFFFF87D0

# This harness' own build dir (kept separate from the shared host_oracle build).
SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = '/tmp/rx8-recon-obd_service_handler_63312'

# Edge vectors: exhaustive flag bytes (incl. the only trigger value 0x01, the
# untouched neighbours 0x00/0x02/0xFF, ...) against four pad values.
EDGE = [(flag, pad)
        for flag in range(256)
        for pad in (0x00, 0x01, 0xAA, 0xFF)]


def build_oracle(cc='cc'):
    """Compile this harness' own oracle (oracle_obd_service_handler_63312.c
    + the reconstructed source)."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_obd_service_handler_63312.c'),
           os.path.join(SAMPLES, 'src', 'rx8_obd_service_handler_63312.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(0x63312)

    vectors = list(EDGE) + [(rng.randint(0, 0xFF), rng.randint(0, 0xFF))
                            for _ in range(n)]

    # (a) ROM behaviour via the emulator: seed the cell, read back its two
    # bytes after the call (big-endian sparse RAM overlay == ROM byte layout).
    emu = []
    for flag, pad in vectors:
        cpu.call(ADDR, ram={FLAG: flag & 0xFF, FLAG + 1: pad & 0xFF})
        emu.append('%02X %02X' % (cpu.ram.get(FLAG, 0) & 0xFF,
                                  cpu.ram.get(FLAG + 1, 0) & 0xFF))

    # (b) host C on the same vectors (same cell VALUE, printed in ROM order).
    lines = ['obd %02X %02X' % (flag & 0xFF, pad & 0xFF) for flag, pad in vectors]
    host = run_oracle(oracle, lines)

    # (c) compare the side-effected RAM byte-for-byte.
    mismatches = []
    for i, ((flag, pad), e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d flag=%02X pad=%02X ROM=[%s] C=[%s]' % (i, flag, pad, e, h))
            if len(mismatches) >= 5:
                break

    report('obd_service_handler_63312', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
