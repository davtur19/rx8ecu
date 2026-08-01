#!/usr/bin/env python3
"""
harness_shift_right_logical.py — equivalence of rx8_shift_right_logical_r0 @0x44E0.

Reconstructed source: samples/src/rx8_shift_right_logical.c
Verified lift   : c/shift_right_logical_r0.c

Semantics (SH-2 convention: value in r0, shift count in r1, result in r0):
    cnt < 0   -> return val unchanged
    cnt >= 32 -> return 0
    else      -> val >> cnt        (logical / zero-fill)

Procedure (Track-A pattern):
  1. build host oracle (system gcc) from tests/oracle_shift_right_logical.c
     + src/rx8_shift_right_logical.c,
  2. edge cases + N random (val, cnt) vectors (seeded),
  3. run the ACTUAL ROM bytes @0x44E0 in tools/sh2emu.py,
  4. run the host C on the same inputs,
  5. compare — 0 mismatches required.

NOTE: sh2emu.SH2.call() only sets r4..r7, so this r0/r1-convention function
is run with the same SENT-return stepper used by
c/tests/test_shift_right_logical_r0.py.

Usage:  python3 harness_shift_right_logical.py [N]     (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0x44E0
N_DEFAULT = 20000

# samples root (reconstructed/samples)
SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = '/tmp/rx8-recon-shift_right_logical'
ORACLE = os.path.join(BUILD_DIR, 'oracle')

# Edge counts straddle every dispatch boundary (8/16-bit tails and the 32/33
# clamp); the all-ones value 0xFFFFFFFF exposes zero-fill vs sign-fill at a
# glance.  Negative counts exercise the cmp/pz fast path.
EDGE = [(0xFFFFFFFF, cnt) for cnt in (0, 1, 15, 16, 17, 31, 32, 33, -1)]
EDGE += [(0x80000000, 1), (0x80000000, 8), (0x80000000, 16), (0x80000000, 31),
         (0x00000001, 32), (0x00000001, -10), (0x00000000, 0),
         (0xABCDEF01, 12), (0x12345678, 28), (0xDEADBEEF, -1)]


def build_oracle(cc='cc'):
    """Compile the reconstructed shift source + its oracle into a host binary."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_shift_right_logical.c'),
           os.path.join(SAMPLES, 'src', 'rx8_shift_right_logical.c'),
           '-o', ORACLE]
    subprocess.run(cmd, check=True)
    return ORACLE


def call_r0r1(cpu, entry, r0_val, r1_val, r15=0xFFFFDF00):
    """Run a function whose args are r0 (value) and r1 (count); returns r0."""
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


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(0x60E1D400)

    vectors = list(EDGE) + [(rng.getrandbits(32), rng.randint(-40, 72))
                            for _ in range(n)]

    # (a) ROM behaviour via the emulator, (b) host-C on the same inputs.
    emu = [call_r0r1(cpu, ADDR, v, c) for v, c in vectors]
    lines = ['%08X %08X' % (v & 0xFFFFFFFF, c & 0xFFFFFFFF)
             for v, c in vectors]
    host = [int(x, 16) for x in run_oracle(oracle, lines)]

    # (c) compare.
    mismatches = []
    for i, ((v, c), e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d val=0x%08X cnt=%d ROM=0x%08X C=0x%08X' % (i, v, c, e, h))
            if len(mismatches) >= 5:
                break

    report('shiftRightLogical', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
