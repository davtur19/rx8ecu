#!/usr/bin/env python3
"""
harness_complement_shift_u32.py — equivalence of rx8_complement_shift_u32 @0x2440.

Reconstructed source: samples/src/rx8_complement_shift_u32.c
Verified lift   : c/complement_shift_u32.c (IDA-ai symbol `complement_shift_u32`).

Single-precision deadband test: returns 1 when |threshold - value| > adjustment,
else 0.  The ROM reads the three operands from the SH-2E FPU registers
FR4 / FR5 / FR6 (fr4 = threshold, fr5 = value, fr6 = adjustment) and leaves the
result in r0.  All vectors are IEEE-754 single bit patterns so the emulator FR
values and the host `float` operands are bit-identical; the EDGE set pins the
NaN / inf / denormal / signed-zero behaviour (unordered comparisons are false
on the SH-2E fcmp/gt, T=0).

RANDOM DOMAIN — the random operands are drawn from the same bounded range as
the verified c/tests/test_complement_shift_u32.py (|t|,|v| <= 100, |a| <= 50)
rather than the full 32-bit pattern space.  Reason: tools/sh2emu.py computes
the FPU adds/subs in double precision and only then rounds to single via
`struct.pack('>f', ...)`, which raises OverflowError for a finite double whose
magnitude exceeds the single range (real SH-2E hardware would round to +-inf).
Unbounded patterns such as 3.4e38 - (-3.4e38) therefore crash the emulator
instead of producing +inf — a known emulator gap, reported, not worked around
here.  The extreme-value behaviour that IS reachable (inf, -inf, NaN, sNaN,
denormals, signed zero) is covered exhaustively by EDGE.

This harness compiles its OWN oracle — a standalone rig, not the shared
host_oracle.c — so it does not depend on common.py's SRC_FILES list:

    cc -O2 -Wall -Wextra -I include -I src \
       tests/oracle_complement_shift_u32.c src/rx8_complement_shift_u32.c \
       -o /tmp/rx8-recon-complement_shift_u32/oracle

Usage:  python3 harness_complement_shift_u32.py [N]     (default N = 20000)
"""
import os
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0x2440
N_DEFAULT = 20000

# Standalone build dir (NOT common.BUILD_DIR) so the shared host_oracle
# binary of the other harnesses is never touched.
BUILD_DIR = os.path.join('/tmp', 'rx8-recon-complement_shift_u32')
ORACLE_BIN = os.path.join(BUILD_DIR, 'oracle')

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def build_oracle(cc='cc'):
    """Compile the reconstructed source + the standalone oracle into /tmp."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_complement_shift_u32.c'),
           os.path.join(SAMPLES, 'src', 'rx8_complement_shift_u32.c'),
           '-o', ORACLE_BIN]
    subprocess.run(cmd, check=True)
    return ORACLE_BIN


def f32(x):
    """IEEE-754 single-precision bit pattern of a Python float (big-endian)."""
    return struct.unpack('>I', struct.pack('>f', x))[0]


def bits2f(b):
    """Python float holding exactly the single value encoded by bit pattern b."""
    return struct.unpack('>f', struct.pack('>I', b & 0xFFFFFFFF))[0]


# Edges: deadband boundaries, one-sided / two-sided outsides, negative and
# zero-width adjustments, NaN / inf / signed zero / denormal operands.
EDGE = [
    (f32(0.0),   f32(0.0),   f32(1.0)),            # |0| <= 1  -> inside  -> 0
    (f32(2.0),   f32(0.0),   f32(1.0)),            # |2| > 1   -> outside -> 1 (above)
    (f32(-2.0),  f32(0.0),   f32(1.0)),            # |2| > 1   -> outside -> 1 (below)
    (f32(1.0),   f32(0.0),   f32(1.0)),            # exact boundary, not >  -> 0
    (f32(-1.0),  f32(0.0),   f32(1.0)),            # exact boundary, not >  -> 0
    (f32(0.5),   f32(0.0),   f32(1.0)),            # inside -> 0
    (f32(-0.5),  f32(0.0),   f32(1.0)),            # inside -> 0
    (f32(5.0),   f32(3.0),   f32(2.0)),            # |5-3|=2  not > 2 -> 0
    (f32(5.0),   f32(3.0),   f32(1.5)),            # |5-3|=2  > 1.5   -> 1
    (f32(1.0),   f32(3.0),   f32(1.5)),            # |1-3|=2  > 1.5   -> 1
    (f32(1.0),   f32(0.0),   f32(1.0 - 2.0**-23)),  # largest float < 1.0 -> 1
    (f32(0.0),   f32(0.0),   f32(-1.0)),           # negative adj: 1 > 0  -> 1
    (f32(0.0),   f32(0.0),   f32(0.0)),            # all +0  -> 0
    (0x80000000, 0x80000000, 0x80000000),          # all -0: -0 > -0 false -> 0
    (0x7F800000, f32(0.0),   f32(1.0)),            # threshold +inf -> 1
    (0xFF800000, f32(0.0),   f32(1.0)),            # threshold -inf -> 1
    (f32(0.0),   0x7F800000, f32(1.0)),            # value +inf: inf-1 > 0 -> 1
    (f32(0.0),   f32(0.0),   0x7F800000),          # adj +inf: inside -> 0
    (0x7FC00000, f32(0.0),   f32(1.0)),            # NaN threshold: unordered -> 0
    (f32(1.0),   0x7F800001, f32(1.0)),            # sNaN value -> 0
    (f32(1.0),   f32(0.0),   0x00000001),          # denormal adj -> 1
    (f32(0.0),   0x00000001, f32(0.0)),            # denormal value: +den > 0 -> 1
]


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(0x60E1D400)

    # Random operands: bounded to the deadband-relevant range (see module
    # docstring — the emulator's single-precision round-off cannot represent
    # an add/sub overflow, so the full bit space is not fuzzed).  Adjustment
    # spans both signs so the "negative deadband -> always outside" path and
    # the "inside" path are both exercised at scale.
    vectors = list(EDGE)
    for _ in range(n):
        vectors.append((f32(rng.uniform(-100.0, 100.0)),
                        f32(rng.uniform(-100.0, 100.0)),
                        f32(rng.uniform(-50.0, 50.0))))

    # (a) ROM behaviour: operands in FR4/FR5/FR6, result returns in r0.
    emu = [cpu.call(ADDR, r4=0, fr={4: bits2f(t), 5: bits2f(v), 6: bits2f(a)})
           for t, v, a in vectors]

    # (b) host-C on the very same bit patterns.
    lines = ['f32 %08X %08X %08X' % (t, v, a) for t, v, a in vectors]
    host = [int(x, 16) for x in run_oracle(oracle, lines)]

    # (c) compare.
    mismatches = []
    for i, ((t, v, a), e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d t=0x%08X v=0x%08X a=0x%08X ROM=0x%08X C=0x%08X'
                % (i, t, v, a, e, h))
            if len(mismatches) >= 5:
                break

    report('complement_shift_u32', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
