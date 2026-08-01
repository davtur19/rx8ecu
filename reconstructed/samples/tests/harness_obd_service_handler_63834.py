#!/usr/bin/env python3
"""
harness_obd_service_handler_63834.py — equivalence of
obd_service_handler_63834 @0x63834.

Reconstructed source: samples/src/rx8_obd_service_handler_63834.c
Verified lift   : c/obd_service_handler_63834.c (also verified by
                  c/tests/test_obd_service_handler_63834.{py,c})

Mode-1 status read leaf over the 21-entry DTC context table
(base 0xFFFF87D8, 16-byte stride, code word @+0, type byte @+6):

    cur = word@0xFFFF8928 & 0xFFFF
    for i in 0..20:
        p = 0xFFFF87D8 + i*16
        if word@p == (r4 & 0xFFFF) and i != cur:
            return s8(byte@p+0x06)     ; sign-extended (mov.b)
    return 0

The function is entered through the normal ABI (r4 = DTC code) and returns
its result in r0, so the plain `cpu.call()` works — no call_leaf needed
(same as c/tests/test_obd_service_handler_63834.py).  It READS the on-chip
RAM window (table + current-index word) but never writes it, so the compared
state is the 32-bit return value; the oracle still mirrors the table + index
state on the host via MAP_FIXED (same trick as oracle_obd_dtc_row_update_64418.c).

Procedure (Track-A pattern):
  1. build the host oracle (system gcc; -O2, -Wall, -Wextra),
  2. edge vectors (per-row match/skip/miss with type bytes 0x00/0x01/0x7F/0x80/
     0xFF incl. sign-extension, cur at 0..20 / 0xFFFF, duplicate-code rows,
     boundary codes 0x0000/0xFFFF, no-match tables) + N random full-table
     vectors (seeded RNG),
  3. run the ROM bytes @0x63834 in tools/sh2emu.py on the same vectors
     (sparse RAM overlay seeds every row + the index word),
  4. run the host C on the same vectors,
  5. compare the 32-bit results — 0 mismatches required.

Usage:  python3 harness_obd_service_handler_63834.py [N]   (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0x63834
N_DEFAULT = 20000

BASE = 0xFFFF87D8
CUR = 0xFFFF8928
COUNT = 21
STRIDE = 16

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = os.path.join('/tmp', 'rx8-recon-obd_service_handler_63834')


def s8(x):
    x &= 0xFF
    return x - 256 if x & 0x80 else x


def gen_edges():
    """Edge vectors: (dtc, cur, rows) with rows = 21 (code, type) tuples."""
    v = []
    filler = (0xFFFF, 0x00)                     # never matches dtc below
    for r in range(COUNT):
        for t6 in (0x00, 0x01, 0x7F, 0x80, 0xFF):
            rows = [filler] * COUNT
            rows[r] = (0x1234, t6)
            v.append((0x1234, r, rows))                     # cur == row: skip -> 0
            v.append((0x1234, (r + 1) % COUNT, rows))       # cur elsewhere -> hit
            v.append((0x1234, 0xFFFF, rows))                # cur beyond rows -> hit
            v.append((0x9999, r, rows))                     # code miss -> 0
    # duplicate-code rows: first match wins
    for t6a, t6b in ((0x01, 0x02), (0xFF, 0x7F), (0x80, 0x00)):
        rows = [filler] * COUNT
        rows[3] = (0x5AA5, t6a)
        rows[17] = (0x5AA5, t6b)
        v.append((0x5AA5, 3, rows))      # first row is current -> returns 2nd's type
        v.append((0x5AA5, 17, rows))     # second row is current -> returns 1st's type
        v.append((0x5AA5, 0, rows))      # neither current -> returns 1st's type
    # boundary codes and no-match table
    rows0 = [filler] * COUNT; rows0[0] = (0x0000, 0xAA)
    v.append((0x0000, 0, rows0))                              # skip row 0
    v.append((0x0000, 5, rows0))                              # hit row 0
    rowsf = [filler] * COUNT; rowsf[20] = (0xFFFF, 0x99)
    v.append((0xFFFF, 0, rowsf))                              # hit row 20 (last row)
    v.append((0xFFFF, 20, rowsf))                             # skip row 20
    v.append((0x1234, 0x8000, [filler] * COUNT))              # no match anywhere
    v.append((0x0000, 0x8000, [filler] * COUNT))              # dtc 0, no code 0 -> 0
    v.append((0xFFFF, 0x8000, [filler] * COUNT))              # dtc FFFF, no code FFFF -> 0
    return v


def gen_random(rng, k):
    """k random vectors: every row gets a random code/type, dtc and cur are
    full-range 16-bit values.  Fully-populated tables exercise the first-match
    scan and the sign-extended type return without any filler-row hazards."""
    v = []
    for _ in range(k):
        rows = [(rng.randint(0, 0xFFFF), rng.randint(0, 0xFF))
                for _ in range(COUNT)]
        v.append((rng.randint(0, 0xFFFF), rng.randint(0, 0xFFFF), rows))
    return v


def build_oracle(cc='cc'):
    """Compile this harness' own oracle (oracle_obd_service_handler_63834.c +
    src/rx8_obd_service_handler_63834.c).  common.build_oracle is not reusable:
    it hardcodes the sample .c list."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_obd_service_handler_63834.c'),
           os.path.join(SAMPLES, 'src', 'rx8_obd_service_handler_63834.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def seed_and_call(cpu, dtc, cur, rows):
    """Seed the 21 table rows + the current-index word in the sparse RAM
    overlay and run the actual ROM bytes @0x63834; return r0 (32-bit)."""
    ram = {CUR: (cur >> 8) & 0xFF, CUR + 1: cur & 0xFF}
    for i, (code, typ) in enumerate(rows):
        p = BASE + i * STRIDE
        ram[p] = (code >> 8) & 0xFF
        ram[p + 1] = code & 0xFF
        ram[p + 6] = typ & 0xFF
    return cpu.call(ADDR, r4=dtc, ram=ram)


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(0x63834)

    vectors = gen_edges() + gen_random(rng, n)

    # (a) ROM behaviour via the emulator (r4 = dtc, sparse RAM overlay).
    emu = [seed_and_call(cpu, dtc, cur, rows) for dtc, cur, rows in vectors]

    # (b) host C on the same inputs.
    lines = ['obd %08X %04X %s' % (dtc, cur,
                                   ' '.join('%04X %02X' % r for r in rows))
             for dtc, cur, rows in vectors]
    host = [int(x, 16) for x in run_oracle(oracle, lines)]

    # (c) compare the 32-bit results.
    mismatches = []
    for i, ((dtc, cur, rows), e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d dtc=%04X cur=%04X first-rows=%s ROM=0x%08X C=0x%08X'
                % (i, dtc & 0xFFFF, cur & 0xFFFF,
                   ['%04X:%02X' % r for r in rows[:3]], e, h))
            if len(mismatches) >= 5:
                break

    report('obd_service_handler_63834', ADDR, n, mismatches, edges=len(vectors))


if __name__ == '__main__':
    main()
