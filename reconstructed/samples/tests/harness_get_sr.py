#!/usr/bin/env python3
"""
harness_get_sr.py — equivalence of rx8_get_sr @0x3920.

Reconstructed source: samples/src/rx8_get_sr.c
Verified lift   : c/getSR.c (the hand-annotated Ghidra RE by equinox311
                  names this leaf `getSR`; ROM bytes at 0x3920 decode to
                  mov.w @lit,r5 / stc sr,r0 / and / cmp/hi / bf /
                  rts+delay-ldc — see the lift header for the trace).

getSR is the entry half of the firmware's interrupt-masking critical-section
layer (165 callers).  Despite its name it CONDITIONALLY WRITES SR: it raises
the interrupt priority level (IPL, SR bits 7-4) when the requested value is
higher than the current one, and always returns the old (SR & 0xF0) mask
which callers pass to setSR (0x3934) to restore.

Procedure (Track-A pattern, cloned from harness_add_s32.py but with an
oracle compiled from THIS function only — SR is a hidden input/output, so
each vector is a (cur_sr, requested) pair):
  1. build host oracle (system gcc),
  2. EDGE cases + N random (cur_sr, requested) pairs,
  3. run the ROM bytes @0x3920 in tools/sh2emu.py — the emulator's call()
     accepts sr= and stores the final SR back in cpu.sr,
  4. run the host C on the same pairs (SR seeded via rx8_sr_set_state),
  5. compare BOTH the return value and the final SR — 0 mismatches required.

Usage:  python3 harness_get_sr.py [N]     (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0x3920
N_DEFAULT = 20000
BUILD_DIR = '/tmp/rx8-recon-get_sr'

# samples/tests -> samples (parent dirs)
SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CC = os.environ.get('CC', 'cc')

# Every possible IPL nibble (SR bits 7-4), as in c/tests/test_setSR_getSR.py.
IPLS = [0x00, 0x10, 0x20, 0x30, 0x40, 0x50, 0x60, 0x70,
        0x80, 0x90, 0xA0, 0xB0, 0xC0, 0xD0, 0xE0, 0xF0]

# (cur_sr, requested): low SR bits are varied to prove the 0xF0 mask works.
EDGE = [
    (0x00000000, 0x00000000),   # both zero
    (0x000000F0, 0x00000000),   # request lower than current
    (0x00000000, 0x000000F0),   # request raises to max
    (0x000000F0, 0x000000F0),   # equal -> unchanged
    (0x000000F0, 0x000000F1),   # just above (low bit in requested kept)
    (0x000000F0, 0x000000FF),   # max nibble + low bits
    (0x00000010, 0x00000020),   # raise one level
    (0x00000030, 0x00000020),   # lower -> unchanged
    (0x000000F3, 0x000000F0),   # current has T=1,S=1 set; equal nibble
    (0x0000000F, 0x00000000),   # all low bits set, request 0
    (0x000000FF, 0x00000000),   # 0xFF current (mask -> 0xF0), request 0
    (0x00000080, 0x7FFFFFFF),   # huge request
    (0x00000080, 0x80000000),   # huge request (sign bit)
    (0x00000080, 0xFFFFFFFF),   # max uint32 request
    (0x000000F0, 0x00010000),   # request with high bits only
    (0xABCDEF03, 0x000000F0),   # garbage low bits in current SR
]


def build_oracle():
    """Compile THIS function's oracle (host gcc) — not common.build_oracle,
    which links a fixed set of reconstructed samples."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [CC, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_get_sr.c'),
           os.path.join(SAMPLES, 'src', 'rx8_get_sr.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(0x60E1D400)          # fixed seed: ROM basename

    # Random pairs: current SR = random IPL nibble | random low bits;
    # requested = full random 32-bit (matches r4 in the ROM).
    def rand_cur_sr():
        return rng.choice(IPLS) | rng.getrandbits(4)

    vectors = list(EDGE) + [(rand_cur_sr(), rng.getrandbits(32))
                            for _ in range(n)]

    # (a) ROM behaviour via the emulator — each call re-seeds SR (sr=) and
    # leaves the final value in cpu.sr; (b) host-C on the same pairs.
    emu = []
    for cur_sr, requested in vectors:
        r0 = cpu.call(ADDR, r4=requested, sr=cur_sr)
        emu.append((r0, cpu.sr))

    lines = ['sr %08X %08X' % (cur_sr, requested)
             for cur_sr, requested in vectors]
    host_raw = run_oracle(oracle, lines)
    host = [(int(h[0], 16), int(h[1], 16)) for h in (l.split()
            for l in host_raw)]

    # (c) compare both the returned mask and the final SR state.
    mismatches = []
    for i, ((cur_sr, requested), (er, esr), (hr, hsr)) in enumerate(
            zip(vectors, emu, host)):
        if er != hr or esr != hsr:
            mismatches.append(
                'vec#%d cur_sr=0x%08X req=0x%08X ROM=(ret=0x%08X sr=0x%08X) '
                'C=(ret=0x%08X sr=0x%08X)' % (i, cur_sr, requested,
                                              er, esr, hr, hsr))
            if len(mismatches) >= 5:
                break

    report('getSR', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
