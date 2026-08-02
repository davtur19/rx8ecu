#!/usr/bin/env python3
"""
harness_add_saturate_8bit.py — equivalence of rx8_add_saturate_8bit @0x2478.

Reconstructed source: samples/src/rx8_add_saturate_8bit.c
Verified lift   : c/addSaturate8Bit.c (saturating unsigned 8-bit add;
                  name from the equinox311 hand Ghidra RE, program 60E0FC00;
                  byte-identical helper matched into 60E1D400 by signature).

CALLING CONVENTION (SH-2E, register-only leaf):
    in  r4 = add1 (u8), r5 = add2 (u8)     (both `extu.b`-masked by the ROM)
    out r0 = result (u8)
No RAM side-effects, no stack frame.  SH2.call() seeds exactly r4/r5 and
returns r0, so the leaf is invoked with the plain `cpu.call(0x2478, r4=..,
r5=..)` — no call_leaf driver is required (same choice as harness_add_s32.py
for addS32Saturate @0x2304).

Procedure (Track-A pattern):
  1. build the host oracle (system gcc; own binary, common.build_oracle
     untouched),
  2. edge vectors (0, 1, max, overflow-wrap, sign-flip pairs) + N random
     (seeded) u8 pairs,
  3. run the ROM bytes @0x2478 in tools/sh2emu.py on the same vectors,
  4. run the host C on the same vectors,
  5. compare bit-exact — 0 mismatches required.

Usage:  python3 harness_add_saturate_8bit.py [N]   (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0x2478
N_DEFAULT = 20000
SEED = 0x60E1D400

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = os.path.join('/tmp', 'rx8-recon-add_saturate_8bit')
ORACLE = os.path.join(BUILD_DIR, 'oracle')

# Edge pairs: 0, 1, max, exact-threshold (254+1=255: NO clamp), overflow
# wraps (255+1=256, 128+128=256, 255+255=510: clamp to 255), sign-bit flips
# (0x80/0xFF viewed as u8; extu.b makes the comparison sign-irrelevant).
EDGE = [
    (0x00, 0x00),   # 0 + 0
    (0x00, 0x01),   # 0 + 1
    (0x01, 0x00),   # 1 + 0
    (0xFF, 0x00),   # max + 0          -> 255 (at threshold, no clamp)
    (0x00, 0xFF),   # 0 + max          -> 255
    (0xFE, 0x01),   # 254 + 1 = 255    -> 255 (exact threshold)
    (0x01, 0xFE),   # 1 + 254          -> 255
    (0xFE, 0x02),   # 254 + 2 = 256    -> 255 (overflow wrap -> clamp)
    (0x02, 0xFE),   # 2 + 254          -> 255
    (0xFF, 0x01),   # 255 + 1 = 256    -> 255 (overflow wrap -> clamp)
    (0x01, 0xFF),   # 1 + 255          -> 255
    (0xFF, 0xFF),   # 255 + 255 = 510  -> 255 (overflow wrap -> clamp)
    (0x7F, 0x7F),   # 127 + 127 = 254  -> 254 (below threshold)
    (0x7F, 0x80),   # 127 + 128 = 255  -> 255 (exact threshold)
    (0x80, 0x80),   # 128 + 128 = 256  -> 255 (sign-bit pair, overflow)
    (0x80, 0xFF),   # 128 + 255        -> 255
    (0xFE, 0xFE),   # 254 + 254 = 508  -> 255
    (0x0F, 0xF0),   # 15 + 240 = 255   -> 255 (exact threshold)
    (0xF0, 0x0E),   # 240 + 14 = 254   -> 254 (below threshold)
]


def build_oracle():
    """Compile THIS sample + its own oracle (do NOT touch common.build_oracle)."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    cmd = ['cc', '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_add_saturate_8bit.c'),
           os.path.join(SAMPLES, 'src', 'rx8_add_saturate_8bit.c'),
           '-lm', '-o', ORACLE]
    subprocess.run(cmd, check=True)
    return ORACLE


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(SEED)

    vectors = list(EDGE) + [(rng.getrandbits(8), rng.getrandbits(8))
                            for _ in range(n)]

    # (a) ROM behaviour via the emulator (leaf args r4/r5, result r0).
    emu = [cpu.call(ADDR, r4=a, r5=b) for a, b in vectors]

    # (b) host-C on the same inputs.
    lines = ['add8 %02X %02X' % (a, b) for a, b in vectors]
    host = [int(x, 16) for x in run_oracle(oracle, lines)]

    # (c) compare bit-exact (u8 range on both sides).
    mismatches = []
    for i, ((a, b), e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d add1=0x%02X add2=0x%02X ROM=0x%02X C=0x%02X'
                % (i, a, b, e, h))
            if len(mismatches) >= 5:
                break

    report('addSaturate8Bit', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
