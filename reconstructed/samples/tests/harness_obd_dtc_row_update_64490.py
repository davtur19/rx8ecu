#!/usr/bin/env python3
"""
harness_obd_dtc_row_update_64490.py — equivalence of
rx8_obd_dtc_row_update_64490 @0x64490.

Reconstructed source: samples/src/rx8_obd_dtc_row_update_64490.c
Verified lift   : c/obd_dtc_row_update_0x64490.c  (obd_dtc_row_update_0x64490,
                  0x64490..0x644C4, 52 bytes, verified in c/tests/).

Side-effect leaf, takes r4 (16-bit delta word).  Active row = u16@0xFFFF8D74,
table base 0xFFFF8930, stride 0x34:

    row = word@0xFFFF8D74
    p   = 0xFFFF8930 + row * 0x34
    w   = word@p+0x02
    delta = (s16(w) + ((w>>8)&0xFF)) - (r4 + ((r4&0xFFFF)>>8))
    p[0x32] = (s8(p[0x32]) + delta) & 0xFF
    word@p+0x02 = r4 & 0xFFFF

so the equivalence check compares RAM side-effects, not a return value:

  - emulator side: seed the row-index word + the row cells in the sparse ram
    overlay, call the ROM entry @0x64490, read the cells back;
  - host side: the dedicated oracle mmap()s the on-chip RAM pages, seeds the
    same logical values, runs the reconstructed C, reads the cells back.

ROW SPACE: rows 0..0x1AA (=426) keep p+0x32 inside the on-chip RAM window
(pages 0xFFFF8000..0xFFFFD000) and are compared on BOTH sides.  Larger rows
wrap p through 32-bit arithmetic below mmap_min_addr on this host, so they
cannot be run in the host oracle; the harness additionally sweeps the full
16-bit row space on the emulator side against the same formula (emulator-only
sanity, reported separately).

Usage:  python3 harness_obd_dtc_row_update_64490.py [N]   (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, SAMPLES  # noqa: E402

ADDR = 0x64490
ROW_ADDR = 0xFFFF8D74
BASE = 0xFFFF8930
STRIDE = 0x34
MAX_ROW = 0x1AA            # largest row whose p+0x32 stays in the mapped pages
N_DEFAULT = 20000
BUILD_DIR = '/tmp/rx8-recon-obd_dtc_row_update_64490'


def addr(row, off):
    """Row-cell byte address, 32-bit wrap exactly like the ROM's add."""
    return (BASE + (row & 0xFFFF) * STRIDE + off) & 0xFFFFFFFF


def s8(x):
    x &= 0xFF
    return x - 256 if x & 0x80 else x


def s16(x):
    x &= 0xFFFF
    return x - 0x10000 if x & 0x8000 else x


def model(r4, row, b32, w):
    """Behavioural reference: byte-exact mirror of the ROM's 32-bit fold
    (identical to the c/ lift)."""
    delta = (s16(w) + ((w & 0xFFFF) >> 8)) - (r4 & 0xFFFFFFFF) \
            - ((r4 & 0xFFFF) >> 8)
    return ((s8(b32) + delta) & 0xFF, r4 & 0xFFFF)


# Edge vectors: (r4, row, b32, w).  Boundary rows 0/1/last, byte values
# 0x00/0x01/0x7F/0x80/0xFF bracket the sign-extension path of the mov.b load,
# 16-bit values 0x0000/0x0001/0x00FF/0x0100/0x7FFF/0x8000/0x8001/0xFFFF bracket
# the mov.w load and its shlr8 split, and r4 covers 16-bit AND full 32-bit
# values (the fold's `add r4,r7` uses the full register; only the stored low
# byte/word depend on r4 & 0xFF/0xFFFF, but bit-exactness must hold for the
# intermediate too).
EDGE = []
_BV = [0x00, 0x01, 0x7E, 0x7F, 0x80, 0x81, 0xFE, 0xFF]
_WV = [0x0000, 0x0001, 0x00FF, 0x0100, 0x7FFF, 0x8000, 0x8001, 0xFFFF]
for _row in (0, 1, 2, 0x10, 0x100, MAX_ROW):
    for _r4 in (0x0000, 0x0001, 0x007F, 0x0080, 0x00FF, 0x8000, 0xFFFF):
        for _b32 in _BV:
            for _w in _WV:
                EDGE.append((_r4, _row, _b32, _w))
# full-32-bit r4 pinpoints: high bits must not corrupt the fold or the store.
for _r4 in (0x0100, 0x7FFF0000, 0x80000000, 0xFFFFFF00, 0xFFFFFFFF):
    for _b32 in _BV:
        for _w in _WV:
            EDGE.append((_r4, 0, _b32, _w))


def build_oracle(cc='cc'):
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_obd_dtc_row_update_64490.c'),
           os.path.join(SAMPLES, 'src', 'rx8_obd_dtc_row_update_64490.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def run_oracle(oracle, vectors):
    proc = subprocess.run([oracle], input='\n'.join(vectors) + '\n',
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError('host oracle failed:\n' + proc.stderr)
    lines = proc.stdout.splitlines()
    if len(lines) != len(vectors):
        raise RuntimeError(
            'oracle produced %d outputs for %d vectors' % (len(lines), len(vectors)))
    return lines


def run_emu(cpu, r4, row, b32, w):
    """Seed the ROM state and call the actual ROM bytes @0x64490."""
    ram = {ROW_ADDR: (row >> 8) & 0xFF, ROW_ADDR + 1: row & 0xFF,
           addr(row, 0x32): b32 & 0xFF,
           addr(row, 0x02): (w >> 8) & 0xFF, addr(row, 0x03): w & 0xFF}
    cpu.call(ADDR, r4=r4 & 0xFFFFFFFF, ram=ram)
    return (cpu.rd(addr(row, 0x32), 1), cpu.rd(addr(row, 0x02), 2))


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(0x64490)

    # Random vectors: row within the host-mappable on-chip RAM window, r4 full
    # 32-bit range (exercises the full-register fold), cells full range.
    vectors = list(EDGE) + [(rng.randint(0, 0xFFFFFFFF), rng.randint(0, MAX_ROW),
                             rng.randint(0, 0xFF), rng.randint(0, 0xFFFF))
                            for _ in range(n)]

    # (a) ROM behaviour via the emulator (RAM side-effects).
    emu = [run_emu(cpu, r4, row, b32, w) for r4, row, b32, w in vectors]

    # (b) host-C on the same pre-states.
    lines = ['dtc %04X %02X %04X %08X' % (row, b32, w, r4)
             for r4, row, b32, w in vectors]
    host = [tuple(int(x, 16) for x in out.split())
            for out in run_oracle(oracle, lines)]

    # (c) compare.
    mismatches = []
    for i, ((r4, row, b32, w), e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d r4=%08X row=%04X (b32,w)=(%02X,%04X) ROM=(%02X,%04X) C=(%02X,%04X)'
                % (i, r4 & 0xFFFFFFFF, row, b32, w, e[0], e[1], h[0], h[1]))
            if len(mismatches) >= 5:
                break

    # (d) emulator-only sweep of the FULL 16-bit row space (wrap-around rows
    # land below mmap_min_addr on the host; not comparable to the C there).
    wraps = [run_emu(cpu, r, r, r, r) for r in (0xFFFF, 0xFFFE, 0x8000, 0x7FFF)]
    wrap_ok = all(w == model(r, r, r, r)
                  for w, r in zip(wraps, (0xFFFF, 0xFFFE, 0x8000, 0x7FFF)))

    report('obd_dtc_row_update_64490', ADDR, n, mismatches, edges=len(EDGE))
    if not wrap_ok:
        print('FAIL emulator-only row-wrap sanity: %s' % (wraps,))
        sys.exit(1)


if __name__ == '__main__':
    main()
