#!/usr/bin/env python3
"""test_task_full_context_save_3BF4.py

Differential test for ROM 0x3BF4 (60E1D400.bin) — the RTOS full context-save.

This is the "context-switch write path" whose C lift (c/task_full_context_save.c)
is assembly-first / logical.  Instead of host-compiling the C, we compare the
ACTUAL ROM bytes run in tools/sh2emu.py (the oracle) against a bit-exact Python
model built from the disassembly, so we verify the exact WRITE ORDER and target
addresses of the save.  Callers (0x3490 / task_execute_by_index 0x3854 /
os_context_switch 0x3DB0) hand r4=tcb, r6=task-desc.

Stub: the schedule tail @0x3C68 (real: enters kernel at 0x375C/0x3848) is
patched to rts;nop (same as test_task_full_context_save.py / 0x3DB0 test) so the
save path terminates cleanly with pr still = SENT.

Save-path semantics (0x3BF4..0x3C28, 60E1D400), prologue pushes to @-r15:
  order, then address (start SP = 0xFFFFDF00):
   1 R5    -> 0xFFFFDEFC   (mov.l r5,@-r15)
   2 PR    -> 0xFFFFDEF8   (sts.l pr,@-r15)
   3 (pad) 0xFFFFDEF4      (add #-4,r15 -- NOT written: r15 moves only)
   4 R8    -> 0xFFFFDEF0
   5 R9    -> 0xFFFFDEEC
   6 R10   -> 0xFFFFDEE8
   7 R11   -> 0xFFFFDEE4
   8 R12   -> 0xFFFFDEE0
   9 GBR   -> 0xFFFFDEDC   (stc.l gbr,@-r15)
  10 R13   -> 0xFFFFDED8
  11 MACH  -> 0xFFFFDED4   (sts.l mach,@-r15)
  12 R14   -> 0xFFFFDED0
  13 MACL  -> 0xFFFFDECC   (sts.l macl,@-r15)  [non-FPU saved_sp = 0xFFFFDECC]
  if task->type == 4 (mov.b @(0,r6) signed == 4):
  14 FR12  -> 0xFFFFDEC8   (fmov.s fr12,@-r15)
  15 FR13  -> 0xFFFFDEC4
  16 FR14  -> 0xFFFFDEC0
  17 FR15  -> 0xFFFFDEBC   [FPU saved_sp = 0xFFFFDEBC]
  then: *status_ptr( = u32@(desc+4)) = 4 ;  tcb[0x0C] = saved_sp ; bra 0x3C68
The two non-stack RAM writes are therefore: status byte = 4, and tcb+0x0C =
final saved SP. pr value on the stack is the call's SENT (entry PR).

Run: python3 c/tests/test_task_full_context_save_3BF4.py [N]
     (N = random inputs per seed; default 500 -> 2500 across 5 seeds)
"""
import os, random, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2, ts

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ADDR = 0x3BF4
MASK = 0xFFFFFFFF
SP_IN = 0xFFFFDF00
SENT = 0xEEEE0000


def rb(m, a):
    a &= MASK
    v = m.get(a)
    return v if v is not None else 0


def rd(m, a, n):
    v = 0
    for i in range(n):
        v = (v << 8) | rb(m, a + i)
    return v


def wr(m, a, n, v):
    for i in range(n):
        m[(a + i) & MASK] = (v >> (8 * (n - 1 - i))) & 0xFF


def ref(ram, tcb, desc, vals, fpu):
    """Mirror of task_full_context_save: reproduce the exact stack writes in
    order, the status write, and the TCB saved-SP write."""
    m = dict(ram)
    sp = SP_IN

    def push32(v):
        nonlocal sp
        sp = (sp - 4) & MASK
        wr(m, sp, 4, v)
    # order must match the disassembly
    push32(vals['r5'] & MASK)
    push32(SENT)                       # sts.l pr (pr == SENT)
    sp = (sp - 4) & MASK                     # add #-4,r15 : no memory write
    for reg in ('r8', 'r9', 'r10', 'r11', 'r12'):
        push32(vals[reg] & MASK)
    push32(vals['gbr'] & MASK)
    push32(vals['r13'] & MASK)
    push32(vals['mach'] & MASK)
    push32(vals['r14'] & MASK)
    push32(vals['macl'] & MASK)
    if fpu:
        # pass float32 bits -> store IEEE-754 single bytes
        for fr in (12, 13, 14, 15):
            sp = (sp - 4) & MASK
            for i, b in enumerate(struct.pack('>f', ts(fpu[fr]))):
                m[(sp + i) & MASK] = b

    status_ptr = rd(m, desc + 4, 4)
    wr(m, status_ptr, 1, 4)
    wr(m, tcb + 0x0C, 4, sp)
    return m, sp


def gen_state(rng):
    """Random TCB/desc addresses, random caller-save register values (the values
    that actually land on the stack), and a pre-seeded stack region so un-written
    slots (e.g. the pad) match exactly between oracle and model."""
    tcb = 0x4000 + ((rng.getrandbits(10)) << 4)
    desc = 0x8000 + ((rng.getrandbits(10)) << 4)
    status = 0x0C000 + ((rng.getrandbits(10)) << 4)
    # ~35% FPU path (type byte == 4), rest scattered across 0..0xFF non-4
    task_type = 4 if rng.random() < 0.35 else rng.getrandbits(8)
    if task_type == 4 and rng.random() < 0.02:
        task_type = rng.getrandbits(8)

    vals = {
        'r5': rng.getrandbits(32), 'r8': rng.getrandbits(32),
        'r9': rng.getrandbits(32), 'r10': rng.getrandbits(32),
        'r11': rng.getrandbits(32), 'r12': rng.getrandbits(32),
        'r13': rng.getrandbits(32), 'r14': rng.getrandbits(32),
        'gbr': rng.getrandbits(32), 'macl': rng.getrandbits(32),
        'mach': rng.getrandbits(32),
    }

    # pre-seed the whole stack window (incl. below saved_sp) with junk
    ram = {}
    for a in range(0xFFFFDE80, 0xFFFFDF00):
        ram[a] = rng.getrandbits(8)

    # TCB region: junk then saved_sp slot (tcb+0x0C) overwritten by func
    for a in range(tcb, tcb + 0x20):
        ram[a] = rng.getrandbits(8)
    # task descriptor: [0] type byte, [4..8] status ptr
    ram[desc] = task_type
    for i in range(4):
        ram[desc + 4 + i] = (status >> (24 - 8 * i)) & 0xFF
    for a in range(status, status + 4):
        ram[a] = rng.getrandbits(8)

    # schedule tail stub @0x3C68: rts ; nop
    ram[0x3C68] = 0x00; ram[0x3C69] = 0x0B
    ram[0x3C6A] = 0x00; ram[0x3C6B] = 0x09

    # FPU register values as exact float32 bit patterns
    fpu = {}
    for fr in (12, 13, 14, 15):
        fpu[fr] = struct.unpack('>f', struct.pack('>I', rng.getrandbits(32)))[0]

    return ram, tcb, desc, status, task_type, vals, fpu


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 500
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    seeds = (0x3BF4, 0x3C68, 0x3CBD, 0x8000, 0xF000)
    total_fails = 0

    for seed in seeds:
        rng = random.Random(seed)
        fails = 0
        for it in range(N):
            ram, tcb, desc, status, task_type, vals, fpu = gen_state(rng)
            fpu_expected = (task_type & 0xFF) == 4
            regs = {k: v for k, v in vals.items() if k != 'pr'}
            want, want_sp = ref(ram, tcb, desc, vals, fpu if fpu_expected else {})
            got_r0 = None
            try:
                got_r0 = cpu.call(ADDR, r4=tcb, r6=desc, ram=ram,
                                  fr={k: v for k, v in fpu.items()},
                                  regs=regs)
            except Exception as e:
                print('EMULATOR EXC seed=0x%X iter=%d type=%d: %s'
                      % (seed, it, task_type, e))
                fails += 1
                if fails >= 3:
                    break
                continue
            got = cpu.ram
            if got_r0 != 4:
                print('RET MISMATCH seed=0x%X iter=%d: r0=%d (want 4)'
                      % (seed, it, got_r0))
                fails += 1
                if fails >= 3:
                    break
                continue
            bad = []
            for k in set(k for k in want if isinstance(k, int)) | set(got.keys()):
                if got.get(k, 0) != want.get(k, 0):
                    bad.append((k, got.get(k, 0), want.get(k, 0)))
            if bad:
                print('MISMATCH seed=0x%X iter=%d type=%d : %s' %
                      (seed, it, task_type,
                       {hex(k): (hex(g), hex(e)) for k, g, e in bad[:16]}))
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
    print('OK  0x3BF4 task_full_context_save  (context-save write path bit-exact, '
          '%d inputs across %d seeds)' % (N * len(seeds), len(seeds)))
    sys.exit(0)


if __name__ == '__main__':
    main()