#!/usr/bin/env python3
"""
harness_task_full_context_save.py — equivalence of rx8_task_full_context_save
@0x3BF4.

Reconstructed source: samples/src/rx8_task_full_context_save.c
Verified lift   : c/task_full_context_save.c  (task_full_context_save @ 0x3BF4;
                  the same ROM bytes are executed for real here via
                  tools/sh2emu.py).

The ROM function is the RTOS full-context-save: called by the scheduler at the
idle->task transition (callers 0x3490 / 0x3854 / 0x3DB0).  It pushes the
suspended task's registers onto the kernel stack @0xFFFFDF00 (r5, pr, a
reserved slot, r8..r12, GBR, r13, mach, r14, macl, plus fr12..fr15 when the
task type byte is 0x04), writes 0x04 to the status byte pointed at by the
descriptor field +0x04, records the final SP into tcb+0x0C and tail-branches
to the scheduler dispatch @0x3C68 (never returns).  The equivalence check
therefore compares RAM side-effects bit-exactly, not a return value:

  - emulator side: seed the task descriptor (type +0, status pointer +0x04)
    and the status cell in the sparse RAM overlay, install the `rts; nop`
    stub @0x3C68 over the ROM (the scheduler-dispatch tail-jump; pr returns
    to the emulator's 0xEEEE0000 sentinel), call the ROM entry @0x3BF4 with
    r4 = TCB, r5 = the ABI scratch word to push, r6 = descriptor, then read
    back the final saved SP from tcb+0x0C, the status byte and the whole
    68-byte context block (17 u32 words);
  - host side: the dedicated oracle mmap()s the same pages, seeds the same
    bytes, runs the reconstructed C and prints the same 19 cells.

EDGE vectors cover type 0/1/2/3/4/5/0x7F/0x80/0xFF (0x04 toggles the FPU
block, shifting the saved SP by 16 bytes), r5 with 0 / max / sign flips and
status pre-states with 0 / max / bit-15 patterns; N random pre-states follow
(fixed seed, 50% type 0x04 so the FPU path is exercised equally).

Usage:  python3 harness_task_full_context_save.py [N]   (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROM_PATH, make_rng, report, run_oracle  # noqa: E402
from sh2emu import SH2, MASK  # noqa: E402

ADDR = 0x3BF4
N_DEFAULT = 20000
SEED = 0x60E1D400               # the ROM file id doubles as the RNG seed

TCB_ADDR = 0xFFFFA000           # task control block (r4): saved_sp @ +0x0C
DESC_ADDR = 0xFFFFA100          # task descriptor (r6): type @ +0, ptr @ +0x04
STATUS_CELL = 0xFFFF8060        # byte the ROM writes 0x04 into (via desc+4)
STACK_TOP = 0xFFFFDF00          # kernel stack top (the emulator's default r15)
DISP_STUB_ADDR = 0x3C68         # scheduler-dispatch tail-jump (rts; nop stub)
CTX_WORDS = 17                  # 68-byte context window read from saved SP


def put16(ram, addr, word):
    ram[addr & MASK] = (word >> 8) & 0xFF
    ram[(addr + 1) & MASK] = word & 0xFF


def put32(ram, addr, val):
    ram[addr & MASK] = (val >> 24) & 0xFF
    ram[(addr + 1) & MASK] = (val >> 16) & 0xFF
    ram[(addr + 2) & MASK] = (val >> 8) & 0xFF
    ram[(addr + 3) & MASK] = val & 0xFF


def build_ram(type_, r5, status_pre):
    ram = {}
    put16(ram, DISP_STUB_ADDR, 0x000B)      # rts
    put16(ram, DISP_STUB_ADDR + 2, 0x0009)  # nop (delay slot)
    ram[DESC_ADDR + 0] = type_ & 0xFF       # descriptor type byte
    put32(ram, DESC_ADDR + 4, STATUS_CELL)  # descriptor status pointer
    ram[STATUS_CELL] = status_pre & 0xFF    # status cell pre-state
    return ram


def run_context_save(cpu, type_, r5, status_pre):
    """Execute the ROM @0x3BF4 with the given pre-state; return the 19
    post-state cells: (saved_sp, status, ctx[0..16])."""
    ram = build_ram(type_, r5, status_pre)
    cpu.call(ADDR, r4=TCB_ADDR, r5=r5 & MASK, r6=DESC_ADDR, ram=ram)
    sp = cpu.rd(TCB_ADDR + 0x0C, 4)
    status = cpu.rd(STATUS_CELL, 1)
    ctx = tuple(cpu.rd(sp + 4 * i, 4) for i in range(CTX_WORDS))
    return (sp, status) + ctx


# Edge vectors: (type, r5, status_pre).  type 0x04 exercises the FPU block.
EDGE = [
    (0x00, 0x00000000, 0x00),
    (0x00, 0x00000000, 0xFF),
    (0x00, 0x00000000, 0x80),
    (0x00, 0xFFFFFFFF, 0x00),
    (0x00, 0xDEADBEEF, 0x5A),
    (0x00, 0x80000000, 0xFF),
    (0x00, 0x7FFFFFFF, 0x01),
    (0x00, 0x12345678, 0x00),
    (0x04, 0x00000000, 0x00),
    (0x04, 0xFFFFFFFF, 0xFF),
    (0x04, 0xCAFEBABE, 0x80),
    (0x04, 0x80000000, 0x00),
    (0x04, 0x00000001, 0x7F),
    (0x04, 0x7FFFFFFF, 0xFF),
    (0x04, 0x11111111, 0x00),
    (0x01, 0x00000000, 0x00),
    (0x02, 0xFFFFFFFF, 0x00),
    (0x03, 0xDEADBEEF, 0xFF),
    (0x05, 0x00000000, 0xFF),
    (0x7F, 0xFFFFFFFF, 0x00),
    (0x80, 0x00000000, 0x80),
    (0xFF, 0xFFFFFFFF, 0xFF),
]


def gen_random(rng, n):
    """n random pre-states: type 0x04 with 50% probability (FPU block), else a
    random non-0x04 byte; random r5; random status pre-state."""
    out = []
    for _ in range(n):
        if rng.random() < 0.5:
            type_ = 0x04
        else:
            type_ = rng.randrange(256)
            if type_ == 0x04:
                type_ = 0x00
        out.append((type_, rng.getrandbits(32), rng.randrange(256)))
    return out


def vec_line(v):
    type_, r5, status_pre = v
    return 'save %02X %08X %02X' % (type_, r5, status_pre)


SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = os.path.join('/tmp', 'rx8-recon-task_full_context_save')


def build_oracle(cc='cc'):
    """Compile the reconstructed source + its dedicated oracle into a binary."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_task_full_context_save.c'),
           os.path.join(SAMPLES, 'src', 'rx8_task_full_context_save.c'),
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

    # (a) ROM behaviour via the emulator (RAM side-effects).
    emu = [run_context_save(cpu, *v) for v in vectors]

    # (b) host C on the same pre-states.
    host = [tuple(int(x, 16) for x in out.split())
            for out in run_oracle(oracle, [vec_line(v) for v in vectors])]

    # (c) compare the 19 post-state cells bit-exactly.
    mismatches = []
    for k, (v, e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            type_, r5, status_pre = v
            mismatches.append(
                'vec#%d type=0x%02X r5=0x%08X status_pre=0x%02X  ROM=(%s) C=(%s)'
                % (k, type_, r5, status_pre,
                   ' '.join('%08X' % w for w in e),
                   ' '.join('%08X' % w for w in h)))
            if len(mismatches) >= 5:
                break

    report('taskFullContextSave', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()