#!/usr/bin/env python3
"""
harness_task_execute_by_index.py — equivalence of rx8_task_execute_by_index @0x3854.

Reconstructed source: samples/src/rx8_task_execute_by_index.c
Verified lift   : c/task_execute_by_index.c  (task_execute_by_index @ 0x3854)

The ROM routine is the OS task-dispatch helper: look the task up in the kernel
task table (16-byte entries at 0x4990), test its run counter (+3 of the task
state block), and
  - counter == 0 -> not runnable: return 4 and, when the kernel flag at 0x4B08
    is set, call the interrupt-priority dispatcher 0x3610 with (4, 1, status);
  - otherwise    -> decrement the counter, call the per-task execution helper
    0x39BA with (os_ctrl, index, priority); if the helper returns non-zero AND
    ((entry SR & 0xF0) | os_ctrl->status) == 0 AND the OS context-save block's
    gate byte (+1) == 0, set os_ctrl->status = 0x0100, call the task-running
    flag barrier 0x35EE(2) when the kernel flag at 0x4B10 is set, then call
    the full-context-save routine 0x3BF4(os_ctrl, entry_sr, state_block).

The function enters through the normal ABI (r4 = task index) but immediately
indirect-calls the four OS-layer callees, so the harness follows the
harness_task_flag_run_c.py pattern: the callee addresses are stubbed IN the
emulator's ram overlay (which the fetch path probes before the ROM) with tiny
SH-2 bodies that (a) return a harness-seeded value for the 0x39BA helper and
(b) record their observed arguments + a 0xA5 marker into scratch cells.  The
real ROM control flow is then executed end-to-end.

A per-vector input is a 13-tuple (see the oracle header): index, priority byte,
task-state-block pointer + gate byte + counter, os_ctrl status/saved_sr/
state-block pointer + its gate byte, the two kernel flags (0x4B08/0x4B10), the
entry status register, and the helper-return value.  Compared bit-exactly
after every call:

  - the return value (0 or 4),
  - the task run counter byte (decrement side effect),
  - the os_ctrl status word (0x0100 side effect on the full-context path),
  - the helper/barrier/context-save/dispatcher call boundaries (markers +
    recorded r4/r5/r6 arguments),
  - the final status register (path-dependent: the full-context-save exit
    does NOT restore SR, every other exit does).

The task table lives at ROM address 0x4990 and the kernel flags at 0x4B08 /
0x4B10 — all below the host's mmap_min_addr, so on the host they are modelled
as parameters (documented in the source header; the oracle seeds byte-identical
values on its re-homed table copy, and the harness seeds the identical bytes
at 0x4990/0x4B08/0x4B10 in the emulator overlay).

Procedure (Track-A pattern):
  1. build the host oracle (system gcc; -O2, -Wall, -Wextra),
  2. edge vectors (counter 0/1/0x80/0xFF, sign-flip priorities, helper ret
     0/non-zero, gate-word boundaries, flags on/off, index bounds, SR edges)
     + N random vectors (a fraction path-directed so every branch is hit),
  3. run the ROM bytes @0x3854 in tools/sh2emu.py on the same vectors,
  4. run the host C on the same vectors,
  5. compare all 17 output words bit-exactly — 0 mismatches required.

Usage:  python3 harness_task_execute_by_index.py [N]   (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROM_PATH, make_rng, report, run_oracle  # noqa: E402
from sh2emu import SH2, MASK  # noqa: E402

ADDR = 0x3854
N_DEFAULT = 20000

# --- ROM-side kernel structure addresses ------------------------------------
TASK_TABLE   = 0x00004990        # task table base (16-byte entries)
FLAG_4B08    = 0x00004B08        # kernel flag: interrupt-priority dispatch
FLAG_4B10    = 0x00004B10        # kernel flag: task-running-flag barrier
OS_CTRL      = 0xFFFF72B0        # OS control block base
OS_STATUS    = OS_CTRL + 8       # +8  u32 status word
OS_SAVED_SR  = OS_CTRL + 16      # +16 u32 saved status register
OS_STATE_BLK = OS_CTRL + 24      # +24 u8* context-save state block

# --- host-side scratch / marker cells (page 0xFFFF7000, mmap'd by the
# oracle; seeded into the emulator overlay for the stubs) ---------------------
HELPER_RET   = 0xFFFF71C0        # seeded: value the 0x39BA stub returns
HELPER_REC   = 0xFFFF71C8        # 0x39BA observed r4/r5/r6
FLAGRUN_MARK = 0xFFFF71D4        # 0xA5 if 0x35EE was reached
FLAGRUN_ARG  = 0xFFFF71D8        # 0x35EE observed r4
CTX_MARK     = 0xFFFF71DC        # 0xA5 if 0x3BF4 was reached
CTX_REC      = 0xFFFF71E0        # 0x3BF4 observed r4/r5/r6
IPD_MARK     = 0xFFFF71EC        # 0xA5 if 0x3610 was reached
IPD_REC      = 0xFFFF71F0        # 0x3610 observed r4/r5/r6

# State blocks: task blocks at 0x00100000 + k*32, OS ctx-save block at
# 0x00100200 / 0x00100240 (all inside the page the oracle mmap()s).
STB_POOL = [0x00100000, 0x00100020, 0x00100040, 0x00100060,
            0x00100080, 0x001000A0, 0x001000C0, 0x001000E0]
OS_SB_CHOICES = (0x00100200, 0x00100240)

N_IDX = 23                      # task table entries: indices 0..22 (entry 23
                                # at 0x4B10 would alias the kernel flag word)                        # indices tested: 0..63 (16-byte stride)

# --- callee stubs (big-endian SH-2 words), installed in the emulator overlay
# at the ROM addresses the constant pool points at.  Each records its observed
# arguments + a 0xA5 marker into the scratch cells; the 0x39BA helper returns
# *HELPER_RET.  (mov.l r4,@r1 = 0x2124, mov.l r2,@r0 = 0x2022, mov r3,r0 =
# 0x6003, rts = 0x000B, nop = 0x0009.) ---------------------------------------
STUBS = {
    # 0x39BA task_execute_helper: r3 = *HELPER_RET; rec r4/r5/r6 at HELPER_REC;
    #   return r0 = r3.  PC-rel consts: 0x3A0C <- disp 0x14 (base 0x39BC),
    #   0x3A20 <- disp 0x18 (base 0x39C0).
    0x39BA: ([0xD014, 0xD118, 0x6302, 0x2142, 0x7104, 0x2152, 0x7104,
              0x2162, 0x6033, 0x000B, 0x0009],
             {0x3A0C: HELPER_RET, 0x3A20: HELPER_REC}),
    # 0x35EE task_flag_run_C: *FLAGRUN_ARG = r4; *FLAGRUN_MARK = 0xA5.
    #   PC-rel consts: 0x3660 <- disp 0x1C (base 0x35F0), 0x3674 <- disp 0x20
    #   (base 0x35F4), 0x3688 <- disp 0x25 (base 0x35F4).
    0x35EE: ([0xD01C, 0xD120, 0xD225, 0x2142, 0x2022, 0x000B, 0x0009],
             {0x3660: FLAGRUN_MARK, 0x3674: FLAGRUN_ARG, 0x3688: 0xA5}),
    # 0x3BF4 task_full_context_save: rec r4/r5/r6 at CTX_REC; mark.
    #   PC-rel consts: 0x3C68 <- disp 0x1C (base 0x3BF8), 0x3C78 <- disp 0x20
    #   (base 0x3BF8), 0x3C88 <- disp 0x23 (base 0x3BFC).
    0x3BF4: ([0xD01C, 0xD120, 0xD223, 0x2142, 0x7104, 0x2152, 0x7104,
              0x2162, 0x2022, 0x000B, 0x0009],
             {0x3C68: CTX_MARK, 0x3C78: CTX_REC, 0x3C88: 0xA5}),
    # 0x3610 interrupt_priority_dispatch: rec r4/r5/r6 at IPD_REC; mark.
    #   PC-rel consts: 0x3684 <- disp 0x1C (base 0x3614), 0x3694 <- disp 0x20
    #   (base 0x3614), 0x36A4 <- disp 0x23 (base 0x3618).
    0x3610: ([0xD01C, 0xD120, 0xD223, 0x2142, 0x7104, 0x2152, 0x7104,
              0x2162, 0x2022, 0x000B, 0x0009],
             {0x3684: IPD_MARK, 0x3694: IPD_REC, 0x36A4: 0xA5}),
}

# --- edge vectors ------------------------------------------------------------
# (idx, prio, stp, sb1, cnt, status, savsr, ossb, ossb1, f08, f10, sr, hret)
# stp  = task state block ptr; sb1/cnt = its +1/+3 bytes
# ossb = OS ctx-save block ptr; ossb1 = its +1 gate byte
EDGE = [
    # not runnable (counter == 0): ipd off / on, boundary indices
    (0, 5, 0x00100000, 0, 0, 0x00000000, 0x000000F0, 0x00100200, 0, 0, 0,
     0x000000F0, 0),
    (0, 5, 0x00100000, 0, 0, 0x00000000, 0x000000F0, 0x00100200, 0,
     0x12345678, 0, 0x000000F0, 0),
    (63, 5, 0x001000E0, 0, 0, 0xDEADBEEF, 0x000000F0, 0x00100200, 0,
     0xFFFFFFFF, 0, 0x000000F0, 0),
    # runnable, helper returns 0 (simple exit, SR restored)
    (0, 5, 0x00100000, 0, 1, 0x00000000, 0x000000F0, 0x00100200, 0, 0, 0,
     0x000000F0, 0),
    (1, 5, 0x00100020, 0, 2, 0x00000100, 0x000000F0, 0x00100200, 0, 0, 0,
     0x000000F0, 0),
    # runnable, counter sign-extension edges: 0x80 -> 0x7F, 0xFF -> 0xFE,
    # 1 -> 0xFF
    (0, 5, 0x00100000, 0, 0x80, 0, 0x000000F0, 0x00100200, 0, 0, 0,
     0x000000F0, 0),
    (0, 5, 0x00100000, 0, 0xFF, 0, 0x000000F0, 0x00100200, 0, 0, 0,
     0x000000F0, 0),
    (0, 5, 0x00100000, 0, 0x7F, 0, 0x000000F0, 0x00100200, 0, 0, 0,
     0x000000F0, 0),
    # priority sign-extension edges (helper records (int8)prio)
    (0, 0x80, 0x00100000, 0, 1, 0, 0x000000F0, 0x00100200, 0, 0, 0,
     0x000000F0, 1),
    (0, 0xFF, 0x00100000, 0, 1, 0, 0x000000F0, 0x00100200, 0, 0, 0,
     0x000000F0, 1),
    # helper != 0 but (entry SR & 0xF0) | status != 0  ->  restore SR, exit
    (0, 5, 0x00100000, 0, 1, 0x00000000, 0x000000F0, 0x00100200, 0, 0, 0,
     0x000000F0, 1),
    (0, 5, 0x00100000, 0, 1, 0x00000001, 0x000000F0, 0x00100200, 0, 0, 0,
     0x00000010, 1),
    (0, 5, 0x00100000, 0, 1, 0x00000000, 0x000000F0, 0x00100200, 0, 0, 0,
     0x00000010, 1),
    (0, 5, 0x00100000, 0, 1, 0xFFFFFFFF, 0x000000F0, 0x00100200, 0, 0, 0,
     0x000000F0, 1),
    # gates clear but OS ctx-save gate byte != 0  ->  restore SR, exit
    (0, 5, 0x00100000, 0, 1, 0x00000000, 0x000000F0, 0x00100200, 1, 0, 0,
     0x0000000F, 1),
    (0, 5, 0x00100000, 0, 1, 0x00000000, 0x000000F0, 0x00100200, 0xFF, 0, 0,
     0x00000000, 1),
    # full context save, flag-run barrier off / on, SR NOT restored on exit
    (0, 5, 0x00100000, 0, 1, 0x00000000, 0x11111111, 0x00100200, 0, 0, 0,
     0x0000000F, 1),
    (0, 5, 0x00100000, 0, 1, 0x00000000, 0x000000F0, 0x00100200, 0, 0,
     0xAAAAAAAA, 0x00000000, 1),
    (2, 0x90, 0x00100040, 0, 3, 0x00000000, 0x00000010, 0x00100240, 0,
     0x01020304, 0x00000001, 0x00000000, 0xFFFFFFFF),
    (15, 0xFF, 0x00100080, 0, 0xFF, 0x00000000, 0x000000FF, 0x00100200, 0,
     0, 0x80000000, 0x00000000, 0x00000001),
    # index / misc boundaries (task table has 23 entries: idx 0..22; higher
    # indices alias the kernel flags at 0x4B08/0x4B10 and are out of range)
    (22, 0, 0x001000C0, 0, 1, 0, 0, 0x00100200, 0, 0, 0, 0, 0),
    (22, 1, 0x001000E0, 0, 1, 0, 0, 0x00100200, 0, 0, 0, 0, 1),
    (0, 5, 0x00100000, 0, 1, 0, 0, 0x00100200, 0, 0, 0, 0x000000F0, 1),
]

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = os.path.join('/tmp', 'rx8-recon-task_execute_by_index')


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


def build_ram(v):
    """ram overlay for one vector: callee stubs, task table entry, state
    blocks, OS control block fields, kernel flags and the scratch cells."""
    idx, prio, stp, sb1, cnt, status, savsr, ossb, ossb1, f08, f10, sr, hret = v
    ram = {}

    for base, (code, consts) in STUBS.items():
        for i, op in enumerate(code):
            put16(ram, base + 2 * i, op)
        for a, val in consts.items():
            put32(ram, a, val)

    # task table entry for `idx` (16-byte stride; the ROM reads the priority
    # byte at +2 and the state-block pointer at +4).
    te = TASK_TABLE + idx * 16
    ram[te + 2] = prio & 0xFF
    put32(ram, te + 4, stp)

    # task state block: +1 gate byte (unused by this function, seeded for
    # byte-identical RAM), +3 run counter.
    put16(ram, stp + 0, 0)
    put16(ram, stp + 2, 0)
    ram[stp + 1] = sb1 & 0xFF
    ram[stp + 3] = cnt & 0xFF

    # OS context-save state block + its gate byte.
    put16(ram, ossb + 0, 0)
    put16(ram, ossb + 2, 0)
    ram[ossb + 1] = ossb1 & 0xFF

    # OS control block: status(+8), saved_sr(+16), state block ptr(+24).
    put32(ram, OS_STATUS, status)
    put32(ram, OS_SAVED_SR, savsr)
    put32(ram, OS_STATE_BLK, ossb)

    # Kernel flags and the scratch cells.
    put32(ram, FLAG_4B08, f08)
    put32(ram, FLAG_4B10, f10)
    put32(ram, HELPER_RET, hret)
    put32(ram, HELPER_REC + 0, 0)
    put32(ram, HELPER_REC + 4, 0)
    put32(ram, HELPER_REC + 8, 0)
    put32(ram, FLAGRUN_MARK, 0)
    put32(ram, FLAGRUN_ARG, 0)
    put32(ram, CTX_MARK, 0)
    put32(ram, CTX_REC + 0, 0)
    put32(ram, CTX_REC + 4, 0)
    put32(ram, CTX_REC + 8, 0)
    put32(ram, IPD_MARK, 0)
    put32(ram, IPD_REC + 0, 0)
    put32(ram, IPD_REC + 4, 0)
    put32(ram, IPD_REC + 8, 0)
    return ram


def run(cpu, v):
    """Drive the ROM @0x3854 with the given vector; return the 17 output
    words: (ret, counter', status', helper rec r4/r5/r6, flagrun mark/arg,
    ctx mark/r4/r5/r6, ipd mark/r4/r5/r6, sr')."""
    idx, prio, stp, sb1, cnt, status, savsr, ossb, ossb1, f08, f10, sr, hret = v
    ret = cpu.call(ADDR, r4=idx, ram=build_ram(v), sr=sr)
    ram = cpu.ram
    out = [
        ret,
        ram.get(stp + 3, 0),
        get32(ram, OS_STATUS),
        get32(ram, HELPER_REC + 0), get32(ram, HELPER_REC + 4),
        get32(ram, HELPER_REC + 8),
        get32(ram, FLAGRUN_MARK), get32(ram, FLAGRUN_ARG),
        get32(ram, CTX_MARK), get32(ram, CTX_REC + 0),
        get32(ram, CTX_REC + 4), get32(ram, CTX_REC + 8),
        get32(ram, IPD_MARK), get32(ram, IPD_REC + 0),
        get32(ram, IPD_REC + 4), get32(ram, IPD_REC + 8),
        cpu.sr,
    ]
    return out


def build_oracle(cc='cc'):
    """Compile the reconstructed source + its own oracle into a host binary."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_task_execute_by_index.c'),
           os.path.join(SAMPLES, 'src', 'rx8_task_execute_by_index.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    with open(ROM_PATH, 'rb') as f:
        cpu = SH2(f.read())
    oracle = build_oracle()
    rng = make_rng(0x3854)               # fixed seed: the function address

    def rand_vec(kind):
        idx = rng.randrange(N_IDX)
        prio = rng.randrange(256)
        stp = rng.choice(STB_POOL)
        sb1 = rng.randrange(256)
        ossb = rng.choice(OS_SB_CHOICES)
        ossb1 = rng.randrange(256)
        f08 = rng.getrandbits(32)
        f10 = rng.getrandbits(32)
        savsr = rng.getrandbits(32)
        if kind == 0:                       # not-runnable: counter == 0
            cnt = 0
            status = rng.getrandbits(32)
            sr = rng.getrandbits(32)
            hret = rng.getrandbits(32)
        elif kind == 1:                     # full-context-save candidate
            cnt = rng.randrange(1, 256)
            status = 0
            sr = rng.randrange(16)          # (sr & 0xF0) == 0
            hret = 1 if rng.random() < 0.5 else rng.getrandbits(32)
            if hret == 0:
                hret = 1
            ossb1 = 0
        else:                               # fully random
            cnt = rng.randrange(256)
            status = rng.getrandbits(32)
            sr = rng.getrandbits(32)
            hret = rng.getrandbits(32)
            ossb1 = rng.randrange(256)
        return (idx, prio, stp, sb1, cnt, status, savsr, ossb, ossb1,
                f08, f10, sr, hret)

    vectors = list(EDGE)
    for i in range(n):
        vectors.append(rand_vec(i % 3))

    # (a) ROM behaviour via the emulator.
    emu = [run(cpu, v) for v in vectors]

    # (b) host-C on the same vectors.
    lines = ['task %X %X %X %X %X %X %X %X %X %X %X %X %X' % v
             for v in vectors]
    host = [[int(x, 16) for x in ln.split()] for ln in run_oracle(oracle, lines)]

    # (c) compare all 17 output words bit-exactly.
    mismatches = []
    for k, (v, e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d idx=%d cnt=0x%02X hret=0x%08X ROM=(%s) C=(%s)'
                % (k, v[0], v[4], v[12],
                   ' '.join('%08X' % w for w in e),
                   ' '.join('%08X' % w for w in h)))
            if len(mismatches) >= 5:
                break

    report('task_execute_by_index', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
