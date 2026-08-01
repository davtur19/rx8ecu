#!/usr/bin/env python3
"""
harness_task_end_routine.py — equivalence of rx8_task_end_routine @0x3D58.

Reconstructed source: samples/src/rx8_task_end_routine.c
Verified lift   : c/taskEndRoutine.c  (taskEndRoutine @ 0x3D58; the same ROM
                  bytes are executed for real here via tools/sh2emu.py).

The ROM function is a void OS tear-down routine with NO ABI return value: its
whole effect is on RAM — the OS control block @0xFFFF72B0 (status +8, result
+12, saved_sr +16, current_task +20) and the task control block it points to
(active +0, type +1, refcount +3, saved_sp +4).  The equivalence check
therefore compares RAM side-effects bit-exactly, not a return value:

  - emulator side: seed the OS/task control blocks in the sparse RAM overlay,
    install the task-body stub @0x00100000 and the two callee stubs
    (consistencyCheck @0x3A28 and task_dispatcher @0x3C2A — the established
    c/tests/test_taskEndRoutine.py pattern), seed 0x4B10 to the stub address
    when the running-flag path is to be exercised, call the ROM entry @0x3D58
    and read the five post-state cells back.  task_flag_run_C @0x35EE is
    executed for REAL (its acquire/body/release on the flag word @0xFFFF72B8,
    which aliases os_ctrl->status);
  - host side: the dedicated oracle mmap()s the same pages, seeds the same
    bytes, runs the reconstructed C and prints the same five cells.

EDGE vectors cover the flag 0/1 paths with boundaries, 0, max and sign flips
for every field (plus aliasing: status_pre/result_pre with bit 15, refcount
0xFF wrap, all-ones task block); N random pre-states follow (fixed seed).

Usage:  python3 harness_task_end_routine.py [N]   (default N = 20000)
"""
import os
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROM_PATH, make_rng, report, run_oracle  # noqa: E402
from sh2emu import SH2, MASK  # noqa: E402

ADDR = 0x3D58
N_DEFAULT = 20000
SEED = 0x3D58                    # the ROM address doubles as the RNG seed

OS_CTRL_ADDR = 0xFFFF72B0        # OS control block base
FLAG_ADDR = 0x00004B10           # task-body flag / fn pointer (constant pool @0x3D9C)
STATE_ADDR = 0xFFFF72B8          # = os_ctrl+8  (running-flag word = status cell)
DELTA_ADDR = 0xFFFF72BC          # = os_ctrl+12 (barrier stub's per-vector edit)
MARK_ADDR = 0xFFFF72C0           # = os_ctrl+16 (barrier stub's observation cell)
TASK_BLOCK_ADDR = 0xFFFFA000     # task control block base
CONSISTENCY_STUB_ADDR = 0x3A28   # stubbed: rts; nop (c/tests precedent)
DISPATCHER_STUB_ADDR = 0x3C2A    # stubbed: mov #0,r0; rts; nop
STUB_ADDR = 0x00100000           # sparse-RAM address backing the task body

# Task-body stub (big-endian SH-2 words) — byte-for-byte the `task_body_stub`
# in oracle_task_end_routine.c.  Layout:
#   D007 mov.l @(0x20,pc),r0        r0 = 0xFFFF72B8 (flag word / status cell)
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

# Edge vectors: (flag, saved_sr, status_pre, result_pre, active, type,
#                refcount, saved_sp).  Boundaries, 0, max, sign flips, and the
# aliasing cases where status/result carry bit 15 (the barrier's running bit).
EDGE = []
for flag in (0, 1):
    for saved_sr in (0x000000F0, 0x00000000):
        for status_pre in (0x00000000, 0x00000100, 0x00008000, 0xFFFF7FFF,
                           0xFFFFFFFF):
            for result_pre in (0x00000000, 0x00000004, 0x00008000,
                               0xFFFFFFFF):
                for active in (0x00, 0x01, 0xFF):
                    for type_ in (0x00, 0x01, 0x7F, 0x80, 0xFF):
                        for ref in (0x00, 0x01, 0xFF):
                            for sp in (0x00000000, 0xDEADBEEF, 0xFFFFFFFF):
                                EDGE.append((flag, saved_sr, status_pre,
                                             result_pre, active, type_, ref,
                                             sp))
# sign-flip / wrap specials
EDGE += [
    (0, 0x000000F0, 0x80000000, 0x80000000, 0x00, 0x00, 0x00, 0x80000000),
    (1, 0x000000F0, 0x80000000, 0x80000000, 0xFF, 0xFF, 0xFF, 0x80000000),
    (1, 0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF, 0xFF, 0xFF, 0xFF, 0xFFFFFFFF),
    (0, 0x00000000, 0x00000000, 0x00000000, 0x00, 0x00, 0x00, 0x00000000),
    (1, 0x00008000, 0x00008000, 0x00008000, 0x01, 0x01, 0xFE, 0x00008000),
]

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = os.path.join('/tmp', 'rx8-recon-task_end_routine')


def build_oracle(cc='cc'):
    """Compile the reconstructed source + its dedicated oracle into a binary."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_task_end_routine.c'),
           os.path.join(SAMPLES, 'src', 'rx8_task_end_routine.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def put16(ram, addr, word):
    ram[addr & MASK] = (word >> 8) & 0xFF
    ram[(addr + 1) & MASK] = word & 0xFF


def put32(ram, addr, val):
    ram[addr & MASK] = (val >> 24) & 0xFF
    ram[(addr + 1) & MASK] = (val >> 16) & 0xFF
    ram[(addr + 2) & MASK] = (val >> 8) & 0xFF
    ram[(addr + 3) & MASK] = val & 0xFF


def run_end_routine(cpu, flag, saved_sr, status_pre, result_pre,
                    active, type_, ref, sp):
    """Execute the ROM @0x3D58 with the given pre-state; return the five
    post-state cells: (status, result, saved_sr_final, active, refcount)."""
    ram = {}
    for i, w in enumerate(STUB):
        put16(ram, STUB_ADDR + 2 * i, w)
    for a, v in STUB_CONST.items():
        put32(ram, a, v)
    put32(ram, FLAG_ADDR, STUB_ADDR if flag else 0)
    put32(ram, OS_CTRL_ADDR + 16, saved_sr)      # saved_sr (mark cell)
    put32(ram, OS_CTRL_ADDR + 20, TASK_BLOCK_ADDR)
    put32(ram, OS_CTRL_ADDR + 8, status_pre)     # status (flag word)
    put32(ram, OS_CTRL_ADDR + 12, result_pre)    # result (delta cell)
    ram[TASK_BLOCK_ADDR + 0] = active & 0xFF
    ram[TASK_BLOCK_ADDR + 1] = type_ & 0xFF
    ram[TASK_BLOCK_ADDR + 3] = ref & 0xFF
    put32(ram, TASK_BLOCK_ADDR + 4, sp)
    # callee stubs (c/tests/test_taskEndRoutine.py precedent)
    put16(ram, CONSISTENCY_STUB_ADDR, 0x000B)    # rts
    put16(ram, CONSISTENCY_STUB_ADDR + 2, 0x0009)  # nop
    put16(ram, DISPATCHER_STUB_ADDR, 0xE000)     # mov #0,r0
    put16(ram, DISPATCHER_STUB_ADDR + 2, 0x000B)  # rts
    put16(ram, DISPATCHER_STUB_ADDR + 4, 0x0009)  # nop
    cpu.call(ADDR, ram=ram)
    return (cpu.rd(OS_CTRL_ADDR + 8, 4),
            cpu.rd(OS_CTRL_ADDR + 12, 4),
            cpu.rd(OS_CTRL_ADDR + 16, 4),
            cpu.rd(TASK_BLOCK_ADDR + 0, 1),
            cpu.rd(TASK_BLOCK_ADDR + 3, 1))


def gen_random(rng, n):
    """n random pre-states over the full range of every field."""
    return [(rng.getrandbits(1), rng.getrandbits(32), rng.getrandbits(32),
             rng.getrandbits(32), rng.randrange(256), rng.randrange(256),
             rng.randrange(256), rng.getrandbits(32))
            for _ in range(n)]


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    with open(ROM_PATH, 'rb') as f:
        cpu = SH2(f.read())
    oracle = build_oracle()
    rng = make_rng(SEED)

    vectors = list(EDGE) + gen_random(rng, n)

    # (a) ROM behaviour via the emulator (RAM side-effects).
    emu = [run_end_routine(cpu, *v) for v in vectors]

    # (b) host C on the same pre-states.
    lines = ['end %08X %08X %08X %08X %02X %02X %02X %08X' % v
             for v in vectors]
    host = [tuple(int(x, 16) for x in out.split())
            for out in run_oracle(oracle, lines)]

    # (c) compare the five post-state cells bit-exactly.
    mismatches = []
    for k, (v, e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d flag=%d pre=(sr=%08X st=%08X r=%08X a=%02X t=%02X '
                'rc=%02X sp=%08X) ROM=(%s) C=(%s)'
                % (k, v[0], v[1], v[2], v[3], v[4], v[5], v[6], v[7],
                   ' '.join('%08X' % w for w in e), ' '.join('%08X' % w for w in h)))
            if len(mismatches) >= 5:
                break

    report('taskEndRoutine', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
