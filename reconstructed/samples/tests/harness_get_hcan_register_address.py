#!/usr/bin/env python3
"""
harness_get_hcan_register_address.py — equivalence of
                                      rx8_get_hcan_register_address @0xD198.

Reconstructed source: samples/src/rx8_get_hcan_register_address.c
Verified lift   : c/getHCANRegisterAddress.c (getHCANRegisterAddress @ 0xD198)

CALLING CONVENTION: normal ABI.  r4 = channel index (masked to 8 bits by the
ROM's first `extu.b r4,r4`), r5 = register-block base; the result is returned
in r0.  `cpu.call()` seeds exactly r4/r5 and returns r0, so no call_leaf
driver is needed.

Procedure (Track-A pattern):
  1. build the host oracle (system gcc; -O2, -Wall, -Wextra),
  2. edge vectors (the COMPLETE 8-bit index space 0..255 over a fixed base,
     index values with bits above bit 7 set — exercising the extu.b mask — and
     wrap-around bases near 0xFFFFFFFF) + N random (idx, base) pairs,
  3. run the ROM bytes @0xD198 in tools/sh2emu.py on the same vectors,
  4. run the host C on the same inputs,
  5. compare the raw 32-bit results — 0 mismatches required.

The function is a pure leaf (no memory traffic), so there are no RAM
side effects to mirror.

Usage:  python3 harness_get_hcan_register_address.py [N]   (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0xD198
N_DEFAULT = 20000

# This harness' own build dir (kept separate from the shared host_oracle build).
SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = os.path.join('/tmp', 'rx8-recon-get_hcan_register_address')


def build_oracle(cc='cc'):
    """Compile this harness' own oracle (oracle_get_hcan_register_address.c
    + the reconstructed source)."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_get_hcan_register_address.c'),
           os.path.join(SAMPLES, 'src', 'rx8_get_hcan_register_address.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def gen_edges():
    """Edge vectors: the complete 8-bit index space 0..255 over one base, plus
    index words whose bit 8+ is set (the ROM `extu.b r4,r4` masks them — e.g.
    0x100 must behave exactly like 0), plus wrap-around base values near
    0xFFFFFFFF (base + 0x0200 wraps through 32-bit arithmetic)."""
    v = [(idx, 0x12345678) for idx in range(256)]          # full 8-bit idx space
    # high-bit idx words -> masked down to 0x00..0xFF by extu.b
    v += [(0x100, 0x12345678), (0x1FF, 0x12345678), (0x1234, 0x12345678),
          (0x7FFFFFFF, 0x12345678), (0x80000000, 0x12345678),
          (0xFFFFFFFF, 0x12345678)]
    # wrap-around / boundary bases, exercised with both the idx==0 and idx!=0 path
    for base in (0x00000000, 0x00000001, 0x000001FF, 0x00000200, 0x00000201,
                 0xFFFFFE00, 0xFFFFFF00, 0xFFFFFF01, 0xFFFFFFFF,
                 0x7FFFFFFF, 0x80000000):
        v += [(0, base), (1, base)]
    return v


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(0x60E1D400)

    vectors = list(gen_edges()) + [(rng.getrandbits(32), rng.getrandbits(32))
                                   for _ in range(n)]

    # (a) ROM behaviour via the emulator (idx=r4, base=r5 -> result in r0).
    emu = [cpu.call(ADDR, r4=idx, r5=base) for idx, base in vectors]

    # (b) host C on the same inputs.
    lines = ['hcan %08X %08X' % (idx, base) for idx, base in vectors]
    host = [int(x, 16) for x in run_oracle(oracle, lines)]

    # (c) compare raw 32-bit results.
    mismatches = []
    for i, ((idx, base), e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d idx=0x%08X base=0x%08X ROM=0x%08X C=0x%08X'
                % (i, idx, base, e, h))
            if len(mismatches) >= 5:
                break

    report('getHCANRegisterAddress', ADDR, n, mismatches, edges=len(vectors))


if __name__ == '__main__':
    main()
