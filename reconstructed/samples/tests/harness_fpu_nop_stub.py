#!/usr/bin/env python3
"""
harness_fpu_nop_stub.py — equivalence of rx8_fpu_nop_stub @0x2064.

Reconstructed source: samples/src/rx8_fpu_nop_stub.c
Verified lift   : c/fpu_nop_stub.c (rts / ldc r4,sr  -> raw SR write)

The ROM function is a 4-byte leaf: 0x2064 `rts` with delay-slot 0x2066
`ldc r4,sr`.  It takes the new Status Register value in r4 (normal ABI), has
no register return value, and its entire observable effect is the write of r4
into SR (a full 32-bit store — the base emulator's `ldc Rn,SR` does no
masking of reserved bits).  `cpu.call()` seeds r4 and reinitialises SR from
the `sr=` parameter, so the plain SH2 is used and the resulting `cpu.sr` is
read back after each call.

Procedure (Track-A pattern):
  1. build the host oracle (system gcc; -O2, -Wall, -Wextra),
  2. edge vectors (0, all-ones, IPL 0xF0 reset default, every condition bit,
     Q/M/T/S combos, single IPL levels, sign bit, sign flips, byte flips) +
     N random 32-bit words (fixed seed),
  3. run the ROM bytes @0x2064 in tools/sh2emu.py on the same vectors,
  4. run the host C on the same vectors,
  5. compare the resulting SR bit-exactly — 0 mismatches required.

Usage:  python3 harness_fpu_nop_stub.py [N]   (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0x2064
N_DEFAULT = 20000

# This harness' own build dir (kept separate from the shared host_oracle build).
SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = '/tmp/rx8-recon-fpu_nop_stub'

# Initial SR the emulator boots each call with (a value that must be fully
# overwritten by the function; arbitrary, distinct from every edge vector).
INIT_SR = 0x5A5A5A5A

# Edge vectors: boundaries, 0, max, sign flips, and the SR fields the PCM
# actually manipulates (IPL bits 7-4, T/S/M/Q bits 0-3, FD bit 6 on SH-2E).
EDGE = [
    0x00000000,   # clear everything
    0xFFFFFFFF,   # all 32 bits set
    0x000000F0,   # power-on reset default (IPL=15)
    0x000000F1,   # IPL=15 + T
    0x000000F2,   # IPL=15 + S
    0x000000F3,   # IPL=15 + T|S
    0x00000001,   # T bit only
    0x00000002,   # S bit only
    0x00000004,   # M bit only
    0x00000008,   # Q bit only
    0x0000000C,   # Q|M
    0x0000000F,   # T|S|M|Q
    0x00000010,   # IPL level 1
    0x00000020,   # IPL level 2
    0x00000040,   # IPL level 4
    0x00000080,   # IPL level 8
    0x00000040,   # FD bit (SR bit 6, SH-2E) alone
    0x00000050,   # FD + IPL level 1
    0x0000004F,   # FD + T|S|M|Q
    0x000007F0,   # bits 4..10 (IPL + FD + reserved 5)
    0x00000FF0,   # bits 4..11
    0x000000FF,   # low byte
    0x0000FF00,   # second byte
    0x00FF0000,   # third byte
    0xFF000000,   # top byte
    0x80000000,   # sign bit
    0x7FFFFFFF,   # sign flip of max
    0x80000001,   # sign bit + T
    0xAAAAAAAA,   # alternating bits
    0x55555555,   # alternating bits (sign flip)
    0x0F0F0F0F,   # nibble flip
    0xF0F0F0F0,   # nibble flip
    0xDEADBEEF,
    0xCAFEBABE,
    0x12345678,
]


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(0x60E1D400)

    vectors = list(EDGE) + [rng.getrandbits(32) for _ in range(n)]

    # (a) ROM behaviour via the emulator: seed r4, read SR back after the call.
    emu = []
    for v in vectors:
        cpu.call(ADDR, r4=v, sr=INIT_SR)
        emu.append(cpu.sr & 0xFFFFFFFF)

    # (b) host C on the same inputs (SR value in, resulting SR out).
    lines = ['sr %08X' % v for v in vectors]
    host = [int(x, 16) for x in run_oracle(oracle, lines)]

    # (c) compare bit-exactly.
    mismatches = []
    for i, (v, e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d sr=0x%08X ROM SR=0x%08X C SR=0x%08X' % (i, v, e, h))
            if len(mismatches) >= 5:
                break

    report('fpu_nop_stub', ADDR, n, mismatches, edges=len(EDGE))


def build_oracle(cc='cc'):
    """Compile the reconstructed source + its own oracle into a host binary."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_fpu_nop_stub.c'),
           os.path.join(SAMPLES, 'src', 'rx8_fpu_nop_stub.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


if __name__ == '__main__':
    main()
