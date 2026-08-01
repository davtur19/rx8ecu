#!/usr/bin/env python3
"""
harness_ignition_dwell_output_init.py — equivalence of
rx8_ignition_dwell_output_init @0x8F62.

Reconstructed source: samples/src/rx8_ignition_dwell_output_init.c
Verified lift   : c/ignitionDwellOutputInit.c (same address; the ROM bytes
                  are executed for real here via tools/sh2emu.py).

The function is a void init chain with NO ABI return value: its whole effect
is on RAM/MMIO, so the equivalence check compares RAM+MMIO side-effects, not
a return value (Track-A RAM pattern):

  - emulator side: seed the 60 RAM bytes 0xFFFFA0C4..0xFFFFA0FF (the four
    32-bit dwell cells, the 0x94C8 dwell-limit word pair at 0xFFFFA0D4/A0D6
    and the four 8-byte per-channel control blocks), the 14 MMIO bytes the
    sensor chain (0x8FCC) and the channel-init leaf (0xAA74) touch
    (0xFFFFF626/627, words 0xFFFFF630/650/652/654/656/66C) and the two float
    inputs of the tail phase's 2-D u16 lookup (0xFFFF9F68 = y, 0xFFFF9F80 =
    x); call the ROM entry @0x8F62, read the 74 cells back;
  - host side: the oracle mmap()s the backing pages (MAP_FIXED, same trick
    as host_oracle.c), seeds the same bytes, runs the reconstructed C with
    its faithful models of the three ROM callees (sensor chain, channel-init
    leaf, tail phase incl. the lookup @0x213C over the real ROM descriptor
    @0x6C1C0), reads the 74 cells back.

The callee models must be bit-exact because the emulator executes the REAL
ROM bytes of all three: the sensor chain's 12 ordered read-modify-writes
(the two byte cells are RMW'd twice, so order matters), the channel-init
leaf's u16 zero-stores to the four control words, and the tail phase's
fused-fmac 2-D lookup + 0xFFFF clamp.  The harness verifies the embedded
descriptor data against the ROM at startup.

EDGE vectors cover all-zero/all-ones/bit-pattern RAM+MMIO pre-states,
lookup inputs at every breakpoint of both axes, just below/above the range,
0.0, +/-1e30 and NaN; N random vectors follow (fixed seed): random pre-state
bytes plus half uniform-in-range / half raw-bit lookup inputs.

Usage:  python3 harness_ignition_dwell_output_init.py [N]  (default N = 20000)
"""
import math
import os
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402
from sh2emu import ts, f2bits, bits2f  # noqa: E402

ADDR = 0x8F62
N_DEFAULT = 20000
SEED = 0x60E1D400

# --- compared cells (74 bytes) -------------------------------------------------
RAM_BLOCK = list(range(0xFFFFA0C4, 0xFFFFA0C4 + 60))   # 0xFFFFA0C4..0xFFFFA0FF
MMIO_ADDRS = [0xFFFFF626, 0xFFFFF627,
              0xFFFFF630, 0xFFFFF631,
              0xFFFFF650, 0xFFFFF651,
              0xFFFFF652, 0xFFFFF653,
              0xFFFFF654, 0xFFFFF655,
              0xFFFFF656, 0xFFFFF657,
              0xFFFFF66C, 0xFFFFF66D]
FLT_Y_ADDR = 0xFFFF9F68    # lookup input y (float, big-endian)
FLT_X_ADDR = 0xFFFF9F80    # lookup input x (float, big-endian)
OUTPUT_ADDRS = RAM_BLOCK + MMIO_ADDRS

# The SH-2E emulator is big-endian, but the host oracle's RX8_IO16 is native
# (little-endian on this host).  The oracle protocol carries the 16-bit cells
# as raw byte pairs, so the harness byte-swaps those pairs when writing the
# oracle input line and swaps them back when reading its output — making the
# oracle see exactly the same 16-bit values as the emulator.  (8-bit cells and
# the u32 dwell cells — zeroed, never read — need no swap.)
RAM_WORD_PAIRS = [(16, 17), (18, 19)]    # 0xFFFFA0D4/5 written, 0xFFFFA0D6/7 read
MMIO_WORD_PAIRS = [(2, 3), (4, 5), (6, 7), (8, 9), (10, 11), (12, 13)]


def swap16(blob, pairs):
    """Byte-swap the u16 cell pairs of a pre/post-state byte blob."""
    b = bytearray(blob)
    for i, j in pairs:
        b[i], b[j] = b[j], b[i]
    return bytes(b)

# The tail phase's 2-D u16 lookup @0x213C reads the real ROM descriptor
# @0x6C1C0 (9x9: RPM 1000..9000 x load 6.5..16.5, u16 cells @0x7CB20).  The
# oracle embeds this data; assert it against the ROM here.
DESC_ADDR = 0x6C1C0
DESC_AXIS_X_ADDR = 0x7CAD8
DESC_AXIS_Y_ADDR = 0x7CAFC
DESC_VALUES_ADDR = 0x7CB20
AXIS_X = [1000.0, 2000.0, 3000.0, 4000.0, 5000.0,
          6000.0, 7000.0, 8000.0, 9000.0]
AXIS_Y = [6.5, 7.75, 9.0, 10.25, 11.5, 12.75, 14.0, 15.25, 16.5]
CELLS = [
    1895, 1500, 1188,  890,  712,  595,  510,  445,  395,
    1688, 1332, 1168,  890,  712,  595,  510,  445,  395,
    1520, 1208, 1055,  890,  712,  595,  510,  445,  395,
    1395, 1105,  965,  880,  712,  595,  510,  445,  395,
    1292, 1020,  895,  818,  712,  595,  510,  445,  395,
    1208,  958,  840,  760,  708,  595,  510,  445,  395,
    1105,  895,  785,  712,  662,  595,  510,  445,  395,
     938,  845,  742,  678,  625,  590,  510,  445,  395,
     812,  782,  702,  640,  595,  560,  510,  445,  395,
]

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = '/tmp/rx8-recon-ignition_dwell_output_init'


def build_oracle(cc='cc'):
    """Compile the reconstructed source + its own oracle into a binary."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_ignition_dwell_output_init.c'),
           os.path.join(SAMPLES, 'src', 'rx8_ignition_dwell_output_init.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def check_descriptor(cpu):
    """Assert the ROM descriptor @0x6C1C0 matches the data the oracle embeds."""
    rom = cpu.rom
    cx = struct.unpack_from('>H', rom, DESC_ADDR)[0]
    cy = struct.unpack_from('>H', rom, DESC_ADDR + 2)[0]
    if cx != 9 or cy != 9:
        raise RuntimeError('unexpected 2-D descriptor @0x%X: %dx%d'
                           % (DESC_ADDR, cx, cy))
    ax = [struct.unpack_from('>f', rom, DESC_AXIS_X_ADDR + 4 * i)[0]
          for i in range(cx)]
    ay = [struct.unpack_from('>f', rom, DESC_AXIS_Y_ADDR + 4 * i)[0]
          for i in range(cy)]
    cells = [struct.unpack_from('>H', rom, DESC_VALUES_ADDR + 2 * i)[0]
             for i in range(cx * cy)]
    if ax != AXIS_X or ay != AXIS_Y or cells != CELLS:
        raise RuntimeError('ROM descriptor data @0x%X mismatch vs oracle' % DESC_ADDR)


def gen_edges():
    """Edge vectors: structured RAM/MMIO pre-states x lookup-input edges.

    Vectors use the SAME (ram60, mmio14, xbits, ybits) 4-tuple shape as
    gen_random(): ram60 = the 60 RAM bytes 0xFFFFA0C4..0xFFFFA0FF, mmio14 =
    the 14 MMIO bytes (0xFFFFF626/627, 0xFFFFF630 u16, the four 0xFFFFF65x
    control words and 0xFFFFF66C u16, in MMIO_ADDRS order) and the two f32
    bit-pattern args (x @0xFFFF9F80, y @0xFFFF9F68)."""
    v = []

    def edge(blob, xbits, ybits):
        # split the 74-byte RAM+MMIO pre-state blob: RAM cells 0..59, MMIO 60..
        return (blob[:60], blob[60:], xbits, ybits)

    pats = [
        [0x00] * 74,
        [0xFF] * 74,
        [0xAA if i % 2 else 0x55 for i in range(74)],
        [0x5A if i % 2 else 0xA5 for i in range(74)],
    ]

    # lookup-axis edges: every breakpoint (exact), +-1 ulp, just out of range
    xs = [1000.0, 2000.0, 3000.0, 4000.0, 5000.0,
          6000.0, 7000.0, 8000.0, 9000.0,
          999.0, 9001.0, 0.0, 1e30, -1e30, float('nan')]
    ys = [6.5, 7.75, 9.0, 10.25, 11.5, 12.75, 14.0, 15.25, 16.5,
          6.49, 16.51, 0.0, 100.0, -100.0, float('nan')]

    # every pre-state pattern x a handful of in-range lookup edges
    for p in pats:
        for x in xs[:5]:
            for y in ys[:5]:
                v.append(edge(bytes(p), f2bits(x), f2bits(y)))

    # every breakpoint on both axes (pattern 0), incl. ulp neighbours
    for x in xs:
        for y in ys[:3]:
            v.append(edge(bytes([0x00] * 74), f2bits(x), f2bits(y)))
    # per-axis out-of-range and special values (pattern 1)
    for x in xs:
        v.append(edge(bytes([0xFF] * 74), f2bits(x), f2bits(6.5)))
    for y in ys:
        v.append(edge(bytes([0xFF] * 74), f2bits(1000.0), f2bits(y)))
    # ulp neighbours of every breakpoint (in-range pairs)
    for x in (1000.0, 5000.0, 9000.0):
        for dx in (-1, 1):
            for y in (6.5, 9.0, 16.5):
                v.append(edge(bytes([0x55] * 74),
                              f2bits(ts(x * (1.0 + dx * 6e-8))), f2bits(y)))
    return v


def gen_random(rng, k):
    """k random vectors: random RAM/MMIO pre-state bytes; lookup inputs are
    half uniform-in-range / half raw float bits."""
    out = []
    for _ in range(k):
        ram = bytes(rng.randrange(256) for _ in range(60))
        mmio = bytes(rng.randrange(256) for _ in range(14))
        if rng.random() < 0.5:
            x = ts(rng.uniform(-500.0, 9500.0))
            y = ts(rng.uniform(-2.0, 20.0))
            xb, yb = f2bits(x), f2bits(y)
        else:
            xb, yb = rng.getrandbits(32), rng.getrandbits(32)
        out.append((ram, mmio, xb, yb))
    return out


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(SEED)
    check_descriptor(cpu)

    EDGE = gen_edges()
    vectors = EDGE + gen_random(rng, n)

    # (a) ROM behaviour via the emulator (RAM + MMIO side-effects).  The real
    # bytes of 0x8FCC / 0xAA74 / 0x94C8 run inside the emulator.
    emu = []
    for ram60, mmio14, xbits, ybits in vectors:
        ram = dict(zip(RAM_BLOCK, ram60))
        ram.update(dict(zip(MMIO_ADDRS, mmio14)))
        for i in range(4):
            ram[FLT_Y_ADDR + i] = (ybits >> (8 * (3 - i))) & 0xFF
            ram[FLT_X_ADDR + i] = (xbits >> (8 * (3 - i))) & 0xFF
        cpu.call(ADDR, ram=ram)
        emu.append(tuple(cpu.rd(a, 1) for a in OUTPUT_ADDRS))

    # (b) host-C on the same pre-states (oracle seeds the same 82 bytes).  The
    # u16 cells and the two f32 inputs are byte-swapped into the oracle's
    # native (little-endian) byte order so both sides operate on identical
    # 16-bit values and identical float bit patterns.
    lines = []
    for ram60, mmio14, xbits, ybits in vectors:
        toks = ['%02X' % b
                for b in swap16(ram60, RAM_WORD_PAIRS) + swap16(mmio14, MMIO_WORD_PAIRS)]
        # the oracle memcpy's these bytes into host-native (LE) floats
        toks += ['%02X' % ((ybits >> (8 * i)) & 0xFF) for i in range(4)]
        toks += ['%02X' % ((xbits >> (8 * i)) & 0xFF) for i in range(4)]
        lines.append('dwl ' + ' '.join(toks))
    raw = [tuple(int(x, 16) for x in out.split())
           for out in run_oracle(oracle, lines)]
    # swap the oracle's u16 cells back to big-endian before comparing
    host = [tuple(swap16(bytes(r[:60]), RAM_WORD_PAIRS))
            + tuple(swap16(bytes(r[60:74]), MMIO_WORD_PAIRS)) for r in raw]

    # (c) compare the 74 post-state bytes byte-for-byte.
    mismatches = []
    for i, (v, e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d x=0x%08X y=0x%08X pre=%s..%s ROM=%s..%s C=%s..%s'
                % (i, v[2], v[3],
                   ' '.join('%02X' % b for b in v[0][:8]),
                   ' '.join('%02X' % b for b in v[1][:4]),
                   ' '.join('%02X' % b for b in e[:8]),
                   ' '.join('%02X' % b for b in e[60:64]),
                   ' '.join('%02X' % b for b in h[:8]),
                   ' '.join('%02X' % b for b in h[60:64])))
            if len(mismatches) >= 5:
                break

    report('ignition_dwell_output_init', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
