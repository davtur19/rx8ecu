#!/usr/bin/env python3
"""
harness_obd_service_handler_648b4.py — equivalence of
rx8_obd_service_handler_648b4 @0x648B4.

Reconstructed source: samples/src/rx8_obd_service_handler_648b4.c
Verified lift   : c/obd_service_handler_648B4.c (ROM 0x648B4, side-effect
                  leaf: folds r4 into two (value,~value) 16-bit run-sum cells
                  at 0xFFFF8E98 / 0xFFFF8E9A via the enc8 leaf @0x2420).

CALLING CONVENTION: normal ABI entry (r4 = byte value), so cpu.call() is used
directly.  The function is a PURE SIDE-EFFECT leaf (no return value): both the
emulator run and the host oracle compare the two 16-bit run-sum cells after
every call, exactly as the firmware caller (can_encode_handler_62ABC) would
observe them.

Because the function acts on RAM, equivalence compares RAM side-effects:

  - emulator side: seed the sparse ram overlay at 0xFFFF8E98/0xFFFF8E9A with
    the two 16-bit words (big-endian: high byte first), call the ROM entry
    with r4 = b, read both words back;
  - host side: the oracle mmap()s the very same page (MAP_FIXED), seeds the
    same words, runs the reconstructed C, prints both words back.

Vectors are self-contained (b, wA, wB) triples, so every result is compared
bit-exactly.  In addition to plain edges + random triples, a long CHAIN of
bytes is applied with the state carried from one step to the next (the real
usage pattern: successive DTC encodes accumulate into the same cells); the
chain's intermediate states are produced by the emulator (the ground truth)
so each step is still an independent (b, wA, wB) comparison.

Procedure (Track-A pattern):
  1. build host oracle (system gcc),
  2. edge vectors (b boundaries, cell-value boundaries, sum-wraparound cases)
     + N random triples + a 1024-step state-carrying chain,
  3. run the ROM bytes @0x648B4 in tools/sh2emu.py,
  4. run the host C on the same inputs,
  5. compare both 16-bit cells — 0 mismatches required.

Usage:  python3 harness_obd_service_handler_648b4.py [N]   (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0x648B4
N_DEFAULT = 20000

CELL_A = 0xFFFF8E98            # running-delta (value,~value) cell
CELL_B = 0xFFFF8E9A            # last-input   (value,~value) cell

# This harness' own build dir (kept separate from the shared host_oracle build).
SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = '/tmp/rx8-recon-obd_service_handler_648b4'

# Edge vectors: (b, wA, wB).  b values straddle the signed-byte boundaries;
# cell values straddle the value-byte boundaries (high byte 0x00/0x7F/0x80/
# 0xFF) with arbitrary complement (low) bytes, proving the low byte is
# ignored.  The extra triples hit the sum-wraparound cases of
# s8(hi A) + s8(hi B) - s8(b) mod 256.
EDGE_B = [0x00, 0x01, 0x7F, 0x80, 0x81, 0xFE, 0xFF]
EDGE_CELL = [0x0000, 0x00FF, 0xFF00, 0xFFFF, 0x7F00, 0x8000, 0x1234, 0xABCD]
EDGE = [(b, wA, wB) for b in EDGE_B for wA in EDGE_CELL for wB in EDGE_CELL]
EDGE += [
    (0x00, 0x0000, 0x0000),   # 0 + 0 - 0      -> delta 0x00
    (0x00, 0x8000, 0x8000),   # -128 + -128    -> delta -256 == 0x00 (wrap)
    (0x00, 0x7F00, 0x7F00),   # 127 + 127      -> delta 0xFE
    (0xFF, 0x7F00, 0x7F00),   # 127 + 127 + 1  -> delta 0xFF (sat at max)
    (0x01, 0x8000, 0x0000),   # -128 - 1       -> delta 0x7F
    (0x01, 0x0000, 0x8000),   # -128 - 1       -> delta 0x7F (commuted read)
    (0x80, 0x8000, 0x8000),   # -128 - 128 + 128 -> delta 0x80
    (0x80, 0x0000, 0x0000),   # 0 - 128        -> delta 0x80
    (0x7F, 0x0000, 0x0000),   # 0 - 127        -> delta 0x81
    (0xFF, 0x0000, 0x0000),   # 0 - (-1)       -> delta 0x01
    (0xFF, 0xFFFF, 0xFFFF),   # -1 + -1 + 1    -> delta 0xFF
    (0x00, 0xFF00, 0xFF00),   # -1 + -1        -> delta 0xFE
    (0xFF, 0x8000, 0x0000),   # -128 + 0 + 1   -> delta 0x81
    (0x01, 0x7F00, 0x8000),   # 127 - 128 - 1  -> delta 0xFE
]


def build_oracle(cc='cc'):
    """Compile this harness' own oracle (oracle_obd_service_handler_648b4.c
    + the source under test)."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_obd_service_handler_648b4.c'),
           os.path.join(SAMPLES, 'src', 'rx8_obd_service_handler_648b4.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def seed_cells(wA, wB):
    """Sparse ram overlay with the two big-endian 16-bit cells (high byte
    first, exactly how the SH-2E `mov.w` writes/reads them)."""
    return {
        CELL_A: (wA >> 8) & 0xFF, CELL_A + 1: wA & 0xFF,
        CELL_B: (wB >> 8) & 0xFF, CELL_B + 1: wB & 0xFF,
    }


def read_cells(cpu):
    """Reassemble the two 16-bit cells from the emulator's byte overlay."""
    return (((cpu.ram.get(CELL_A, 0) << 8) | cpu.ram.get(CELL_A + 1, 0)),
            ((cpu.ram.get(CELL_B, 0) << 8) | cpu.ram.get(CELL_B + 1, 0)))


def run_emu(cpu, b, wA, wB):
    """Execute the ROM bytes @0x648B4 with r4=b over the seeded cells."""
    cpu.call(ADDR, r4=b, ram=seed_cells(wA, wB))
    return read_cells(cpu)


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(0x648B4)

    vectors = list(EDGE)                 # (b, wA, wB) triples
    vectors += [(rng.randrange(256), rng.getrandbits(16), rng.getrandbits(16))
                for _ in range(n)]

    # State-carrying chain (the real usage pattern: successive DTC encodes
    # accumulate in the same cells).  The chain's intermediate states come
    # from the emulator (ground truth), so each step is still a plain
    # self-contained (b, wA, wB) vector.
    wA = wB = 0
    chain_b = [0x00, 0xFF, 0x80, 0x7F, 0x01, 0xFE, 0x81, 0x00] + \
              [rng.randrange(256) for _ in range(1024)]
    for b in chain_b:
        vectors.append((b, wA, wB))
        wA, wB = run_emu(cpu, b, wA, wB)

    # (a) ROM behaviour via the emulator (RAM side-effects).
    emu = [run_emu(cpu, b, wA, wB) for b, wA, wB in vectors]

    # (b) host C on the same vectors (state fully specified per line).
    lines = ['obd %02X %04X %04X' % (b, wA, wB) for b, wA, wB in vectors]
    host = [tuple(int(x, 16) for x in out.split())
            for out in run_oracle(oracle, lines)]

    # (c) compare both 16-bit cells bit-exactly.
    mismatches = []
    for i, ((b, wA, wB), e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d b=%02X wA=%04X wB=%04X ROM=%04X/%04X C=%04X/%04X'
                % (i, b, wA, wB, e[0], e[1], h[0], h[1]))
            if len(mismatches) >= 5:
                break

    report('obd_service_handler_648B4', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
