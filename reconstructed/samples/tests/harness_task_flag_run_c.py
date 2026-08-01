#!/usr/bin/env python3
"""
harness_task_flag_run_c.py — equivalence of rx8_task_flag_run_c @0x35EE.

Reconstructed source: samples/src/rx8_task_flag_run_c.c
Verified lift   : c/task_flag_run_C.c  (task_flag_run_C @ 0x35EE)

The ROM routine is the OS task-switch barrier: set bit 15 of the kernel state
word @0xFFFF72B8, call the task body through a function pointer held in RAM at
0x4B10, then clear bit 15 (re-reading the state word, so any edit the task body
makes while the flag is held is preserved).  It ignores its register arguments,
so the plain SH2.call() entry point works.

Because the behaviour is almost pure RAM traffic, the vectors are (state, delta)
pairs: `state` is the pre-call state word, and `delta` is a per-vector edit the
harness' task body ORs into the state word (plus a fixed 0x4 marker bit).  Two
words are compared bit-exactly after every call:

    0xFFFF72B8  final state word   (proves the release mask is exactly
                                    ~0x8000, and — via delta — that the
                                    post-call read is a real re-read)
    0xFFFF72C0  marker word        (what the task body observed, proving the
                                    acquire bit 15 was set BEFORE the call
                                    and that the 0x4B10 indirect call fired)

The task body is a tiny SH-2 stub installed in the emulator's sparse RAM at
0x00100000 (behaviourally identical to the C `task_stub` in the oracle).  The
function pointer at 0x4B10 is seeded to the stub's address exactly like the
real scheduler does, so the whole indirection is exercised.

Procedure (Track-A pattern):
  1. build the host oracle (system gcc; -O2, -Wall, -Wextra),
  2. edge vectors (0, all-ones, bit-15 on/off, sign flips, delta with bit 15,
     marker-bit aliasing) + N random (state, delta) pairs,
  3. run the ROM bytes @0x35EE in tools/sh2emu.py on the same vectors,
  4. run the host C on the same vectors,
  5. compare both RAM words bit-exactly — 0 mismatches required.

Usage:  python3 harness_task_flag_run_c.py [N]   (default N = 20000)
"""
import os
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROM_PATH, make_rng, report, run_oracle  # noqa: E402
# common.py already put <repo>/tools on sys.path (its sh2emu import).
from sh2emu import SH2, MASK  # noqa: E402

ADDR = 0x35EE
N_DEFAULT = 20000

STATE_ADDR = 0xFFFF72B8
DELTA_ADDR = 0xFFFF72BC
MARK_ADDR = 0xFFFF72C0
FN_PTR_ADDR = 0x00004B10           # ROM constant pool @0x3698 = 0x4B10
STUB_ADDR = 0x00100000             # sparse-RAM address backing the task body

# Task-body stub (big-endian SH-2 words) — byte-for-byte the C `task_stub` in
# oracle_task_flag_run_c.c.  Layout:
#   D007 mov.l @(0x20,pc),r0        r0 = 0xFFFF72B8 (state)
#   D108 mov.l @(0x24,pc),r1        r1 = 0xFFFF72BC (delta)
#   D208 mov.l @(0x20,pc),r2        r2 = 0x00000004 (marker bit)
#   D309 mov.l @(0x24,pc),r3        r3 = 0xFFFF72C0 (mark)
#   6412 mov.l @r1,r4               r4 = *delta
#   6102 mov.l @r0,r1               r1 = *state     (bit 15 held here)
#   214B or    r4,r1                r1 |= *delta
#   212B or    r2,r1                r1 |= 0x4
#   2012 mov.l r1,@r0               *state = r1
#   2312 mov.l r1,@r3               *mark = r1
#   000B rts / 0009 nop             (delay slot)
STUB = [0xD007, 0xD108, 0xD208, 0xD309,
        0x6412, 0x6102, 0x214B, 0x212B,
        0x2012, 0x2312, 0x000B, 0x0009]

# Stub's PC-relative constant pool.
STUB_CONST = {
    0x00100020: STATE_ADDR,
    0x00100024: DELTA_ADDR,
    0x00100028: 0x00000004,
    0x0010002C: MARK_ADDR,
}

# Edge vectors: (initial state word, task-body delta).  Boundaries, 0, max,
# bit-15 on/off, sign flips, marker-bit aliasing (delta == 0x4).
EDGE_STATE = [0x00000000, 0xFFFFFFFF, 0xFFFF7FFF, 0x00008000, 0x80000000,
              0x7FFFFFFF, 0x0000FFFF, 0xFFFF0000, 0x00008004, 0xAAAAAAAA]
EDGE_DELTA = [0x00000000, 0x00008000, 0xFFFFFFFF, 0x80000000, 0x00000004,
              0x7FFFFFFF, 0x00000001, 0xFFFF7FFF, 0xDEADBEEF]
EDGE = [(s, d) for s in EDGE_STATE for d in EDGE_DELTA]
EDGE += [  # sign-flip / bit-flip specials
    (0xFFFFFFFF, 0x00000000), (0x00000000, 0xFFFFFFFF),
    (0x80008000, 0x80000001), (0x00000001, 0xFFFFFFFE),
    (0xFFFF7FFF, 0xFFFF7FFF), (0x00008000, 0x00008000),
    (0x00008000, 0xFFFF7FFF), (0x00000000, 0x00000004),
]

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = os.path.join('/tmp', 'rx8-recon-task_flag_run_c')


def put16(ram, addr, word):
    ram[addr & MASK] = (word >> 8) & 0xFF
    ram[(addr + 1) & MASK] = word & 0xFF


def put32(ram, addr, val):
    ram[addr & MASK] = (val >> 24) & 0xFF
    ram[(addr + 1) & MASK] = (val >> 16) & 0xFF
    ram[(addr + 2) & MASK] = (val >> 8) & 0xFF
    ram[(addr + 3) & MASK] = val & 0xFF


def get32(ram, addr):
    return ((ram.get(addr, 0) << 24) | (ram.get(addr + 1, 0) << 16)
            | (ram.get(addr + 2, 0) << 8) | ram.get(addr + 3, 0))


def run_flag(cpu, state, delta):
    """Execute the ROM @0x35EE with the given state word + task-body delta;
    return (final state word, marker word) read back from the RAM overlay."""
    ram = {}
    for i, w in enumerate(STUB):
        put16(ram, STUB_ADDR + 2 * i, w)
    for a, v in STUB_CONST.items():
        put32(ram, a, v)
    put32(ram, FN_PTR_ADDR, STUB_ADDR)      # scheduler's fn pointer
    put32(ram, STATE_ADDR, state)
    put32(ram, DELTA_ADDR, delta)
    put32(ram, MARK_ADDR, 0)
    cpu.call(ADDR, ram=ram)
    return get32(cpu.ram, STATE_ADDR), get32(cpu.ram, MARK_ADDR)


def build_oracle(cc='cc'):
    """Compile the reconstructed source + its own oracle into a host binary."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_task_flag_run_c.c'),
           os.path.join(SAMPLES, 'src', 'rx8_task_flag_run_c.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    with open(ROM_PATH, 'rb') as f:
        cpu = SH2(f.read())
    oracle = build_oracle()
    rng = make_rng(0x60E1D400)

    vectors = list(EDGE) + [(rng.getrandbits(32), rng.getrandbits(32))
                            for _ in range(n)]

    # (a) ROM behaviour via the emulator, (b) host C on the same inputs.
    emu = [run_flag(cpu, s, d) for s, d in vectors]
    lines = ['flag %08X %08X' % (s, d) for s, d in vectors]
    host = [tuple(x.split()) for x in run_oracle(oracle, lines)]

    # (c) compare both RAM words bit-exactly.
    mismatches = []
    for k, ((s, d), e, h) in enumerate(zip(vectors, emu, host)):
        if tuple('%08X' % w for w in e) != h:
            mismatches.append(
                'vec#%d state=0x%08X delta=0x%08X ROM=(%s) C=(%s)'
                % (k, s, d,
                   ' '.join('%08X' % w for w in e), ' '.join(h)))
            if len(mismatches) >= 5:
                break

    report('task_flag_run_C', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
