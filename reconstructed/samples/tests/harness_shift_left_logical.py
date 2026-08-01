#!/usr/bin/env python3
"""
harness_shift_left_logical.py — equivalence of rx8_shift_left_logical @0x4308.

Reconstructed source: samples/src/rx8_shift_left_logical.c
Verified lift   : c/shift_left_logical_r0.c

SH-2 calling convention: value in r0, shift count in r1, result in r0.  The
count is a SIGNED 32-bit register image: the ROM's `cmp/pz` reads its sign
bit, so negative counts return `val` unchanged and counts >= 32 return 0.
`SH2.call()` only wires r4..r7, so this harness uses the same `call_r0r1`
driver as c/tests/test_shift_left_logical_r0.py.

Procedure (Track-A pattern):
  1. build THIS harness's own host oracle (it compiles ONLY
     rx8_shift_left_logical.c — not the shared host_oracle.c),
  2. edge cases (shift counts 0,1,2,7,8,15,16,17,31,32,33,63 + clamping
     bounds) and N random (val, cnt) pairs,
  3. run the ROM bytes @0x4308 in tools/sh2emu.py,
  4. run the host C on the same inputs,
  5. compare — 0 mismatches required.

Usage:  python3 harness_shift_left_logical.py [N]     (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0x4308
N_DEFAULT = 20000
SEED = ADDR          # fixed, reproducible

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORACLE_DIR = '/tmp/rx8-recon-shift_left_logical'
ORACLE = os.path.join(ORACLE_DIR, 'oracle')

# Values that exercise every interesting bit pattern: all-zero, all-ones,
# sign bit alone/with neighbours, and dense/arbitrary 32-bit patterns.
EDGE_VALS = [
    0x00000000, 0x00000001, 0x00000002, 0x000000FF,
    0x7FFFFFFF, 0x80000000, 0xFFFFFFFF, 0xABCDEF01, 0x12345678,
]
# Shift counts straddling every jump-table boundary: 0..2, 7/8, 15/16/17,
# 23/24 (shll16 -> masked-rotate), 31 (max valid), 32/33/63 (clamp to 0),
# and negative counts (clamp to val).
EDGE_CNTS = [0, 1, 2, 7, 8, 15, 16, 17, 23, 24, 31, 32, 33, 63, -1, -2, -40]
EDGE = [(v, c) for v in EDGE_VALS for c in EDGE_CNTS]


def call_r0r1(cpu, entry, r0_val, r1_val, r15=0xFFFFDF00):
    """Run a leaf whose args live in r0 (value) and r1 (count), result in r0.

    Mirrors c/tests/test_shift_left_logical_r0.py: reset state, seed r0/r1,
    place the SENTINEL in pr (rts target), then single-step until rts.
    """
    cpu.ram = {}
    cpu.r = [0] * 16
    cpu.r[0] = r0_val & 0xFFFFFFFF
    cpu.r[1] = r1_val & 0xFFFFFFFF
    cpu.r[15] = r15 & 0xFFFFFFFF
    cpu.fr = [0.0] * 16
    cpu.pr = cpu.SENT
    cpu.T = 0; cpu.macl = 0; cpu.mach = 0; cpu.gbr = 0
    cpu.fpul = 0; cpu.fpscr = 0
    cpu.pc = entry & 0xFFFFFFFF
    steps = 0
    while True:
        if cpu.pc == cpu.SENT:
            return cpu.r[0] & 0xFFFFFFFF
        steps += 1
        if steps > 500000:
            raise RuntimeError('runaway at 0x%X' % cpu.pc)
        op = cpu.rd(cpu.pc, 2)
        br = cpu._delayed(op)
        if br is None:
            cpu._exec(op, cpu.pc)
            cpu.pc = (cpu.pc + 2) & 0xFFFFFFFF
        else:
            target, take = br
            cpu._exec(cpu.rd(cpu.pc + 2, 2), cpu.pc + 2)
            cpu.pc = target if take else (cpu.pc + 4) & 0xFFFFFFFF


def build_oracle():
    """Compile the reconstructed source + this harness's own oracle.

    Unlike common.build_oracle() (which links the shared host_oracle.c plus
    the fixed SRC_FILES list), this compiles ONLY the file under test, so the
    oracle exercises no unrelated code.
    """
    os.makedirs(ORACLE_DIR, exist_ok=True)
    cmd = ['cc', '-O2', '-Wall', '-Wextra',
           '-I', 'include', '-I', 'src',
           'tests/oracle_shift_left_logical.c',
           'src/rx8_shift_left_logical.c',
           '-o', ORACLE]
    subprocess.run(cmd, cwd=SAMPLES, check=True)
    return ORACLE


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(SEED)

    vectors = list(EDGE) + [(rng.getrandbits(32), rng.getrandbits(32))
                            for _ in range(n)]

    # (a) ROM behaviour via the emulator, (b) host-C on the same inputs.
    emu = [call_r0r1(cpu, ADDR, v, c) for v, c in vectors]
    lines = ['shl %08X %08X' % (v, c & 0xFFFFFFFF) for v, c in vectors]
    host = [int(x, 16) for x in run_oracle(oracle, lines)]

    # (c) compare.
    mismatches = []
    for i, ((v, c), e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d val=0x%08X cnt=%d ROM=0x%08X C=0x%08X'
                % (i, v, c, e, h))
            if len(mismatches) >= 5:
                break

    report('shift_left_logical', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
