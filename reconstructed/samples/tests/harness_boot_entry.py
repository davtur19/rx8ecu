#!/usr/bin/env python3
"""
harness_boot_entry.py — equivalence of the RX-8 boot/reset entry chain.

Reconstructed source : samples/src/rx8_boot_entry.c
Verified ladder (truth): c/boot_entry.c  (main_entry @0xD49C,
                       secondary_boot_main @0xA038, task_context_switch @0x3AD8).

Verifies the three boot-chain functions against the REAL ROM bytes via
tools/sh2emu.py.  main_entry / secondary_boot_main are M1-tier "paint the
hardware then never return" boot routines: their deep peripheral leaves
(0x4C80 / 0xD7B0 / 0x2064 / 0x4CF8) are stubbed on BOTH sides with tiny
behaviour-identical RAM-overlay call-trace stubs (the convention of
harness_os_task_scheduler.py's dispatcher stub).  The terminal callee
(task_context_switch @0x3AD8) jumps to the emulator SENT constant so the boot
chain terminates cleanly instead of reaching its own `bra $` infinite loop.
Each stub writes one call-trace cell at 0xFFFFE000 + slot*16: [tag a0 a1 a2].

Modes
-----
 0x3AD8 : task_context_switch — the data-dependent member.  EDGE + N random
          (seed 0x60E1D400).  Compares (ret, sr, sp, [0xFFFFF2D8], [0xFFFFF72B8]).
 0xA038 : secondary_boot_main — fixed chain.  Compares the 32 trace dwords.
 0xD49C : main_entry — fixed register image + chain.  Compares (vbr, fpscr, sp)
          + 32 trace dwords.

Usage: python3 harness_boot_entry.py [N]    (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROM_PATH, make_rng, report, run_oracle  # noqa: E402
from sh2emu import SH2, MASK  # noqa: E402

SENT = 0xEEEE0000
N_DEFAULT = 20000
SEED = 0x60E1D400

TRACE_BASE = 0xFFFFE000
SAVED_SP = 0xFFFF72D8
CTL8 = 0xFFFF72B8

CELL = {0x4C80: 0xFFFFE000, 0xD7B0: 0xFFFFE010, 0xA0DC: 0xFFFFE020,
        0x2054: 0xFFFFE030, 0x4BBC: 0xFFFFE040, 0x2064: 0xFFFFE050,
        0x4CF8: 0xFFFFE060, 0x3AD8: 0xFFFFE070}

# callee -> tuple of meaningful ABI args subset of {r4,r5,r6}
CAP = {0x4C80: (), 0xD7B0: (), 0xA0DC: ('r4',), 0x2054: ('r5',),
       0x4BBC: ('r4', 'r5', 'r6'), 0x2064: (), 0x4CF8: (), 0x3AD8: ('r4',)}


def put16(ram, addr, w):
    ram[addr & MASK] = (w >> 8) & 0xFF
    ram[(addr + 1) & MASK] = w & 0xFF


def put32(ram, addr, v):
    for i in range(4):
        ram[(addr + i) & MASK] = (v >> (24 - 8 * i)) & 0xFF


def get32(ram, addr):
    return sum(ram.get((addr + i) & MASK, 0) << (24 - 8 * i) for i in range(4))


# ---------------------------------------------------------------------------
#  Stub assembler — opcode forms validated against sh2emu.py's decoder:
#    0xD000|(reg<<8)|disp : mov.l r,@(disp,pc)      (disp in 4-byte units)
#    0xE00r               : mov #0,r
#    0x2000|n<<8|m<<4|2   : mov.l rm,@rn
#    0x1000|n<<8|m<<4|d   : mov.l rm,@(d*4,rn)
#    0x000B / 0x0009      : rts / nop
#    0x402B / 0x0009      : jmp @r0 (delay) / nop
# ---------------------------------------------------------------------------
def _stub(r, body, callee, cell, capture, terminal, sentinel, pool=None):
    """Assemble a call-trace stub.  `body` is where the stub code goes (with
    its literal pool at `pool` or body+0x20), `callee` is the logical tag.
    All SE-2 opcode forms below are validated against sh2emu.py's decoder:
      0xD0|(reg<<8)|disp : mov.l reg,@(disp,pc)     (disp in 4-byte units)
      0xE0rr              : mov #0,rr
      0x2000|n<<8|m<<4|2  : mov.l Rm,@Rn
      0x1000|n<<8|m<<4|d  : mov.l Rm,@(d*4,Rn)
      0x000B/0x0009       : rts / nop
      0x402B/0x0009       : jmp @r0 (delay) / nop
      0xB000|disp         : bra disp (used as the 0xA0DC trampoline)
    """
    body &= MASK
    if pool is None:
        pool = (body + 0x20) & MASK
    words = [0xD000, 0xD700]          # r0=tag, r7=cell (PC-rel, patched)
    for rn in (4, 5, 6):              # zero r4/r5/r6 except captured ABI args
        if ('r%d' % rn) not in capture:
            words.append(0xE000 | (rn << 8))   # mov #0,rn  (0xEn00)
    words.append(0x2000 | (7 << 8) | (0 << 4) | 2)   # mov.l r0,@r7 (tag)
    if 'r4' in capture:
        words.append(0x1000 | (7 << 8) | (4 << 4) | 1)
    if 'r5' in capture:
        words.append(0x1000 | (7 << 8) | (5 << 4) | 2)
    if 'r6' in capture:
        words.append(0x1000 | (7 << 8) | (6 << 4) | 3)
    if terminal:
        words += [0xD000, 0x402B, 0x0009]    # r0=SENT ; jmp @r0
    else:
        words += [0x000B, 0x0009]            # rts
    put32(r, pool + 0, callee)
    put32(r, pool + 4, cell)
    if terminal:
        put32(r, pool + 8, sentinel)
    ld = 0
    for k, op in enumerate(words):
        if (op >> 12) == 0xD:           # mov.l @(disp)) any destination reg
            ea = ((body + 2 * k + 4) & ~3)
            tgt = [pool, pool + 4, pool + 8][ld]
            disp = (tgt - ea) // 4
            reg = (op >> 8) & 0x0F
            words[k] = 0xD000 | (reg << 8) | (disp & 0xFF)
            ld += 1
    for k, op in enumerate(words):
        put16(r, body + 2 * k, op)


def _build_boot(ram, sentinel):
    """Install the call-trace stub layer.  All callees are tiny self-contained
    bodies at their own ROM addresses (surrounding real code is unexecuted in
    the boot path) EXCEPT 0xA0DC: that is a `bsr` target inside the middle of
    secondary_boot_4's own literal pool, so its body lives in free space
    @0xA0B0 and 0xA0DC holds a `bra` trampoline to it."""
    for callee, capture in CAP.items():
        terminal = (callee == 0x3AD8)
        if callee == 0xA0DC:
            _stub(ram, 0xA0B0, callee, CELL[callee], capture, terminal, sentinel)
            # trampoline at 0xA0DC:  bra 0xA0B0 ; nop   (0xAxxx = bra, NOT bsr)
            disp = (0xA0B0 - (0xA0DC + 4)) // 2       # disp*2 12-bit
            d12 = disp & 0xFFF
            put16(ram, 0xA0DC, 0xA000 | d12)
            put16(ram, 0xA0DE, 0x0009)
        else:
            _stub(ram, callee, callee, CELL[callee], capture, terminal, sentinel)


def trace_run(cpu):
    out = []
    for i in range(8):
        b = TRACE_BASE + i * 16
        for k in range(4):
            out.append(get32(cpu.ram, b + 4 * k))
    return out


def run_boot(cpu, addr):
    ram = {}
    _build_boot(ram, SENT)
    put32(ram, SAVED_SP, 0)
    put32(ram, CTL8, 0)
    cpu.call(addr, ram=ram)
    if addr == 0xD49C:
        return [cpu.vbr, cpu.fpscr, cpu.r[15]] + trace_run(cpu)
    return trace_run(cpu)


def run_switch(cpu, tid, cnt, ks, ksp):
    ram = {}
    put32(ram, 0x4B00, cnt << 24)          # byte count (top byte of the long)
    put32(ram, 0x4B04, ks)
    put32(ram, 0x4938, ksp)
    # init_main tail stub @0x3E10 -> r0 = 0x0A0A ; rts
    put32(ram, 0x3E20, 0x00000A0A)
    disp = (0x3E20 - 0x3E14) // 4
    put16(ram, 0x3E10, 0xD000 | (0 << 8) | (disp & 0xFF))
    put16(ram, 0x3E10 + 2, 0x000B)
    put16(ram, 0x3E10 + 4, 0x0009)
    put32(ram, SAVED_SP, 0)
    put32(ram, CTL8, 0)
    ret = cpu.call(0x3AD8, r4=tid, ram=ram)
    return (ret, cpu.sr, cpu.r[15], get32(cpu.ram, SAVED_SP), get32(cpu.ram, CTL8))


BUILD_DIR = os.path.join('/tmp', 'rx8-recon-boot_entry')


def build_oracle(cc='cc'):
    samples = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(samples, 'include'),
           '-I', os.path.join(samples, 'src'),
           os.path.join(samples, 'tests', 'oracle_boot_entry.c'),
           os.path.join(samples, 'src', 'rx8_boot_entry.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    with open(ROM_PATH, 'rb') as f:
        cpu = SH2(f.read())
    oracle = build_oracle()

    # ---- 1. task_context_switch @0x3AD8 -----------------------------------
    EDGE = [
        (0x00, 0x01, 0x000000B0, 0xFFFF719C), (0x01, 0x01, 0xB0, 0xFFFF719C),
        (0x02, 0x01, 0xB0, 0xFFFF719C), (0xFF, 0x01, 0xB0, 0xFFFF719C),
        (0x01, 0x00, 0xB0, 0xFFFF719C), (0x00, 0xFF, 0xB0, 0xFFFF719C),
        (0x80, 0x01, 0xDEAD, 0x00001000), (0x04, 0x05, 0x0002, 0x40000000),
        (0x05, 0x05, 0x0001, 0x00008000), (0x00, 0x01, 0x0000, 0x00000000),
    ]
    rng = make_rng(SEED)
    vsw = list(EDGE)
    for _ in range(n):
        vsw.append((rng.randrange(0x100), rng.randrange(0x100),
                    rng.getrandbits(32), rng.getrandbits(32)))
    emu = [run_switch(cpu, tid, cnt, ks, ksp) for (tid, cnt, ks, ksp) in vsw]
    lines = ['sw %02X %02X %08X %08X' % (v[0], v[1], v[2], v[3]) for v in vsw]
    host = [tuple(int(x, 16) for x in o.split())
            for o in run_oracle(oracle, lines)]
    mm = []
    for k, (v, e, h) in enumerate(zip(vsw, emu, host)):
        if e != h:
            mm.append('vec#%d tid=0x%02X cnt=0x%02X ROM=%s C=%s'
                      % (k, v[0], v[1], ' '.join('%08X' % x for x in e),
                         ' '.join('%08X' % x for x in h)))
            if len(mm) >= 5:
                break
    report('task_context_switch', 0x3AD8, n, mm, edges=len(EDGE))

    # ---- 2. secondary_boot_main @0xA038 -----------------------------------
    sec_emu = run_boot(cpu, 0xA038)
    sec_host = [int(x, 16) for x in run_oracle(oracle, ['sec'])[0].split()]
    mm2 = []
    for i in range(32):
        if sec_emu[i] != sec_host[i]:
            mm2.append('sec dword#%d ROM=0x%08X C=0x%08X' % (i, sec_emu[i], sec_host[i]))
    report('secondary_boot_main', 0xA038, 1, mm2, edges=1)

    # ---- 3. main_entry @0xD49C --------------------------------------------
    mn_emu = run_boot(cpu, 0xD49C)
    mn_host = [int(x, 16) for x in run_oracle(oracle, ['main'])[0].split()]
    m = []
    for i in range(3 + 32):
        if mn_emu[i] != mn_host[i]:
            m.append('main idx%d ROM=0x%08X C=0x%08X' % (i, mn_emu[i], mn_host[i]))
    report('main_entry', 0xD49C, 1, m, edges=1)


if __name__ == '__main__':
    main()