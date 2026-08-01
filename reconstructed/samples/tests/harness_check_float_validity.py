#!/usr/bin/env python3
"""
harness_check_float_validity.py — equivalence of rx8_check_float_validity @0x46CC.

Reconstructed source: samples/src/rx8_check_float_validity.c
Verified lift   : c/checkFloatValidity.c  (same address).

Calling convention (SH-2E FPU): single float argument in fr4; single-precision
result returned in fr0.  The ROM additionally executes a preceding
float->fixed-point conversion pipeline (helpers @0x48C8 / 0x4740 / 0x481C)
whose output — not the raw fr4 operand — is the value that the NaN/Inf check
inspects; this harness reports that divergence directly.

Procedure (Track-A pattern):
  1. build host oracle (system gcc; own binary, common.build_oracle untouched),
  2. edge vectors (NaN, +-Inf, +-0.0, denormals, min/max float, boundary
     exponent) + N random (seeded) single-precision bit patterns,
  3. run the ROM bytes @0x46CC in tools/sh2emu.py on the same vectors,
  4. run the host C on the same vectors,
  5. compare bit-exact — 0 mismatches required.

Usage:  python3 harness_check_float_validity.py [N]   (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, run_oracle, report  # noqa: E402
# common() puts ROOT/tools on sys.path, so sh2emu is importable here.
from sh2emu import bits2f, f2bits  # noqa: E402

ADDR = 0x46CC
N_DEFAULT = 20000

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = os.path.join('/tmp', 'opencode', 'rx8-recon-check_float_validity')
ORACLE = os.path.join(BUILD_DIR, 'oracle')


def build_oracle():
    """Compile THIS sample + its own oracle (do NOT touch common.build_oracle)."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    cmd = ['cc', '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_check_float_validity.c'),
           os.path.join(SAMPLES, 'src', 'rx8_check_float_validity.c'),
           '-o', ORACLE]
    subprocess.run(cmd, check=True)
    return ORACLE


# --- IEEE-754 single-precision bit patterns used in the edge set -------------
_ZERO = 0x00000000          # +0.0
_NZERO = 0x80000000         # -0.0
_ONE = 0x3F800000           # 1.0
_NEGONE = 0xBF800000        # -1.0
_HALF = 0x3F000000          # 0.5
_PINF = 0x7F800000          # +Inf
_NINF = 0xFF800000          # -Inf
_QNAN = 0x7FC00000          # quiet NaN
_QNAN_NEG = 0xFFC00000      # quiet NaN, negative
_SNAN = 0x7F800001          # signaling NaN
_SNAN_PAYLOAD = 0x7F812345  # NaN, payload 0x12345
_MINNORM = 0x00800000       # min positive normal
_MAXDEN = 0x007FFFFF        # max subnormal
_MINDEN = 0x00000001        # min subnormal
_MAXF = 0x7F7FFFFF          # FLT_MAX
_BIG = 0x4B000000           # 8388608.0 (2^23)

EDGE = [
    _ZERO, _NZERO, _ONE, _NEGONE, _HALF,
    _PINF, _NINF, _QNAN, _QNAN_NEG, _SNAN, _SNAN_PAYLOAD,
    _MINNORM, _MAXDEN, _MINDEN, _MAXF, _BIG,
    # boundary-exponent neighbours: the largest finite exponent (0xFE) and the
    # exponent immediately below the special-value field.
    0x7F000000, 0x7F7FFFFF, 0xFEFFFFFF, 0x7EFFFFFF, 0xFF7FFFFF,
]


def rflt(rng):
    """Random 32-bit IEEE-754 bit pattern (full exponent/mantissa space)."""
    return rng.getrandbits(32)


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(0x46CC)

    vectors = list(EDGE) + [rflt(rng) for _ in range(n)]

    # (a) ROM behaviour via the emulator (FPU arg fr4, result fr0).
    emu = []
    for b in vectors:
        cpu.call(ADDR, fr={4: bits2f(b)})
        emu.append(f2bits(cpu.fr[0]))

    # (b) host-C on the same inputs (bit patterns round-trip exactly).
    lines = ['flt %08X' % b for b in vectors]
    host = [int(x, 16) for x in run_oracle(oracle, lines)]

    # (c) compare bit-exact.
    mismatches = []
    for i, (b, e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append('vec#%d in=%08X ROM=%08X C=%08X' % (i, b, e, h))
            if len(mismatches) >= 5:
                break

    report('checkFloatValidity', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
