#!/usr/bin/env python3
"""
harness_purge_control_state_update.py — equivalence of
rx8_purge_control_state_update @0xF544.

Reconstructed source: samples/src/rx8_purge_control_state_update.c
Verified lift   : c/purge_control_state_update.c (same address; the ROM bytes
                  are executed for real here via tools/sh2emu.py).

The function is a void state machine with NO ABI return value: its whole
effect is on RAM (three u8 cells — the published flow counter @0xFFFFA4B0,
the selected purge state @0xFFFFA4B1 and the latched flow demand
@0xFFFFA4B3), so the equivalence check compares RAM side-effects, not a
return value:

  - emulator side: seed the six input bytes in the sparse ram overlay
    (trigger @0xFFFFBED0 read through the 0x104C8 leaf, flow demand
    @0xFFFF9F94, alt trigger @0xFFFFCE6E, plus the three purge-cell
    pre-states), call the ROM entry @0xF544, read the three cells back;
  - host side: the dedicated oracle mmap()s the pages backing the cells AND
    the ROM calibration table @0x792FC, seeds the same bytes, runs the
    reconstructed C and prints the same three cells.

EDGE vectors cover the trigger == 1 path with demands around both ROM
thresholds (0/1/2/3/4/5/9/10/11/12...), the trigger != 1 paths with the
alt-trigger around its ==1 test, and distinguishable stale pre-states to
catch any cell the function forgets to (re)write; N random pre-states follow
(fixed seed).

Usage:  python3 harness_purge_control_state_update.py [N]  (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0xF544
TRIG_ADDR = 0xFFFFBED0        # read by the 0x104C8 leaf (mov.w 0xBED0 sign-ext)
FLOW_DEMAND_ADDR = 0xFFFF9F94
ALT_TRIG_ADDR = 0xFFFFCE6E
FLOW_ADDR = 0xFFFFA4B0        # published flow counter (purge_flow_decrement)
STATE_ADDR = 0xFFFFA4B1       # selected purge state
DEMAND_ADDR = 0xFFFFA4B3      # latched flow demand
ROM_TABLE_ADDR = 0x000792FC   # 6 calibration bytes the function reads

N_DEFAULT = 20000
SEED = 0x60E1D400

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = '/tmp/rx8-recon-purge_control_state_update'


def build_oracle(cc='cc'):
    """Compile the reconstructed source + its dedicated oracle into a binary."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_purge_control_state_update.c'),
           os.path.join(SAMPLES, 'src', 'rx8_purge_control_state_update.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def gen_edges():
    """Edge pre-states (trigger, fd, alt, flow0, state0, demand0)."""
    v = []
    # trigger == 1: demands around both ROM thresholds (4 and 10)
    for fd in (0, 1, 2, 3, 4, 5, 6, 9, 10, 11, 12, 0x7F, 0x80, 0xFE, 0xFF):
        v.append((1, fd, 0, 0x55, 0x55, 0x55))
    # trigger != 1: alt-trigger around the ROM's ==1 test
    for trig in (0, 2, 0xFF):
        for alt in (0, 1, 2, 0xFF):
            v.append((trig, 0x55, alt, 0x55, 0x55, 0x55))
    # distinguishable stale pre-states: catch any cell left unwritten
    for pre in (0x00, 0xFF, 0xAA, 0x01):
        v.append((1, pre, 1, 0x11, 0x22, 0x33))
        v.append((0, pre, 0, 0x11, 0x22, 0x33))
    return v


def gen_random(rng, n):
    """n random pre-states over the full byte range of every input."""
    return [(rng.randrange(256), rng.randrange(256), rng.randrange(256),
             rng.randrange(256), rng.randrange(256), rng.randrange(256))
            for _ in range(n)]


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(SEED)

    # The 6 calibration bytes the ROM reads at 0x792FC..0x79301 (stock bin).
    cal = list(cpu.rom[ROM_TABLE_ADDR:ROM_TABLE_ADDR + 6])
    if cal != [0x04, 0x0A, 0x01, 0x00, 0x00, 0x00]:
        raise RuntimeError(
            'unexpected ROM calibration @0x%X: %s' % (ROM_TABLE_ADDR,
                                                      ' '.join('%02X' % b for b in cal)))

    EDGE = gen_edges()
    vectors = EDGE + gen_random(rng, n)

    # (a) ROM behaviour via the emulator (RAM side-effects).
    emu = []
    for trig, fd, alt, flow0, state0, demand0 in vectors:
        cpu.call(ADDR, ram={TRIG_ADDR: trig & 0xFF,
                            FLOW_DEMAND_ADDR: fd & 0xFF,
                            ALT_TRIG_ADDR: alt & 0xFF,
                            FLOW_ADDR: flow0 & 0xFF,
                            STATE_ADDR: state0 & 0xFF,
                            DEMAND_ADDR: demand0 & 0xFF})
        emu.append((cpu.rd(FLOW_ADDR, 1), cpu.rd(STATE_ADDR, 1),
                    cpu.rd(DEMAND_ADDR, 1)))

    # (b) host-C on the same pre-states (ROM calibration bytes shipped inline).
    caltok = ' '.join('%02X' % b for b in cal)
    lines = ['purge %s %02X %02X %02X %02X %02X %02X'
             % (caltok, trig, fd, alt, flow0, state0, demand0)
             for trig, fd, alt, flow0, state0, demand0 in vectors]
    host = [tuple(int(x, 16) for x in out.split())
            for out in run_oracle(oracle, lines)]

    # (c) compare the post-state triples byte-for-byte.
    mismatches = []
    for i, ((trig, fd, alt, f0, s0, d0), e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d trig=%02X fd=%02X alt=%02X pre=(%02X,%02X,%02X) '
                'ROM=(%02X,%02X,%02X) C=(%02X,%02X,%02X)'
                % (i, trig, fd, alt, f0, s0, d0, e[0], e[1], e[2],
                   h[0], h[1], h[2]))
            if len(mismatches) >= 5:
                break

    report('purge_control_state_update', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
