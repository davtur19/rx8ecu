#!/usr/bin/env python3
"""
harness_obd_dtc_find_6443e.py — equivalence of rx8_obd_dtc_find_6443e @0x6443E.

Reconstructed source: samples/src/rx8_obd_dtc_find_6443e.c
Verified lift   : c/obd_dtc_find_0x6443E.c (verified vs the ROM emulator in
                  c/tests/test_obd_dtc_find_0x6443E.{py,c})

CALLING CONVENTION: normal ABI entry — r4 = byte search key, result returned
in r0 (sign-extended byte@row+0x08, or the default 0x08), so the plain
`cpu.call()` driver is used.  The leaf only READS the DTC table
(0xFFFF8930, 21 rows x 0x34) and the row-index word @0xFFFF8D74; its only RAM
writes go to the r15 stack area (r14/macl pushes).  To prove the DTC state is
untouched, both sides also print a checksum of the DTC-table region, and the
emulator-side pre/post call checksums are compared as well.

Procedure (Track-A pattern):
  1. build the host oracle (system gcc; -O2, -Wall, -Wextra),
  2. edge vectors (empty table, single hit at every row, hit on the current
     row only -> skipped, all-rows-hit first-wins, currow at/outside bounds,
     key high-bit masking, b08 sign flips) + N random vectors
     (40% force at least one hit),
  3. run the ROM bytes @0x6443E in tools/sh2emu.py on the same vectors,
  4. run the host C on the same vectors,
  5. compare the 32-bit return values and the region checksums — 0 mismatches.

Usage:  python3 harness_obd_dtc_find_6443e.py [N]   (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0x6443E
N_DEFAULT = 20000

DTC_BASE = 0xFFFF8930
DTC_STRIDE = 0x34
DTC_ROWS = 0x15
DTC_CURROW = 0xFFFF8D74
DTC_CKSUM_LEN = DTC_ROWS * DTC_STRIDE        # byte-accessed rows only

# This harness' own build dir (kept separate from the shared host_oracle build).
SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = '/tmp/rx8-recon-obd_dtc_find_6443e'

KEYS = [0x00, 0x01, 0x02, 0x7F, 0x80, 0xFE, 0xFF]
B08S = [0x00, 0x01, 0x7F, 0x80, 0xC3, 0x3C, 0xFE, 0xFF]   # incl. sign flips


def gen_edges():
    """Edge vectors: every key/currow combination on an empty table; a single
    hit at every row (hit and skip-it variants); every-row-hit (first row
    wins unless it is the current row); currow at/outside the 0..0x14 range;
    r4 with garbage in the high bits (must be masked to 8)."""
    v = []
    empty = [0] * DTC_ROWS
    for k in KEYS:
        for cur in range(DTC_ROWS):
            v.append((k, cur, empty, empty))            # no hit -> 0x08

    for row in range(DTC_ROWS):
        for k in KEYS:
            for b08 in B08S:
                b06s = [0] * DTC_ROWS
                b08s = [0] * DTC_ROWS
                b06s[row] = k
                b08s[row] = b08
                for cur in (0, DTC_ROWS - 1):
                    v.append((k, cur, b06s, b08s))      # hit row != currow
        # hit ONLY at the current row -> skipped -> 0x08
        b06s = [0] * DTC_ROWS
        b08s = [0] * DTC_ROWS
        b06s[row] = 0x5A
        b08s[row] = 0xC3
        v.append((0x5A, row, b06s, b08s))

    for k in KEYS:
        b06s = [k] * DTC_ROWS
        b08s = [(0x80 + i) & 0xFF for i in range(DTC_ROWS)]
        for cur in list(range(DTC_ROWS)) + [0x15, 0xFFFF]:
            v.append((k, cur, b06s, b08s))              # first (non-cur) row wins

    # high-bit masking of r4 (leaf only looks at r4 & 0xFF)
    b06s = [0] * DTC_ROWS
    b08s = [0] * DTC_ROWS
    b06s[3] = 0x7F
    b08s[3] = 0xFF
    for extra in (0x100, 0x1FF, 0x80000000, 0xFFFFFF00, 0xFFFFFF80):
        v.append((extra | 0x7F, 7, b06s, b08s))         # low byte 0x7F -> hit
        v.append((extra | 0x80, 7, b06s, b08s))         # low byte 0x80 -> miss
    return v


def gen_random(rng, n):
    """n random vectors: full-32-bit key, 16-bit currow (so >= 0x15 skips
    nothing), random columns.  40% force a hit (and sometimes a second hit
    behind a skipped current row)."""
    v = []
    for _ in range(n):
        r4 = rng.getrandbits(32)
        currow = rng.getrandbits(16)
        b06s = [rng.randrange(256) for _ in range(DTC_ROWS)]
        b08s = [rng.randrange(256) for _ in range(DTC_ROWS)]
        if rng.random() < 0.4:
            row = rng.randrange(DTC_ROWS)
            b06s[row] = r4 & 0xFF
            if rng.random() < 0.3 and currow <= 0x14:
                b06s[(row + 1) % DTC_ROWS] = r4 & 0xFF
        v.append((r4 & 0xFFFFFFFF, currow & 0xFFFF, b06s, b08s))
    return v


def row_ram(b06s, b08s, currow):
    """Big-endian sparse-RAM image of the DTC table + currow word, matching
    the oracle's seeding (unlisted bytes zeroed)."""
    ram = {}
    for i in range(DTC_ROWS):
        base = DTC_BASE + i * DTC_STRIDE
        for j in range(DTC_STRIDE):
            ram[base + j] = 0
        ram[base + 0x06] = b06s[i] & 0xFF
        ram[base + 0x08] = b08s[i] & 0xFF
    ram[DTC_CURROW] = (currow >> 8) & 0xFF
    ram[DTC_CURROW + 1] = currow & 0xFF
    return ram


def cksum(ram):
    return sum(ram.get(a, 0) for a in range(DTC_BASE, DTC_BASE + DTC_CKSUM_LEN)) \
        & 0xFFFFFFFF


def build_oracle(cc='cc'):
    """Compile this harness' own oracle (oracle_obd_dtc_find_6443e.c + source)."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_obd_dtc_find_6443e.c'),
           os.path.join(SAMPLES, 'src', 'rx8_obd_dtc_find_6443e.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(0x6443E)

    vectors = gen_edges() + gen_random(rng, n)

    # (a) ROM behaviour via the emulator (r4 = key) + region checksum.
    emu = []
    for (r4, cur, b06s, b08s) in vectors:
        ram = row_ram(b06s, b08s, cur)
        pre = cksum(ram)
        cpu.call(ADDR, r4=r4, ram=ram)
        ret = cpu.r[0] & 0xFFFFFFFF
        post = cksum(cpu.ram)
        if pre != post:
            emu.append((ret | 0x80000000, post))        # flag: ROM wrote the region
        else:
            emu.append((ret, post))

    # (b) host C on the same inputs.
    def fmt_b(y):
        return ''.join('%02X' % b for b in y)

    lines = ['dtc %08X %04X %s %s'
             % (r4, cur, fmt_b(b06s), fmt_b(b08s))
             for (r4, cur, b06s, b08s) in vectors]
    host = []
    for out in run_oracle(oracle, lines):
        a, b = out.split()
        host.append((int(a, 16), int(b, 16)))

    # (c) compare return values and region checksums.
    mismatches = []
    for k, ((r4, cur, b06s, b08s), e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d r4=0x%08X cur=0x%04X b06=%s b08=%s ROM=%08X/%08X C=%08X/%08X'
                % (k, r4, cur, fmt_b(b06s), fmt_b(b08s), e[0], e[1], h[0], h[1]))
            if len(mismatches) >= 5:
                break

    report('obd_dtc_find', ADDR, n, mismatches, edges=len(vectors) - n)


if __name__ == '__main__':
    main()
