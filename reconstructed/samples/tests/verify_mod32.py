#!/usr/bin/env python3
"""
verify_mod32.py — era-ROM toolchain validation for rx8_mod32_signed @0x4144.

Closes the "ROM -> abstract C -> era-ROM toolchain (gcc 3.4.6)" loop on the
behavioural plane for the Lotto-2 SIGNED 32-BIT REMAINDER helper — the sister
of div32_signed @0x3FE8.

  - reconstructed source : reconstructed/samples/src/rx8_mod32_signed.c
  - verified lift        : c/mod32_signed.c (same range; the div0s/div1
                           remainder counterpart of div32_signed @0x3FE8)
  - ROM convention       : the SAME "broken" r0/r1 argument pair as
                           div32_signed (NOT the r4/r5 ABI):
                               r0 = divisor, r1 = dividend, result in r0.

Methodology (identical to verify_gcc346.py's handling of div32_signed):
  (a) compile the reconstructed source with the era-ROM recipe
      `-m2e -O1 -fomit-frame-pointer` via /home/davide/gcc346-build/gcc/xgcc
      (sh-elf gcc 3.4.6), using the /tmp/verify_gcc346/inc stub headers;
  (b) link at fixed base 0x4000, pulling libgcc 3.4.6 (modulo compiles to
      ___sdivsi3 + mul + sub — the SH-2E has no hardware divide);
  (c) `objcopy --only-section=.text` extracts a self-contained blob;
  (d) load the blob into the same SH-2E emulator (tools/sh2emu.py) at 0x4000;
  (e) generate seeded random vectors + a targeted edge set;
  (f) drive the REAL ROM bytes @0x4144 with the call_regs() step-loop driver
      (r0/r1 in, r0 out) and the gcc-3.4.6 blob with the standard cpu.call()
      (r4/r5 ABI — two different entry conventions, same semantic inputs),
      compare r0;
  (g) additionally compare the blob against a host-gcc oracle of the same C
      (oracle_mod32_signed.c).

Semantics of the div/mod family (verified here and in harness_div32_signed.py /
harness_mod32_signed.py):
  * divisor == 0  -> the ROM stores diag code 0x44E at 0xFFFF7304 and returns
                     r0 = 0.  Modulo keeps this exactly like division.
  * INT32_MIN % -1 -> the non-restoring loop yields remainder 0 (the C99
                     quotient would overflow; the ROM returns 0, NOT the
                     0x80000000 wrap that div32_signed @0x3FE8 produces for
                     INT32_MIN / -1 — a deliberate per-function difference).
  * otherwise: C99 truncation-toward-zero remainder, sign(result) ==
                     sign(dividend), |result| < |divisor|.

The harness is read-only w.r.t. the repo: everything it writes goes to /tmp,
and the exit code is non-zero iff any mismatch is reported.

Usage:  python3 tests/verify_mod32.py [N]   (default N random vectors)
"""
import os
import subprocess
import sys
import time

TESTS = os.path.dirname(os.path.abspath(__file__))   # reconstructed/samples/tests
SAMPLES = os.path.dirname(TESTS)                      # reconstructed/samples
ROOT = os.path.dirname(os.path.dirname(SAMPLES))     # rx8ecu
sys.path.insert(0, TESTS)
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2  # noqa: E402
from common import load_cpu, make_rng  # noqa: E402

# ---- era-ROM toolchain ------------------------------------------------------
XGCC = '/home/davide/gcc346-build/gcc/xgcc'
XGCC_B = '/home/davide/gcc346-build/gcc'
LD = '/usr/bin/sh-elf-ld'
OBJCOPY = '/usr/bin/sh-elf-objcopy'
NM = '/usr/bin/sh-elf-nm'
CC_HOST = os.environ.get('CC', 'cc')
LIBGCC = os.path.join(XGCC_B, 'libgcc.a')   # ___sdivsi3 used by the modulo

STUB_INC = '/tmp/verify_gcc346/inc'         # stub headers (shared, never committed)
WORK = '/tmp/verify_mod32'                  # objects / elf / blob / oracle
LINK_BASE = 0x4000                          # fixed link base

SRC_DIR = os.path.join(SAMPLES, 'src')
INC_DIR = os.path.join(SAMPLES, 'include')

# Function config: ROM @0x4144 (r0/r1 input convention, result r0).
NAME = 'mod32_signed'
SRC = 'rx8_mod32_signed.c'
ENTRY_SYM = 'rx8_mod32_signed'
ADDR_ROM = 0x4144
SEED = 0x4144
N_DEFAULT = 5000

# Stub headers exactly as verify_gcc346.py writes them.
_STDINT = (
    '#ifndef _STDINT_H\n#define _STDINT_H\n'
    'typedef signed char int8_t; typedef unsigned char uint8_t;\n'
    'typedef signed short int16_t; typedef unsigned short uint16_t;\n'
    'typedef signed int int32_t; typedef unsigned int uint32_t;\n'
    'typedef signed long long int64_t; typedef unsigned long long uint64_t;\n'
    'typedef unsigned long uintptr_t; typedef long intptr_t;\n'
    '#define INT8_MIN (-128)\n#define INT16_MIN (-32767-1)\n'
    '#define INT32_MIN (-2147483647-1)\n#define INT64_MIN (-9223372036854775807LL-1)\n'
    '#define INT8_MAX 127\n#define INT16_MAX 32767\n#define INT32_MAX 2147483647\n'
    '#define INT64_MAX 9223372036854775807LL\n'
    '#define UINT8_MAX 255\n#define UINT16_MAX 65535\n'
    '#define UINT32_MAX 4294967295U\n#define UINT64_MAX 18446744073709551615ULL\n'
    '#endif\n')

_MATH = (
    '#ifndef _MATH_H\n#define _MATH_H\n'
    'float fabsf(float x);\n#endif\n')

_LINKER = (
    'OUTPUT_FORMAT(elf32-sh)\n'
    'MEMORY { RAM (rx) : ORIGIN = 0x%X, LENGTH = 0x1000 }\n'
    'SECTIONS {\n'
    '  .text : { *(.text) *(.text.*) *(.rodata) *(.rodata.*) *(.rdata) } > RAM\n'
    '  /DISCARD/ : { *(.comment) *(.note*) *(.symtab) *(.strtab) '
    '*(.shstrtab) *(.debug*) }\n}\n' % LINK_BASE)


def ensure_stubs():
    os.makedirs(STUB_INC, exist_ok=True)
    with open(os.path.join(STUB_INC, 'stdint.h'), 'w') as f:
        f.write(_STDINT)
    with open(os.path.join(STUB_INC, 'math.h'), 'w') as f:
        f.write(_MATH)


def build_blob():
    """Compile src with gcc 3.4.6, link at 0x4000, extract .text blob.

    Returns (blob_bytes, {symbol: linked_absolute_addr})."""
    os.makedirs(WORK, exist_ok=True)
    obj, elf, blb = (os.path.join(WORK, m) for m in
                     ('mod32.o', 'mod32.elf', 'mod32.bin'))

    subprocess.run(
        [XGCC, '-B', XGCC_B, '-m2e', '-O1', '-fomit-frame-pointer',
         '-c', os.path.join(SRC_DIR, SRC), '-o', obj,
         '-I', STUB_INC, '-I', SRC_DIR, '-I', INC_DIR],
        check=True, capture_output=True)

    ld_script = os.path.join(WORK, 'link346.ld')
    if not os.path.exists(ld_script):
        with open(ld_script, 'w') as f:
            f.write(_LINKER)
    # libgcc supplies ___sdivsi3 (the modulo needs the quotient to subtract
    # back; the div0 internal helper rides along) — all cells stay inside the
    # extracted .text, so the blob is self-contained.
    subprocess.run([LD, '-T', ld_script, obj, LIBGCC, '-o', elf],
                   check=True, capture_output=True)
    subprocess.run([OBJCOPY, '-O', 'binary', '--only-section=.text', elf, blb],
                   check=True, capture_output=True)

    with open(blb, 'rb') as f:
        blob_bytes = f.read()
    nm = subprocess.run([NM, elf], capture_output=True, text=True)
    syms = {}
    for line in nm.stdout.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[1] == 'T':
            try:
                syms[parts[2].lstrip('_')] = int(parts[0], 16)
            except ValueError:
                pass
    return blob_bytes, syms


def ram_overlay(blob):
    return {LINK_BASE + i: blob[i] for i in range(len(blob))}


def get_oracle():
    """Build the host oracle (oracle_mod32_signed.c + src) once. Returns path."""
    binp = os.path.join(WORK, 'oracle_mod32')
    if os.path.exists(binp):
        return binp
    subprocess.run(
        [CC_HOST, '-O2', '-Wall', '-Wextra', '-I', INC_DIR, '-I', SRC_DIR,
         os.path.join(TESTS, 'oracle_mod32_signed.c'),
         os.path.join(SRC_DIR, SRC), '-o', binp],
        check=True, capture_output=True)
    return binp


# ============================================================================
# Targeted edge vectors (divisor, dividend) — mapped to r0/r1 on the ROM side
# and r4/r5 on the blob side.  Covers the modulo-specific boundary conditions
# (mirrors harness_mod32_signed.py's EDGE list, keeping every line commented).
# ============================================================================
EDGES = [
    #          divisor,        dividend
    (0x00000000, 0x00000000),   # 0 % 0  (div-by-zero)
    (0x00000001, 0x00000000),   # 0 % 1
    (0x00000000, 0x00000001),   # 1 % 0  (div-by-zero)
    (0x00000001, 0x00000001),   # 1 % 1 = 0
    (0x00000002, 0x00000005),   # 5 % 2 = 1
    (0x00000005, 0x00000011),   # 17 % 5 = 2
    (0x00000007, 0x00000064),   # 100 % 7 = 2
    (0x00000007, 0xFFFFFF9C),   # -100 % 7 = -2 (trunc toward zero)
    (0xFFFFFFF9, 0x00000007),   # 7 % -7 = 0
    (0xFFFFFFFF, 0xFFFFFFFF),   # -1 % -1 = 0
    (0x00000001, 0xFFFFFFFF),   # -1 % 1 = 0
    (0xFFFFFFFF, 0x00000001),   # 1 % -1 = 0
    (0x00000003, 0x00000007),   # 7 % 3 = 1
    (0xFFFFFFFD, 0x00000007),   # 7 % -3 = 1  (trunc toward zero)
    (0x00000003, 0xFFFFFFF9),   # -7 % 3 = -1
    (0xFFFFFFFD, 0xFFFFFFF9),   # -7 % -3 = -1
    (0x7FFFFFFF, 0x00000064),   # 100 % INT32_MAX = 100
    (0x80000000, 0x00000064),   # 100 % INT32_MIN = 100
    (0x00000064, 0x00000000),   # 0 % 100
    (0xFFFFFF9C, 0x00000000),   # 0 % -100
    (0x00010000, 0x0001E240),   # 123456 % 65536
    (0x00000002, 0x80000000),   # INT32_MIN % 2 = 0
    (0xFFFFFFFE, 0x80000000),   # INT32_MIN % -2 = 0
    (0xFFFFFFFF, 0x80000000),   # INT32_MIN % -1 = 0 (the wrap case yields
                                # remainder 0, NOT the 0x80000000 quotient
                                # that div32_signed returns)
    (0x80000000, 0x80000000),   # INT32_MIN % INT32_MIN = 0
    (0x00000000, 0x00000064),   # div-by-zero -> 0
    (0x80000000, 0x7FFFFFFF),   # INT32_MAX % INT32_MIN = INT32_MAX
    (0x7FFFFFFF, 0x80000000),   # INT32_MIN % INT32_MAX = -1
    (0x40000000, 0xC0000000),   # C0000000 % 40000000 = 0
    (0xABCDEF01, 0x12345678),
    (0xDEADBEEF, 0xCAFEBABE),
]


def gen_vectors(n):
    rng = make_rng(SEED)
    vecs = list(EDGES) + [(rng.getrandbits(32), rng.getrandbits(32))
                          for _ in range(n)]
    return vecs


# ============================================================================
# Evaluation drivers
# ============================================================================
def call_regs(cpu, entry, r0=0, r1=0):
    """Run the ROM leaf whose args arrive in r0/r1, result in r0.

    Mirrors the r0/r1 driver of harness_div32_signed.py / harness_mod32_signed.py:
    reset state, seed r0/r1, place the SENTINEL in pr as the rts target, then
    single-step until rts.  Only the ROM side needs this — the gcc-3.4.6 blob
    compiles the same C with the standard r4/r5 ABI and is driven by cpu.call."""
    cpu.ram = {}
    cpu.r = [0] * 16
    cpu.r[0] = r0 & 0xFFFFFFFF
    cpu.r[1] = r1 & 0xFFFFFFFF
    cpu.r[15] = 0xFFFFDF00
    cpu.fr = [0.0] * 16
    cpu.pr = cpu.SENT
    cpu.T = 0
    cpu.macl = 0
    cpu.mach = 0
    cpu.gbr = 0
    cpu.fpul = 0
    cpu.fpscr = 0
    cpu.pc = entry & 0xFFFFFFFF
    steps = 0
    while True:
        if cpu.pc == cpu.SENT:
            return cpu.r[0] & 0xFFFFFFFF
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


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    ensure_stubs()

    blob, syms = build_blob()
    entry = syms.get(ENTRY_SYM, LINK_BASE)
    base = ram_overlay(blob)
    cpu = load_cpu()                 # ROM emulator (call_regs resets state)

    vecs = gen_vectors(n)
    t0 = time.time()

    # (1) ROM side: non-ABI r0/r1 register images via the step-loop driver.
    rom_res = [call_regs(cpu, ADDR_ROM, r0=d, r1=v) for d, v in vecs]
    # (2) blob side: the same C compiled by gcc 3.4.6 uses the standard r4/r5
    #     ABI, so cpu.call(r4=, r5=) covers it.
    blb_res = [cpu.call(entry, r4=d, r5=v, ram=dict(base)) for d, v in vecs]

    # (3) host oracle vs blob (cross-check of the era-ROM codegen itself).
    ob = None
    lines = ['mod %08X %08X' % (d, v) for d, v in vecs]
    proc = subprocess.run([get_oracle()], input='\n'.join(lines) + '\n',
                          capture_output=True, text=True)
    if proc.returncode != 0:
        print('    (host oracle failed: %s)' % proc.stderr.strip())
    else:
        outs = [int(x, 16) for x in proc.stdout.splitlines()]
        if len(outs) == len(blb_res):
            ob = sum(1 for h, o in zip(blb_res, outs) if h != o)

    rb = 0
    samples = []
    for i, (e, b) in enumerate(zip(rom_res, blb_res)):
        if e != b:
            rb += 1
            if len(samples) < 5:
                d, v = vecs[i]
                samples.append('vec#%d divisor=0x%08X dividend=0x%08X '
                               'ROM(r0)=0x%08X blob=0x%08X'
                               % (i, d, v, e, b))

    dt = time.time() - t0
    status = 'OK  ' if rb == 0 and not ob else 'FAIL'
    print('%s %-22s @0x%-6X  n=%-6d  ROM-vs-blob=%-4d  oracle-vs-blob=%-4s  '
          'edges=%d  %.2fs'
          % (status, NAME, ADDR_ROM, len(vecs), rb,
             ob if ob is not None else '-', len(EDGES), dt))
    for s in samples:
        print('        ' + s)

    total = rb + (ob or 0)
    if total:
        print('\nverify_mod32: %d mismatch(es) — FAIL' % total)
        sys.exit(1)
    print('\nverify_mod32: rx8_mod32_signed @0x4144 OK (0 mismatch; ROM == '
          'gcc-3.4.6 blob == host oracle)')


if __name__ == '__main__':
    main()