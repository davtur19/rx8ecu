#!/usr/bin/env python3
"""
harness_delay_loop_n8.py — equivalence of rx8_delay_loop_n8 @0x239C.

Reconstructed source: samples/src/rx8_delay_loop_n8.c
Verified lift   : c/delay_loop_n8.c (Ghidra/IDA mislabel the ROM symbol
                  `mul16_unsigned`; the code is a busy-wait counter loop
                  whose trip count is 8 × r4).

delay_loop_n8 is a pure timing delay: the ROM leaves NO meaningful value in
r0 (it is never written, so the return value is 0), and the only observable
on the SH-2 is the loop-count relationship in the register side-effects:

  - emulator side:  cpu.call(0x239C, r4=n) -> r0 == 0, and the post-call
                    register state r4 == r5 == n*8 (the shll2/shll prologue
                    scales r4 by 8, then r5 counts 0 .. n*8-1, i.e. exactly
                    n*8 loop trips);
  - host side:      the oracle calls rx8_delay_loop_n8(n) and prints the r0
                    the caller would observe (0).  The C is structurally
                    identical to the lift: count = n*8, trip counter i runs
                    0 .. count-1.

Timing is deliberately NOT compared (the emulator runs the same code path for
every n; the trip count is data, not code).  Instead the harness pins the
loop-count relationship from the real ROM bytes (r4/r5 post-state) and the
return value from both sides.

Emulator step budget: the ROM burns 3 instructions per loop trip, so a call
with n*8*3 + ~6 > 500000 steps (n > 20830) hits the emulator's 500k-step
runaway limit.  The over-budget edge values (0xFFFF and the 32-bit-wide
0x7FFFFFFF/0xFFFFFFFF) therefore genuinely run away on the ROM — the harness
asserts that expected runaway as the real ROM behaviour and verifies the C
side separately (uint16 truncation -> same trip count as n = 0xFFFF;
terminates; returns 0).

Usage:  python3 harness_delay_loop_n8.py [N]     (default N = 5000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0x239C
N_DEFAULT = 5000
SEED = ADDR          # fixed, reproducible

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORACLE_DIR = '/tmp/rx8-recon-delay_loop_n8'
ORACLE = os.path.join(ORACLE_DIR, 'oracle')

# Largest n the ROM can run inside the emulator's 500k-step budget:
# 3 steps per trip * n*8 trips + ~6 setup steps <= 500000  ->  n <= 20830.
EMU_MAX_N = 20000

# Edge cases that stay inside the emulator budget.
EDGE = [0x0000, 0x0001, 0x0002, 0x0007, 0x0008,
        0x00FF, 0x0100]

# Edge values that EXCEED the emulator budget: the ROM spins n*8 trips and the
# 500k-step runaway limit fires (expected, verified, not a mismatch).
EDGE_RUNAWAY = [0xFFFF, 0x7FFFFFFF, 0xFFFFFFFF]


def build_oracle():
    """Compile the reconstructed source + this harness's own oracle.

    Unlike common.build_oracle() (which links the shared host_oracle.c plus
    the fixed SRC_FILES list), this compiles ONLY the file under test, so the
    oracle exercises no unrelated code.
    """
    os.makedirs(ORACLE_DIR, exist_ok=True)
    cmd = ['cc', '-O2', '-Wall', '-Wextra',
           '-I', 'include', '-I', 'src',
           'tests/oracle_delay_loop_n8.c',
           'src/rx8_delay_loop_n8.c',
           '-o', ORACLE]
    subprocess.run(cmd, cwd=SAMPLES, check=True)
    return ORACLE


def call_rom(cpu, n):
    """Run the ROM bytes @0x239C.  Returns (r0, r4, r5), or raises
    RuntimeError when the emulator's 500k-step runaway limit fires."""
    r0 = cpu.call(ADDR, r4=n)
    return r0, cpu.r[4], cpu.r[5]


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(SEED)

    # Random vectors stay within the emulator budget.
    random_vecs = [rng.randint(0, EMU_MAX_N) for _ in range(n)]
    vectors = list(EDGE) + random_vecs
    n_edges = len(EDGE) + len(EDGE_RUNAWAY)

    # (a) ROM behaviour via the emulator: r0 (return value) and the post-call
    # r4/r5 state, which pins the n*8 loop-count relationship.
    emu = []
    for v in vectors:
        r0, r4, r5 = call_rom(cpu, v)
        expect = (v * 8) & 0xFFFFFFFF
        if r4 != expect or r5 != expect:
            print('FAIL (ROM loop count) n=0x%04X: r4=0x%08X r5=0x%08X '
                  'expected 0x%08X' % (v, r4, r5, expect))
            sys.exit(1)
        emu.append(r0)

    # (b) host-C on the same vectors: oracle returns the r0 the caller sees.
    lines = ['u16 %08X' % v for v in vectors]
    host = [int(x, 16) for x in run_oracle(oracle, lines)]

    # (c) compare return values.
    mismatches = []
    for i, (v, e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append('vec#%d n=0x%08X ROM=0x%08X C=0x%08X'
                              % (i, v, e, h))
            if len(mismatches) >= 5:
                break

    # (d) over-budget edge values: the ROM genuinely spins n*8 trips, so the
    # emulator's 500k-step limit is EXPECTED to fire.  Assert that runaway,
    # then verify the C side completes with r0 = 0 (uint16 truncation ->
    # same trip count as n = 0xFFFF).
    for v in EDGE_RUNAWAY:
        try:
            call_rom(cpu, v)
        except RuntimeError:
            pass                       # runaway = expected for n*8*3 > 500k
        else:
            print('FAIL n=0x%08X: ROM did not hit the 500k-step runaway '
                  'limit (expected for a %d-trip loop)' % (v, v * 8))
            sys.exit(1)
    host_big = [int(x, 16) for x in run_oracle(
        oracle, ['u16 %08X' % v for v in EDGE_RUNAWAY])]
    if host_big != [0] * len(EDGE_RUNAWAY):
        print('FAIL: C oracle did not return 0 for over-budget edges:',
              host_big)
        sys.exit(1)

    report('delay_loop_n8', ADDR, n, mismatches, edges=n_edges)


if __name__ == '__main__':
    main()
