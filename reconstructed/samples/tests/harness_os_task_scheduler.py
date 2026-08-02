#!/usr/bin/env python3
"""
harness_os_task_scheduler.py — equivalence of rx8_os_task_scheduler @0x9668.

Reconstructed source: samples/src/rx8_os_task_scheduler.c
Verified lift   : c/osTaskScheduler.c  (osTaskScheduler @ 0x9668; the same ROM
                  bytes are executed for real here via tools/sh2emu.py).

The ROM function is the central OS task dispatch point: given (task_id,
entry_idx) it resolves the task entry from the kernel task pointer table,
copies the caller's argument words onto a 20-byte stack frame, then either
calls the entry's own function pointer (marker == 0xFFFF, r4 = &frame[1]) or
calls the scheduler dispatcher @0x5F34 (marker != 0xFFFF) and returns 1 iff
the dispatcher result is non-zero (a reschedule request).

The equivalence check compares, bit-exactly:

  - emulator side: seed the task pointer table @0xDB14, the task pool
    @0x00120000 and the caller args @0xFFFFD000 in the sparse RAM overlay,
    install the DIRECT-call stub @0x00101000 (the "task function": writes
    REC[0] = arg_count, echoes frame[0..arg_count] — the entry func_ptr then
    the copied args — and stamps the running-mark cell with 0xA5) and the
    DISPATCHER stub @0x5F34 (writes r4 (marker) to the marker cell
    @0xFFFFA100 and returns the seeded disp_ret), then call the ROM entry
    @0x9668 and read the nine post-state cells back;
  - host side: the dedicated oracle mmap()s the same pages, seeds the same
    bytes, runs the reconstructed C and prints the same nine cells.

EDGE vectors cover the direct path (marker 0xFFFF) and the dispatch path
(marker 0/1/2/3/0x7FFF/0xFFFE) across tid 0..28 and eidx 0..11, arg_count
0..4 (the real frame is 20 bytes, so > 4 corrupts the ROM stack), args with
0 / all-ones / sign flips and every dispatcher return seed; N random vectors
follow (fixed seed, 50% direct / 50% dispatch).

Usage:  python3 harness_os_task_scheduler.py [N]   (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROM_PATH, make_rng, report, run_oracle  # noqa: E402
from sh2emu import SH2, MASK  # noqa: E402

ADDR = 0x9668
N_DEFAULT = 20000
SEED = 0x9668                     # the ROM address doubles as the RNG seed

TABLE_ADDR = 0x0000DB14           # g_task_table_ptr (constant pool @0x9780)
POOL_ADDR = 0x00120000            # task pool base
POOL_STRIDE = 0x60                # bytes per task structure (12 entries x 8)
ARGS_ADDR = 0xFFFFD000            # caller argument words

STUB_ADDR = 0x00101000            # DIRECT-call task-body stub
REC_ADDR = STUB_ADDR + 48         # record area (stub output)
MARK_ADDR = STUB_ADDR + 88        # running-mark cell (0xA5 when fired)
PAT_ADDR = STUB_ADDR + 92         # 0xA5 constant slot

DISP_STUB_ADDR = 0x5F34           # dispatcher stub (RAM overlay over ROM)
DMARK_CELL = 0xFFFFA100           # dispatcher marker cell
DISP_SLOT = DISP_STUB_ADDR + 16   # pool slot: DMARK_CELL self-address
DISP_RET_SLOT = DISP_STUB_ADDR + 20  # pool slot: seeded dispatcher return

FUNC_ADDR = STUB_ADDR             # func_ptr value seeded for direct entries


def put16(ram, addr, word):
    ram[addr & MASK] = (word >> 8) & 0xFF
    ram[(addr + 1) & MASK] = word & 0xFF


def put32(ram, addr, val):
    ram[addr & MASK] = (val >> 24) & 0xFF
    ram[(addr + 1) & MASK] = (val >> 16) & 0xFF
    ram[(addr + 2) & MASK] = (val >> 8) & 0xFF
    ram[(addr + 3) & MASK] = val & 0xFF


# ---------------------------------------------------------------------------
# DIRECT-call stub (big-endian SH-2 words) — byte-for-byte the `direct_stub`
# in oracle_os_task_scheduler.c.  The ROM calls it with r4 = &frame[1],
# r5 = args advanced past arg_count words and r6 = args base, so the stub
# derives arg_count as (r5 - r6) / 4.  Layout (21 words):
#   6353 mov r5,r3         ; r3 = args_advanced
#   3368 sub r6,r3         ; r3 = args_advanced - args_base = arg_count*4
#   4309 shlr2 r3          ; r3 = arg_count
#   6233 mov r3,r2         ; r2 = arg_count (0x6nm3: n=dest=2, m=src=3)
#   D009 mov.l @(0x24,pc),r0 ; r0 = REC (0x00101030)
#   2022 mov.l r2,@r0      ; REC[0] = arg_count
#   7004 add #4,r0         ; r0 = &REC[1]
#   7201 add #1,r2         ; r2 = arg_count + 1 (words to echo)
#   6743 mov r4,r7         ; r7 = &frame[1]
#   77FC add #-4,r7        ; r7 = &frame[0]
#   6176 mov.l @r7+,r1     ; r1 = frame[i], r7++
#   2012 mov.l r1,@r0      ; REC[1+i] = frame[i], r0 += 4 (next)
#   7004 add #4,r0
#   72FF add #-1,r2
#   2228 tst r2,r2 / 8BF9 bf -7    ; loop while r2 != 0
#   D10D mov.l @(0x34,pc),r1 ; r1 = MARK self-address
#   D20E mov.l @(0x38,pc),r2 ; r2 = 0xA5
#   2122 mov.l r2,@r1      ; MARK = 0xA5
#   000B rts / 0009 nop
# ---------------------------------------------------------------------------
DIR_STUB = [0x6353, 0x3368, 0x4309, 0x6233, 0xD009, 0x2022, 0x7004, 0x7201,
            0x6743, 0x77FC, 0x6176, 0x2012, 0x7004, 0x72FF, 0x2228, 0x8BF9,
            0xD10D, 0xD20E, 0x2122, 0x000B, 0x0009]

# ---------------------------------------------------------------------------
# DISPATCHER stub (RAM overlay over the ROM at 0x5F34) — the ROM tail-calls it
# with r4 = marker, r5 = frame and uses r0 as a reschedule flag.  Layout
# (words at 0x5F34, 0x5F36, 0x5F38, 0x5F3A, 0x5F3C, 0x5F3E):
#   6143 mov r4,r1         ; keep marker (mov r4,r1 = 0x6nm3, n=dest=1, m=src=4)
#   D003 mov.l @(0xC,pc),r0 ; r0 = [slot] = DMARK_CELL (0xFFFFA100)
#                           ;   EA = ((pc+4) & ~3) + 0xC = 0x5F38 + 0xC = 0x5F44
#   2042 mov.l r4,@r0      ; *DMARK_CELL = marker
#   D003 mov.l @(0xC,pc),r0 ; r0 = [slot] = seeded disp_ret @ 0x5F48
#                           ;   EA = ((pc+4) & ~3) + 0xC = 0x5F3C + 0xC = 0x5F48
#   000B rts / 0009 nop
# ---------------------------------------------------------------------------
# SH-2 gotcha (fixed): 0x6144 is mov.b @r4+,r1 (byte load with r4++) — it
# bumped r4 by 1 so the marker written to DMARK_CELL was marker+1.  The real
# move is 0x6143.  And D004 at 0x5F3A would target EA 0x5F4C (real ROM bytes
# 0x2F966A53), not the seeded slot at 0x5F48: the dispatcher then always
# returned non-zero, so the ROM scheduler returned ret=1 even when disp_ret=0.
# ---------------------------------------------------------------------------
DISP_STUB = [0x6143, 0xD003, 0x2042, 0xD003, 0x000B, 0x0009]


def build_ram(tid, eidx, marker, ac, func, args, disp_ret):
    ram = {}
    for i, w in enumerate(DIR_STUB):
        put16(ram, STUB_ADDR + 2 * i, w)
    put32(ram, REC_ADDR, REC_ADDR)       # pool slot self-address
    put32(ram, MARK_ADDR, MARK_ADDR)     # mark cell self-address
    put32(ram, PAT_ADDR, 0xA5)           # running-mark constant
    for i, w in enumerate(DISP_STUB):
        put16(ram, DISP_STUB_ADDR + 2 * i, w)
    put32(ram, DISP_SLOT, DMARK_CELL)    # dispatcher marker cell address
    put32(ram, DISP_RET_SLOT, disp_ret)  # seeded dispatcher return
    put32(ram, DMARK_CELL, 0)
    for t in range(29):
        put32(ram, TABLE_ADDR + 4 * t, POOL_ADDR + t * POOL_STRIDE)
    e = POOL_ADDR + tid * POOL_STRIDE + eidx * 8
    put16(ram, e + 0, marker)
    put16(ram, e + 2, ac)
    put32(ram, e + 4, func)
    for i, a in enumerate(args):
        put32(ram, ARGS_ADDR + 4 * i, a)
    return ram


def run_scheduler(cpu, tid, eidx, marker, ac, func, args, disp_ret):
    """Execute the ROM @0x9668 with the given pre-state; return the nine
    post-state cells: (ret, MARK, REC[0..5], DMARK)."""
    ram = build_ram(tid, eidx, marker, ac, func, args, disp_ret)
    ret = cpu.call(ADDR, r4=tid, r5=eidx, r6=ARGS_ADDR, ram=ram)
    mark = cpu.rd(MARK_ADDR, 4)
    rec = tuple(cpu.rd(REC_ADDR + 4 * i, 4) for i in range(6))
    dmark = cpu.rd(DMARK_CELL, 4)
    return (ret, mark) + rec + (dmark,)


# ---------------------------------------------------------------------------
# Edge vectors: (tid, eidx, marker, ac, func, args8, disp_ret).
# Direct path (marker == 0xFFFF, func = the stub address).
# ---------------------------------------------------------------------------
ARGS_Z = (0, 0, 0, 0, 0, 0, 0, 0)
ARGS_O = (0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF,
          0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF)
ARGS_D = (0xDEADBEEF, 0xCAFEBABE, 0x12345678, 0x9ABCDEF0,
          0x00008000, 0x80000000, 0x7FFFFFFF, 0x11111111)
ARGS_S = (0x00000001, 0xFFFFFFFE, 0x80000000, 0x7FFFFFFF,
          0x00000000, 0xFFFFFFFF, 0xAAAAAAAA, 0x55555555)

EDGE = [
    # direct: tid/eidx/ac boundaries, 0 / max / sign-flip args
    (0, 0, 0xFFFF, 0, FUNC_ADDR, ARGS_Z, 0),
    (0, 0, 0xFFFF, 0, FUNC_ADDR, ARGS_O, 0),
    (1, 2, 0xFFFF, 1, FUNC_ADDR, ARGS_D, 0),
    (1, 2, 0xFFFF, 2, FUNC_ADDR, (0x11111111, 0x22222222, 0, 0, 0, 0, 0, 0), 0),
    (5, 4, 0xFFFF, 4, FUNC_ADDR, (1, 2, 3, 4, 0, 0, 0, 0), 0),
    (0, 11, 0xFFFF, 1, FUNC_ADDR, (0x99, 0x88, 0, 0, 0, 0, 0, 0), 0),
    (28, 0, 0xFFFF, 0, FUNC_ADDR, ARGS_S, 0),
    (28, 11, 0xFFFF, 4, FUNC_ADDR, (0xFFFFFFFF, 0, 0x80000000, 0x7FFFFFFF,
                                    0, 0, 0, 0), 0),
    (28, 11, 0xFFFF, 0, FUNC_ADDR, ARGS_O, 0),
    (2, 0, 0xFFFF, 2, FUNC_ADDR, (0x80000000, 0x7FFFFFFF, 0, 0, 0, 0, 0, 0), 0),
    # dispatch: marker 0 / 1 / 2 / 3 / 0x7FFF / 0xFFFE, ac 0/2/4, all ret seeds
    (2, 0, 0x0002, 3, 0xDEADBEEF, ARGS_D, 1),
    (2, 3, 0x0003, 1, 0xDEADBEEF, (0xCAFEBABE, 0, 0, 0, 0, 0, 0, 0), 0),
    (0, 5, 0x0001, 2, 0xDEADBEEF, (5, 6, 0, 0, 0, 0, 0, 0), 0xFFFFFFFF),
    (0, 5, 0x0001, 2, 0xDEADBEEF, (5, 6, 0, 0, 0, 0, 0, 0), 2),
    (0, 0, 0x0000, 0, 0x00000000, ARGS_Z, 0),
    (3, 7, 0xFFFE, 0, 0x12345678, ARGS_Z, 0),
    (28, 11, 0x7FFF, 4, 0x12345678, (9, 8, 7, 6, 0, 0, 0, 0), 1),
    (28, 11, 0x0001, 4, 0x12345678, (9, 8, 7, 6, 0, 0, 0, 0), 0),
    (0, 1, 0xFFFE, 2, 0xDEADBEEF, ARGS_S, 0xFFFFFFFF),
    (2, 0, 0x0002, 0, 0xDEADBEEF, ARGS_O, 1),
]


def gen_random(rng, n):
    """n random pre-states: tid 0..28, eidx 0..11, arg_count 0..4, random args;
    50% direct (marker 0xFFFF) / 50% dispatch (random marker != 0xFFFF)."""
    out = []
    for _ in range(n):
        tid = rng.randrange(29)
        eidx = rng.randrange(12)
        ac = rng.randrange(5)
        args = tuple(rng.getrandbits(32) for _ in range(8))
        if rng.random() < 0.5:
            out.append((tid, eidx, 0xFFFF, ac, FUNC_ADDR, args, 0))
        else:
            marker = rng.getrandbits(16)
            if marker == 0xFFFF:
                marker = 0xFFFE
            disp_ret = rng.choice((0, 1, 2, 0xFFFFFFFF))
            out.append((tid, eidx, marker, ac, 0xDEADBEEF, args, disp_ret))
    return out


def vec_line(v):
    tid, eidx, marker, ac, func, args, disp_ret = v
    return ('sched %02X %02X %04X %04X %08X ' % (tid, eidx, marker, ac, func)
            + ' '.join('%08X' % a for a in args) + ' %08X' % disp_ret)


SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = os.path.join('/tmp', 'rx8-recon-os_task_scheduler')


def build_oracle(cc='cc'):
    """Compile the reconstructed source + its dedicated oracle into a binary."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_os_task_scheduler.c'),
           os.path.join(SAMPLES, 'src', 'rx8_os_task_scheduler.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    with open(ROM_PATH, 'rb') as f:
        cpu = SH2(f.read())
    oracle = build_oracle()
    rng = make_rng(SEED)

    vectors = list(EDGE) + gen_random(rng, n)

    # (a) ROM behaviour via the emulator (RAM side-effects + return value).
    emu = [run_scheduler(cpu, *v) for v in vectors]

    # (b) host C on the same pre-states.
    host = [tuple(int(x, 16) for x in out.split())
            for out in run_oracle(oracle, [vec_line(v) for v in vectors])]

    # (c) compare the nine post-state cells bit-exactly.
    mismatches = []
    for k, (v, e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            tid, eidx, marker, ac, func, args, disp_ret = v
            mismatches.append(
                'vec#%d tid=%d eidx=%d marker=0x%04X ac=%d func=0x%08X '
                'disp_ret=0x%08X  ROM=(%s) C=(%s)'
                % (k, tid, eidx, marker, ac, func, disp_ret,
                   ' '.join('%08X' % w for w in e), ' '.join('%08X' % w for w in h)))
            if len(mismatches) >= 5:
                break

    report('osTaskScheduler', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
