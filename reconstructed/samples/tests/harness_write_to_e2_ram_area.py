#!/usr/bin/env python3
"""
harness_write_to_e2_ram_area.py — equivalence of
rx8_write_to_e2_ram_area @0x39124.

Reconstructed source: samples/src/rx8_write_to_e2_ram_area.c
Verified lift   : c/writeToE2RAMArea.c (writeToE2RAMArea @ 0x39124)

CALLING CONVENTION (SH-2E, normal ABI — NOT a leaf):
    in  r4 = index (u16), r5 = src (ptr), r6 = length (u8)
    out void; r0 = side channel (see the sample header)
The function builds a real stack frame and calls getSR@0x3920 /
setSR@0x3934 via jsr, so it is entered with the plain `cpu.call()` (which
seeds r4/r5/r6, gives it a stack at 0xFFFFDF00 and returns r0).  Unlike the
SPI helpers 0xC0A8/0xBFCA (which busy-wait on peripheral bits sh2emu cannot
model and ARE stubbed in the sibling E2 harnesses), getSR/setSR are plain
register code that terminates under the emulator, so the REAL ROM bytes of
both helpers run inside the call — no RAM-overlay stubs are needed.

Procedure (Track-A pattern):
  1. build the host oracle (system gcc; -O2, -Wall, -Wextra),
  2. edge vectors (len 0; single bytes at index 0/0x7F/0x80/0xFF; boundary-
     crossing len 2; 0x7F/0x80/0xFF sweeps; full 255-byte sweep) + N random
     vectors (index 0..0xFF, len 0..0xFF, random src, random pre-fill seeds),
  3. run the ROM bytes @0x39124 in tools/sh2emu.py on the same vectors,
  4. run the host C on the same vectors,
  5. compare r0 (the side channel: (index+len-1)&0xFFFF, or 0xF0 for len 0)
     and the full 256-byte primary + complement E2 shadows — 0 mismatches.

Usage:  python3 harness_write_to_e2_ram_area.py [N]   (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROM_PATH, make_rng, report, run_oracle  # noqa: E402
from sh2emu import SH2  # noqa: E402

ADDR = 0x39124
N_DEFAULT = 20000
SEED = 0x60E1D400

E2_PRIM = 0xFFFFC2FE          # primary   EEPROM shadow base
E2_COMP = 0xFFFFC3FE          # complement EEPROM shadow base
SRC_BASE = 0xFFFFD000         # source buffer (host oracle maps this page)

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = os.path.join('/tmp', 'rx8-recon-write_to_e2_ram_area')
ORACLE = os.path.join(BUILD_DIR, 'oracle')


def run_vector(cpu, index, src, pseed, cseed):
    """Execute the REAL ROM bytes @0x39124 on one vector; return the full
    observable result tuple (r0, primary[256], complement[256])."""
    ram = {}
    for i, b in enumerate(src):
        ram[SRC_BASE + i] = b & 0xFF
    for i in range(256):                # pre-fill (deterministic, seed-driven)
        ram[E2_PRIM + i] = (pseed + 5 * i) & 0xFF
        ram[E2_COMP + i] = (cseed + 7 * i) & 0xFF

    r0 = cpu.call(ADDR, r4=index & 0xFFFF, r5=SRC_BASE,
                  r6=len(src) & 0xFF, ram=ram)
    prim = bytes(cpu.ram.get(E2_PRIM + i, 0) for i in range(256))
    comp = bytes(cpu.ram.get(E2_COMP + i, 0) for i in range(256))
    return ((r0 & 0xFFFF), prim, comp)


# ---------------------------------------------------------------------------
# vectors
# ---------------------------------------------------------------------------
def gen_edges():
    """Edge vectors: len 0 (only the getSR/setSR envelope runs), single
    bytes at the E2 boundary indices, boundary-crossing len 2, 0x7F/0x80
    boundary lengths and the full 255-byte sweep."""
    v = []
    for index in (0x0000, 0x0001, 0x7F, 0x80, 0xFE, 0xFF):
        v.append((index, 0, b'', 0x55, 0xAA))       # len 0: nothing written
    for src in (0x00, 0x7F, 0x80, 0xFF):
        v.append((0x00, 1, bytes([src]), 0xAA, 0x55))
        v.append((0xFF, 1, bytes([src]), 0xAA, 0x55))
    v.append((0x00, 2, bytes([0xAA, 0x55]), 0x11, 0x22))
    v.append((0xFE, 2, bytes([0x01, 0x02]), 0x33, 0x44))   # crosses 0xFF
    v.append((0x7F, 3, bytes([0x10, 0x20, 0x30]), 0x77, 0x88))
    v.append((0x00, 0x7F, bytes((5 * i) & 0xFF for i in range(0x7F)), 0x99, 0x55))
    v.append((0x00, 0x80, bytes((3 * i) & 0xFF for i in range(0x80)), 0x44, 0x77))
    v.append((0x80, 0x80, bytes((7 * i) & 0xFF for i in range(0x80)), 0x22, 0x99))
    v.append((0x01, 0xFF, bytes((11 * i) & 0xFF for i in range(0xFF)), 0x01, 0xFE))
    v.append((0x00, 0xFF, bytes((i * i) & 0xFF for i in range(0xFF)), 0xFF, 0x00))
    return v


def gen_random(rng, n):
    """N random vectors: index 0..0xFF, len 0..0xFF, random source bytes,
    random pre-fill seeds."""
    v = []
    for _ in range(n):
        length = rng.randrange(256)
        v.append((rng.randrange(256), length,
                  bytes(rng.randrange(256) for _ in range(length)),
                  rng.randrange(256), rng.randrange(256)))
    return v


# ---------------------------------------------------------------------------
# oracle
# ---------------------------------------------------------------------------
def build_oracle(cc='cc'):
    """Compile the reconstructed source + its own oracle into a host binary.
    (common.build_oracle is not reusable: it hardcodes the sample .c list.)"""
    os.makedirs(BUILD_DIR, exist_ok=True)
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_write_to_e2_ram_area.c'),
           os.path.join(SAMPLES, 'src', 'rx8_write_to_e2_ram_area.c'),
           '-lm', '-o', ORACLE]
    subprocess.run(cmd, check=True)
    return ORACLE


def parse_oracle(line):
    toks = line.split()
    return (int(toks[0], 16), bytes.fromhex(toks[1]), bytes.fromhex(toks[2]))


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    with open(ROM_PATH, 'rb') as f:
        cpu = SH2(f.read())
    oracle = build_oracle()
    rng = make_rng(SEED)

    vectors = gen_edges() + gen_random(rng, n)

    # (a) ROM behaviour via the emulator (real bytes @0x39124).
    emu = [run_vector(cpu, index, src, pseed, cseed)
           for index, length, src, pseed, cseed in vectors]

    # (b) host C on the same inputs (source shipped inline as hex).
    lines = ['e2 %04X %02X %02X %02X %s'
             % (index, len(src), pseed, cseed, src.hex())
             for index, length, src, pseed, cseed in vectors]
    host = [parse_oracle(l) for l in run_oracle(oracle, lines)]

    # (c) compare r0 + the full observable shadow state bit-exactly.
    mismatches = []
    for i, ((index, length, src, pseed, cseed), e, h) in enumerate(
            zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d idx=%03X len=%03X ROM(r0=%04X prim=%s.. comp=%s..) '
                'C(r0=%04X prim=%s.. comp=%s..)'
                % (i, index, length, e[0], e[1][:4].hex(), e[2][:4].hex(),
                   h[0], h[1][:4].hex(), h[2][:4].hex()))
            if len(mismatches) >= 5:
                break

    report('write_to_e2_ram_area', ADDR, n, mismatches, edges=len(gen_edges()))


if __name__ == '__main__':
    main()
