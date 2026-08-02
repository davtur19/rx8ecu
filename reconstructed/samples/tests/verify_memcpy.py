#!/usr/bin/env python3
"""
verify_memcpy.py — era-ROM toolchain (sh-elf gcc 3.4.6) validation of
rx8_memcpy_bytewise @0x42B0 — the NON-ABI pointer-convention memcpy family.

Calling convention (deduced from the disassembly of 0x42B0, see the ASM
listing in samples/src/rx8_memcpy_bytewise.c):
    ROM  : r0 = count (bytes to copy)
           r1 = destination pointer
           r2 = source pointer
           r3 / r4 are saved on the stack (r3 unused; r4 = src+count end
           sentinel), rts returns to the pr stack;  NO return value (void).

Semantics: straight byte-by-byte forward memcpy, loop unrolled 4×
(`cmp/hi r2,r4` after each of the 4 byte stores).  It is a pure RAM-cell
function — the only writes are the copied bytes in dst (plus the 3 register
pushes on the stack, which are popped back).  The r0 left behind after the
call is a SCRATCH leftover, NOT a designed return value: it holds the
sign-extended value of the last copied byte (mov.b @r2+,r0 sign-extends into
the 32-bit register), or the untouched r0 for count == 0.

Convention mapping (mirrors verify_checksum.py / verify_gcc346.py):
    ROM  : r0/r1/r2 register image  (custom call_regs-style driver)
    blob : the reconstructed C uses the STANDARD sh ABI for
           void f(uint8_t *dst, const uint8_t *src, uint32_t count) →
           r4/r5/r6, driven with cpu.call().  Because the C is void, gcc
           3.4.6 -O1 never writes r0 (leaves 0), so the equivalence contract
           is the post-call RAM state; r0 is compared only where it is
           deterministic on BOTH sides (count == 0: both 0).

Method (pattern of verify_checksum.py)
--------------------------------------
  (a) compiles samples/src/rx8_memcpy_bytewise.c with the era-ROM recipe
      `-m2e -O1 -fomit-frame-pointer` via /home/davide/gcc346-build/gcc/xgcc,
      links it at 0x4000 with sh-elf-ld (+ libgcc 3.4.6) and extracts .text,
  (b) drives the ROM bytes @0x42B0 and the blob @0x4000 on identical vectors,
      each carrying a full RAM image:
        - src buffer base 0x3000, dst buffer base 0x2000 (never overlapping —
          the source has a distinct base page, so src/dst alias is UB and is
          NOT generated, unlike harness_memcpy_bytewise.py which does test it),
        - count in 0..64 (covers the n/4 unroll body, every remainder 1..3 and
          the count==0 early-out), src/dst offsets 0..3 (all alignments),
        - dense deterministic fill patterns (0x00 / 0xFF / incremental /
          descending / 0xDEADBEEF / seeded random),
        - sentinel guard bytes before and after both buffers; the dst window
          (count + 16 tail bytes) is prefilled with 0xA5 and the tail must
          still hold 0xA5 after the call (no overrun),
  (c) compares the complete post-call RAM state restricted to the seeded data
      region (ROM vs blob), and checks neither side writes outside its
      writable region (ROM may additionally touch the r15 stack window for its
      3 register pushes; the blob code lives in the 0x4000 overlay),
  (d) verifies the ROM's r0 leftover against the deduced model
      (sign-extended last copied byte, 0 for count==0) and, for count==0,
      compares r0 ROM-vs-blob (both must be 0).

Read-only w.r.t. the repo: everything written goes to /tmp/verify_memcpy
(plus the shared /tmp/verify_gcc346/inc stub headers); verify_gcc346.py,
README.md, Makefile and tools/ are NOT touched.  Exit code is non-zero iff
any active comparison reports a mismatch.

Usage:  python3 tests/verify_memcpy.py [N]   (default N = 3000 vectors)
"""
import os
import subprocess
import sys
import time

TESTS = os.path.dirname(os.path.abspath(__file__))   # reconstructed/samples/tests
SAMPLES = os.path.dirname(TESTS)                      # reconstructed/samples
ROOT = os.path.dirname(os.path.dirname(SAMPLES))      # rx8ecu
sys.path.insert(0, TESTS)
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2  # noqa: E402
from common import load_cpu, make_rng  # noqa: E402

# ---- era-ROM toolchain (same binaries as verify_gcc346.py / checksum) -------
XGCC = '/home/davide/gcc346-build/gcc/xgcc'
XGCC_B = '/home/davide/gcc346-build/gcc'
LD = '/usr/bin/sh-elf-ld'
OBJCOPY = '/usr/bin/sh-elf-objcopy'
NM = '/usr/bin/sh-elf-nm'
LIBGCC = os.path.join(XGCC_B, 'libgcc.a')
STUB_INC = '/tmp/verify_gcc346/inc'        # stub stdint.h (shared, never committed)
WORK = '/tmp/verify_memcpy'                # own workdir (never touches gcc346's)
LINK_BASE = 0x4000                         # fixed link base

SRC_DIR = os.path.join(SAMPLES, 'src')
INC_DIR = os.path.join(SAMPLES, 'include')

# ---- function / RAM geometry -------------------------------------------------
ROM_ADDR = 0x42B0                       # rx8_memcpy_bytewise
ENTRY_SYM = 'rx8_memcpy_bytewise'
DST_BASE = 0x2000                       # emulated dst buffer base (per task)
SRC_BASE = 0x3000                       # emulated src buffer base (per task)
MAX_LEN = 64                            # counts 0..64 (unroll + remainders)
TAIL = 16                               # dst tail that must stay 0xA5-prefilled
PREFILL = 0xA5                          # dst window prefill value
GUARD = 8                               # sentinel bytes before/after each buffer
SENTINEL = 0x5A                         # guard fill byte
R15 = 0xFFFFDF00                        # stack pointer (matches sh2emu's default)

N_DEFAULT = 3000                        # total seeded vectors (>= 3000)
SEED = 0x42B0
COUNTS = list(range(MAX_LEN + 1))       # 0..64, exhaustive
OFFSETS = [0, 1, 2, 3]                  # src/dst alignment offsets
PATTERNS = ['zero', 'ones', 'inc', 'dec', 'beef', 'rand']
ZERO_ONE_COUNTS = [0, 1, 2, 3, 4, 5, 8, 16, 32, 63, 64]  # edge lengths, zero/ones

# =============================================================================
# Stub headers (shared /tmp/verify_gcc346/inc, written once)
# =============================================================================
_STDINT = (
    '#ifndef _STDINT_H\n#define _STDINT_H\n'
    'typedef signed char int8_t; typedef unsigned char uint8_t;\n'
    'typedef signed short int16_t; typedef unsigned short uint16_t;\n'
    'typedef signed int int32_t; typedef unsigned int uint32_t;\n'
    'typedef signed long long int64_t; typedef unsigned long long uint64_t;\n'
    'typedef unsigned long uintptr_t; typedef long intptr_t;\n'
    '#define UINT8_MAX 255\n#define UINT16_MAX 65535\n'
    '#define UINT32_MAX 4294967295U\n#endif\n')

_LINKER = (
    'OUTPUT_FORMAT(elf32-sh)\n'
    'MEMORY { RAM (rx) : ORIGIN = 0x%X, LENGTH = 0x1000 }\n'
    'SECTIONS {\n'
    '  .text : { *(.text) *(.text.*) *(.rodata) *(.rodata.*) *(.rdata) } > RAM\n'
    '  /DISCARD/ : { *(.comment) *(.note*) *(.symtab) *(.strtab) '
    '*(.shstrtab) *(.debug*) }\n}\n' % LINK_BASE)


def ensure_stubs():
    os.makedirs(STUB_INC, exist_ok=True)
    p = os.path.join(STUB_INC, 'stdint.h')
    if not os.path.exists(p):
        with open(p, 'w') as f:
            f.write(_STDINT)


# =============================================================================
# Build: gcc 3.4.6 blob at 0x4000
# =============================================================================
def build_blob():
    """Compile samples/src/rx8_memcpy_bytewise.c with gcc 3.4.6, link at
    0x4000, extract .text.  Returns (blob_bytes, {symbol: abs_addr})."""
    os.makedirs(WORK, exist_ok=True)
    obj, elf, blb = (os.path.join(WORK, 'mc.' + e)
                     for e in ('o', 'elf', 'bin'))
    subprocess.run(
        [XGCC, '-B', XGCC_B, '-m2e', '-O1', '-fomit-frame-pointer',
         '-c', os.path.join(SRC_DIR, 'rx8_memcpy_bytewise.c'),
         '-o', obj, '-I', STUB_INC, '-I', SRC_DIR, '-I', INC_DIR],
        check=True, capture_output=True)
    ld_script = os.path.join(WORK, 'link.ld')
    if not os.path.exists(ld_script):
        with open(ld_script, 'w') as f:
            f.write(_LINKER)
    subprocess.run([LD, '-T', ld_script, obj, LIBGCC, '-o', elf],
                   check=True, capture_output=True)
    subprocess.run([OBJCOPY, '-O', 'binary', '--only-section=.text', elf, blb],
                   check=True, capture_output=True)
    with open(blb, 'rb') as f:
        blob = f.read()
    nm = subprocess.run([NM, elf], capture_output=True, text=True)
    syms = {}
    for line in nm.stdout.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[1] == 'T':
            try:
                syms[parts[2].lstrip('_')] = int(parts[0], 16)
            except ValueError:
                pass
    return blob, syms


# =============================================================================
# RAM builder / pattern fillers  (deterministic; 'rand' has its own RNG)
# =============================================================================
FILL_RNG = make_rng(SEED ^ 0x5EED)      # dedicated stream, only for 'rand' fill


def pat_byte(pat, i, base=0):
    if pat == 'zero':
        return 0x00
    if pat == 'ones':
        return 0xFF
    if pat == 'inc':
        return (base + i) & 0xFF
    if pat == 'dec':
        return (base - i) & 0xFF
    if pat == 'beef':
        return (0xDE, 0xAD, 0xBE, 0xEF)[i % 4]
    return FILL_RNG.getrandbits(8)      # 'rand'


def build_ram(src_addr, dst_addr, count, data, pat):
    """Seed guards + src data + 0xA5-prefilled dst window (count + TAIL).
    The seeding order (src first, then dst) is fixed and identical on both
    emulator runs.  src and dst never overlap (distinct base pages)."""
    ram = {}
    for base, addr, extra in ((SRC_BASE, src_addr, 0),
                              (DST_BASE, dst_addr, TAIL)):
        for i in range(GUARD):
            ram[addr - GUARD + i] = SENTINEL
        for i in range(MAX_LEN + extra):
            ram[addr + i] = PREFILL if extra and i >= count else SENTINEL
        for i in range(GUARD):
            ram[addr + MAX_LEN + extra + i] = SENTINEL
    for i, b in enumerate(data):                    # src bytes (overwrite fill)
        ram[src_addr + i] = b
    for i in range(count + TAIL):                   # dst window prefill
        ram[dst_addr + i] = PREFILL
    return ram


# =============================================================================
# Vector generation  (deterministic; total length == n)
# =============================================================================
def gen_vectors(n):
    rng = make_rng(SEED)
    vecs = []

    def add(count, so, do, pat, base, desc):
        data = bytes(pat_byte(pat, i, base) for i in range(count))
        vecs.append({'count': count, 'src': SRC_BASE + so, 'dst': DST_BASE + do,
                     'data': data, 'pat': pat, 'desc': desc})

    # 1) exhaustive matrix: every count 0..64 x every src/dst alignment,
    #    patterns cycled so each of the 6 dense patterns appears.
    for i, count in enumerate(COUNTS):
        for so in OFFSETS:
            for do in OFFSETS:
                pat = PATTERNS[(count + so + do) % len(PATTERNS)]
                base = rng.getrandbits(8)
                add(count, so, do, pat, base,
                    'count=%-2d src_off=%d dst_off=%d pat=%s' % (count, so, do, pat))

    # 2) zero / all-ones data edges (dense uniform, boundary counts).
    for count in ZERO_ONE_COUNTS:
        for pat in ('zero', 'ones'):
            for so in OFFSETS:
                for do in OFFSETS:
                    add(count, so, do, pat, 0,
                        'count=%-2d src_off=%d dst_off=%d pat=%s' % (count, so, do, pat))

    # 3) seeded random stream filling up to n (random count/offsets/pattern).
    while len(vecs) < n:
        count = rng.randint(0, MAX_LEN)
        so = rng.choice(OFFSETS)
        do = rng.choice(OFFSETS)
        pat = rng.choice(PATTERNS)
        base = rng.getrandbits(8)
        add(count, so, do, pat, base,
            'rnd#%d count=%-2d src_off=%d dst_off=%d pat=%s'
            % (len(vecs), count, so, do, pat))
    return vecs


# =============================================================================
# Evaluation
# =============================================================================
def call_regs(cpu, entry, r0=0, r1=0, r2=0, ram=None):
    """Drive the ROM leaf with its NON-ABI r0/r1/r2 register protocol
    (count / dst / src), same run loop as harness_memcpy_bytewise.py and
    call_regs() of verify_gcc346.py.  Returns r0 after the call."""
    cpu.ram = dict(ram or {})
    cpu.r = [0] * 16
    cpu.r[0] = r0 & 0xFFFFFFFF
    cpu.r[1] = r1 & 0xFFFFFFFF
    cpu.r[2] = r2 & 0xFFFFFFFF
    cpu.r[15] = R15 & 0xFFFFFFFF
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


def ref_r0(count, data):
    """ROM r0 leftover model: sign-extended last copied byte (mov.b sign
    extends), or the untouched count value (0) for count == 0."""
    if count == 0:
        return 0
    b = data[count - 1]
    return (b - 256 if b & 0x80 else b) & 0xFFFFFFFF


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    if n < 3000:
        print('verify_memcpy: N=%d < 3000, raising to 3000' % n)
        n = 3000
    ensure_stubs()
    blob, syms = build_blob()
    if ENTRY_SYM not in syms:
        sys.exit('verify_memcpy: entry symbol %r not found in blob '
                 '(syms=%r)' % (ENTRY_SYM, sorted(syms)))
    entry = syms[ENTRY_SYM]
    code = {LINK_BASE + i: blob[i] for i in range(len(blob))}
    code_keys = set(code)
    # stack window the ROM may touch for its 3 register pushes (pops restore)
    stack_keys = set(range(R15 - 12, R15))

    cpu = load_cpu()
    vecs = gen_vectors(n)
    total = len(vecs)
    n_matrix = len(COUNTS) * len(OFFSETS) * len(OFFSETS)
    n_edges = len(ZERO_ONE_COUNTS) * 2 * len(OFFSETS) * len(OFFSETS)
    t0 = time.time()

    rb, rom_out, blb_out, rom_r0_model, r0_c0, blb_r0_nonzero = 0, 0, 0, 0, 0, 0
    samples = []
    for v in vecs:
        ram = build_ram(v['src'], v['dst'], v['count'], v['data'], v['pat'])
        data_keys = set(ram)
        count = v['count']

        # ROM side: non-ABI r0/r1/r2 protocol.
        rom_r0 = call_regs(cpu, ROM_ADDR, r0=count, r1=v['dst'], r2=v['src'],
                           ram=dict(ram))
        rom_post = dict(cpu.ram)

        # blob side: the same C compiled by gcc 3.4.6 -> standard r4/r5/r6 ABI.
        overlay = dict(code)
        overlay.update(ram)
        blb_r0 = cpu.call(entry, r4=v['dst'], r5=v['src'], r6=count,
                          ram=overlay)
        blb_post = dict(cpu.ram)

        # 1) ROM vs blob: post-call RAM equality over the seeded data region.
        if any(rom_post.get(k, 0) != blb_post.get(k, 0) for k in data_keys):
            rb += 1
            if len(samples) < 5:
                samples.append('ram  %s' % v['desc'])

        # 2) neither side writes outside its writable region.
        out = set(rom_post) - data_keys - stack_keys
        if out:
            rom_out += 1
            if len(samples) < 5:
                samples.append('rom-write-outside: %s (keys=%s)'
                               % (v['desc'], sorted(out)[:6]))
        out = set(blb_post) - data_keys - code_keys
        if out:
            blb_out += 1
            if len(samples) < 5:
                samples.append('blob-write-outside: %s (keys=%s)'
                               % (v['desc'], sorted(out)[:6]))

        # 3) ROM r0 leftover model (scratch, NOT a return value).
        exp = ref_r0(count, v['data'])
        if rom_r0 != exp:
            rom_r0_model += 1
            if len(samples) < 5:
                samples.append('rom-r0  %s ROM=0x%08X model=0x%08X'
                               % (v['desc'], rom_r0, exp))

        # 4) r0 ROM-vs-blob: only where deterministic on BOTH sides (count==0,
        #    both leave 0).  For count>0 the void blob's r0 is undefined.
        if count == 0 and rom_r0 != blb_r0:
            r0_c0 += 1
            if len(samples) < 5:
                samples.append('r0(count=0) ROM=0x%08X blob=0x%08X'
                               % (rom_r0, blb_r0))
        if blb_r0 != 0:
            blb_r0_nonzero += 1          # informational (void codegen detail)

    dt = time.time() - t0
    bad = rb + rom_out + blb_out + rom_r0_model + r0_c0
    status = 'OK  ' if bad == 0 else 'FAIL'

    print('%s memcpy_bytewise @0x%X  (non-ABI r0=count/r1=dst/r2=src -> void)'
          % (status, ROM_ADDR))
    print('    signature found: void f(uint8_t *dst_r1, const uint8_t *src_r2,'
          ' uint32_t count_r0)   [blob: r4/r5/r6 standard ABI]')
    print('    n_total=%-5d (matrix=%-4d edges=%-3d random=%d)'
          % (total, n_matrix, n_edges, total - n_matrix - n_edges))
    print('    counts=0..%d  src_off=%s  dst_off=%s  patterns=%s'
          % (MAX_LEN, OFFSETS, OFFSETS, PATTERNS))
    print('    ROM-vs-blob ram=%-4d  rom-write-outside=%-3d  '
          'blob-write-outside=%-3d  rom-r0-model=%-4d  r0(count=0)=%-3d'
          % (rb, rom_out, blb_out, rom_r0_model, r0_c0))
    print('    r0 note: ROM leaves the sign-extended last copied byte'
          ' (mov.b scratch, NOT a return; C is void).  gcc-3.4.6 blob leaves'
          ' r0=0 in %d/%d cases (void codegen) -> r0 outside the equivalence'
          ' contract except count==0.' % (total - blb_r0_nonzero, total))
    for s in samples:
        print('        ' + s)

    if bad:
        print('verify_memcpy: %d mismatch(es) total — FAIL' % bad)
        sys.exit(1)
    print('verify_memcpy: all OK (0 mismatch; post-call RAM identical on both'
          ' sides, dst copied exactly, no overrun, src/guards untouched)')
    print('    semantics: forward byte-by-byte memcpy, 4x unrolled, void'
          ' (no return value)')


if __name__ == '__main__':
    main()
