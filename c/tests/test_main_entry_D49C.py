#!/usr/bin/env python3
"""test_main_entry_D49C.py

Differential test for ROM 0xD49C (60E1D400.bin) — main_entry (the app's
reset entry; lift: c/boot_entry.c).  ROM longword @0x7FFF8 == 0xD49C routes
the boot-ROM here: VBR = 0x0007FC50, FPSCR = 0x00040001, SP = [0xD9C8] =
0xFFFF7304 via stack_frame_set_sp (0x4C7A), then secondary_boot_main
(0xA038) — which never returns (tail `bra 0xD4B2`).

Level: SKELETON (dispatch).  The two callees (0x4C7A, 0xA038) are stubbed
with trace-append stubs (pattern test_calc_lambda_feedback_pid_11A34.py);
the terminal `bra 0xD4B2` is overlaid with `mov.l SENT,r0; jmp @r0; nop` so
the emulator terminates after the second dispatch.

Pinned bit-exactly:
  * VBR register  = 0x0007FC50   (ldc r3,VBR)
  * FPSCR register = 0x00040001  (lds r2,fpscr)
  * dispatch order k=0 (0x4C7A), k=1 (0xA038), trace len = 2
  * r15 untouched = 0xFFFFDF00
  * r0 = SENT (0xEEEE0000) loaded by the terminal overlay; PR = 0xD4B2
    (the second jsr's return address, rewritten by neither the stub nor
    the terminal jmp).

Model (Python): reproduce the two trace appends on the seeded span; all
other observable state is constant.

Run: python3 c/tests/test_main_entry_D49C.py [N]
     (N = seeded span variations per seed; default 600 -> 3000 across 5 seeds)
"""
import os, random, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2  # noqa: E402

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ADDR = 0xD49C
SENT = 0xEEEE0000
VBR_WANT = 0x0007FC50
FPSCR_WANT = 0x00040001
SP_SRC = 0xD9C8               # literal: [0xD9C8] = SP value (loaded, not used by skeleton)
PR_AFTER = 0xD4B2             # second jsr (0xD4AE) return address

DISPATCH = (0x4C7A, 0xA038)   # k=0 stack_frame_set_sp, k=1 secondary_boot_main
TERM_START = 0xD4B2

SPAN_START = 0xFFFFD12F
SPAN_LEN = 53
LEN_ADDR = 0xFFFFD130
TRACE_ADDR = 0xFFFFD140


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


def build_harness(span_seed):
    ram = {}
    for k, addr in enumerate(DISPATCH):
        st = make_stub(k, addr)
        for i, byte in enumerate(st):
            ram[addr + i] = byte
    # SP source literal so the [0xD9C8] load is well-defined
    for i in range(4):
        ram[SP_SRC + i] = (0xFFFF7304 >> (8 * (3 - i))) & 0xFF
    # terminal overlay @0xD4B2: mov.l @(disp=1,pc),r0 ; jmp @r0 ; nop ; SENT
    ram[TERM_START] = 0xD0; ram[TERM_START + 1] = 0x01
    ram[TERM_START + 2] = 0x40; ram[TERM_START + 3] = 0x2B
    ram[TERM_START + 4] = 0x00; ram[TERM_START + 5] = 0x09
    for i in range(4):
        ram[TERM_START + 6 + i] = (SENT >> (8 * (3 - i))) & 0xFF
    for off, val in enumerate(span_seed):
        ram[SPAN_START + off] = val & 0xFF
    return ram


def model(span_seed):
    m = list(span_seed)
    ln = m[1]
    for k in range(2):
        idx = ln - 256 if ln & 0x80 else ln
        m[17 + idx] = k
        ln = (ln + 1) & 0xFF
    m[1] = ln
    return tuple(m)


def gen_span(rng):
    s = [rng.getrandbits(8) for _ in range(SPAN_LEN)]
    s[1] = rng.choice((0, 0, 0, 1, 2, 3, 5, 7, 8, 12, 17))
    s[0] = 0x5A
    s[2] = 0xA5
    return s


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 600
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    seeds = (0xD49C, 0xD558, 0x4C7A, 0x7FC50, 0x5EED)
    total_fails = 0

    for seed in seeds:
        rng = random.Random(seed)
        fails = 0
        for it in range(N):
            span = gen_span(rng)
            ram = build_harness(span)
            try:
                got_r0 = cpu.call(ADDR, ram=ram)
            except Exception as e:
                print('EMULATOR EXC seed=0x%X iter=%d: %s' % (seed, it, e))
                fails += 1
                break
            want_span = model(span)
            got_span = tuple(cpu.ram.get(SPAN_START + i, 0)
                             for i in range(SPAN_LEN))
            bad = []
            if got_span != want_span:
                bad.append('trace-span')
                if fails < 3:
                    print('  span got %s' % ' '.join('%02X' % x for x in got_span))
                    print('  span want %s' % ' '.join('%02X' % x for x in want_span))
            if got_r0 != SENT:
                bad.append(('r0', got_r0, SENT))
            if cpu.vbr != VBR_WANT:
                bad.append(('vbr', cpu.vbr, VBR_WANT))
            if cpu.fpscr != FPSCR_WANT:
                bad.append(('fpscr', cpu.fpscr, FPSCR_WANT))
            if cpu.r[15] != 0xFFFFDF00:
                bad.append(('r15', cpu.r[15], 0xFFFFDF00))
            if cpu.pr != PR_AFTER:
                bad.append(('pr', cpu.pr, PR_AFTER))
            for a in cpu.ram:
                if a in ram or (SPAN_START <= a < SPAN_START + SPAN_LEN):
                    continue
                bad.append(('extra-write', a, cpu.ram[a]))
            if bad:
                print('MISMATCH seed=0x%X iter=%d: %s' % (seed, it, bad[:6]))
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
    print('OK  0xD49C main_entry  (SKELETON dispatch: VBR/FPSCR install + '
          '2/2 callees in ROM order, %d inputs across %d seeds)'
          % (N * len(seeds), len(seeds)))
    sys.exit(0)


if __name__ == '__main__':
    main()
