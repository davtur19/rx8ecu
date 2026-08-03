#!/usr/bin/env python3
"""test_task_context_switch_3AD8.py

Differential test for ROM 0x3AD8 (60E1D400.bin) — task_context_switch
(lift: c/boot_entry.c).  This is the RTOS bootstrap entry: it validates the
task id, saves the caller context onto the RAM stack, installs the kernel
SR/SP, flags the RTOS control block, and tail-jumps to init_main (0x3E10).

Method (repo Track-A pattern, see test_task_full_context_save_3BF4.py): the
ACTUAL ROM bytes run in tools/sh2emu.py (the oracle) against a bit-exact
Python model built from the disassembly.  The tail target init_main @0x3E10
is stubbed with rts;nop so the path terminates with PR still = SENT.

Disassembly (60E1D400):
  0x3AD8  mov.l @(0x3B10),r0        ; r0 = 0x4B00 (task_count ptr)
  0x3ADA  mov.b @r0,r0              ; task_count = (u8)[0x4B00]  (zero-ext)
  0x3ADC  exts.b r4,r4              ; r4 = sign-extended task_id
  0x3ADE  cmp/hs r0,r4              ; T = (r4 >= task_count)  (UNSIGNED)
  0x3AE0  bf  0x3AE6                ; valid iff task_id < task_count
  0x3AE2  rts                       ; invalid: return 0
  0x3AE4  mov #0,r0
  0x3AE6  stc.l SR,@-r15            ; [SP-4]  = initial SR
  0x3AE8  sts.l pr,@-r15            ; [SP-8]  = PR (SENT)
  0x3AEA  mov.l @(0x3B20),r0        ; r0 = 0xFFFF72D8
  0x3AEC  mov.l r15,@r0             ; [0xFFFF72D8] = SP-8 (saved SP)
  0x3AEE  mov.l @(0x3B1C),r0        ; r0 = 0x4B04
  0x3AF0  mov.l @r0,r0              ; r0 = [0x4B04] (kernel SR)
  0x3AF2  ldc r0,SR                 ; SR = kernel SR
  0x3AF4  mov.l @(0x3B18),r0        ; r0 = 0x4938
  0x3AF6  mov.l @r0,r15             ; SP = [0x4938] (kernel stack)
  0x3AF8  mov.l @(0x3B24),r2        ; r2 = 0xFFFF72B0 (RTOS ctl block)
  0x3AFA  mov.l @(0x3B04),r0        ; r0 = 0x100
  0x3AFC  mov.l r0,@(8,r2)          ; [0xFFFF72B8] = 0x100
  0x3AFE  mov.l @(0x3B14),r0        ; r0 = 0x3E10 (init_main)
  0x3B00  jmp @r0                   ; tail call (PR untouched)
  0x3B02  nop

Compared bit-exactly (valid path): the two stack words (SR @0xFFFFDEFC,
PR=SENT @0xFFFFDEF8), the saved-SP slot [0xFFFF72D8] = 0xFFFFDEF8, the
kernel SR install ([0x4B04]), the kernel SP install ([0x4938]) in r15,
the ctl magic [0xFFFF72B8] = 0x100, r0 = 0x3E10 on return, PR = SENT.
Invalid path (task_id >= task_count): r0 = 0, no RAM writes, r15 untouched.

Lift notes (c/boot_entry.c, logical/assembly-first lift): the C model omits
the two stack pushes (it models a host `_pr`/`_sp` register image) and
compares `(int8_t)task_id >= (int8_t)TASK_COUNT_PTR` (signed), whereas the
ROM sign-extends r4 then compares UNSIGNED against the zero-extended count
byte — the two disagree only when count >= 0x80 (never in practice: 0x4B00
== 1).  This test pins the ROM behavior; the stack writes are the exact
frame the OS context-save expects.

Run: python3 c/tests/test_task_context_switch_3AD8.py [N]
     (N = random inputs per seed; default 800 -> 4000 across 5 seeds)
"""
import os, random, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2  # noqa: E402

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ADDR = 0x3AD8
MASK = 0xFFFFFFFF
SP_IN = 0xFFFFDF00
SENT = 0xEEEE0000
TAIL = 0x3E10          # init_main tail target (stubbed rts;nop)
TASK_COUNT_PTR = 0x4B00
KERNEL_SR_PTR = 0x4B04
KERNEL_SP_PTR = 0x4938
CTL_BLOCK = 0xFFFF72B0
SAVED_SP_SLOT = 0xFFFF72D8
PUSHED_SR = 0xFFFFDEFC     # SP-4  (first push: SR)
PUSHED_PR = 0xFFFFDEF8     # SP-8  (second push: PR)


def rb(m, a):
    return m.get(a & MASK, 0)


def rd(m, a, n):
    v = 0
    for i in range(n):
        v = (v << 8) | rb(m, a + i)
    return v


def wr(m, a, n, v):
    for i in range(n):
        m[(a + i) & MASK] = (v >> (8 * (n - 1 - i))) & 0xFF


def gen_state(rng):
    """Random task_id, task-count byte, kernel SR/SP, pre-seeded stack and
    control-block windows, random initial SR register."""
    ram = {}
    # task-count byte and kernel SR/SP cells
    ram[TASK_COUNT_PTR] = rng.getrandbits(8)
    wr(ram, KERNEL_SR_PTR, 4, rng.getrandbits(32))
    wr(ram, KERNEL_SP_PTR, 4, rng.getrandbits(32))
    # control block + saved-SP slot pre-seeded with junk
    for a in range(CTL_BLOCK, CTL_BLOCK + 0x20):
        ram[a] = rng.getrandbits(8)
    for a in range(SAVED_SP_SLOT, SAVED_SP_SLOT + 4):
        ram[a] = rng.getrandbits(8)
    # whole stack window pre-seeded so un-written slots match exactly
    for a in range(0xFFFFDE80, 0xFFFFDF00):
        ram[a] = rng.getrandbits(8)
    # init_main tail stub: rts ; nop
    ram[TAIL] = 0x00; ram[TAIL + 1] = 0x0B
    ram[TAIL + 2] = 0x00; ram[TAIL + 3] = 0x09
    task_id = rng.getrandbits(32)
    sr = rng.getrandbits(32)
    return ram, task_id, sr


def s8b(v):
    v &= 0xFF
    return (v - 0x100) & MASK if v & 0x80 else v


def ref(ram, task_id, sr):
    """Python model of 0x3AD8.  Returns (r0, r15, sr_out, post-RAM, pr_out).

    NOTE: mirrors the emulator (tools/sh2emu.py) which sign-extends the
    mov.b @r0,r0 byte load (opcode 0x6000); the real SH-2 zero-extends the
    load and would only sign-extend via the exts.b on r4.  The emulator's
    quirk makes count>=0x80 compare as a huge unsigned value; the repo's
    established oracle (sh2emu) is matched here.  [0x4B00] == 1 in the real
    ROM, so the quirk never fires in production.
    """
    m = dict(ram)
    count = s8b(rb(m, TASK_COUNT_PTR))      # emulator: sign-extended load
    sid = s8b(task_id)                      # exts.b r4,r4
    if sid >= count:                        # cmp/hs : T=(r4>=count), bf skip
        return 0, SP_IN, sr, m, SENT        # invalid: return 0, nothing else
    # valid path
    sp = (SP_IN - 4) & MASK
    wr(m, sp, 4, sr)                        # stc.l SR,@-r15  -> 0xFFFFDEFC
    sp = (sp - 4) & MASK
    wr(m, sp, 4, SENT)                      # sts.l pr,@-r15  -> 0xFFFFDEF8
    wr(m, SAVED_SP_SLOT, 4, sp)             # [0xFFFF72D8] = 0xFFFFDEF8
    kern_sr = rd(m, KERNEL_SR_PTR, 4)
    kern_sp = rd(m, KERNEL_SP_PTR, 4)
    wr(m, CTL_BLOCK + 8, 4, 0x100)          # ctl magic
    return TAIL, kern_sp, kern_sr, m, SENT  # r0 = 0x3E10, jmp tail


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 800
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    seeds = (0x3AD8, 0x3B00, 0x8000, 0xF000, 0x1234)
    total_fails = 0

    for seed in seeds:
        rng = random.Random(seed)
        fails = 0
        for it in range(N):
            ram, task_id, sr = gen_state(rng)
            want_r0, want_r15, want_sr, want, want_pr = ref(ram, task_id, sr)
            try:
                got_r0 = cpu.call(ADDR, r4=task_id, ram=ram, sr=sr)
            except Exception as e:
                print('EMULATOR EXC seed=0x%X iter=%d: %s' % (seed, it, e))
                fails += 1
                break
            got = cpu.ram
            bad = []
            if got_r0 != want_r0:
                bad.append(('r0', got_r0, want_r0))
            if cpu.r[15] != want_r15:
                bad.append(('r15', cpu.r[15], want_r15))
            if cpu.sr != want_sr:
                bad.append(('sr', cpu.sr, want_sr))
            if cpu.pr != want_pr:
                bad.append(('pr', cpu.pr, want_pr))
            for k in set(got) | set(want):
                if got.get(k, 0) != want.get(k, 0):
                    bad.append((k, got.get(k, 0), want.get(k, 0)))
            if bad:
                print('MISMATCH seed=0x%X iter=%d task_id=0x%08X count=0x%02X' %
                      (seed, it, task_id, ram[TASK_COUNT_PTR]))
                shown = []
                for k, g, e in bad[:20]:
                    if isinstance(k, int):
                        shown.append((hex(k), hex(g), hex(e)))
                    else:
                        shown.append((k, hex(g), hex(e)))
                print('  %s' % shown)
                fails += 1
                if fails >= 3:
                    break
        print('  seed 0x%X: %d inputs, fails=%d' % (seed, N, fails))
        total_fails += fails
        if total_fails:
            break

    if total_fails:
        print('\n%d FAILURE(S)' % total_fails)
        sys.exit(1)
    print('OK  0x3AD8 task_context_switch  (RAM-stack save + kernel SR/SP '
          'install bit-exact, %d inputs across %d seeds)'
          % (N * len(seeds), len(seeds)))
    sys.exit(0)


if __name__ == '__main__':
    main()
