#!/usr/bin/env python3
"""
harness_div32_unsigned.py — equivalence of rx8_div32_unsigned @0x409C.

Reconstructed source: samples/src/rx8_div32_unsigned.c
Verified lift   : c/div32_unsigned.c (software 32-bit unsigned division built
                  on the SH-2E div0u/div1 non-restoring division primitives —
                  the SH7055 core has no hardware divide).

CALLING CONVENTION: this ROM routine is NOT ABI-clean.  It takes its operands
in r0 (divisor) and r1 (dividend) and returns the quotient in r0.  The
standard SH2.call(r4=, r5=) entry point therefore cannot be used; a small
call_div() driver below sets r0/r1 directly (same trick as
c/tests/test_div32_unsigned.py).

Procedure (Track-A pattern):
  1. build host oracle (system gcc),
  2. N random uint32 pairs + edge cases,
  3. run the ROM bytes @0x409C in tools/sh2emu.py,
  4. run the host C on the same inputs,
  5. compare — 0 mismatches required.

This harness compiles its OWN oracle binary (sources: tests/oracle_div32_unsigned.c
+ src/rx8_div32_unsigned.c) into /tmp/rx8-recon-div32_unsigned/; it does not touch
the shared host_oracle.c build.

Usage:  python3 harness_div32_unsigned.py [N]     (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0x409C
N_DEFAULT = 20000

# This harness' own build dir (kept separate from the shared host_oracle build).
SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = '/tmp/rx8-recon-div32_unsigned'

# Edge vectors: (divisor, dividend).  Values are raw 32-bit words (unsigned).
EDGE = [
    (0x00000000, 0x00000000),   # divide by zero
    (0x00000000, 0x7FFFFFFF),   # divide by zero
    (0x00000000, 0x80000000),   # divide by zero
    (0x00000000, 0xFFFFFFFF),   # divide by zero (MAX dividend)
    (0x00000001, 0x00000000),   # 0 / 1 = 0
    (0x00000001, 0x00000001),   # 1 / 1 = 1
    (0x00000001, 0xFFFFFFFF),   # MAX / 1 = MAX
    (0x00000002, 0x00000005),   # 5 / 2 = 2
    (0x00000005, 0x00000011),   # 17 / 5 = 3
    (0x00000007, 0x00000064),   # 100 / 7 = 14
    (0xFFFFFFFF, 0xFFFFFFFF),   # MAX / MAX = 1
    (0xFFFFFFFF, 0xFFFFFFFE),   # (MAX-1) / MAX = 0
    (0x80000000, 0xFFFFFFFF),   # MAX / 2^31 = 1
    (0x00010000, 0xFFFFFFFF),   # MAX / 2^16 = 0xFFFF
    (0x00000010, 0xFFFFFFFF),   # MAX / 16 = 0x0FFFFFFF
    (0x00010000, 0x12345678),   # 0x12345678 / 2^16 = 0x1234
    (0x00000100, 0x12345678),   # 0x12345678 / 256 = 0x123456
    (0x7FFFFFFF, 0x7FFFFFFF),   # equal MAX-int32 = 1
    (0x7FFFFFFF, 0x80000000),   # 2^31 / (2^31-1) = 1
    (0x80000000, 0x80000000),   # 2^31 / 2^31 = 1
    (0x00000003, 0x00000000),   # 0 / 3 = 0
    (0x0000000A, 0x00000000),   # 0 / 10 = 0
    (0x00000002, 0x00000001),   # 1 / 2 = 0
    (0x00000002, 0x00000003),   # 3 / 2 = 1
    (0xABCDEF01, 0x12345678),
    (0xDEADBEEF, 0xCAFEBABE),
    (0xCAFEBABE, 0xDEADBEEF),
    (0x00000001, 0x80000000),   # 2^31 / 1 = 2^31
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
    """Compile this harness' own oracle (oracle_div32_unsigned.c + the source)."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_div32_unsigned.c'),
           os.path.join(SAMPLES, 'src', 'rx8_div32_unsigned.c'),
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

    report('div32_unsigned', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
