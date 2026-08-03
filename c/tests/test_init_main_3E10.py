#!/usr/bin/env python3
"""test_init_main_3E10.py

Differential test for ROM 0x3E10 (60E1D400.bin) — init_main (RTOS/system
init; lift: c/init_main.c).  Reached from task_context_switch (0x3AD8) with
r4 = mode (0 cold / 1 warm).  It fills the RTOS control block at 0xFFFF72B0,
dispatches 10-11 init subroutines, and tail-jumps to task_full_context_save
(0x3C2A) with the stack frame unwound in the jump's delay slot.

Level: FULL model of the observable init state + SKELETON dispatch.  All 11
callees are stubbed (trace-append stubs, pattern test_calc_lambda_feedback_pid_11A34.py)
so the outer's OWN behavior — every control-block write and the dispatch
sequence — is pinned bit-exactly against a Python model of the disassembly.

Disassembly (60E1D400):
  0x3E10 sts.l pr,@-r15              ; [0xFFFFDEFC] = PR (SENT)
  0x3E12 mov r4,r0                   ; r0 = mode
  0x3E14 mov.l @(0x3E88),r1          ; r1 = 0x4938 (RAM base ptr)
  0x3E16 mov.l @(0x3E80),r14         ; r14 = 0xFFFF72B0 (ctl)
  0x3E18 mov.l @(0x3E84),r2          ; r2 = 0x4B04 (init SR ptr)
  0x3E1A mov.l @r2,r3                ; r3 = [0x4B04]
  0x3E1C mov.l r3,@(0x10,r14)        ; ctl->initial_sr  = [0x4B04]
  0x3E1E mov.b r0,@(0x01,r14)        ; ctl->mode        = mode & 0xFF
  0x3E20 mov.l @r1,r3                ; r3 = [0x4938]
  0x3E22 mov #0xFF,r0                ; r0 = -1
  0x3E24 mov.l r3,@(0xC,r14)         ; ctl->ram_base    = [0x4938]
  0x3E26 mov.w r0,@(0x04,r14)        ; ctl->field_4     = 0xFFFF
  0x3E28 mov.l @(0x3E8C),r3          ; r3 = 0x4990 (task config)
  0x3E2A mov.l r3,@(0x18,r14)        ; ctl->task_config = 0x4990
  0x3E2C mov r3,r2
  0x3E2E mov.l @(0x4,r2),r3          ; r3 = [0x4994]
  0x3E30 mov.l @(0x3E90),r2          ; r2 = task_queue_init
  0x3E32 mov.l r3,@(0x14,r14)        ; ctl->field_20    = [0x4994]
  0x3E34 jsr @r2                     ; k=0 0x3964
  0x3E38 mov.l @(0x3E94),r3 / jsr    ; k=1 0x3EC0
  0x3E3E mov.l @(0x3E98),r2 / jsr    ; k=2 0x3F10
  0x3E44 mov.l @(0x3E9C),r3 / jsr    ; k=3 0x3AC0
  0x3E4A mov.l @(0x3EA0),r2 / jsr    ; k=4 0x3F8C
  0x3E50 mov.l @(0x3EA4),r3 / jsr    ; k=5 0x3F88
  0x3E56 mov.l @(0x3EA8),r2 / jsr    ; k=6 0x3F90
  0x3E5C mov.l @(0x3EAC),r3 / jsr    ; k=7 0x3F9C
  0x3E62 mov.l @(0x3EB0),r3 / mov.l @r3,r2   ; r2 = [0x4B14] (flag)
  0x3E66 tst r2,r2 / bt 0x3E70       ; flag != 0 -> k=8 0x3588
  0x3E70 mov.l @(0x3EB8),r3 / jsr    ; k=9 0x3FA8
  0x3E76 mov r14,r4
  0x3E78 mov.l @(0x3EBC),r2          ; r2 = 0x3C2A (task_full_context_save)
  0x3E7A jmp @r2                     ; TAIL (delay: lds.l @r15+,pr -> PR=SENT,
  0x3E7C lds.l @r15+,pr              ;   r15 back to 0xFFFFDF00, then stub rts)

Stub placement: the nullsub cluster (0x3F88..0x3FA8) is 4-20 bytes between
adjacent callees, so the 42-byte stubs cannot sit at their real addresses.
All 11 stubs are relocated to a dedicated RAM block and the caller's
literal-pool slots (0x3E90..0x3EBC) are overlaid with the relocated homes.

Compared bit-exactly: all 6 ctl-block fields, the PR word @0xFFFFDEFC,
the trace (10 or 11 entries depending on [0x4B14]), r15 = 0xFFFFDF00
(restored by the tail-call delay slot), r0 = LEN_ADDR (last stub), PR = SENT.

Run: python3 c/tests/test_init_main_3E10.py [N]
     (N = random inputs per seed; default 600 -> 3000 across 5 seeds)
"""
import os, random, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2  # noqa: E402

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ADDR = 0x3E10
MASK = 0xFFFFFFFF
SENT = 0xEEEE0000
CTL = 0xFFFF72B0
PR_WORD = 0xFFFFDEFC
LEN_ADDR = 0xFFFFD130
TRACE_ADDR = 0xFFFFD140
TASK_CONFIG = 0x4990

# relocated stub homes (real callee addresses in comments)
HOMES = {0: 0xA400, 1: 0xA42A, 2: 0xA454, 3: 0xA47E, 4: 0xA4A8,
         5: 0xA4D2, 6: 0xA4FC, 7: 0xA526, 8: 0xA550, 9: 0xA57A, 10: 0xA5A4}
REAL = {0: 0x3964, 1: 0x3EC0, 2: 0x3F10, 3: 0x3AC0, 4: 0x3F8C,
        5: 0x3F88, 6: 0x3F90, 7: 0x3F9C, 8: 0x3588, 9: 0x3FA8, 10: 0x3C2A}
# caller literal-pool slot -> stub index (redirect dispatch)
POOL_REDIRECT = {0x3E90: 0, 0x3E94: 1, 0x3E98: 2, 0x3E9C: 3, 0x3EA0: 4,
                 0x3EA4: 5, 0x3EA8: 6, 0x3EAC: 7, 0x3EB4: 8, 0x3EB8: 9,
                 0x3EBC: 10}
# data-literal slots that must KEEP their real values (pointers, not dispatch)
KEEP_LITERALS = (0x3E80, 0x3E84, 0x3E88, 0x3E8C, 0x3EB0)

SPAN_START = 0xFFFFD12F
SPAN_LEN = 53


def make_stub(k, addr):
    b = bytearray(34)
    b[0] = 0xE4; b[1] = k & 0xFF
    pool = (addr + 22 + 3) & ~3
    b2 = (addr + 6) & ~3
    b4 = (addr + 8) & ~3
    b[2] = 0xD0; b[3] = (pool - b2) // 4
    b[4] = 0xD3; b[5] = (pool + 4 - b4) // 4
    b[6] = 0x62; b[7] = 0x00
    b[8] = 0x32; b[9] = 0x3C
    b[10] = 0x22; b[11] = 0x40
    b[12] = 0x62; b[13] = 0x00
    b[14] = 0x72; b[15] = 0x01
    b[16] = 0x20; b[17] = 0x20
    b[18] = 0x00; b[19] = 0x0B
    b[20] = 0x00; b[21] = 0x09
    lo = pool - addr
    b[lo:lo + 4] = struct.pack('>I', LEN_ADDR)
    b[lo + 4:lo + 8] = struct.pack('>I', TRACE_ADDR)
    return bytes(b)


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
    """Random mode, RAM input cells, seeded ctl/stack windows and trace span."""
    ram = {}
    mode = rng.getrandbits(32)
    wr(ram, 0x4B04, 4, rng.getrandbits(32))     # initial SR
    wr(ram, 0x4938, 4, rng.getrandbits(32))     # RAM base
    wr(ram, 0x4994, 4, rng.getrandbits(32))     # task config field_4
    wr(ram, 0x4B14, 4, rng.getrandbits(32))     # task_flag_run_A gate
    # ctl block + stack window pre-seeded with junk
    for a in range(CTL, CTL + 0x30):
        ram[a] = rng.getrandbits(8)
    for a in range(0xFFFFDEF0, 0xFFFFDF00):
        ram[a] = rng.getrandbits(8)
    # trace span: small len so appends stay inside the compared span
    for a in range(SPAN_START, SPAN_START + SPAN_LEN):
        ram[a] = rng.getrandbits(8)
    ram[SPAN_START + 1] = rng.choice((0, 0, 0, 1, 2, 3, 5, 7, 8, 12, 17))
    ram[SPAN_START] = 0x5A
    ram[SPAN_START + 2] = 0xA5
    # stubs + literal redirects
    for k, h in HOMES.items():
        st = make_stub(k, h)
        for i, byte in enumerate(st):
            ram[h + i] = byte
    for pool, k in POOL_REDIRECT.items():
        wr(ram, pool, 4, HOMES[k])
    return ram, mode


def ref(ram, mode):
    """Python model of 0x3E10.  Returns (r0, r15, pr, post-RAM)."""
    m = dict(ram)
    wr(m, CTL + 0x10, 4, rd(m, 0x4B04, 4))
    wr(m, CTL + 0x01, 1, mode & 0xFF)
    wr(m, CTL + 0x0C, 4, rd(m, 0x4938, 4))
    wr(m, CTL + 0x04, 2, 0xFFFF)
    wr(m, CTL + 0x18, 4, TASK_CONFIG)
    wr(m, CTL + 0x14, 4, rd(m, 0x4994, 4))
    wr(m, PR_WORD, 4, SENT)
    # trace appends in ROM dispatch order
    ln = rb(m, SPAN_START + 1)
    trace = SPAN_START + 17
    for k in range(11):
        if k == 8 and rd(m, 0x4B14, 4) == 0:
            continue                        # bt 0x3E70: flag==0 skips k=8
        idx = ln - 256 if ln & 0x80 else ln
        m[(trace + idx) & MASK] = k
        ln = (ln + 1) & 0xFF
    m[SPAN_START + 1] = ln
    return LEN_ADDR, 0xFFFFDF00, SENT, m


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 600
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    seeds = (0x3E10, 0x3EC0, 0x3C2A, 0x8000, 0x5EED)
    total_fails = 0

    for seed in seeds:
        rng = random.Random(seed)
        fails = 0
        for it in range(N):
            ram, mode = gen_state(rng)
            want_r0, want_r15, want_pr, want = ref(ram, mode)
            try:
                got_r0 = cpu.call(ADDR, r4=mode, ram=ram)
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
            if cpu.pr != want_pr:
                bad.append(('pr', cpu.pr, want_pr))
            for k in set(got) | set(want):
                if got.get(k, 0) != want.get(k, 0):
                    bad.append((k, got.get(k, 0), want.get(k, 0)))
            if bad:
                print('MISMATCH seed=0x%X iter=%d mode=0x%08X' %
                      (seed, it, mode))
                shown = []
                for k, g, e in bad[:16]:
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
    print('OK  0x3E10 init_main  (RTOS ctl-block init + conditional dispatch '
          'bit-exact, %d inputs across %d seeds)'
          % (N * len(seeds), len(seeds)))
    sys.exit(0)


if __name__ == '__main__':
    main()
