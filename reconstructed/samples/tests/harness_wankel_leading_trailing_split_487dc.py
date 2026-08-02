#!/usr/bin/env python3
"""
harness_wankel_leading_trailing_split_487dc.py — equivalence of
rx8_wankel_leading_trailing_split_487dc @0x487DC.

Reconstructed source: samples/src/rx8_wankel_leading_trailing_split_487dc.c
Verified lift   : c/wankel_leading_trailing_split_487DC.c (same address;
                  verified by c/tests/test_wankel_leading_trailing_split_487DC.py
                  over 100000 random inputs x 5 seeds, 0 mismatches).

The function is a void task with NO ABI return value: its whole effect is on
RAM (the selector byte u8@0xFFFFCCD2, plus the leaf's fault flag
u8@0xFFFFC6AC), so the equivalence check compares RAM side-effects, not a
return value.  It computes CCD2 as a gated running maximum over the 29
calibration bytes cal8[0x7C27F..0x7C29B]:

  - emulator side: seed the 22 plain gate bytes (0xFFFFB5xx / 0xFFFFCCxx),
    the 7 redundant (value, ~value) u8 pairs (0xFFFF8750/8764/8768/876C/
    8770/8778/8780) and the fault-flag + selector pre-states in the sparse
    ram overlay, call the ROM entry @0x487DC (which internally jsr's the
    REAL ROM bytes of the verified leaf 0x3ED3C — and its 0x3F050 fault-flag
    write), then read the two post-state bytes back;
  - host side: the dedicated oracle mmap()s the pages backing the cells AND
    the ROM calibration page 0x7C27F..0x7C29B straight from the ROM file
    (MAP_FIXED, same trick as oracle_ssv_control.c / oracle_purge_control_
    state_update.c), seeds the same bytes, runs the reconstructed C and
    prints the same two bytes.

EDGE vectors cover: all-gates-off / all-gates-on, every plain gate active
alone (pins gate -> threshold wiring), every redundant pair valid-with-value-1
alone and broken alone (pins the leaf's ==1 gate and the C6AC fault side
effect), complement-boundary pair values (0x00/0x7F/0x80/0xFF), the fault-flag
pre-state (good pairs must leave it untouched) and distinguishable stale
selector pre-states (CCD2 must always be overwritten).  N random pre-states
follow (fixed seed = 0x60E1D400, the ROM name).

Usage:  python3 harness_wankel_leading_trailing_split_487dc.py [N]
        (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROM_PATH, load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0x487DC
N_DEFAULT = 20000
SEED = 0x60E1D400
BUILD_DIR = '/tmp/rx8-recon-wankel_leading_trailing_split_487dc'

SPLIT_ADDR = 0xFFFFCCD2          # u8 selector byte (output)
FAULT_ADDR = 0xFFFFC6AC          # u8 fault flag (leaf 0x3ED3C output)

# 22 plain-byte gate cells, in ROM block order (cf. GATE_ADDRS in the lift test).
GATE_ADDRS = [
    0xFFFFB563, 0xFFFFB565, 0xFFFFB567, 0xFFFFB569, 0xFFFFB56D, 0xFFFFB56B,
    0xFFFFCCD6, 0xFFFFCCD7, 0xFFFFCCDE,
    0xFFFFB57C,
    0xFFFFB560, 0xFFFFB588, 0xFFFFCCD3, 0xFFFFCCD4, 0xFFFFCCD5,
    0xFFFFB584, 0xFFFFB586, 0xFFFFB57E, 0xFFFFB580, 0xFFFFB582,
    0xFFFFCC8C, 0xFFFFCC8D,
]

# 7 redundant (value, ~value) pair bases, in ROM block order (cf. RV_GATES in
# the lift test); the leaf 0x3ED3C reads base and base+1.
PAIR_ADDRS = [
    0xFFFF8750, 0xFFFF8764, 0xFFFF8768, 0xFFFF876C,
    0xFFFF8770, 0xFFFF8778, 0xFFFF8780,
]

# Vector layout: 22 gate bytes + 14 pair bytes + fault pre-state + selector
# pre-state.  Same token order as the oracle's `split ...` line.
NG, NP, NC = 22, 14, 2
NTOK = NG + NP + NC


def make_all_gates(val):
    return [val] * NG


def make_valid_pairs(value):
    return [b for v in PAIR_ADDRS for b in (value, (~value) & 0xFF)]


def make_bad_pairs(value, complement):
    return [b for v in PAIR_ADDRS for b in (value, complement)]


def gen_edges():
    """Edge pre-states (22 gates, 14 pair bytes, fault, selector)."""
    v = []
    ZG = make_all_gates(0)          # all gates 0
    OG = make_all_gates(1)          # all gates 1
    P0 = make_valid_pairs(0)        # all pairs valid, value 0
    P1 = make_valid_pairs(1)        # all pairs valid, value 1

    # (a) all-off: nothing bumps -> CCD2 0; fault untouched.
    for fault in (0x00, 0x01):
        for ccd2 in (0x00, 0x01, 0xFF):
            v.append(tuple(ZG + P0 + [fault, ccd2]))
    # (b) all-on: every threshold is a candidate -> CCD2 = max(cal) = 3.
    for fault in (0x00, 0x01):
        for ccd2 in (0x00, 0x01, 0xFF):
            v.append(tuple(OG + P0 + [fault, ccd2]))
            v.append(tuple(OG + P1 + [fault, ccd2]))
    # (c) each plain gate alone == 1 (pins gate -> threshold wiring; the
    #     redundant pairs are all valid value 0 so C6AC is untouched).
    for i in range(NG):
        g = ZG[:]
        g[i] = 1
        v.append(tuple(g + P0 + [0x00, 0xFF]))
        v.append(tuple(g + P0 + [0x01, 0x00]))
    # (d) each redundant pair alone valid with value 1 (pins the leaf's ==1
    #     gate); the block-1 pair 0x8768 (i == 2) also exercises the cal
    #     threshold path.  All plain gates 0.
    for i in range(7):
        p = make_valid_pairs(0)
        p[2 * i] = 1
        p[2 * i + 1] = 0xFE
        v.append(tuple(ZG + p + [0x00, 0x00]))
        v.append(tuple(ZG + p + [0x01, 0xFF]))
    # (e) each redundant pair alone BROKEN (value 1, complement 0x00): the
    #     leaf returns 0 (gate off) and sets C6AC = 1.
    for i in range(7):
        p = make_valid_pairs(0)
        p[2 * i] = 1
        p[2 * i + 1] = 0x00
        v.append(tuple(ZG + p + [0x00, 0x00]))
        v.append(tuple(ZG + p + [0x00, 0xFF]))
    # (f) complement-boundary pair values: valid (0xFF,0x00) and (0x80,0x7F)
    #     gate on the value being == 1 only; a value != 1 must NOT bump even
    #     when the pair is valid.
    for val in (0xFF, 0x80, 0x02, 0x7F):
        v.append(tuple(ZG + make_valid_pairs(val) + [0x00, 0x00]))
        v.append(tuple(OG + make_valid_pairs(val) + [0x00, 0xFF]))
    # (g) broken complement = the valid one of the neighbour byte (bad pairs
    #     only 0x8000-page pairs are in range; all plain gates off).
    for val in (0x00, 0x01, 0x80, 0xFF):
        p = make_bad_pairs(val, (val + 1) & 0xFF)
        v.append(tuple(ZG + p + [0x01, 0xFF]))
    # (h) all pairs valid value 1, all gates 0 but one high byte -> C6AC stays
    #     the pre-state (leaf never fired a fault).
    v.append(tuple(ZG + P1 + [0x00, 0xAA]))
    v.append(tuple(ZG + P1 + [0x01, 0x55]))
    return v


def gen_random(rng, k):
    """k random pre-states: gates biased toward 0/1, pairs half valid / half
    broken, fault and selector over the full byte range."""
    v = []
    for _ in range(k):
        g = [rng.choice((0, 1, 0, 1, rng.getrandbits(8))) for _ in range(NG)]
        p = []
        for i in range(7):
            val = rng.randint(0, 255)
            if rng.random() < 0.5:
                p += [val, (~val) & 0xFF]        # valid complement
            else:
                p += [val, rng.randint(0, 255)]  # broken complement
        v.append(tuple(g + p + [rng.choice((0, 1, 0, 1, rng.getrandbits(8))),
                                rng.getrandbits(8)]))
    return v


def check_cal(cpu):
    """The stock-Rom calibration bytes are fixed; refuse to run if they ever
    change so the ROM-page mapping stays meaningful."""
    first = cpu.rom[0x7C27F]
    last = cpu.rom[0x7C29B]
    if first != 0x03 or last != 0x00:
        raise RuntimeError('unexpected wankel cal bytes @0x7C27F=0x%02X '
                           '0x7C29B=0x%02X' % (first, last))


def run_emu(cpu, vec):
    """Seed every input cell, run the ROM bytes @0x487DC (the 0x3ED3C leaf
    and its 0x3F050 fault-flag write included) and return the post-state
    (CCD2, C6AC) tuple."""
    g = vec[:NG]
    p = vec[NG:NG + NP]
    init = {}
    for a, b in zip(GATE_ADDRS, g):
        init[a] = b
    for i, a in enumerate(PAIR_ADDRS):
        init[a] = p[2 * i]
        init[a + 1] = p[2 * i + 1]
    init[FAULT_ADDR] = vec[NG + NP]
    init[SPLIT_ADDR] = vec[NG + NP + 1]
    cpu.call(ADDR, ram=init)
    return (cpu.rd(SPLIT_ADDR, 1), cpu.rd(FAULT_ADDR, 1))


def build_oracle(cc='cc'):
    """Compile the reconstructed source + its dedicated oracle into a binary."""
    samples = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(samples, 'include'),
           '-I', os.path.join(samples, 'src'),
           os.path.join(samples, 'tests',
                        'oracle_wankel_leading_trailing_split_487dc.c'),
           os.path.join(samples, 'src',
                        'rx8_wankel_leading_trailing_split_487dc.c'),
           '-lm', '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(SEED)
    check_cal(cpu)
    # The oracle maps the ROM cal page straight from the file — point it there.
    os.environ['RX8_ROM_PATH'] = ROM_PATH

    EDGE = gen_edges()
    vectors = EDGE + gen_random(rng, n)

    # (a) ROM behaviour via the emulator (the 0x3ED3C callees run as real ROM
    #     bytes).
    emu = [run_emu(cpu, v) for v in vectors]

    # (b) host-C on the same pre-states (cal constants from the mapped ROM).
    lines = ['split %s' % ' '.join('%02X' % b for b in v) for v in vectors]
    host = [tuple(int(x, 16) for x in out.split())
            for out in run_oracle(oracle, lines)]

    # (c) compare the post-state bytes bit-exactly.
    mismatches = []
    for i, (v, e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d gates=%s pairs=%s fault0=%02X split0=%02X '
                'ROM=(CCD2=%02X,C6AC=%02X) C=(CCD2=%02X,C6AC=%02X)'
                % (i,
                   ','.join('%02X' % b for b in v[:NG]),
                   ','.join('%02X' % b for b in v[NG:NG + NP]),
                   v[NG + NP], v[NG + NP + 1],
                   e[0], e[1], h[0], h[1]))
            if len(mismatches) >= 5:
                break

    report('wankel_leading_trailing_split_487dc', ADDR, n, mismatches,
           edges=len(EDGE))


if __name__ == '__main__':
    main()
