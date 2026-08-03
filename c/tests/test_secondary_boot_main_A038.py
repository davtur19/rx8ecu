#!/usr/bin/env python3
"""test_secondary_boot_main_A038.py

Differential test for ROM 0xA038 (60E1D400.bin) — secondary_boot_main
(lift: c/boot_entry.c).  The second-stage boot: chains 7 peripheral init
calls then starts the RTOS via task_context_switch(0); the tail `bra self`
@0xA06E means it NEVER returns.

Level: SKELETON (dispatch).  The 8 callees are stubbed (equivalent
trace-append stubs, see harness pattern test_calc_lambda_feedback_pid_11A34.py)
so the OUTER's own behavior is pinned bit-exactly: dispatch order, call
count, and the stack/PR discipline of the tail-call path.

The real callee addresses are:
  k=0 0x4C80  peripheral_init_chain_A
  k=1 0xD7B0  secondary_peripheral_initializer
  k=2 0xA0DC  sfr_write_a16c          (reached via `bsr 0xA0DC`)
  k=3 0x2054  setSR_PARAM
  k=4 0x4BBC  setRegister_REG_BIT_VAL
  k=5 0x2064  loadStatusRegister_ADDR
  k=6 0x4CF8  sfr_init_dma_channels
  k=7 0x3AD8  task_context_switch     (tail-boot, real flow never returns)

Stub placement: the 42-byte stubs cannot sit at 0xA0DC/0x2054/0x2064 —
0xA0DC is inside the caller's literal pool (0xA0E8..0xA10C) and 0x2054 vs
0x2064 are 16 bytes apart (stubs would collide).  They are therefore
RELOCATED to a dedicated RAM block and the dispatch is redirected:
  * the ROM literal pool entries (mov.l @(disp,PC) targets) are overlaid
    with the relocated stub addresses;
  * the `bsr 0xA0DC` displacement at 0xA046 is patched (B049 -> B023) to
    reach the relocated k=2 stub at 0xA090 (in-range for the 8-bit bsr
    displacement);
  * the terminal `bra 0xA06E` is overlaid with `mov.l SENT,r0; jmp @r0; nop`
    so the emulator terminates after the last dispatch instead of spinning.

Each trace stub appends its slot index k to a trace buffer:
    idx = (int8_t)RAM8[0xFFFFD130]; RAM8[0xFFFFD140+idx]=k; len++  (r0=LEN)
The stub leaves r0 = 0xFFFFD130; the terminal overlay then loads r0 = SENT
(0xEEEE0000) before jmp'ing to SENT, so the emulator returns r0 = SENT.

Model (Python): the outer's observable effect with these stubs is exactly
"append k=0..7 in order", r15 = 0xFFFFDEFC (add #0xFC,r15 never unwound —
the real flow never returns), PR = 0xA06E (the last jsr's return address,
which the terminal jmp does not rewrite).

Run: python3 c/tests/test_secondary_boot_main_A038.py [N]
     (N = seeded span variations per seed; default 600 -> 3000 across 5 seeds)
"""
import os, random, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2  # noqa: E402

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ADDR = 0xA038
SENT = 0xEEEE0000
R15_AFTER = 0xFFFFDEFC          # add #0xFC,r15 at entry; never unwound
PR_AFTER = 0xA06E               # last jsr (0xA06A) return address

# stub homes (relocated; real targets in comments)
HOMES = {0: 0xA200, 1: 0xA222, 2: 0xA090, 3: 0xA244,
         4: 0xA266, 5: 0xA288, 6: 0xA2AA, 7: 0xA2CC}
REAL = {0: 0x4C80, 1: 0xD7B0, 2: 0xA0DC, 3: 0x2054,
        4: 0x4BBC, 5: 0x2064, 6: 0x4CF8, 7: 0x3AD8}
# caller literal-pool slots -> relocated home
POOL_REDIRECT = {0xA0F0: 0, 0xA0F4: 1, 0xA0F8: 3, 0xA0FC: 4,
                 0xA100: 5, 0xA104: 6, 0xA108: 7}
# terminal overlay @0xA06E: mov.l @(disp=1,pc),r0 ; jmp @r0 ; nop ; SENT
TERM_START = 0xA06E

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
    """Assemble the full sparse RAM harness: stubs, redirects, terminal
    overlay, and the seeded trace span.  span_seed = 53-byte list."""
    ram = {}
    for k, h in HOMES.items():
        st = make_stub(k, h)
        for i, byte in enumerate(st):
            ram[h + i] = byte
    for pool, k in POOL_REDIRECT.items():
        for i in range(4):
            ram[pool + i] = (HOMES[k] >> (8 * (3 - i))) & 0xFF
    ram[0xA046] = 0xB0; ram[0xA047] = 0x23          # bsr -> k=2 home 0xA090
    # terminal overlay: mov.l @(disp=1,pc),r0 ; jmp @r0 ; nop ; SENT
    ram[TERM_START] = 0xD0; ram[TERM_START + 1] = 0x01
    ram[TERM_START + 2] = 0x40; ram[TERM_START + 3] = 0x2B
    ram[TERM_START + 4] = 0x00; ram[TERM_START + 5] = 0x09
    for i in range(4):
        ram[TERM_START + 6 + i] = (SENT >> (8 * (3 - i))) & 0xFF
    for off, val in enumerate(span_seed):
        ram[SPAN_START + off] = val & 0xFF
    return ram


def model(span_seed):
    """Python model: 8 trace appends in ROM order on the seeded span."""
    m = list(span_seed)
    ln = m[1]
    for k in range(8):
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
    seeds = (0xA038, 0xA0DC, 0x2054, 0x3AD8, 0x5EED)
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
            if cpu.r[15] != R15_AFTER:
                bad.append(('r15', cpu.r[15], R15_AFTER))
            if cpu.pr != PR_AFTER:
                bad.append(('pr', cpu.pr, PR_AFTER))
            # no writes outside the seeded harness + trace span
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
    print('OK  0xA038 secondary_boot_main  (SKELETON dispatch: 8/8 callees in '
          'ROM order, r15/pr tail invariants, %d inputs across %d seeds)'
          % (N * len(seeds), len(seeds)))
    sys.exit(0)


if __name__ == '__main__':
    main()
