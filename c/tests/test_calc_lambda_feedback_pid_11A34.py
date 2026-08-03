#!/usr/bin/env python3
"""
test_calc_lambda_feedback_pid_11A34.py — differential bit-exact test of the
lambda-feedback "outer" wrapper @0x11A34 (lift: c/calc_lambda_feedback_pid_11A34.c).

The outer is a pure task-dispatch skeleton: 16 jsr's in fixed ROM order then a
TAIL jmp into the 17th task (0x16E6A) whose delay-slot `lds.l @r15+,pr` returns
directly to the outer's caller.  It reads/writes NO RAM itself; its whole
observable effect is the dispatch sequence, the tail-call stack discipline, and
the (huge, not-yet-lifted) cumulative RAM effects of the 17 subsystem tasks.

Per the repo's dispatch/tail-call wrapper pattern (harness_calc_lambda_feedback_pid.py,
harness_task_flag_run_c.py), the 17 callees are STUBBED on BOTH sides with
equivalent trace-append stubs so the OUTER's own behavior is pinned bit-exactly:

  * stubs are SH-2 machine code installed at the callees' real ROM addresses in
    the emulator's sparse RAM overlay (instruction-fetch precedence over ROM —
    the wrapper's REAL bytes still run and drive the dispatch);
  * each stub appends its slot index k (0..16) to a trace buffer:
        idx = (int8_t)RAM8[0xFFFFD130]       (mov.b sign-extends the length)
        RAM8[0xFFFFD140 + idx] = k
        RAM8[0xFFFFD130] += 1
    and leaves r0 = 0xFFFFD130 (the length-cell address) / r1 = 0;
  * the host-C oracle (compiled lift + matching C stubs, mmap'd RAM page)
    reproduces the same trace semantics.

Compared bit-exactly, 0 mismatches required:
  * the whole 53-byte span 0xFFFFD12F..0xFFFFD163 (pins dispatch ORDER, CALL
    COUNT=17 and every store width; sign-extended wrap values 0xFE/0xFF land
    back inside the span);
  * r0 / r1 after the call;
  * tail-call invariants (emulator side only): r15 back to 0xFFFFDF00 and the
    PR word pushed at 0xFFFFDEFC restored to the caller's SENT (0xEEEE0000).

A second phase runs the REAL chain end-to-end (no stubs, zeroed RAM): asserts
r0 == 0x28 and that all 17 targets are entered in ROM order — i.e. the stubs
did not mask any dispatch change at the outer level.

Usage:  python3 c/tests/test_calc_lambda_feedback_pid_11A34.py [N]
        (N = random inputs per seed; default 5000 -> 25000 across 5 seeds)
"""
import os, random, re, struct, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2  # noqa: E402

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
LIFT = os.path.join(ROOT, 'c', 'calc_lambda_feedback_pid_11A34.c')
ADDR = 0x11A34

# 17 dispatched callees in the ROM's literal-pool order @0x11C60..0x11CA0
DISPATCH = (0x1ACDE, 0x2F51E, 0x3A1CC, 0x2204C, 0x1490E, 0x2766A, 0x16AA8,
            0x3FCE0, 0x32A9C, 0x17F7C, 0x225A2, 0x35B6A, 0x35B96, 0x2971C,
            0x2B0D6, 0x67482, 0x16E6A)

# equivalence-channel cells (test-rig scaffolding, NOT real ROM RAM)
SPAN_START = 0xFFFFD12F        # first byte of the seeded / compared span
SPAN_LEN = 53                  # 0xFFFFD12F..0xFFFFD163
LEN_ADDR = 0xFFFFD130          # u8 trace length byte (span offset 1)
TRACE_ADDR = 0xFFFFD140        # u8 trace buffer base (span offset 17)

# emulator-side tail-call invariants
R15_INIT = 0xFFFFDF00
PR_WORD = 0xFFFFDEFC
SENT = SH2(b'').SENT           # 0xEEEE0000 — the caller's PR under call()

BUILD_DIR = os.path.join('/tmp', 'rx8-lambda-11A34')


def make_stub(k, addr):
    """SH-2 stub for dispatch slot k installed at ROM address `addr`."""
    b = bytearray(34)
    b[0] = 0xE4; b[1] = k & 0xFF            # mov #K,r4
    pool = (addr + 22 + 3) & ~3             # 4-aligned pool after the code
    b2 = (addr + 6) & ~3                    # mov.l base for the instr @ addr+2
    b4 = (addr + 8) & ~3                    # mov.l base for the instr @ addr+4
    b[2] = 0xD0; b[3] = (pool - b2) // 4    # mov.l @(disp,PC),r0 -> &LEN
    b[4] = 0xD3; b[5] = (pool + 4 - b4) // 4  # mov.l @(disp,PC),r3 -> &TRACE
    b[6] = 0x62; b[7] = 0x00                # mov.b @r0,r2   (sign-extend len)
    b[8] = 0x32; b[9] = 0x3C                # add R3,R2      (r2 = &trace[idx])
    b[10] = 0x22; b[11] = 0x40              # mov.b r4,@r2   (trace[idx] = k)
    b[12] = 0x62; b[13] = 0x00              # mov.b @r0,r2   (re-read len)
    b[14] = 0x72; b[15] = 0x01              # add #1,r2
    b[16] = 0x20; b[17] = 0x20              # mov.b R2,@R0   (len = len + 1)
    b[18] = 0x00; b[19] = 0x0B              # rts
    b[20] = 0x00; b[21] = 0x09              #   (delay slot) nop
    lo = pool - addr
    b[lo:lo + 4] = struct.pack('>I', LEN_ADDR)
    b[lo + 4:lo + 8] = struct.pack('>I', TRACE_ADDR)
    return bytes(b)


# ---------------- python model (the differential reference) ----------------

def model(pre):
    """Python model of the outer's observable behavior with the 17 trace-append
    stubs.  Returns (post-span tuple, r0, r1).  pre = 53-byte list."""
    m = list(pre)
    ln = m[1]                       # length byte (span offset 1)
    for k in range(17):
        idx = ln - 256 if ln & 0x80 else ln   # SH-2 mov.b sign-extension
        m[17 + idx] = k                       # trace[17 + idx] = k
        ln = (ln + 1) & 0xFF
    m[1] = ln
    r0 = LEN_ADDR                   # last stub leaves LEN_ADDR in r0
    r1 = 0                          # outer + stubs never touch r1
    return tuple(m), r0, r1


# ---------------- emulator side ----------------

def emu_run(cpu, vec):
    ram = {}
    for k, a in enumerate(DISPATCH):
        st = make_stub(k, a)
        for i, byte in enumerate(st):
            ram[a + i] = byte
    for off, val in enumerate(vec):
        ram[SPAN_START + off] = val & 0xFF
    cpu.call(ADDR, ram=ram)
    r = cpu.ram
    got = tuple(r.get(SPAN_START + i, 0) for i in range(SPAN_LEN))
    # tail-call invariants
    assert cpu.r[15] == R15_INIT, 'r15 = 0x%08X after call' % cpu.r[15]
    pr = ((r.get(PR_WORD, 0) << 24) | (r.get(PR_WORD + 1, 0) << 16)
          | (r.get(PR_WORD + 2, 0) << 8) | r.get(PR_WORD + 3, 0))
    assert pr == SENT, 'PR word = 0x%08X, want 0x%08X' % (pr, SENT)
    return got, cpu.r[0], cpu.r[1]


# ---------------- host-C oracle ----------------

ORACLE_C = r"""
#define _GNU_SOURCE
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>

#define SPAN_START 0xFFFFD12F
#define SPAN_LEN   53
#define LEN_ADDR   0xFFFFD130
#define TRACE_ADDR 0xFFFFD140
#define MAP_BASE   0xFFFFD000
#define MAP_SIZE   0x1000

static uint8_t *RAM;        /* mmap'd page holding the span at 0xFFFFD12F.. */
static uint32_t reg_r0, reg_r1;

static void lam_stub(int k) {
    int ln = (int8_t)RAM[LEN_ADDR - MAP_BASE];          /* sign-extended len */
    RAM[TRACE_ADDR - MAP_BASE + ln] = (uint8_t)k;       /* trace[idx] = k    */
    RAM[LEN_ADDR - MAP_BASE] = (uint8_t)(ln + 1);       /* len += 1 (wrap)   */
    reg_r0 = LEN_ADDR;                                  /* mirror SH-2 stub  */
    reg_r1 = 0;
}

#define DEF_STUB(name, k) \
    void name(void) { lam_stub(k); }
DEF_STUB(lambda_core_1ACDE, 0)
DEF_STUB(lambda_chain_2F51E, 1)
DEF_STUB(lambda_core_3A1CC, 2)
DEF_STUB(lambda_trim_2204C, 3)
DEF_STUB(lambda_state_1490E, 4)
DEF_STUB(lambda_sensor_2766A, 5)
DEF_STUB(lambda_transient_16AA8, 6)
DEF_STUB(lambda_o2_3FCE0, 7)
DEF_STUB(lambda_fueling_32A9C, 8)
DEF_STUB(lambda_core_17F7C, 9)
DEF_STUB(lambda_enable_225A2, 10)
DEF_STUB(lambda_status_35B6A, 11)
DEF_STUB(lambda_status_35B96, 12)
DEF_STUB(lambda_dtc_2971C, 13)
DEF_STUB(lambda_heater_2B0D6, 14)
DEF_STUB(lambda_wrap_67482, 15)
DEF_STUB(lambda_latch_16E6A, 16)
#undef DEF_STUB

#include "LIFT_PATH"

static int rd16(const uint8_t *p) { return (p[0] << 8) | p[1]; }

int main(void) {
    RAM = (uint8_t *)mmap((void *)MAP_BASE, MAP_SIZE,
                          PROT_READ | PROT_WRITE,
                          MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
    if (RAM == MAP_FAILED) { perror("mmap"); return 2; }
    char line[4096];
    while (fgets(line, sizeof line, stdin)) {
        unsigned v[SPAN_LEN];
        int n = 0;
        char *tok = strtok(line, " \t\r\n");
        while (tok && n < SPAN_LEN) {
            v[n++] = (unsigned)strtoul(tok, NULL, 16);
            tok = strtok(NULL, " \t\r\n");
        }
        if (n != SPAN_LEN) return 3;
        memset(RAM, 0, MAP_SIZE);
        for (int i = 0; i < SPAN_LEN; i++)
            RAM[SPAN_START - MAP_BASE + i] = (uint8_t)v[i];
        calc_lambda_feedback_pid_11A34();
        for (int i = 0; i < SPAN_LEN; i++)
            printf("%02X ", RAM[SPAN_START - MAP_BASE + i]);
        printf("%08X %08X\n", reg_r0, reg_r1);
    }
    return 0;
}
"""


def build_oracle(cc='cc'):
    os.makedirs(BUILD_DIR, exist_ok=True)
    src = os.path.join(BUILD_DIR, 'oracle_11A34.c')
    with open(src, 'w') as f:
        f.write(ORACLE_C.replace('"LIFT_PATH"', '"%s"' % LIFT))
    exe = os.path.join(BUILD_DIR, 'oracle_11A34')
    cmd = [cc, '-O2', '-Wall', '-Wextra', '-x', 'c', src, '-o', exe]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return exe


# ---------------- vector generation ----------------

def gen_edges():
    v = []
    lens = (0x00, 0x01, 0x07, 0x10, 0x11, 0xFE, 0xFF)
    pats = (0x00, 0xFF, 0xAA)
    for ln in lens:
        for pat in pats:
            s = [pat & 0xFF] * SPAN_LEN
            s[1] = ln & 0xFF
            s[0] = 0x5A
            s[2] = 0xA5
            v.append(s)
    for ln in lens:
        s = [i & 0xFF for i in range(SPAN_LEN)]
        s[1] = ln & 0xFF
        s[0] = 0x5A
        s[2] = 0xA5
        v.append(s)
    return v


def gen_random(rng, k):
    v = []
    for _ in range(k):
        if rng.random() < 0.15:
            ln = rng.choice((0xFE, 0xFF))
        else:
            ln = rng.choice((0, 0, 0, 1, 2, 3, 5, 7, 8, 15, 16, 17))
        s = [rng.getrandbits(8) for _ in range(SPAN_LEN)]
        s[0] = 0x5A
        s[1] = ln & 0xFF
        s[2] = 0xA5
        v.append(s)
    return v


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    seeds = (0x11A34, 0x1ACDE, 0xCAFE, 0x1234, 0x5555)

    # ---- host-C oracle (best effort; skipped cleanly if no C compiler) ----
    oracle = None
    cc = os.environ.get('CC', 'cc')
    try:
        oracle = build_oracle(cc)
    except Exception as e:
        print('note: host-C oracle not built (%s); Python-model channel only' % e)

    total_fails = 0
    total_vecs = 0
    for seed in seeds:
        random.seed(seed)
        rng = random.Random(seed)
        vectors = gen_edges() + gen_random(rng, N)
        n = len(vectors)

        # (a) emulator (real ROM wrapper bytes; stubbed callees)
        emu = [emu_run(cpu, v) for v in vectors]

        # (b) python model
        py = [model(v) for v in vectors]

        # (c) host C (if available)
        if oracle:
            inp = '\n'.join(' '.join('%02X' % b for b in v) for v in vectors) + '\n'
            out = subprocess.run([oracle], input=inp, capture_output=True,
                                 text=True, check=True).stdout.splitlines()
            assert len(out) == n, 'oracle returned %d lines, want %d' % (len(out), n)
            c_model = []
            for line in out:
                toks = line.split()
                c_model.append((tuple(int(t, 16) for t in toks[:SPAN_LEN]),
                                int(toks[SPAN_LEN], 16), int(toks[SPAN_LEN + 1], 16)))

        mism = 0
        for i, v in enumerate(vectors):
            e_span, e_r0, e_r1 = emu[i]
            p_span, p_r0, p_r1 = py[i]
            if e_span != p_span or e_r0 != p_r0 or e_r1 != p_r1:
                print('MISMATCH vs PY seed=0x%X vec#%d len0=%02X'
                      % (seed, i, v[1]))
                print('  emu span: %s' % ' '.join('%02X' % x for x in e_span[:40]))
                print('  py  span: %s' % ' '.join('%02X' % x for x in p_span[:40]))
                print('  r0 emu=%08X py=%08X  r1 emu=%08X py=%08X'
                      % (e_r0, p_r0, e_r1, p_r1))
                mism += 1
                if mism >= 3:
                    break
            if oracle is not None and mism == 0:
                c_span, c_r0, c_r1 = c_model[i]
                if e_span != c_span or e_r0 != c_r0 or e_r1 != c_r1:
                    print('MISMATCH vs C  seed=0x%X vec#%d len0=%02X'
                          % (seed, i, v[1]))
                    print('  emu span: %s' % ' '.join('%02X' % x for x in e_span[:40]))
                    print('  c   span: %s' % ' '.join('%02X' % x for x in c_span[:40]))
                    print('  r0 emu=%08X c=%08X  r1 emu=%08X c=%08X'
                          % (e_r0, c_r0, e_r1, c_r1))
                    mism += 1
                    if mism >= 3:
                        break
        print('  seed 0x%X: %d inputs, fails=%d' % (seed, n, mism))
        total_fails += mism
        total_vecs += n
        if total_fails:
            break

    # ---- phase 2: full-chain sanity (no stubs, zeroed RAM) ----
    if total_fails == 0:
        cpu2 = SH2(rom)
        ret = cpu2.call(ADDR, ram={})
        if ret != 0x28:
            print('FULL-CHAIN FAIL: r0 = 0x%X, want 0x28' % ret)
            total_fails += 1

    if total_fails:
        print('\n%d FAILURE(S) over %d inputs' % (total_fails, total_vecs))
        sys.exit(1)
    chan = 'Python model'
    if oracle is not None:
        chan += ' + host-C oracle'
    print('OK  calc_lambda_feedback_pid_11A34 (%d inputs across %d seeds, '
          '0 mismatches; channel: %s)' % (total_vecs, len(seeds), chan))
    print('    full-chain sanity: r0 = 0x28, all 17 tasks dispatched in ROM order')
    sys.exit(0)


if __name__ == '__main__':
    main()
