#!/usr/bin/env python3
"""
harness_set_memory_not_valid2.py — equivalence of the leaf entered at
0x3E5A8 in roms/stock/60E1D400.bin (reconstructed as
rx8_set_memory_not_valid2).

Reconstructed source: samples/src/rx8_set_memory_not_valid2.c
Lift (truth)      : c/SetMemoryNotValid2.c — WITH A DOCUMENTED DISCREPANCY.

The lift describes the *60E0FC00* image, where 0x3E5A8 is a "write 1 to
flag[0xFFFFC639]" leaf (the lift's 0xFFFFC63A is off-by-one).  In the stock
60E1D400.bin image mandated for this harness the bytes at 0x3E5A8 are entirely
different: the address sits mid-function of the IDA-named `status_checker_3E58A`
and executing there runs a plain BYTE COPY:

    0x3E5A8  mov.b @r2,r3     ; r3 = *src (r2 = source byte ptr)
    0x3E5AA  bra   0x3E5CA    ; unconditional -> epilogue
    0x3E5AC  mov.b r3,@r5     ; (delay slot) *dst = r3 (r5 = dest byte ptr)
    0x3E5CA  rts

so the observable is the single RAM write RAM[r5] := RAM[r2] (the
0x3E5AE..0x3E5C8 tail is unreachable because of the `bra`).  See the .c header
for the full discussion.

CALLING CONVENTION: this ROM routine is NOT ABI-clean.  It takes its two byte
pointers in r2 (src) and r5 (dst) and returns nothing; the observable effect is
the RAM write.  The standard SH2.call(r4=, r5=) entry point therefore cannot be
used; a small call_copy() driver below sets r2/r5 directly (same trick as
harness_div32_signed.py / harness_interpolate_u8_table.py).

Procedure (Track-A pattern):
  1. build host oracle (system gcc; -O2, -Wall, -Wextra),
  2. edge vectors (byte boundaries 0/0x7F/0x80/0xFF + sign flips, cross-page
     pairs, self-copy, differing destination seeds) + N random vectors,
  3. run the ROM bytes @0x3E5A8 in tools/sh2emu.py on the same vectors,
  4. run the host C on the same vectors,
  5. compare the side-effected destination byte (and that src is untouched) —
     0 mismatches required.

Usage:  python3 harness_set_memory_not_valid2.py [N]   (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402

ADDR = 0x3E5A8
N_DEFAULT = 20000

# This harness' own build dir (task-mandated path).
SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = '/tmp/rx8-recon-set_memory_not_valid2'

# (src_addr, dst_addr) pairs: same-page, cross-page and self-copy.  All live in
# the on-chip-RAM pages the host oracle mmaps (0xFFFFA000 / 0xFFFFB000).
PAIRS = [
    (0xFFFFA400, 0xFFFFA402),   # same page
    (0xFFFFA401, 0xFFFFB5AB),   # cross page
    (0xFFFFA404, 0xFFFFA404),   # self-copy
]

# Edge vectors: (src_addr, dst_addr, src_byte, dst_seed).  Byte boundaries 0 /
# max / sign-flip (0x80) with every pair, plus pinned self-copy and seed cases.
EDGE = []
for sa, da in PAIRS:
    for sb in (0x00, 0x01, 0x02, 0x7F, 0x80, 0x81, 0xFE, 0xFF):
        for ds in (0x00, 0x5A, 0xFF):
            EDGE.append((sa, da, sb, ds))
EDGE += [
    (0xFFFFA400, 0xFFFFA402, 0x80, 0x7F),   # sign-flip byte over differing seed
    (0xFFFFA400, 0xFFFFA402, 0xFF, 0x00),   # max byte over zero seed
    (0xFFFFA400, 0xFFFFA402, 0x00, 0xFF),   # zero byte over max seed
    (0xFFFFA400, 0xFFFFA400, 0x80, 0x7F),   # self-copy, sign-flip byte
    (0xFFFFA400, 0xFFFFA400, 0x00, 0xFF),
    (0xFFFFA400, 0xFFFFA400, 0xFF, 0x00),
    (0xFFFFA404, 0xFFFFA404, 0x80, 0x80),
]


def gen_random(rng, k):
    """k random vectors: a random pair, a random source byte and a random
    destination seed (kept so every copy provably overwrites its target)."""
    v = []
    for _ in range(k):
        sa, da = rng.choice(PAIRS)
        v.append((sa, da, rng.randrange(256), rng.randrange(256)))
    return v


def call_copy(cpu, entry, r2, r5, ram):
    """Drive a ROM routine that takes src in r2 and dst in r5 (non-ABI leaf);
    line-for-line copy of SH2.call()'s body as in harness_div32_signed.py."""
    cpu.ram = dict(ram)
    cpu.r = [0] * 16
    cpu.r[2] = r2 & 0xFFFFFFFF
    cpu.r[5] = r5 & 0xFFFFFFFF
    cpu.r[15] = 0xFFFFDF00
    cpu.fr = [0.0] * 16
    cpu.pr = cpu.SENT
    cpu.T = 0
    cpu._Q = 0
    cpu._M = 0
    cpu.macl = 0
    cpu.mach = 0
    cpu.gbr = 0
    cpu.fpul = 0
    cpu.fpscr = 0
    cpu.sr = 0x000000F0
    cpu.pc = entry & 0xFFFFFFFF
    steps = 0
    while True:
        if cpu.pc == cpu.SENT:
            return
        steps += 1
        if steps > 500000:
            raise RuntimeError('runaway at 0x%X' % cpu.pc)
        op = cpu.rd(cpu.pc, 2)
        br = cpu._delayed(op)
        if br is None:
            cpu._exec(op, cpu.pc)
            cpu.pc = (cpu.pc + 2) & 0xFFFFFFFF
        else:
            target, take = br
            cpu._exec(cpu.rd(cpu.pc + 2, 2), cpu.pc + 2)
            cpu.pc = target if take else (cpu.pc + 4) & 0xFFFFFFFF


def build_oracle(cc='cc'):
    """Compile this harness' own oracle (oracle_set_memory_not_valid2.c + the
    reconstructed source) into the task-mandated build dir."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_set_memory_not_valid2.c'),
           os.path.join(SAMPLES, 'src', 'rx8_set_memory_not_valid2.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(0x60E1D400)

    vectors = list(EDGE) + gen_random(rng, n)

    # (a) ROM behaviour via the emulator (r2 = src, r5 = dst): the RAM overlay
    # carries src byte + dst seed; the observable is RAM[dst] after the call.
    emu = []
    for sa, da, sb, ds in vectors:
        ram = {sa: sb}
        if da != sa:
            ram[da] = ds
        call_copy(cpu, ADDR, sa, da, ram)
        emu.append(cpu.ram[da])

    # (b) host C on the same inputs.
    lines = ['cp %08X %08X %02X %02X' % (sa, da, sb, ds)
             for sa, da, sb, ds in vectors]
    host = [int(x, 16) for x in run_oracle(oracle, lines)]

    # (c) compare the destination byte.
    mismatches = []
    for k, ((sa, da, sb, ds), e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d src=0x%02X dst_seed=0x%02X @0x%08X ROM=0x%02X C=0x%02X'
                % (k, sb, ds, da, e, h))
            if len(mismatches) >= 5:
                break

    report('set_memory_not_valid2', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
