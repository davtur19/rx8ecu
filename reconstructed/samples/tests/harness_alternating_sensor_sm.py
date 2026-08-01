#!/usr/bin/env python3
"""
harness_alternating_sensor_sm.py — equivalence of
rx8_alternating_sensor_sm @0x5D34C.

Reconstructed source: samples/src/rx8_alternating_sensor_sm.c
Verified lift   : c/alternating_sensor_sm_5D34C.c  (symbol
                  `diagMeteringPumpPositionControl`, 0x5D34C..0x5D3E8,
                  verified by c/tests/test_alt_sensor_sm_5D34C.py).

The function is entered through the normal ABI (r4 = cmd, result in r0) but
acts on a block of on-chip RAM plus a flash-shadow SM descriptor, so the
equivalence check compares the return value AND the RAM side-effects:

  - emulator side: seed the descriptor cells (mask @0x6020C, stored output
    pointer @0x60210 -> 0xFFFFD400) and the RAM cells (state @0xFFFFD355,
    magic @0xFFFFD350, source @0xFFFFD352, count @0xFFFFD354, input
    @0xFFFFD3A8, latch @0xFFFFD385, output byte @0xFFFFD400), call the ROM
    entry @0x5D34C, read back return + state + latch + output byte;
  - host side: the dedicated oracle mmap()s the pages backing the same cells,
    seeds the same numeric bytes, runs the reconstructed C, reads them back.

Procedure (Track-A pattern):
  1. build the dedicated oracle (tests/oracle_alternating_sensor_sm.c +
     samples/src/rx8_alternating_sensor_sm.c) with the system gcc;
  2. EDGE pre-states (boundaries, 0, max, sign flips, every FSM branch)
     + N random (seeded) pre-states;
  3. run the ROM bytes @0x5D34C in tools/sh2emu.py on the same pre-states;
  4. run the host C on the same pre-states;
  5. compare the (ret, st, latch, ptrcell) tuples — 0 mismatches required.

Usage:  python3 harness_alternating_sensor_sm.py [N]   (default N = 20000)
"""
import os
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle, SAMPLES  # noqa: E402

ADDR = 0x5D34C
N_DEFAULT = 20000
BUILD_DIR = '/tmp/rx8-recon-alternating_sensor_sm'

PTR_CELL = 0xFFFFD400          # scratch cell the stored output pointer targets
SM_MASK_ADDR = 0x6020C         # u8 sensor mask  (SM_BASE + 8)
SM_PTR_ADDR = 0x60210          # u32 stored output pointer (SM_BASE + 0xC)

# vector layout: (mask, st, magic, src, cnt, inp, latch, ptrcell, cmd)
#
# Targeted edges: every branch of the FSM — ST==0 / ST!=0, magic==0x172D /
# mismatch, masked==0 / !=0 (mask & input), CNT==7 / !=7, and the three
# second-block outcomes (out==0 -> latch cmd, out in {5,7} -> return latch,
# otherwise -> return cmd).
EDGE = [
    # magic match, masked != 0, cnt == 7: cell=7, latch=SRC>>8, st=1
    # -> out=7 -> ret = latch
    (0xFF, 0x00, 0x172D, 0xFFFF, 0x07, 0xFF, 0x00, 0x00, 0x00),
    (0xFF, 0x00, 0x172D, 0x1234, 0x07, 0x01, 0x00, 0x00, 0x05),
    # magic match, masked != 0, cnt != 7: cell=cnt, no latch write, st=1
    (0xFF, 0x00, 0x172D, 0x0000, 0x06, 0x01, 0x00, 0x00, 0x07),
    (0xFF, 0x00, 0x172D, 0x0000, 0x00, 0x80, 0x00, 0x00, 0x80),
    (0xFF, 0x00, 0x172D, 0x0000, 0xFF, 0x01, 0x00, 0x00, 0xFF),
    # magic match, masked == 0: cell=0, st=2 -> out=0 -> latch=cmd, ret=cmd
    (0xFF, 0x00, 0x172D, 0xFFFF, 0x07, 0x00, 0x00, 0x00, 0x00),
    (0xFF, 0x00, 0x172D, 0xFFFF, 0x07, 0x00, 0x05, 0x00, 0x01),
    (0x00, 0x00, 0x172D, 0xFFFF, 0x07, 0xFF, 0x00, 0x00, 0x02),   # mask = 0
    (0x0F, 0x00, 0x172D, 0x7F00, 0x07, 0x40, 0x00, 0x00, 0x00),   # inp&mask == 0
    (0x0F, 0x00, 0x172D, 0x7F00, 0x07, 0x4F, 0x00, 0x00, 0x05),   # inp&mask == 0x0F
    # magic mismatch: masked != 0 -> no store, st=0; masked == 0 -> cell=0, st=0
    (0xFF, 0x00, 0x0000, 0xFFFF, 0x07, 0xFF, 0x00, 0x05, 0x05),
    (0xFF, 0x00, 0x0000, 0xFFFF, 0x07, 0x00, 0x07, 0x05, 0x07),
    (0xFF, 0x00, 0xFFFF, 0xFFFF, 0x07, 0xFF, 0xAA, 0x07, 0x55),
    (0xFF, 0x00, 0x172C, 0x0000, 0x00, 0x80, 0x00, 0x00, 0x05),
    # ST != 0 -> first block skipped; second block still runs
    (0xFF, 0x01, 0x172D, 0xFFFF, 0x07, 0xFF, 0x00, 0x05, 0x01),
    (0xFF, 0x02, 0x172D, 0xFFFF, 0x07, 0xFF, 0x12, 0x07, 0x80),
    (0xFF, 0xFF, 0x172D, 0xFFFF, 0x07, 0xFF, 0x34, 0x05, 0xFF),
    (0x80, 0x7F, 0x172D, 0xFFFF, 0x07, 0x80, 0x56, 0x01, 0x01),
    # second block: out values 0 / 5 / 7 / other after the FSM store
    (0xFF, 0x00, 0x172D, 0xFFFF, 0x07, 0x01, 0x00, 0x00, 0x00),   # cell -> 7
    (0xFF, 0x00, 0x172D, 0xABCD, 0x07, 0x01, 0x00, 0x07, 0x00),   # out=7 -> latch=0xAB
    (0x01, 0x00, 0x172D, 0xFFFF, 0x07, 0x01, 0x00, 0x05, 0x00),   # out=5 -> latch=0xFF
    (0xFF, 0x00, 0x172D, 0xFFFF, 0x07, 0x01, 0x00, 0x08, 0x02),   # out=8 -> ret=cmd
    (0xFF, 0x00, 0x172D, 0xFFFF, 0x07, 0x01, 0x00, 0x01, 0x01),   # out=1 -> ret=cmd
    (0x01, 0x00, 0x0000, 0x0000, 0x00, 0x00, 0x00, 0x05, 0x07),   # out=5 untouched -> latch
    (0x00, 0x00, 0x0000, 0x0000, 0x00, 0x00, 0x00, 0x00, 0x00),   # all zeros
]


def seed_ram(init, addr, n, val):
    """Byte-exact big-endian store of a width-`n` value in the ram overlay."""
    for i in range(n):
        init[addr + i] = (val >> (8 * (n - 1 - i))) & 0xFF


def run_emu(cpu, vec):
    """Seed the SM descriptor + RAM cells, run the ROM bytes @0x5D34C and
    return (ret, state, latch, ptrcell) with the side effects visible."""
    mask, st, magic, src, cnt, inp, latch, ptrcell, cmd = vec
    init = {SM_MASK_ADDR: mask & 0xFF}
    seed_ram(init, SM_PTR_ADDR, 4, PTR_CELL)
    seed_ram(init, 0xFFFFD350, 2, magic & 0xFFFF)
    seed_ram(init, 0xFFFFD352, 2, src & 0xFFFF)
    init[0xFFFFD354] = cnt & 0xFF
    init[0xFFFFD355] = st & 0xFF
    init[0xFFFFD3A8] = inp & 0xFF
    init[0xFFFFD385] = latch & 0xFF
    init[PTR_CELL] = ptrcell & 0xFF
    ret = cpu.call(ADDR, r4=cmd & 0xFF, ram=init)
    return (ret & 0xFF,
            cpu.rd(0xFFFFD355, 1),
            cpu.rd(0xFFFFD385, 1),
            cpu.rd(PTR_CELL, 1))


def gen_random(rng, k):
    """k random pre-states.  Magic is biased to the 0x172D match so the first
    block's interesting paths get covered; cmd is biased to the special
    second-block values (0/5/7) as well as the full byte range."""
    special_cmd = (0, 1, 2, 3, 5, 7, 0x80, 0xFF)
    v = []
    for _ in range(k):
        magic = rng.choice((0x172D, 0x172D, rng.getrandbits(16)))
        cmd = rng.choice(special_cmd) if rng.random() < 0.5 \
            else rng.getrandbits(8)
        v.append((rng.getrandbits(8),          # mask
                  rng.getrandbits(8),          # st
                  magic,
                  rng.getrandbits(16),         # src
                  rng.getrandbits(8),          # cnt
                  rng.getrandbits(8),          # inp
                  rng.getrandbits(8),          # latch
                  rng.getrandbits(8),          # ptrcell
                  cmd))
    return v


def build_oracle(cc='cc'):
    """Compile the reconstructed source + its own oracle into a host binary."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_alternating_sensor_sm.c'),
           os.path.join(SAMPLES, 'src', 'rx8_alternating_sensor_sm.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(0x5D34C)

    vectors = list(EDGE) + gen_random(rng, n)

    # (a) ROM behaviour via the emulator (return value + RAM side-effects).
    emu = [run_emu(cpu, v) for v in vectors]

    # (b) host-C on the same pre-states.
    lines = ['sm %02X %02X %04X %04X %02X %02X %02X %02X %02X' % v
             for v in vectors]
    host = [tuple(int(x, 16) for x in out.split())
            for out in run_oracle(oracle, lines)]

    # (c) compare.
    mismatches = []
    for i, (v, e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d mask=%02X st=%02X magic=%04X src=%04X cnt=%02X '
                'inp=%02X latch=%02X cell=%02X cmd=%02X '
                'ROM=(%02X,%02X,%02X,%02X) C=(%02X,%02X,%02X,%02X)'
                % (i, v[0], v[1], v[2], v[3], v[4], v[5], v[6], v[7], v[8],
                   e[0], e[1], e[2], e[3], h[0], h[1], h[2], h[3]))
            if len(mismatches) >= 5:
                break

    report('alternating_sensor_sm', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
