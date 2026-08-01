#!/usr/bin/env python3
"""
harness_div32_signed.py — equivalence of rx8_div32_signed @0x3FE8.

Reconstructed source: samples/src/rx8_div32_signed.c
Verified lift   : c/div32_signed.c (software 32-bit signed division built on
                  the SH-2E div0s/div1 non-restoring division primitives —
                  the SH7055 core has no hardware divide).

CALLING CONVENTION: this ROM routine is NOT ABI-clean.  It takes its operands
in r0 (divisor) and r1 (dividend) and returns the quotient in r0.  The
standard SH2.call(r4=, r5=) entry point therefore cannot be used; a small
call_div() driver below sets r0/r1 directly (same trick as
c/tests/test_div32_signed.py).

Procedure (Track-A pattern):
  1. build host oracle (system gcc),
  2. N random int32 pairs + edge cases,
  3. run the ROM bytes @0x3FE8 in tools/sh2emu.py,
  4. run the host C on the same inputs,
  5. compare — 0 mismatches required.

This harness compiles its OWN oracle binary (sources: tests/oracle_div32_signed.c
+ src/rx8_div32_signed.c) into /tmp/rx8-recon-div32_signed/; it does not touch
the shared host_oracle.c build.

Usage:  python3 harness_div32_signed.py [N]     (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0x3FE8
N_DEFAULT = 20000

# This harness' own build dir (kept separate from the shared host_oracle build).
SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = '/tmp/rx8-recon-div32_signed'

# Edge vectors: (divisor, dividend).  Values are raw 32-bit words (the host
# oracle and the emulator agree on the signed interpretation).
EDGE = [
    (0x00000000, 0x00000000),   # divide by zero
    (0x00000000, 0x7FFFFFFF),   # divide by zero
    (0x00000000, 0x80000000),   # divide by zero
    (0xFFFFFFFF, 0xFFFFFFFF),   # -1 / -1 = 1
    (0xFFFFFFFF, 0x00000001),   # -1 / 1 = -1
    (0x00000001, 0xFFFFFFFF),   # 1 / -1 = -1
    (0xFFFFFFFF, 0x80000000),   # INT32_MIN / -1 -> wraps to INT32_MIN
    (0x00000001, 0x80000000),   # INT32_MIN / 1 = INT32_MIN
    (0x80000000, 0x80000000),   # INT32_MIN / INT32_MIN = 1
    (0x7FFFFFFF, 0x7FFFFFFF),   # INT32_MAX / INT32_MAX = 1
    (0x80000000, 0x00000001),   # 1 / INT32_MIN = 0 (|divisor| > |dividend|)
    (0x00000001, 0x7FFFFFFF),   # INT32_MAX / 1 = INT32_MAX
    (0x7FFFFFFF, 0xFFFFFFFF),   # -1 / INT32_MAX = 0
    (0x00000001, 0x00000001),   # 1 / 1
    (0x00000002, 0x00000005),   # 5 / 2 = 2
    (0x00000005, 0x00000011),   # 17 / 5 = 3
    (0x00000007, 0x00000064),   # 100 / 7 = 14
    (0x00000007, 0xFFFFFF9C),   # -100 / 7 = -14 (truncation, not floor)
    (0x80000000, 0x40000000),   # 2^30 / INT32_MIN = 0
    (0x80000001, 0x7FFFFFFF),   # INT32_MAX / INT32_MIN = 0
    (0xABCDEF01, 0x12345678),
    (0xDEADBEEF, 0xCAFEBABE),
]


def call_div(cpu, entry, r0_val, r1_val):
    """Drive a ROM routine that takes divisor in r0 and dividend in r1."""
    cpu.ram = {}
    cpu.r = [0] * 16
    cpu.r[0] = r0_val & 0xFFFFFFFF
    cpu.r[1] = r1_val & 0xFFFFFFFF
    cpu.r[15] = 0xFFFFDF00
    cpu.fr = [0.0] * 16
    cpu.pr = cpu.SENT
    cpu.T = 0
    cpu._Q = 0
    cpu._M = 0
    cpu.macl = 0
    cpu.mach = 0
    cpu.gbr = 0
    cpu.fpul = 0
    cpu.fpscr = 0
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


def build_oracle(cc='cc'):
    """Compile this harness' own oracle (oracle_div32_signed.c + the source)."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_div32_signed.c'),
           os.path.join(SAMPLES, 'src', 'rx8_div32_signed.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(0x60E1D400)

    vectors = list(EDGE) + [(rng.getrandbits(32), rng.getrandbits(32))
                            for _ in range(n)]

    # (a) ROM behaviour via the emulator (divisor=r0, dividend=r1),
    # (b) host C on the same inputs.
    emu = [call_div(cpu, ADDR, d, v) for d, v in vectors]
    lines = ['div %08X %08X' % (d, v) for d, v in vectors]
    host = [int(x, 16) for x in run_oracle(oracle, lines)]

    # (c) compare.
    mismatches = []
    for i, ((d, v), e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d divisor=0x%08X dividend=0x%08X ROM=0x%08X C=0x%08X'
                % (i, d, v, e, h))
            if len(mismatches) >= 5:
                break

    report('div32_signed', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
