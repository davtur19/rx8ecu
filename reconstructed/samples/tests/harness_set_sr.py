#!/usr/bin/env python3
"""
harness_set_sr.py — equivalence of rx8_set_sr @0x3934.

Reconstructed source: samples/src/rx8_set_sr.c
Verified lift   : c/setSR.c (hand-annotated Ghidra RE, equinox311).

setSR writes the SH-2 Status Register (SR := r4).  The result is NOT the
return value — it is the SR state observed after the call:

  - emulator side:  cpu.call(0x3934, r4=val, sr=init, ram=kernel_ram),
                    read back cpu.sr;
  - host side:      rx8_sr_write(init); rx8_set_sr(val); read rx8_sr_read().

The ROM gates the write behind a pointer-chain flag check anchored at
0xFFFF72B0 (scheduler-initialized byte).  The harness builds that kernel
struct in the emulator RAM overlay:

  flag == 1  -> fast path:  rts delay-slot `ldc r4,sr`     (all N vectors)
  flag != 1  -> OS detour:  jmp 0x3DB0 with delay-slot `ldc r4,sr`;
               the 0x3DB0 early-exit path (word@0x04 == word@0x06 of the
               kernel struct) is seeded so the handler returns without
               touching SR — the SR outcome stays SR = r4 (dedicated pins).

Usage:  python3 harness_set_sr.py [N]     (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0x3934
N_DEFAULT = 20000
ORACLE = os.path.join('/tmp', 'rx8-recon-set_sr', 'oracle')

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def build_oracle():
    """Compile the reconstructed rx8_set_sr.c + this harness's own oracle
    (NOT the shared host_oracle.c) into a standalone host binary."""
    os.makedirs(os.path.dirname(ORACLE), exist_ok=True)
    cmd = ['cc', '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_set_sr.c'),
           os.path.join(SAMPLES, 'src', 'rx8_set_sr.c'),
           '-o', ORACLE]
    subprocess.run(cmd, check=True)
    return ORACLE


def build_kernel_ram(flag):
    """ROM: r5 = *(0x394C) = 0xFFFF72B0; r6 = *(r5 + 24); flag = *(r6 + 1).
    Seed those cells so the emulator resolves the chain to a known flag.
    flag != 1 additionally seeds the 0x3DB0 early-exit (word@0x04 == word@0x06
    of the struct anchored at 0xFFFF72B0) so the OS handler returns quickly
    without touching SR."""
    PTR1 = 0xFFFFA000          # fake "kernel struct" address
    PTR2 = 0xFFFFA100          # fake "state block" address
    ram = {}
    for i in range(4):                         # *(0xFFFF72B0) = PTR1
        ram[0xFFFF72B0 + i] = (PTR1 >> (24 - 8 * i)) & 0xFF
    for i in range(4):                         # *(PTR1 + 24) = PTR2
        ram[PTR1 + 24 + i] = (PTR2 >> (24 - 8 * i)) & 0xFF
    ram[PTR2 + 1] = flag                       # scheduler-initialized flag
    if flag != 1:
        ram[0xFFFF72B4] = 0; ram[0xFFFF72B5] = 0   # word@0x04 of the struct
        ram[0xFFFF72B6] = 0; ram[0xFFFF72B7] = 0   # word@0x06 (equal -> early exit)
    return ram


# SR restore values that pin the interesting SR bit fields: IPL nibble (7:4),
# T bit (1), S bit (2), Q/M bits (3:2) and full-32-bit edge patterns.
EDGE_SR = [
    0x00000000, 0x00000001, 0x00000002, 0x00000003, 0x00000004,
    0x00000008, 0x0000000F, 0x00000010, 0x00000020, 0x00000040,
    0x00000080, 0x000000F0, 0x000000F3, 0x00000100, 0x00008000,
    0x0000F0F0, 0x0000FFFF, 0x00FFFFFF, 0x7FFFFFFF, 0x80000000,
    0xFFFF0000, 0xFFFFFFFF,
]


def build_vectors(n):
    """(init_sr, sr_value, sched) triples: full cross-product of the edge SR
    values on the fast path, a detour-path pin set, then n random fast-path
    pairs plus a smaller random detour batch."""
    rng = make_rng(ADDR)
    vecs = [(init, val, 1) for init in EDGE_SR for val in EDGE_SR]
    for init in (0x00000000, 0x000000F0, 0x000000F3, 0xFFFFFFFF):
        for val in (0x00000000, 0x00000010, 0x000000F0, 0xFFFFFFFF):
            vecs.append((init, val, 0))               # OS-detour pins
    vecs += [(rng.getrandbits(32), rng.getrandbits(32), 1) for _ in range(n)]
    vecs += [(rng.getrandbits(32), rng.getrandbits(32), 0)
             for _ in range(max(1, n // 10))]         # random OS-detour batch
    return vecs


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    vecs = build_vectors(n)
    n_edges = len(vecs) - n - max(1, n // 10)

    # (a) ROM behaviour via the emulator — observe the SR state after the call.
    emu = []
    for init, val, sched in vecs:
        cpu.call(ADDR, r4=val, sr=init,
                 ram=build_kernel_ram(1 if sched else 2))
        emu.append(cpu.sr)

    # (b) host-C on the same vectors.
    lines = ['sr %08X %08X %d' % (init, val, sched) for init, val, sched in vecs]
    host = [int(x, 16) for x in run_oracle(oracle, lines)]

    # (c) compare.
    mismatches = []
    for i, ((init, val, sched), e, h) in enumerate(zip(vecs, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d sched=%d init=0x%08X val=0x%08X ROM=0x%08X C=0x%08X'
                % (i, sched, init, val, e, h))
            if len(mismatches) >= 5:
                break

    report('setSR', ADDR, n, mismatches, edges=n_edges)


if __name__ == '__main__':
    main()
