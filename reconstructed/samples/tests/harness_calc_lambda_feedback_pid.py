#!/usr/bin/env python3
"""
harness_calc_lambda_feedback_pid.py — equivalence of
                        rx8_calc_lambda_feedback_pid @0x11A34.

Reconstructed source: samples/src/rx8_calc_lambda_feedback_pid.c
Verified lift   : c/calc_lambda_feedback_pid.c (calc_lambda_feedback_pid
                  @ 0x11A34, 104 bytes; the VERIFIED ground truth).

The ROM routine is a task-dispatch WRAPPER of the closed-loop lambda
subsystem: it jsr's 16 sub-functions in a fixed order, then TAIL-JMP's (not
jsr's) into the 17th, 0x16E6A — the delay-slot `lds.l @r15+,pr` restores PR,
so 0x16E6A returns directly to OUR caller.  The wrapper itself reads/writes
NO RAM; its whole observable effect is the 17-dispatch sequence and the
stack discipline around the tail call.

The 17 callees are large, not-yet-reconstructed subsystem blocks (the FP-math
heavy ones implement the actual lambda trimming).  Following the repo pattern
for dispatch/tail-call wrappers (harness_task_flag_run_c.py,
harness_crank_sensor_init.py), this harness STUBS every callee with an
equivalent SH-2 stub installed at its real ROM address in the sparse RAM
overlay (which takes instruction-fetch precedence over ROM — the wrapper's
REAL bytes still run and drive the dispatch).  Each stub appends its dispatch
slot index to a shared trace buffer:

    idx = (int8_t)RAM8[0xFFFFD130]   ; SH-2 mov.b SIGN-EXTENDS the length byte
    RAM8[0xFFFFD140 + idx] = k       ; BYTE store of the slot index (0..16)
    RAM8[0xFFFFD130] += 1            ; BYTE wrap

so the post-state trace IS the dispatch sequence.  The host oracle defines
the matching C stubs (tests/oracle_calc_lambda_feedback_pid.c).

Procedure (Track-A pattern, cf. harness_ssv_control.py):
  1. build the host oracle (system gcc; -O2, -Wall, -Wextra),
  2. edge vectors (trace length pre-state 0/1/7/16/17/0xFE/0xFF over zero /
     all-ones / alternating / ramp pre-fills) + N random pre-states,
  3. run the real ROM wrapper bytes @0x11A34 in tools/sh2emu.py on the same
     vectors (stubbed callees via the RAM overlay),
  4. run the host C on the same vectors,
  5. compare the whole 53-byte RAM span 0xFFFFD12F..0xFFFFD163 bit-exactly
     (pins dispatch ORDER, CALL COUNT and every store width), and additionally
     assert the emulator-side tail-call invariants: r15 returns to 0xFFFFDF00
     and the PR word pushed at 0xFFFFDEFC is the caller's (0xEEEE0000 = SENT)
     — the jmp+delay-slot-pop signature.

Usage:  python3 harness_calc_lambda_feedback_pid.py [N]  (default N = 20000)
"""
import os
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROM_PATH, load_cpu, make_rng, report, run_oracle  # noqa: E402
from sh2emu import SH2, MASK  # noqa: E402

ADDR = 0x11A34
N_DEFAULT = 20000
SEED = 0x60E1D400

# ---- the 17 dispatched callees, in the ROM's literal-pool order @0x11C60.. ----
DISPATCH = (0x1ACDE, 0x2F51E, 0x3A1CC, 0x2204C, 0x1490E, 0x2766A, 0x16AA8,
            0x3FCE0, 0x32A9C, 0x17F7C, 0x225A2, 0x35B6A, 0x35B96, 0x2971C,
            0x2B0D6, 0x67482, 0x16E6A)

# ---- equivalence-channel cells (test-rig scaffolding, NOT real ROM RAM) ----
SPAN_START = 0xFFFFD12F        # first byte of the seeded / compared span
SPAN_LEN = 53                  # 0xFFFFD12F..0xFFFFD163
LEN_ADDR = 0xFFFFD130          # u8 trace length byte (span offset 1)
TRACE_ADDR = 0xFFFFD140        # u8 trace buffer base (span offset 17)

# ---- emulator-side tail-call invariants ----
R15_INIT = 0xFFFFDF00          # SH2.call()'s stack pointer
PR_WORD = 0xFFFFDEFC           # stack word the wrapper pushes / the tail
                               # call's delay-slot lds.l @r15+,pr pops
SENT = SH2(b'').SENT           # 0xEEEE0000 — the caller's PR under call()

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = os.path.join('/tmp', 'rx8-recon-calc_lambda_feedback_pid')


def make_stub(k, addr):
    """SH-2 stub for dispatch slot k installed at ROM address `addr`.

    Appends k to the trace buffer (see module docstring).  The two PC-relative
    pool loads use `mov.l @(disp,PC)` whose base is ((pc+4) & ~3), so the pool
    is placed at the first 4-aligned byte after the code and the disp fields
    are computed for each callee address (they are 2 mod 4 or 0 mod 4).
    """
    b = bytearray(34)
    b[0] = 0xE4; b[1] = k & 0xFF            # mov #K,r4  (K = slot index)
    pool = (addr + 22 + 3) & ~3             # 4-aligned pool after the code
    b2 = (addr + 6) & ~3                    # mov.l base for the instr @ addr+2
    b4 = (addr + 8) & ~3                    # mov.l base for the instr @ addr+4
    b[2] = 0xD0; b[3] = (pool - b2) // 4    # mov.l @(disp,PC),r0  -> &LEN
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


def build_oracle(cc='cc'):
    """Compile the reconstructed source + its own oracle into /tmp."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_calc_lambda_feedback_pid.c'),
           os.path.join(SAMPLES, 'src', 'rx8_calc_lambda_feedback_pid.c'),
           '-lm', '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def seed(init, addr, n, val):
    """Byte-exact big-endian store of a width-`n` value in the ram overlay."""
    for i in range(n):
        init[addr + i] = (val >> (8 * (n - 1 - i))) & 0xFF


def run_emu(cpu, vec):
    """Seed the span + stack word, install the 17 callee stubs at their real
    ROM addresses, run the REAL wrapper bytes @0x11A34, and return the 53
    post-state span bytes.  Also asserts the tail-call invariants."""
    ram = {}
    for k, a in enumerate(DISPATCH):
        st = make_stub(k, a)
        for i, byte in enumerate(st):
            ram[a + i] = byte
    for off, val in enumerate(vec):
        ram[SPAN_START + off] = val & 0xFF
    seed(ram, PR_WORD, 4, 0x6A6A6A6A)       # garbage pre-state; must become SENT
    cpu.call(ADDR, ram=ram)
    r = cpu.ram
    # Tail-call signature: r15 balanced and the pushed PR restored.
    assert cpu.r[15] == R15_INIT, 'r15 = 0x%08X after call' % cpu.r[15]
    got = ((r.get(PR_WORD, 0) << 24) | (r.get(PR_WORD + 1, 0) << 16)
           | (r.get(PR_WORD + 2, 0) << 8) | r.get(PR_WORD + 3, 0))
    assert got == SENT, 'PR word = 0x%08X, want 0x%08X' % (got, SENT)
    return tuple(r.get(SPAN_START + i, 0) for i in range(SPAN_LEN))


def build_span(len0, pattern):
    """53 pre-state bytes: pattern-filled, with len0 at offset 1 and the two
    bytes next to it pinned as sentinels."""
    s = [pattern & 0xFF] * SPAN_LEN
    s[1] = len0 & 0xFF
    s[0] = 0x5A                             # sentinel left of len
    s[2] = 0xA5                             # sentinel right of len
    return s


def gen_edges():
    """Edge pre-states over the trace length byte (0/1/7/16/17 and the
    sign-extension wrap values 0xFE/0xFF) and distinguishable pre-fills."""
    v = []
    lens = (0x00, 0x01, 0x07, 0x10, 0x11, 0xFE, 0xFF)
    pats = {
        'zero': 0x00,
        'ones': 0xFF,
        'alt': 0xAA,
    }
    for ln in lens:
        for name, pat in pats.items():
            v.append(build_span(ln, pat))
    # Ramp pre-fill with the trace seeded to a distinguishable sequence.
    for ln in lens:
        s = [i & 0xFF for i in range(SPAN_LEN)]
        s[1] = ln & 0xFF
        s[0] = 0x5A
        s[2] = 0xA5
        v.append(s)
    return v


def gen_random(rng, k):
    """k random pre-states.  The length byte is biased to the realistic 0..17
    range with occasional wrap values; the rest of the span is uniform."""
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
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(SEED)

    EDGE = gen_edges()
    vectors = EDGE + gen_random(rng, n)

    # (a) ROM behaviour via the emulator (real wrapper bytes; stubbed callees
    #     via the RAM overlay — the trace IS the dispatch sequence).
    emu = [run_emu(cpu, v) for v in vectors]

    # (b) host-C on the same pre-states (identical stubs, mapped RAM pages).
    lines = ['lambda ' + ' '.join('%02X' % b for b in v) for v in vectors]
    host = []
    for out in run_oracle(oracle, lines):
        host.append(tuple(int(x, 16) for x in out.split()))

    # (c) compare the 53 post-state span bytes byte-for-byte.
    mismatches = []
    for i, (v, e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d len0=%02X ROM=(%s) C=(%s)'
                % (i, v[1],
                   ' '.join('%02X' % x for x in e),
                   ' '.join('%02X' % x for x in h)))
            if len(mismatches) >= 5:
                break

    report('calc_lambda_feedback_pid', ADDR, n, mismatches, edges=len(EDGE))


if __name__ == '__main__':
    main()
