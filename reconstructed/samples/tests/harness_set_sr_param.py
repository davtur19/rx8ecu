#!/usr/bin/env python3
"""
harness_set_sr_param.py — equivalence of rx8_set_sr_param @0x2054.

Reconstructed source: samples/src/rx8_set_sr_param.c
Verified lift   : c/setSR_PARAM.c (hand-annotated Ghidra RE by equinox311;
                  ROM symbol `setSR_PARAM`).

setSR_PARAM is an SH-2 status-register (SR) accessor: it reads the current
interrupt-priority-level (IPL) nibble (SR bits 7..4), ALWAYS stores that old
masked value through the caller's pointer, then raises SR to the requested new
value — clamping it to the old IPL when the request would lower it (the SH-2
hardware cannot lower the IPL via `ldc`; the ROM enforces the same rule in
software).  r0 returns the old masked IPL.

Because the observable state is the SR register plus the memory word behind
the store pointer, the equivalence check compares THREE things per vector:

  - the word stored at the caller's pointer (emulator: the sparse RAM overlay
    seeded at 0xFFFF9000 and read back after cpu.call(); host: the store word),
  - the SR state after the call (emulator: cpu.sr; host: rx8_sr_read()),
  - the returned value (emulator: cpu.call() returns r0; host: the return).

Procedure (Track-A pattern):
  1. build the host oracle (system gcc; NO cross toolchain needed),
  2. N random (SR, new-SR) pairs + edge vectors (IPL boundaries, low-bit
     masking, unsigned-comparison edges),
  3. run the ROM bytes @0x2054 in tools/sh2emu.py with `sr=` seeded,
  4. run the host C on the same inputs,
  5. compare — 0 mismatches required.

Usage:  python3 harness_set_sr_param.py [N]     (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import make_rng, report, run_oracle  # noqa: E402

# tools/ must be importable for sh2emu (common.py inserts it; re-assert here).
SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(os.path.dirname(SAMPLES))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2  # noqa: E402

ADDR = 0x2054
N_DEFAULT = 20000
STORE_ADDR = 0xFFFF9000     # scratch write area (sparse emulator RAM overlay)
ORACLE = '/tmp/rx8-recon-set_sr_param/oracle'

# IPL levels occupy SR bits 7..4; the low nibble (T/S/Q/M) must be masked off.
IPLS = [ipl for ipl in range(0x00, 0x100, 0x10)]

EDGE = []
# Mask check: T/S/Q/M low bits set under every IPL -> stored/SR must keep only
# the IPL nibble; the new-value comparison is unsigned.
for ipl in (0x00, 0x30, 0x70, 0xF0):
    for low in (0x00, 0x01, 0x02, 0x03, 0x0F):
        cur = ipl | low
        for new_sr in (0x00000000, 0x0000000F, 0x00000010, 0x000000FF,
                       (ipl - 1) & 0xFFFFFFFF, ipl, (ipl + 1) & 0xFFFFFFFF,
                       0x0FFFFFFF, 0x10000000, 0xFFFFFFFF):
            EDGE.append((cur, new_sr))

# A few "non-nibble" full-width SR values plus mixed random-looking pairs.
EDGE += [
    (0x00000000, 0x00000000),   # IPL 0, request 0      -> clamp, store 0
    (0x000000F0, 0x000000F0),   # IPL 15, request 15    -> unchanged
    (0x000000F0, 0xFFFFFFFF),   # request >= old        -> SR = 0xFFFFFFFF
    (0xFFFFFFFF, 0x00000000),   # request < old         -> clamp to 0xF0
    (0x1234F5F6, 0xABCDEF12),   # full-width SR, arbitrary new value
    (0xABCDEF01, 0x12345678),
    (0xDEADBEEF, 0xCAFEBABE),
]


def build_oracle():
    """Compile ONLY this function's oracle (self-contained, own build dir)."""
    os.makedirs('/tmp/rx8-recon-set_sr_param', exist_ok=True)
    cmd = ['cc', '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_set_sr_param.c'),
           os.path.join(SAMPLES, 'src', 'rx8_set_sr_param.c'),
           '-o', ORACLE]
    subprocess.run(cmd, check=True)
    return ORACLE


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    rom = open(os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin'), 'rb').read()
    cpu = SH2(rom)
    oracle = build_oracle()
    rng = make_rng(0x2054)

    vectors = list(EDGE) + [(rng.getrandbits(32), rng.getrandbits(32))
                            for _ in range(n)]

    # (a) ROM behaviour via the emulator: seed SR through `sr=`, poison the
    #     store area in the sparse RAM overlay, read back word + SR + r0.
    emu = []
    for cur, new_sr in vectors:
        ram = {STORE_ADDR + 0: 0xAA, STORE_ADDR + 1: 0xBB,
               STORE_ADDR + 2: 0xCC, STORE_ADDR + 3: 0xDD}
        ret = cpu.call(ADDR, r4=STORE_ADDR, r5=new_sr, sr=cur, ram=ram)
        stored = ((cpu.ram.get(STORE_ADDR + 0, 0) << 24) |
                  (cpu.ram.get(STORE_ADDR + 1, 0) << 16) |
                  (cpu.ram.get(STORE_ADDR + 2, 0) << 8) |
                  cpu.ram.get(STORE_ADDR + 3, 0))
        emu.append((stored, cpu.sr, ret))

    # (b) host-C on the same inputs.
    lines = ['set %08X %08X' % v for v in vectors]
    host = [tuple(int(x, 16) for x in out.split())
            for out in run_oracle(oracle, lines)]

    # (c) compare all three observable outputs.
    mismatches = []
    for i, (v, e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            cur, new_sr = v
            mismatches.append(
                'vec#%d cur=0x%08X new=0x%08X '
                'ROM=(stored 0x%08X, SR 0x%08X, ret 0x%08X) '
                'C=(stored 0x%08X, SR 0x%08X, ret 0x%08X)'
                % (i, cur, new_sr, e[0], e[1], e[2], h[0], h[1], h[2]))
            if len(mismatches) >= 5:
                break

    report('setSR_PARAM', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
