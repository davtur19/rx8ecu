#!/usr/bin/env python3
"""
harness_can_table_lookup_583e4.py — equivalence of rx8_can_table_lookup_583e4
@0x583E4.

Reconstructed source: samples/src/rx8_can_table_lookup_583e4.c
Verified lift   : c/memory_match_accumulate_583E4.c (same address; the REAL
                  ROM bytes are executed for real here via tools/sh2emu.py).

The function scans a fixed 36-entry, 6-byte-per-entry CAN filter table in ROM
(0x0005FFEE) and returns `r4 & accum`, where accum sums the SIGN-EXTENDED
data byte (+2) of every entry matching:

    1. entry signature (u16 BE at +0) == RAM16[0xFFFFD226]  (expected id)
    2. entry filter   (u8  at +3)     == (r5 & 0xFF)
    3. entry word     (u16 BE at +4)  & RAM16[0xFFFFD3F0]   != 0

It has NO side effects (no RAM writes, no callees): the whole effect is the
ABI return value in r0, so the equivalence check compares r0:

  - emulator side: seed the two input RAM cells in the sparse ram overlay
    (expected id @0xFFFFD226, bitmask @0xFFFFD3F0), call the ROM entry
    @0x583E4 with r4 = mask / r5 = filter, read r0 back;
  - host side: the dedicated oracle mmap()s the pages backing the two RAM
    cells AND the ROM pages holding the table (0x5F000/0x60000) straight
    from the stock bin ($RX8_ROM_PATH), seeds the same cells big-endian,
    runs the reconstructed C and prints the same r0.

EDGE vectors cover every signature present in the ROM table (plus
non-matching ids incl. the sign boundary 0x8000), every filter byte that
appears in the table (0x00/0x01/0x02/0x05/0xFF), bitmask values that include
the table's own 0xFFFC/0x0001/0x155C/0x9DDC/0x0000 word patterns and the
r4-mask edge set (0 / 1 / low byte / low word / 0x7FFFFFFF / 0x80000000 /
0xFFFFFFFF); N random vectors follow (fixed seed 0x60E1D400) with ids biased
toward in-table signatures so the accumulate paths stay exercised.

Usage:  python3 harness_can_table_lookup_583e4.py [N]  (default N = 20000)
"""
import os
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROM_PATH, load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0x583E4
N_DEFAULT = 20000
SEED = 0x60E1D400
BUILD_DIR = '/tmp/rx8-recon-can_table_lookup_583e4'

# RAM input cells.
SIG_ADDR = 0xFFFFD226          # u16 expected CAN id / signature (input)
BM_ADDR = 0xFFFFD3F0           # u16 bitmask (input)

# ROM calibration table (fixed, read-only; must stay as the stock bin has it).
TBL_BASE = 0x0005FFEE          # 36 x 6-byte CAN filter entries

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def build_oracle(cc='cc'):
    """Compile the reconstructed source + its dedicated oracle into a binary."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_can_table_lookup_583e4.c'),
           os.path.join(SAMPLES, 'src', 'rx8_can_table_lookup_583e4.c'),
           '-lm',
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def seed(init, addr, n, val):
    """Byte-exact big-endian store of a width-`n` value in the ram overlay."""
    for i in range(n):
        init[addr + i] = (val >> (8 * (n - 1 - i))) & 0xFF


def check_table(cpu):
    """The 36 scanned table rows are ROM-fixed; refuse to run if the stock
    bin ever changes so the ROM-page mapping stays meaningful."""
    want = [0x0968, 0x0968, 0x09D3, 0x1101, 0x1101, 0x1101, 0x1102, 0x1103,
            0x1103, 0x1103, 0x1103, 0x1104, 0x1104, 0x1631, 0x1631, 0x1681,
            0x1688, 0xA211, 0xA211, 0xA211, 0x1711, 0x1706, 0x1718, 0x1715,
            0x1715, 0x17DE, 0x1710, 0x1710, 0x1710, 0x1710, 0x1710, 0x1710,
            0xFF10, 0xFF10, 0xFF10, 0xFF10]
    for i, w in enumerate(want):
        got = struct.unpack_from('>H', cpu.rom, TBL_BASE + i * 6)[0]
        if got != w:
            raise RuntimeError('unexpected CAN table @0x%X entry %d: '
                               'got %04X want %04X' % (TBL_BASE, i, got, w))


def run_emu(cpu, vec):
    """Seed the two input cells, run the ROM bytes @0x583E4 and return r0."""
    mask, flt, sig, bm = vec
    init = {}
    seed(init, SIG_ADDR, 2, sig & 0xFFFF)
    seed(init, BM_ADDR, 2, bm & 0xFFFF)
    r0 = cpu.call(ADDR, r4=mask & 0xFFFFFFFF, r5=flt & 0xFF, ram=init)
    return (r0 & 0xFFFFFFFF,)


def gen_edges():
    """Edge pre-states (mask, filter, sig, bitmask) targeting every branch."""
    v = []
    # Signatures present in the ROM table (see rx8_can_table_lookup_583e4.c)
    # plus non-matching ids around the sign boundary and the 0/0xFFFF ends.
    sigs = [0x0968, 0x09D3, 0x1101, 0x1102, 0x1103, 0x1104, 0x1631, 0x1681,
            0x1688, 0xA211, 0x1711, 0x1706, 0x1718, 0x1715, 0x17DE, 0x1710,
            0xFF10, 0x0000, 0x7FFF, 0x8000, 0xA000, 0xFFFF, 0x1111, 0x5555,
            0x0080, 0xFF7F]
    filters = [0x00, 0x01, 0x02, 0x05, 0xFF]
    # Table words at +4: 0xFFFC, 0x155C, 0x0000, 0x0001, 0x0005, 0x9DDC — so
    # probe bitmasks that select/clear each of those bit patterns.
    bitmasks = [0x0000, 0x0001, 0x0005, 0x155C, 0x65E1, 0x8000, 0xFFFC,
                0xFFFF]
    masks = [0x00000000, 0x00000001, 0x0000000F, 0x0000FFFF, 0x7FFFFFFF,
             0x80000000, 0xFFFFFFFF]
    # (a) full signature x filter cross at the two extreme r4 masks.
    for sig in sigs:
        for flt in filters:
            for bm in bitmasks:
                v.append((0xFFFFFFFF, flt, sig, bm))
                v.append((0x00000000, flt, sig, bm))
    # (b) every r4 mask at the hot signatures / filters / bitmasks.
    for m in masks:
        for sig in (0x1103, 0x1710, 0x1715, 0x1711, 0xFF10, 0x0968, 0xFFFF,
                    0x8000):
            for flt in (0x00, 0x01, 0x05):
                for bm in (0x0000, 0x0001, 0xFFFC, 0xFFFF):
                    v.append((m, flt, sig, bm))
    return v


def gen_random(rng, n):
    """n random vectors: ids biased toward in-table signatures, the rest
    uniform over the full byte/word range of every input."""
    v = []
    for _ in range(n):
        if rng.random() < 0.5:
            sig = rng.choice([0x0968, 0x09D3, 0x1101, 0x1103, 0xA211,
                              0x1710, 0x1711, 0x1715, 0x17DE, 0xFF10,
                              rng.getrandbits(16)])
        else:
            sig = rng.getrandbits(16)
        v.append((rng.getrandbits(32),      # r4 mask
                  rng.getrandbits(8),       # r5 filter byte
                  sig & 0xFFFF,
                  rng.getrandbits(16)))     # bitmask
    return v


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(SEED)
    check_table(cpu)
    os.environ['RX8_ROM_PATH'] = ROM_PATH

    EDGE = gen_edges()
    vectors = EDGE + gen_random(rng, n)

    # (a) ROM behaviour via the emulator (real ROM bytes @0x583E4).
    emu = [run_emu(cpu, v) for v in vectors]

    # (b) host-C on the same pre-states (table mapped from the stock bin).
    lines = ['tbl %08X %02X %04X %04X' % v for v in vectors]
    host = [tuple(int(x, 16) for x in out.split())
            for out in run_oracle(oracle, lines)]

    # (c) compare the r0 return value byte-for-byte.
    mismatches = []
    for i, (v, e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d mask=%08X filter=%02X sig=%04X bitmask=%04X '
                'ROM=%08X C=%08X' % (i, v[0], v[1], v[2], v[3],
                                     e[0], h[0]))
            if len(mismatches) >= 5:
                break

    report('can_table_lookup_583e4', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
