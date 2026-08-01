#!/usr/bin/env python3
"""
harness_obd_dtc_row_update_64258.py — equivalence of
rx8_obd_dtc_row_update_64258 @0x64258.

Reconstructed source: samples/src/rx8_obd_dtc_row_update_64258.c
Verified lift   : c/obd_dtc_row_update_0x64258.c (side-effect-only leaf over
                  the OBD DTC table @0xFFFF8930, stride 0x34, active row =
                  word @0xFFFF8D74).

CALLING CONVENTION: the ROM routine takes NO register arguments — it reads the
active-row index from RAM (0xFFFF8D74) and updates three bytes of the active
row (offsets 0x07/0x08/0x32).  `cpu.call()` seeds r4-r7 and a sparse RAM
overlay, which is exactly what is needed; there is no non-ABI register input,
so no `call_leaf` driver is required.  Return r0 (= 7) is meaningless — the
equivalence is over RAM side-effects:

  p[0x32] = (p[0x32] + p[0x07] + 0xFF) & 0xFF
  p[0x07] = 1
  p[0x32] = (p[0x32] + p[0x08] + 0xF9) & 0xFF
  p[0x08] = 7

The oracle also echoes the row-index word back; the ROM never writes it, so it
must be unchanged — an over/under-run guard for the host pointer math.

Procedure (Track-A pattern):
  1. build host oracle (system gcc; -O2, -Wall, -Wextra),
  2. edge vectors (all byte corners x rows {0, 1, 0x14}) + N random
     (row in 0..0x14, three random bytes),
  3. run the ROM bytes @0x64258 in tools/sh2emu.py on the same vectors,
  4. run the host C on the same vectors,
  5. compare the three side-effected bytes + the untouched row word —
     0 mismatches required.

Usage:  python3 harness_obd_dtc_row_update_64258.py [N]   (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0x64258
N_DEFAULT = 20000

ROW_INDEX_ADDR = 0xFFFF8D74   # 16-bit active-row index word (mov.w read)
BASE = 0xFFFF8930             # OBD DTC table base
STRIDE = 0x34
ROWS = 0x14                   # 21 rows: 0..0x14 (table bounded by its own index)

# This harness' own build dir (kept separate from the shared host_oracle build).
SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = '/tmp/rx8-recon-obd_dtc_row_update_64258'

# Corner bytes: 0x00/0xFF bounds, the +255/+249 addends' carry neighbours
# (0x06/0x07/0x08), and 0x7F/0x80 for the mov.b sign-extension edge.
CORNER = [0x00, 0x01, 0x06, 0x07, 0x08, 0x7F, 0x80, 0xFF]
EDGE_ROWS = [0x00, 0x01, 0x14]


def paddr(row):
    """Effective row byte address, 32-bit wrapped like the SH-2."""
    return (BASE + (row & 0xFFFF) * STRIDE) & 0xFFFFFFFF


def seed_ram(row, b32, b07, b08):
    """Sparse-RAM overlay: row-index word (big-endian) + the three row bytes."""
    a = paddr(row)
    return {ROW_INDEX_ADDR: (row >> 8) & 0xFF, ROW_INDEX_ADDR + 1: row & 0xFF,
            a + 0x32: b32, a + 0x07: b07, a + 0x08: b08}


def run_emu(cpu, row, b32, b07, b08):
    """Run the ROM bytes and return (p[0x32]', p[0x07]', p[0x08]', row-word)."""
    cpu.call(ADDR, ram=seed_ram(row, b32, b07, b08))
    a = paddr(row)
    rword = (cpu.ram.get(ROW_INDEX_ADDR, 0) << 8) | cpu.ram.get(ROW_INDEX_ADDR + 1, 0)
    return (cpu.ram.get(a + 0x32, 0), cpu.ram.get(a + 0x07, 0),
            cpu.ram.get(a + 0x08, 0), rword)


def build_oracle(cc='cc'):
    """Compile this harness' own oracle (oracle + reconstructed source)."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_obd_dtc_row_update_64258.c'),
           os.path.join(SAMPLES, 'src', 'rx8_obd_dtc_row_update_64258.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def build_vectors(n):
    """Edge vectors (every corner-byte combo on boundary rows) + random ones."""
    rng = make_rng(0x64258)
    edge = [(row, b32, b07, b08)
            for row in EDGE_ROWS
            for b32 in CORNER
            for b07 in CORNER
            for b08 in CORNER]
    rand = [(rng.randint(0, ROWS), rng.getrandbits(8),
             rng.getrandbits(8), rng.getrandbits(8)) for _ in range(n)]
    return edge + rand


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    vectors = build_vectors(n)
    n_edges = len(vectors) - n

    # (a) ROM behaviour via the emulator (seeded RAM, side-effect compare).
    emu = [run_emu(cpu, r, b32, b07, b08) for r, b32, b07, b08 in vectors]

    # (b) host C on the same vectors.
    lines = ['dtc %04X %02X %02X %02X' % (r, b32, b07, b08)
             for r, b32, b07, b08 in vectors]
    host = [tuple(int(x, 16) for x in out.split())
            for out in run_oracle(oracle, lines)]

    # (c) compare.
    mismatches = []
    for i, (v, e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            r, b32, b07, b08 = v
            mismatches.append('vec#%d row=0x%02X (b32,b07,b08)=(%02X,%02X,%02X) '
                              'ROM=(%02X,%02X,%02X,%04X) C=(%02X,%02X,%02X,%04X)'
                              % (i, r, b32, b07, b08, e[0], e[1], e[2], e[3],
                                 h[0], h[1], h[2], h[3]))
            if len(mismatches) >= 5:
                break

    report('obd_dtc_row_update_64258', ADDR, n, mismatches, edges=n_edges)


if __name__ == '__main__':
    main()
