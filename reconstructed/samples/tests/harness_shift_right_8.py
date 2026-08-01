#!/usr/bin/env python3
"""
harness_shift_right_8.py — equivalence of rx8_shift_right_8 @0x467A.

Reconstructed source: samples/src/rx8_shift_right_8.c
Verified lift   : c/shift_right_8_r0.c  (IDA-ai symbol `shift_right_8_r0`).

This is a pure single-argument function, but unlike most helpers it reads its
input from the r0 register (not r4/r5) and returns the result in r0 — see
docs/functions/shift_right_8_r0.md.  cpu.call() seeds r4..r7 only, so the
emulator side is driven with a dedicated r0-based call stub (the same proven
pattern as c/tests/test_shift_right_8_r0.py).

Procedure (Track-A pattern):
  1. build the dedicated host oracle (system gcc; this function only),
  2. edge vectors + N random int32 inputs (fixed seed),
  3. run the ROM bytes @0x467A in tools/sh2emu.py,
  4. run the host C on the same inputs,
  5. compare — 0 mismatches required.

Usage:  python3 harness_shift_right_8.py [N]     (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0x467A
N_DEFAULT = 20000
BUILD = os.path.join('/tmp', 'rx8-recon-shift_right_8', 'oracle')

# Edges that exercise the sign-extension boundary of the arithmetic shift:
# all-zeros, all-ones, the INT32_MIN/INT32_MAX thresholds, byte-aligned
# patterns around 0x0000FF / 0x800000 / 0xFFFF00, and a few realistic words.
EDGE = [
    0x00000000,
    0x00000001,
    0x0000007F,
    0x00000080,
    0x000000FF,
    0x00000100,
    0x0000007FFF,
    0x00008000,
    0x0000FFFF,
    0x00010000,
    0x00FFFFFF,
    0x01000000,
    0x7FFFFF00,
    0x7FFFFFFF,
    0x80000000,
    0x80000001,
    0x800000FF,
    0x80000100,
    0xFFFFFF00,
    0xFFFF00FF,
    0xFF00FFFF,
    0xFFFFFFFF,
    0xABCDEF01,
    0x12345678,
    0xDEADBEEF,
    0xCAFEBABE,
]


def build_oracle(cc='cc'):
    """Compile the dedicated oracle for rx8_shift_right_8 only."""
    samples = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.makedirs(os.path.dirname(BUILD), exist_ok=True)
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(samples, 'include'),
           '-I', os.path.join(samples, 'src'),
           os.path.join(samples, 'tests', 'oracle_shift_right_8.c'),
           os.path.join(samples, 'src', 'rx8_shift_right_8.c'),
           '-o', BUILD]
    subprocess.run(cmd, check=True)
    return BUILD


def call_r0(cpu, entry, r0_val, r15=0xFFFFDF00):
    """Run a function whose argument arrives in r0 (SH-2 convention for this
    helper) and whose result is returned in r0.  Same stub as the c/ test."""
    cpu.ram = {}
    cpu.r = [0] * 16
    cpu.r[0] = r0_val & 0xFFFFFFFF
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


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(0x60E1D400)

    vectors = list(EDGE) + [rng.getrandbits(32) for _ in range(n)]

    # (a) ROM behaviour via the emulator, (b) host-C on the same inputs.
    emu = [call_r0(cpu, ADDR, v) for v in vectors]
    lines = ['%08X' % v for v in vectors]
    host = [int(x, 16) for x in run_oracle(oracle, lines)]

    # (c) compare.
    mismatches = []
    for i, (v, e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d val=0x%08X ROM=0x%08X C=0x%08X' % (i, v, e, h))
            if len(mismatches) >= 5:
                break

    report('shift_right_8', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
