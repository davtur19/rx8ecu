#!/usr/bin/env python3
"""
harness_purge_flow_decrement.py — equivalence of rx8_purge_flow_decrement @0xF5B4.

Reconstructed source: samples/src/rx8_purge_flow_decrement.c
Verified lift   : c/purge_flow_decrement.c  (symbol `purge_flow_decrement`,
                  0xF5B4..0xF5DC, symbols_60E1D400_merged.csv, ida-ai).

The leaf acts on RAM (two u8 cells: FLOW @0xFFFFA4B0, DEC_EN @0xFFFFA4B2), so
the equivalence check compares RAM side-effects, not a return value:

  - emulator side: seed the two bytes in the sparse ram overlay, call the ROM
    entry @0xF5B4, read the bytes back;
  - host side: the dedicated oracle mmap()s the page backing the cells, seeds
    the same numeric bytes, runs the reconstructed C, reads them back.

Procedure (Track-A pattern):
  1. build the dedicated oracle (tests/oracle_purge_flow_decrement.c +
     samples/src/rx8_purge_flow_decrement.c) with the system gcc;
  2. EDGE pre-states + N random (seeded) pre-states;
  3. run the ROM bytes @0xF5B4 in tools/sh2emu.py on the same pre-states;
  4. run the host C on the same pre-states;
  5. compare the post-state pairs — 0 mismatches required.

Usage:  python3 harness_purge_flow_decrement.py [N]   (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, SAMPLES  # noqa: E402

ADDR = 0xF5B4
FLOW_ADDR = 0xFFFFA4B0
DEC_EN_ADDR = 0xFFFFA4B2
N_DEFAULT = 20000
BUILD_DIR = '/tmp/rx8-recon-purge_flow_decrement'

# Edge pre-states.  flow=0/1/255 bracket the counter clamp (0 stays 0, 1 -> 0,
# 255 -> 254); flow=128 pins the extu.b sign path.  dec_en covers the canonical
# latch values 0/1 AND non-canonical ones (2, 0xFE, 0xFF), because the ROM
# arms on `cmp/eq #1` — anything != 1 is treated as "not armed".
EDGE = [
    (0, 0), (0, 1),
    (1, 0), (1, 1),
    (2, 0), (2, 1),
    (254, 0), (254, 1),
    (255, 0), (255, 1),
    (128, 0), (128, 1),
    (3, 2), (0x80, 0xFE), (0x55, 0xFF),
]


def ref_decrement(flow, dec_en):
    """Behavioural reference: byte-exact mirror of the ROM's `cmp/eq #1` on
    DEC_EN and `cmp/pl` on the extu.b-extended FLOW (i.e. the c/ lift)."""
    if dec_en == 1:
        if flow > 0:
            flow = (flow - 1) & 0xFF
    else:
        dec_en = 1
    return flow & 0xFF, dec_en & 0xFF


def build_oracle(cc='cc'):
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_purge_flow_decrement.c'),
           os.path.join(SAMPLES, 'src', 'rx8_purge_flow_decrement.c'),
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


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(0xF5B4)

    # Random pre-states: counter 0..255, latch across the full byte range (the
    # ROM re-arms on any value != 1, so non-canonical latch values matter).
    vectors = list(EDGE) + [(rng.randint(0, 255), rng.randint(0, 255))
                            for _ in range(n)]

    # (a) ROM behaviour via the emulator (RAM side-effects).
    emu = []
    for flow, dec_en in vectors:
        cpu.call(ADDR, ram={FLOW_ADDR: flow & 0xFF, DEC_EN_ADDR: dec_en & 0xFF})
        emu.append((cpu.rd(FLOW_ADDR, 1), cpu.rd(DEC_EN_ADDR, 1)))

    # (b) host-C on the same pre-states.
    lines = ['purg %02X %02X' % (flow, dec_en) for flow, dec_en in vectors]
    host = [tuple(int(x, 16) for x in out.split())
            for out in run_oracle(oracle, lines)]

    # (c) compare.
    mismatches = []
    for i, ((flow, dec_en), e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d flow=%02X dec_en=%02X ROM=(%02X,%02X) C=(%02X,%02X)'
                % (i, flow, dec_en, e[0], e[1], h[0], h[1]))
            if len(mismatches) >= 5:
                break

    report('purge_flow_decrement', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
