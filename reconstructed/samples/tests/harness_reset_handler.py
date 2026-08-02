#!/usr/bin/env python3
"""
harness_reset_handler.py — equivalence of rx8_reset_handler @0x4E0.

Reconstructed source: samples/src/rx8_reset_handler.c
Lift (truth): c/reset_handler.c (the ROM bytes @0x4E0 are executed for real
              here via tools/sh2emu.py).

The ROM function is the primary reset entry of the RTOS application:
  1. watchdog reset            (bsr 0x572);
  2. three hardware-init leaves (jsr 0x170 / 0x41C / 0x3D4);
  3. cold vs warm start detection from the r4 flag and the boot magic
     0x5AA5A55A at 0xFFFFDFFC;
  4. watchdog-induced-reset recovery by reading the reset-vector cells
     0x7FFFC / 0x7FFF8 / 0x1000 (retry loop over checkWatchdog @0x5B0);
  5. stamp the boot magic, then tail-jump through the 0x40 trampoline
     (vector_trampoline_set_sp) with r4 = the chosen reset vector.

The equivalence check compares, bit-exactly:

  - emulator side: install RAM-overlay stubs for the deep leaves (0x572,
    0x170, 0x41C, 0x3D4 = trace-and-return; 0x5B0 = stateful checkWatchdog
    with a per-call counter and the seeded two-step return sequence;
    0x8F6 = warm-start trace; 0x40 = terminal trampoline jumping to the
    emulator SENT constant), seed the cells [0xFFFFDFFC] / [0x7FFFC] +
    its deref target / [0x7FFF8] / [0x1000], then call the ROM entry @0x4E0
    with r4=cold_start, r5=reason and read back the 14 observable tokens
    (ret + 10 trace dwords + magic + reason + wdt counter);
  - host side: the dedicated oracle (tests/oracle_reset_handler.c) mmap()s
    the same pages, seeds the same cells through the module-state accessors,
    runs the reconstructed C and prints the same 14 tokens.

EDGE vectors cover both start flavours, magic match/mismatch, the 0x7FFFC
read/deref matrix (-1 vs valid), the 0x1000 / 0x7FFF8 alternates, the full
checkWatchdog return sequences (0 / non-zero) and the retry-loop exit
conditions; N random vectors follow (fixed seed 0x60E1D400, 50/50 cold/warm
cold_start, biased magic / wdt cells so every branch is hit).

Usage:  python3 harness_reset_handler.py [N]   (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROM_PATH, make_rng, report, run_oracle  # noqa: E402
from sh2emu import SH2, MASK  # noqa: E402

ADDR = 0x4E0
N_DEFAULT = 20000
SEED = 0x60E1D400

SENT = 0xEEEE0000

TRACE_BASE = 0xFFFFE000
WDT_CNT = 0xFFFFD100
MAGIC_LOC = 0xFFFFDFFC
REASON_LOC = 0xFFFFDFA8
MAGIC_VAL = 0x5AA5A55A

# Stub bodies (addresses inside ROM regions that the reset path never uses for
# anything but these leaves — the RAM overlay hides the real bytes).
TRACE = {0x572: (0xFFFFE000, 0x00000572), 0x170: (0xFFFFE010, 0x00000170),
         0x41C: (0xFFFFE020, 0x0000041C), 0x3D4: (0xFFFFE030, 0x000003D4)}


def put16(ram, addr, word):
    ram[addr & MASK] = (word >> 8) & 0xFF
    ram[(addr + 1) & MASK] = word & 0xFF


def put32(ram, addr, val):
    ram[addr & MASK] = (val >> 24) & 0xFF
    ram[(addr + 1) & MASK] = (val >> 16) & 0xFF
    ram[(addr + 2) & MASK] = (val >> 8) & 0xFF
    ram[(addr + 3) & MASK] = val & 0xFF


def get32(ram, addr):
    return sum(ram.get((addr + i) & MASK, 0) << (24 - 8 * i) for i in range(4))


# ---------------------------------------------------------------------------
#  Stub assembler — opcode forms validated against sh2emu.py's decoder:
#    0xD000|(reg<<8)|disp : mov.l @(disp*4,pc),reg      (disp in 4-byte units)
#    0xE00r               : mov #0,r
#    0x6000|n<<8|m<<4|2   : mov.l @rm,rn                 (n = dest, m = src)
#    0x2000|n<<8|m<<4|2   : mov.l rm,@rn                 (n = addr, m = val)
#    0x7000|n<<8|imm      : add #imm,rn
#    0x8800|imm           : cmp/eq #imm,r0
#    0x8900|disp          : bt disp (disp*2 from pc+4)
#    0x000B / 0x0009      : rts / nop
#    0x402B / 0x0009      : jmp @r0 (delay) / nop
# ---------------------------------------------------------------------------
def trace_stub(ram, body, cell, tag):
    """write [cell] = tag ; rts  (uses only r0/r1; pool right after the code)."""
    pool = (body + 10 + 3) & ~3
    disp1 = (pool + 4 - ((body + 4) & ~3)) // 4   # tag slot
    disp0 = (pool + 0 - ((body + 6) & ~3)) // 4   # cell slot
    words = [0xD100 | disp1, 0xD000 | disp0, 0x2012, 0x000B, 0x0009]
    for i, w in enumerate(words):
        put16(ram, body + 2 * i, w)
    put32(ram, pool + 0, cell)
    put32(ram, pool + 4, tag)


def wdt_stub(ram):
    """checkWatchdog @0x5B0: count++ -> [0xFFFFD100]; trace tag+count at
    0xFFFFE040/44; return [0x5EC]=wdt0 on count 1, [0x5F0]=wdt1 on count 2,
    0 afterwards.  Values are patched directly into the pool by build_ram."""
    body = 0x5B0
    words = [
        0xD10B, 0x6012, 0x7001, 0x2102,     # r1=&cnt; r0=cnt; cnt+1; [cnt]=r0
        0xD20A, 0xD30B, 0x2232, 0x7204, 0x2202,  # r2=trace; r3=tag; store; +4; cnt
        0x8801, 0x8904, 0x8802, 0x8905,     # cmp#1/bt 0x5D0 ; cmp#2/bt 0x5D6
        0xE000, 0x000B, 0x0009,             # default 0 ; rts
        0xD006, 0x000B, 0x0009,             # wdt0 path (load 0x5EC) ; rts
        0xD006, 0x000B, 0x0009,             # wdt1 path (load 0x5F0) ; rts
    ]
    for i, w in enumerate(words):
        put16(ram, body + 2 * i, w)
    put32(ram, 0x5E0, WDT_CNT)
    put32(ram, 0x5E4, TRACE_BASE + 0x40)
    put32(ram, 0x5E8, 0x000005B0)


def warm_stub(ram):
    """0x8F6 warm-start leaf: [0xFFFFE050]=0x8F6, [0xFFFFE054]=r4 (cold_start)."""
    body = 0x8F6
    words = [0xD104, 0xD204, 0x2212, 0x6143, 0x7204, 0x2212, 0x000B, 0x0009]
    for i, w in enumerate(words):
        put16(ram, body + 2 * i, w)
    put32(ram, 0x908, 0x000008F6)
    put32(ram, 0x90C, TRACE_BASE + 0x50)


def term_stub(ram):
    """0x40 terminal trampoline: [0xFFFFE060]=0x40, [0xFFFFE064]=r4 (rv),
    r0=SENT ; jmp @r0  (so the emulator call returns SENT = 0xEEEE0000)."""
    body = 0x40
    words = [0xD103, 0xD004, 0x2012, 0xD004, 0x2042, 0xD004, 0x402B, 0x0009]
    for i, w in enumerate(words):
        put16(ram, body + 2 * i, w)
    put32(ram, 0x50, 0x00000040)
    put32(ram, 0x54, TRACE_BASE + 0x60)
    put32(ram, 0x58, TRACE_BASE + 0x64)
    put32(ram, 0x5C, SENT)


def build_ram(cold, reason, magic, w7fffc, wderef, alt1000, w7fff8, wdt0, wdt1):
    ram = {}
    for body, (cell, tag) in TRACE.items():
        trace_stub(ram, body, cell, tag)
    wdt_stub(ram)
    warm_stub(ram)
    term_stub(ram)
    # seed the state cells (the ROM reads/writes these for real)
    put32(ram, MAGIC_LOC, magic)
    put32(ram, WDT_CNT, 0)
    put32(ram, 0x7FFFC, w7fffc)
    put32(ram, 0x7FFF8, w7fff8)
    put32(ram, 0x1000, alt1000)
    put32(ram, w7fffc & MASK, wderef)     # **0x7FFFC deref target
    put32(ram, 0x5EC, wdt0)               # wdt stub pool: return on call 1
    put32(ram, 0x5F0, wdt1)               # wdt stub pool: return on call 2
    put32(ram, REASON_LOC, 0)             # reason byte cleared (byte @DFA8)
    # clear the trace cells
    for a in range(TRACE_BASE, TRACE_BASE + 0x100, 4):
        put32(ram, a, 0)
    return ram


def run_reset(cpu, cold, reason, magic, w7fffc, wderef, alt1000, w7fff8,
              wdt0, wdt1):
    ram = build_ram(cold, reason, magic, w7fffc, wderef, alt1000, w7fff8,
                    wdt0, wdt1)
    ret = cpu.call(ADDR, r4=cold & MASK, r5=reason & MASK, ram=ram)
    cells = [ret,
             get32(cpu.ram, TRACE_BASE + 0x00), get32(cpu.ram, TRACE_BASE + 0x10),
             get32(cpu.ram, TRACE_BASE + 0x20), get32(cpu.ram, TRACE_BASE + 0x30),
             get32(cpu.ram, TRACE_BASE + 0x40), get32(cpu.ram, TRACE_BASE + 0x44),
             get32(cpu.ram, TRACE_BASE + 0x50), get32(cpu.ram, TRACE_BASE + 0x54),
             get32(cpu.ram, TRACE_BASE + 0x60), get32(cpu.ram, TRACE_BASE + 0x64),
             get32(cpu.ram, MAGIC_LOC), get32(cpu.ram, REASON_LOC),
             get32(cpu.ram, WDT_CNT)]
    return cells


BUILD_DIR = os.path.join('/tmp', 'rx8-recon-reset_handler')


def build_oracle(cc='cc'):
    samples = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(samples, 'include'),
           '-I', os.path.join(samples, 'src'),
           os.path.join(samples, 'tests', 'oracle_reset_handler.c'),
           os.path.join(samples, 'src', 'rx8_reset_handler.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    with open(ROM_PATH, 'rb') as f:
        cpu = SH2(f.read())
    oracle = build_oracle()

    # ---- EDGE vectors: every branch of the recovery matrix -----------------
    EDGE = [
        # cold, reason, magic,   w7fffc,    wderef,    alt1000,   w7fff8,   wdt0, wdt1
        # cold path, magic match, deref ok -> rv = *0x1000
        (0x00000000, 0x00, 0x5AA5A55A, 0x00002000, 0x00001234, 0x000012B4, 0x0000D49C, 0x00000000, 0x00000000),
        # cold, magic match, deref ok, alt == -1 -> rv = *0x7FFF8
        (0x00000000, 0x00, 0x5AA5A55A, 0x00002000, 0x00001234, 0xFFFFFFFF, 0x0000D49C, 0x00000000, 0x00000000),
        # cold, magic match, *0x7FFFC == -1, wdt0 == 0 -> default rv
        (0x00000000, 0x00, 0x5AA5A55A, 0xFFFFFFFF, 0x00001234, 0x000012B4, 0x0000D49C, 0x00000000, 0x00000000),
        # cold, magic match, *0x7FFFC == -1, wdt0 != 0, alt ok -> rv = alt
        (0x00000000, 0x00, 0x5AA5A55A, 0xFFFFFFFF, 0x00001234, 0x00003000, 0x0000D49C, 0x00000005, 0x00000000),
        # cold, magic match, *0x7FFFC == -1, alt == -1 -> retry -> wdt1 == 0 -> default
        (0x00000000, 0x00, 0x5AA5A55A, 0xFFFFFFFF, 0x00001234, 0xFFFFFFFF, 0x0000D49C, 0x00000005, 0x00000000),
        # cold, magic match, *0x7FFFC ok, deref == -1 -> loop -> wdt0 == 0 -> default
        (0x00000000, 0x00, 0x5AA5A55A, 0x00002000, 0xFFFFFFFF, 0x000012B4, 0x0000D49C, 0x00000000, 0x00000000),
        # cold, magic mismatch, wdt0 == 0 -> genuine cold start, default rv
        (0x00000000, 0x00, 0x00000000, 0x00002000, 0x00001234, 0x000012B4, 0x0000D49C, 0x00000000, 0x00000000),
        # cold, magic mismatch, wdt0 != 0 -> recovered, deref == -1 -> loop
        (0x00000000, 0x00, 0x00000000, 0x00002000, 0xFFFFFFFF, 0x000012B4, 0x0000D49C, 0x00000003, 0x00000000),
        # warm start (cold == 1): reason stored, default rv
        (0x00000001, 0x5A, 0x00000000, 0x00002000, 0x00001234, 0x000012B4, 0x0000D49C, 0x00000000, 0x00000000),
        # warm start with negative cold_start (sign-extended r4), reason FF
        (0x80000000, 0xFF, 0x00000000, 0x00002000, 0x00001234, 0x000012B4, 0x0000D49C, 0x00000000, 0x00000000),
        # cold, magic match, high deref address -> deref ok -> rv = alt
        (0x00000000, 0x00, 0x5AA5A55A, 0xFFFFD200, 0x00005AA5, 0x00001111, 0x0000D49C, 0x00000000, 0x00000000),
        # cold, magic match, *0x7FFFC == 0, deref == -1 -> loop until wdt runs dry
        (0x00000000, 0x00, 0x5AA5A55A, 0x00000000, 0xFFFFFFFF, 0xFFFFFFFF, 0x0000D49C, 0x00000005, 0x00000003),
        # cold, magic match, deref ok, alt == -1 -> rv = *0x7FFF8
        (0x00000000, 0x00, 0x5AA5A55A, 0x00000001, 0x00000000, 0xFFFFFFFF, 0x0000D49C, 0x00000000, 0x00000000),
        # cold, magic mismatch, wdt0 != 0, *0x7FFFC == -1 -> loop -> alt ok
        (0x00000000, 0x00, 0x00000000, 0xFFFFFFFF, 0x00001234, 0x00002000, 0x0000D49C, 0x00000005, 0x00000007),
    ]

    rng = make_rng(SEED)
    vecs = list(EDGE)
    for _ in range(n):
        # 50/50 cold/warm; magic biased toward the "match" side so the
        # recovery block is exercised; wdt cells biased toward the non-zero
        # side so the retry loop is exercised.
        cold = rng.getrandbits(1)
        magic = 0x5AA5A55A if rng.getrandbits(1) else rng.getrandbits(32)
        w7fffc = 0xFFFFFFFF if rng.getrandbits(1) else rng.getrandbits(32)
        wderef = 0xFFFFFFFF if rng.getrandbits(1) else rng.getrandbits(32)
        alt1000 = 0xFFFFFFFF if rng.getrandbits(1) else rng.getrandbits(32)
        vecs.append((cold, rng.randrange(0x100), magic, w7fffc, wderef,
                     alt1000, rng.getrandbits(32),
                     rng.getrandbits(32) | 1, rng.getrandbits(32) | 1))

    emu = [run_reset(cpu, *v) for v in vecs]
    lines = ['rh %08X %02X %08X %08X %08X %08X %08X %08X %08X' % v
             for v in vecs]
    host = [[int(x, 16) for x in o.split()] for o in run_oracle(oracle, lines)]

    mm = []
    for k, (v, e, h) in enumerate(zip(vecs, emu, host)):
        if e != h:
            mm.append('vec#%d cold=%08X reason=%02X magic=%08X w7fffc=%08X '
                      'wderef=%08X alt1000=%08X w7fff8=%08X wdt0=%08X wdt1=%08X\n'
                      '      ROM=%s\n      C  =%s'
                      % (k, v[0], v[1], v[2], v[3], v[4], v[5], v[6], v[7],
                         v[8], ' '.join('%08X' % x for x in e),
                         ' '.join('%08X' % x for x in h)))
            if len(mm) >= 5:
                break
    report('reset_handler', ADDR, n, mm, edges=len(EDGE))


if __name__ == '__main__':
    main()
