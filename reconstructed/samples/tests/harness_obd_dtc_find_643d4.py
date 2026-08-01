#!/usr/bin/env python3
"""
harness_obd_dtc_find_643d4.py — equivalence of rx8_obd_dtc_find_643d4 @0x643D4.

Reconstructed source: samples/src/rx8_obd_dtc_find_643d4.c
Verified lift   : c/obd_dtc_find_0x643D4.c (OBD DTC-table search leaf @0x643D4)

CALLING CONVENTION: plain ABI.  The ROM function is entered with the 16-bit DTC
key in r4 and returns the int32_t result in r0, so `cpu.call()` works directly
(no call_leaf needed).  It reads three things from fixed RAM — the 21 rows'
16-bit words (0xFFFF8930, stride 0x34), their byte-0x06 status fields, and the
active-row-index word 0xFFFF8D74 — and WRITES NOTHING to the DTC table (the
only store in the 66 bytes is `sts.l macl,@-r15`, the caller-unbalanced stack
save; the RAM side-effect check below asserts the whole table region is
untouched).

Procedure (Track-A pattern):
  1. build host oracle (system gcc),
  2. edge vectors (boundaries 0x0000/0xFFFF, first/last-row hits, active-row
     skip, all-rows-match, duplicate keys, s8 sign boundaries 0x00/0x7F/0x80/
     0xFF, currow outside the table, key upper bits ignored) + N random
     (guaranteed-hit rows planted with 15% probability),
  3. run the ROM bytes @0x643D4 in tools/sh2emu.py on the same vectors,
  4. run the host C on the same vectors (words/bytes shipped inline, big-endian
     byte order on the emulator side, native LE u16 on the host side),
  5. compare the int32_t returns AND verify the emulated DTC-table region bytes
     are unchanged — 0 mismatches required.

Usage:  python3 harness_obd_dtc_find_643d4.py [N]   (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROM_PATH, make_rng, report, run_oracle  # noqa: E402
from sh2emu import SH2  # noqa: E402

ADDR = 0x643D4
N_DEFAULT = 20000

DTC_BASE = 0xFFFF8930
DTC_STRIDE = 0x34
DTC_ROWS = 0x15
DTC_CURROW = 0xFFFF8D74

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = '/tmp/rx8-recon-obd_dtc_find_643d4'

# (r4, currow, words[21], b06s[21])  — key, active row, row words, status bytes.
EDGE = []


def _mk(r4, currow, words=None, b06s=None):
    w = words if words is not None else [0x0000] * DTC_ROWS
    b = b06s if b06s is not None else [0x00] * DTC_ROWS
    return (r4, currow, w, b)


# key boundaries 0x0000 / 0xFFFF with a single hit (incl. s8 sign cases)
for key in (0x0000, 0xFFFF):
    for b06 in (0x00, 0x7F, 0x80, 0xFF):      # sign-extension boundaries
        EDGE.append((key, 1, [key] + [0] * (DTC_ROWS - 1),
                     [b06] + [0] * (DTC_ROWS - 1)))
# first-row hit with currow elsewhere, and the currow-skip case
EDGE.append(_mk(0x1234, 1, [0x1234] + [0] * (DTC_ROWS - 1), [0xAB] + [0] * 20))
EDGE.append(_mk(0x1234, 0))                    # only hit row is the active one -> 0
# last-row hit (i = 0x14)
EDGE.append(_mk(0x00FF, 0, [0] * 20 + [0x00FF], [0] * 20 + [0xFF]))
# all rows match: first non-active row wins
EDGE.append(_mk(0x7777, 0, [0x7777] * DTC_ROWS, list(range(DTC_ROWS))))
EDGE.append(_mk(0x7777, 1, [0x7777] * DTC_ROWS, list(range(DTC_ROWS))))
EDGE.append(_mk(0x7777, 0x14, [0x7777] * DTC_ROWS, list(range(DTC_ROWS))))
EDGE.append(_mk(0x7777, 0xFFFF, [0x7777] * DTC_ROWS, list(range(DTC_ROWS))))
# duplicate keys in two rows: active-row skip must pick the second
EDGE.append(_mk(0x5555, 3, [0x5555, 0x5555] + [0] * (DTC_ROWS - 2),
                [0x10, 0x20] + [0] * (DTC_ROWS - 2)))
# no match at all -> 0
EDGE.append(_mk(0xDEAD, 5, [0x0001] * DTC_ROWS, [0x00] * DTC_ROWS))
# key upper 16 bits must be masked off by the ROM's extu.w compare
EDGE.append(_mk(0x12345678, 0, [0x5678] + [0] * (DTC_ROWS - 1),
                [0x42] + [0] * (DTC_ROWS - 1)))
# r4 = 0 with a zero word in a later row (word==0 is a valid key)
EDGE.append(_mk(0x0000, 0, [0x0001] + [0x0000] + [0] * (DTC_ROWS - 2),
                [0x01, 0x02] + [0] * (DTC_ROWS - 2)))


def build_oracle(cc='cc'):
    """Compile the reconstructed source + its own oracle into a host binary."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_obd_dtc_find_643d4.c'),
           os.path.join(SAMPLES, 'src', 'rx8_obd_dtc_find_643d4.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def row_addr(i, off=0):
    return (DTC_BASE + i * DTC_STRIDE + off) & 0xFFFFFFFF


def emu_ram(r4, currow, words, b06s):
    """Big-endian byte layout: the emulator's mov.w reads byte@a<<8|byte@a+1,
    so a word w goes in as hi,lo — the same numeric value the LE host oracle
    stores natively and the C lift reads back."""
    ram = {DTC_CURROW: (currow >> 8) & 0xFF, DTC_CURROW + 1: currow & 0xFF}
    for i in range(DTC_ROWS):
        w = words[i] & 0xFFFF
        ram[row_addr(i, 0)] = (w >> 8) & 0xFF
        ram[row_addr(i, 1)] = w & 0xFF
        ram[row_addr(i, 6)] = b06s[i] & 0xFF
    return ram


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    with open(ROM_PATH, 'rb') as f:
        cpu = SH2(f.read())
    oracle = build_oracle()
    rng = make_rng(0x60E1D400)

    def gen_random(k):
        v = []
        for _ in range(k):
            r4 = rng.getrandbits(16)
            currow = rng.randrange(0, 0x15) if rng.random() < 0.9 else 0xFFFF
            words = [rng.getrandbits(16) for _ in range(DTC_ROWS)]
            b06s = [rng.getrandbits(8) for _ in range(DTC_ROWS)]
            if rng.random() < 0.15:                     # plant a guaranteed hit
                i = rng.randrange(0, DTC_ROWS)
                if i == currow:
                    i = (i + 1) % DTC_ROWS
                words[i] = r4
                b06s[i] = rng.getrandbits(8)
            v.append((r4, currow, words, b06s))
        return v

    vectors = list(EDGE) + gen_random(n)

    # (a) ROM behaviour via the emulator (r4 = key); assert no DTC-table writes.
    emu = []
    for r4, currow, words, b06s in vectors:
        ram = emu_ram(r4, currow, words, b06s)
        before = dict(ram)
        cpu.call(ADDR, r4=r4, ram=ram)
        emu.append(cpu.r[0] & 0xFFFFFFFF)
        for k in range(DTC_ROWS):
            for off in (0, 1, 6):
                a = row_addr(k, off)
                if cpu.ram[a] != before[a]:
                    raise RuntimeError(
                        'ROM wrote DTC table byte @0x%X (vec r4=%04X)'
                        % (a, r4))

    # (b) host C on the same inputs (words + bytes shipped inline).
    lines = ['dtc %04X %04X %s %s'
             % (r4 & 0xFFFF, currow & 0xFFFF,
                ' '.join('%04X' % (w & 0xFFFF) for w in words),
                ' '.join('%02X' % (b & 0xFF) for b in b06s))
             for r4, currow, words, b06s in vectors]
    host = [int(x, 16) for x in run_oracle(oracle, lines)]

    # (c) compare the int32_t returns.
    mismatches = []
    for k, ((r4, currow, words, b06s), e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d r4=%04X currow=%X words=%s ROM=0x%08X C=0x%08X'
                % (k, r4 & 0xFFFF, currow & 0xFFFF,
                   ' '.join('%04X' % w for w in words), e, h))
            if len(mismatches) >= 5:
                break

    report('obd_dtc_find_643d4', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
