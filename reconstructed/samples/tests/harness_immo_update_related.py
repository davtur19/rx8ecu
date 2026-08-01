#!/usr/bin/env python3
"""
harness_immo_update_related.py — equivalence of rx8_immo_update_related @0x37120.

Reconstructed source: samples/src/rx8_immo_update_related.c
Verified lift   : c/ImmoUpdateRelated.c  (same address 0x37120)

The ROM function is the immobilizer EEPROM write-queue driver: a `void f(void)`
ABI leaf with no register result, so each "vector" is a fresh INITIAL RAM state
for every cell the chain can observe, and the equivalence check compares every
side-effected cell (exactly like harness_immo_bad_state_set.py, plus the E2
shadow and EEPROM-scheduler cells the inlined callees touch):

  - emulator side: seed the cells as big-endian bytes in the sparse `ram`
    overlay, call the ROM entry 0x37120 with plain `cpu.call()`, read back;
  - host side: the oracle mmap()s the same page (0xFFFFC000), seeds the same
    numeric values, runs the reconstructed C, reads them back.

The ROM internally runs sub_37000 @0x37000 (-> eeprom_write_sched @0x38B5C),
updateE2RAMBasedOnInput @0x36D0C (-> writeToE2RAMArea @0x39124) and the SR
helpers — the emulator executes those REAL bytes while the host C inlines their
net effects (documented in the sample header).  The edge set pins the queue
branches (init-done / armed / busy / work-index==0x5A / pending-code dispatch /
write-done / scheduler status), and the random set jams all 59 cells.

Usage:  python3 harness_immo_update_related.py [N]   (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0x37120
N_DEFAULT = 20000

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = '/tmp/rx8-recon-immo_update_related'

# Compared (output) cells, in vector order: (name, addr, width).  All live on
# the 0xFFFFC000 page.  See the oracle header for the full map.
LOCS_OUT = (
    ('C2D1', 0xFFFFC2D1, 1), ('C2D2', 0xFFFFC2D2, 1),
    ('C2D5', 0xFFFFC2D5, 1), ('C2D6', 0xFFFFC2D6, 1),
    ('C2D7', 0xFFFFC2D7, 1), ('C2D8', 0xFFFFC2D8, 1),
    ('C2F8', 0xFFFFC2F8, 1), ('C511', 0xFFFFC511, 1),
    ('C506', 0xFFFFC506, 2), ('C4FE', 0xFFFFC4FE, 2),
    ('C500', 0xFFFFC500, 2), ('C514', 0xFFFFC514, 1),
    ('C2FB', 0xFFFFC2FB, 1), ('C50C', 0xFFFFC50C, 1),
    ('C50F', 0xFFFFC50F, 1), ('C516', 0xFFFFC516, 1),
    ('C515', 0xFFFFC515, 1), ('C510', 0xFFFFC510, 1),
    ('E2_00', 0xFFFFC2FE, 1), ('E2_0C', 0xFFFFC30A, 1),
    ('E2_0D', 0xFFFFC30B, 1), ('E2_0E', 0xFFFFC30C, 1),
    ('E2_0F', 0xFFFFC30D, 1), ('E2_10', 0xFFFFC30E, 1),
    ('E2_12', 0xFFFFC310, 1), ('E2_13', 0xFFFFC311, 1),
    ('E2_14', 0xFFFFC312, 1), ('E2_1A', 0xFFFFC318, 1),
    ('E2_1B', 0xFFFFC319, 1), ('E2_1C', 0xFFFFC31A, 1),
    ('E2_1D', 0xFFFFC31B, 1), ('E2_1E', 0xFFFFC31C, 1),
    ('C_00', 0xFFFFC3FE, 1), ('C_0C', 0xFFFFC40A, 1),
    ('C_0D', 0xFFFFC40B, 1), ('C_0E', 0xFFFFC40C, 1),
    ('C_0F', 0xFFFFC40D, 1), ('C_10', 0xFFFFC40E, 1),
    ('C_12', 0xFFFFC410, 1), ('C_13', 0xFFFFC411, 1),
    ('C_14', 0xFFFFC412, 1), ('C_1A', 0xFFFFC418, 1),
    ('C_1B', 0xFFFFC419, 1), ('C_1C', 0xFFFFC41A, 1),
    ('C_1D', 0xFFFFC41B, 1), ('C_1E', 0xFFFFC41C, 1),
)

# Seed-only cells read by the inlined updateE2RAMBasedOnInput / writeToE2RAMArea.
LOCS_SRC = (
    ('C2E5', 0xFFFFC2E5, 1), ('C2E6', 0xFFFFC2E6, 1),
    ('C2E7', 0xFFFFC2E7, 1), ('C2E8', 0xFFFFC2E8, 1),
    ('C2E9', 0xFFFFC2E9, 1), ('C2EE', 0xFFFFC2EE, 1),
    ('C2EF', 0xFFFFC2EF, 1), ('C2F0', 0xFFFFC2F0, 1),
    ('C2F1', 0xFFFFC2F1, 1), ('C2F2', 0xFFFFC2F2, 1),
    ('C242', 0xFFFFC242, 1), ('C243', 0xFFFFC243, 1),
    ('C244', 0xFFFFC244, 1),
)

ALL_LOCS = LOCS_OUT + LOCS_SRC
N_IN = len(ALL_LOCS)          # 59 seed tokens
N_OUT = len(LOCS_OUT)         # 46 compared tokens

# Edge vectors: cross product over the branch-relevant cells; everything else
# at a fixed pattern (distinct values detect accidental extra writes).
EDGE_IDX = {'C2D1': 0, 'C2D2': 1, 'C2D5': 2, 'C2D6': 3,
            'C2D7': 4, 'C2D8': 5, 'C2F8': 6, 'C511': 7}
EDGE_CHOICES = {
    'C2D5': [0x00, 0x01, 0xFF],
    'C2D6': [0x00, 0x01],
    'C2D7': [0x00, 0x01],
    'C2D8': [0x00, 0x5A, 0xFF],
    'C2D1': [0x00, 0x03, 0x0C, 0x42, 0xFF],
    'C2D2': [0x00, 0x01],
    'C2F8': [0x00, 0x01],
    'C511': [0x00, 0x01],
}


def edge_base():
    b = [0x00] * N_IN
    b[8] = 0x5555          # C506
    b[9] = 0x3333          # C4FE
    b[10] = 0x7777         # C500
    for i in range(11, 18):
        b[i] = 0x11        # C514, C2FB, C50C, C50F, C516, C515, C510
    for i in range(18, 32):
        b[i] = 0x55        # E2 value shadow
    for i in range(32, 46):
        b[i] = 0x66        # E2 complement shadow
    for i in range(46, N_IN):
        b[i] = 0x99        # E2 work sources / CAN shadows
    return b


def make_edges():
    import itertools
    keys = list(EDGE_CHOICES)
    edges = []
    for combo in itertools.product(*(EDGE_CHOICES[k] for k in keys)):
        v = edge_base()
        for k, val in zip(keys, combo):
            v[EDGE_IDX[k]] = val
        edges.append(tuple(v))
    return edges


EDGES = make_edges()


def build_oracle(cc='cc'):
    """Compile this harness' own oracle (oracle_immo_update_related.c + the
    reconstructed source) into /tmp/rx8-recon-immo_update_related/oracle."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_immo_update_related.c'),
           os.path.join(SAMPLES, 'src', 'rx8_immo_update_related.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def fmt_vec(vec):
    """Vector (59 ints) -> oracle stdin line."""
    return 'immoupd ' + ' '.join('%X' % v for v in vec)


def fmt_res(vals):
    """46 ints -> oracle output line format (u8 %02X, u16 %04X)."""
    return ' '.join('%02X' % v if w == 1 else '%04X' % v
                    for v, (_, _, w) in zip(vals, LOCS_OUT))


def call_rom(cpu, vec):
    """Run the ROM bytes @0x37120 over one initial-RAM-state vector and
    return the 46 final side-effected values as ints."""
    ram = {}
    for (name, addr, width), v in zip(ALL_LOCS, vec):
        for i in range(width):
            ram[(addr + i) & 0xFFFFFFFF] = (v >> (8 * (width - 1 - i))) & 0xFF
    cpu.call(ADDR, ram=ram)
    return tuple(cpu.rd(addr, width) for _, addr, width in LOCS_OUT)


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(0x37120)

    # Edge vectors + N random initial-RAM-state vectors (all 59 cells random;
    # the three u16 cells get 16 random bits).
    vectors = list(EDGES)
    for _ in range(n):
        vectors.append(tuple(rng.getrandbits(w * 8) for _, _, w in ALL_LOCS))

    # (a) ROM behaviour via the emulator, (b) host C on the same vectors.
    emu = [call_rom(cpu, v) for v in vectors]
    host = [fmt_res(tuple(int(x, 16) for x in ln.split()))
            for ln in run_oracle(oracle, [fmt_vec(v) for v in vectors])]

    # (c) compare all 46 side-effected cells.
    mismatches = []
    for i, (v, e, h) in enumerate(zip(vectors, emu, host)):
        if fmt_res(e) != h:
            mismatches.append('vec#%d init=%s ROM=%s C=%s'
                              % (i, fmt_vec(v).replace('immoupd ', ''), fmt_res(e), h))
            if len(mismatches) >= 5:
                break

    report('ImmoUpdateRelated', ADDR, n, mismatches, edges=len(EDGES))


if __name__ == '__main__':
    main()
