#!/usr/bin/env python3
"""
harness_immo_good_state_set.py — equivalence of rx8_immo_good_state_set @0x36544.

Reconstructed source: samples/src/rx8_immo_good_state_set.c
Verified lift   : c/ImmoGoodStateSet.c  (same address 0x36544)

The ROM function is a `void f(void)` leaf: it takes no input registers and has
no meaningful return value — its entire observable behaviour is a fixed set of
writes to on-chip RAM (see the source header for the full side-effect map).
Each "vector" is therefore a fresh INITIAL RAM state for the nine side-effected
locations; the lamp register 0xFFFFF754 is a read-modify-write (setImmoLight(1)
ORs 0x40 then 0x20), so its initial value is the only input that matters.

Two lift discrepancies are exercised and pinned here (see source header):
  - the CAN TX flag is written to 0xFFFFC240, not the lift's 0x0000C240
    (`mov.w @(disp,pc),r3` sign-extends the 16-bit constant 0xC240);
  - the lamp write lands at 0xFFFFF754, not the lift's 0xF754 (same reason
    inside setImmoLight @0x263C8).

Procedure (Track-A pattern):
  1. build the host oracle (system gcc; -O2, -Wall, -Wextra),
  2. edge initial-RAM-state vectors (all-0, all-0xFF, bit patterns around the
     lamp read-modify-write, word-boundary init for the two u16 words) +
     N random initial-state vectors,
  3. run the ROM bytes @0x36544 in tools/sh2emu.py on the same vectors,
  4. run the host C on the same vectors,
  5. compare all nine side-effected values — 0 mismatches required.

Usage:  python3 harness_immo_good_state_set.py [N]   (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0x36544
N_DEFAULT = 20000

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = '/tmp/rx8-recon-immo_good_state_set'

# Nine side-effected locations, in vector order (see source header).
# Tuple: (name, address, width-in-bytes).
LOCS = (
    ('C240', 0xFFFFC240, 1),   # CAN TX flag          = 1
    ('C2F2', 0xFFFFC2F2, 1),   # E2[0x1E] working copy = 2
    ('C29F', 0xFFFFC29F, 1),   # seed machine active   = 1
    ('C282', 0xFFFFC282, 2),   # good-state timer      = 0x3A98
    ('C284', 0xFFFFC284, 2),   # good-state timeout    = 0x00FA
    ('C28C', 0xFFFFC28C, 1),   # reserved result slot  = 0
    ('C28D', 0xFFFFC28D, 1),   # result code 3 (good)  = 3
    ('C29A', 0xFFFFC29A, 1),   # good-state flag       = 0
    ('F754', 0xFFFFF754, 2),   # immo lamp reg         = init | 0x60
)

# Edge vectors: (c240, c2f2, c29f, c282, c284, c28c, c28d, c29a, f754).
# The lamp register is a read-modify-write, so its initial value is the only
# input the function observes; the rest are overwritten with fixed constants.
EDGE = [
    (0x00, 0x00, 0x00, 0x0000, 0x0000, 0x00, 0x00, 0x00, 0x0000),  # clean slate
    (0xFF, 0xFF, 0xFF, 0xFFFF, 0xFFFF, 0xFF, 0xFF, 0xFF, 0xFFFF),  # all 1s
    (0x00, 0xFF, 0x00, 0xFFFF, 0x0000, 0xFF, 0x00, 0xFF, 0x8000),  # alt + lamp MSB
    (0xFF, 0x00, 0xFF, 0x0000, 0xFFFF, 0x00, 0xFF, 0x00, 0x7FFF),  # alt + lamp top
    (0x55, 0xAA, 0x55, 0x55AA, 0xAA55, 0x55, 0xAA, 0x55, 0x55AA),  # checker
    (0xAA, 0x55, 0xAA, 0xAA55, 0x55AA, 0xAA, 0x55, 0xAA, 0xAA55),  # checker (inv)
    (0x01, 0x02, 0x01, 0x3A98, 0x00FA, 0x00, 0x03, 0x00, 0x0040),  # already-good + lamp 0x40
    (0x00, 0x00, 0x00, 0x3A98, 0x00FA, 0x00, 0x03, 0x00, 0x0020),  # lamp 0x20 already set
    (0x00, 0x00, 0x00, 0x0000, 0x0000, 0x00, 0x00, 0x00, 0xFFFF),  # lamp saturated
    (0x00, 0x00, 0x00, 0x0000, 0x0000, 0x00, 0x00, 0x00, 0x0060),  # lamp already exact
    (0x00, 0x00, 0x00, 0x0000, 0x0000, 0x00, 0x00, 0x00, 0x009F),  # lamp low nibble 0xF
]


def build_oracle(cc='cc'):
    """Compile this harness' own oracle (oracle_immo_good_state_set.c + the
    reconstructed source) into /tmp/rx8-recon-immo_good_state_set/oracle."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_immo_good_state_set.c'),
           os.path.join(SAMPLES, 'src', 'rx8_immo_good_state_set.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def call_immo(cpu, vec):
    """Run the ROM bytes @0x36544 in the emulator over one initial-RAM-state
    vector and return the nine final side-effected values as ints."""
    ram = {}
    for (name, addr, width), val in zip(LOCS, vec):
        for i in range(width):
            ram[(addr + i) & 0xFFFFFFFF] = (val >> (8 * (width - 1 - i))) & 0xFF
    cpu.call(ADDR, ram=ram)
    out = []
    for name, addr, width in LOCS:
        out.append(cpu.rd(addr, width))
    return tuple(out)


def fmt_vec(vec):
    """Vector -> oracle stdin line."""
    return 'immo ' + ' '.join('%X' % v for v in vec)


def fmt_res(vals):
    """Nine ints -> oracle output line format (u8 as %02X, u16 as %04X)."""
    return ' '.join('%02X' % v if w == 1 else '%04X' % v
                    for v, (_, _, w) in zip(vals, LOCS))


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(0x60E1D400)

    # Random initial-RAM-state vectors: uniform 8/16-bit values per location.
    vectors = list(EDGE)
    for _ in range(n):
        vectors.append(tuple(
            rng.getrandbits(w * 8) for _, _, w in LOCS))

    # (a) ROM behaviour via the emulator, (b) host C on the same vectors.
    emu = [call_immo(cpu, v) for v in vectors]
    host = [fmt_res(tuple(int(x, 16) for x in ln.split()))
            for ln in run_oracle(oracle, [fmt_vec(v) for v in vectors])]

    # (c) compare all nine side-effected values.
    mismatches = []
    for i, (v, e, h) in enumerate(zip(vectors, emu, host)):
        if fmt_res(e) != h:
            mismatches.append('vec#%d init=%s ROM=%s C=%s'
                              % (i, fmt_vec(v).replace('immo ', ''), fmt_res(e), h))
            if len(mismatches) >= 5:
                break

    report('immo_good_state_set', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
