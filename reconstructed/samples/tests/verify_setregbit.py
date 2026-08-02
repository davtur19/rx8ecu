#!/usr/bin/env python3
"""
verify_setregbit.py — era-ROM toolchain (sh-elf gcc 3.4.6) validation of
rx8_set_register_reg_bit_val @0x4BBC — the POINTER-CONVENTION RAM-CELL
set-or-clear-bits primitive.

Target note
-----------
The ROM leaf reads its 16-bit operand through the pointer in r4
(`mov.w @r4,r3`) and writes the result back through r4 (`mov.w r3,@r4`) — it
is a RAM-CELL function with a side-effect, NOT a plain register-value
function, and it returns nothing (void, r0 untouched).  The reconstructed C
(rx8_set_register_reg_bit_val.c) has the same pointer signature
`void f(uint16_t *reg, uint16_t mask, int enable)`, so BOTH sides consume the
*r4 = &cell convention identically:

    ROM  : r4 = &cell -> mov.w @r4,r3  /  mov.w r3,@r4  (12 instructions:
           6341 666d 2668 8b03 6557 2359 000b 2431 235b 2431 000b 0009)
    blob : r4 = &cell -> gcc 3.4.6 emits a branch-swapped equivalent
           (12 instructions: extu.w/mov.w/@r4/tst/bt/bra/or/not/and/rts),
           24 bytes, same size as the ROM body, same 16-bit write-back.

Expected semantics (confirmed from the C and the 0x4BBC disassembly):
the enable flag is zero-extended to 16 bits (`extu.w r6,r6`) BEFORE the
tst/bf — only the low 16 bits of r6 decide set-vs-clear:

    enable16 = enable & 0xFFFF
    *reg = *reg | mask   if enable16 != 0        (set path)
    *reg = *reg & ~mask  if enable16 == 0        (clear path)

A 32-bit caller value with any bit >= 16 set (e.g. 0x10000, 0x80000000)
therefore means "clear", matching the C's `enable &= 0xFFFF` before the if.

What this harness does (verify_checksum.py / verify_gcc346.py pattern)
----------------------------------------------------------------------
  (a) compiles rx8_set_register_reg_bit_val.c with the era-ROM recipe
      `-m2e -O1 -fomit-frame-pointer` via /home/davide/gcc346-build/gcc/xgcc,
      links it at 0x4000 with sh-elf-ld and extracts .text,
  (b) drives the ROM bytes @0x4BBC and the blob @0x4000 on identical vectors,
      each carrying a full RAM image:
        - the 16-bit register cell at 0x2000 (big-endian, mov.w semantics),
        - a surrounding pattern buffer (size 1,2,4,8,16,64,256 bytes filled
          with 0x00 / 0xFF / incremental / descending / 0xDEADBEEF / seeded
          random),
        - sentinel guard bytes before and after the buffer,
  (c) compares the post-call cell value AND the complete post-call RAM state
      (only the two cell bytes may change — proves neither side secretly
      reads/writes elsewhere; the two code regions never overlap the cell),
  (d) as a third leg, checks BOTH sides against the expected set/clear
      semantics written out here in Python (the "semantica confermata"
      evidence: ROM, blob and reference must all agree).
  (e) r0 is compared too — it is a void function, so both sides must leave
      r0 untouched (0 on both sides).

Read-only w.r.t. the repo: everything written goes to /tmp/verify_setregbit
(separate from verify_gcc346.py's /tmp/verify_gcc346); exit non-zero iff any
mismatch.  Does NOT modify verify_gcc346.py, README.md, Makefile or tools/.

Usage:  python3 tests/verify_setregbit.py [N]   (default N = 4000 random)
"""
import os
import random
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

# ---- era-ROM toolchain (same binaries as verify_gcc346.py) ------------------
XGCC = '/home/davide/gcc346-build/gcc/xgcc'
XGCC_B = '/home/davide/gcc346-build/gcc'
LD = '/usr/bin/sh-elf-ld'
OBJCOPY = '/usr/bin/sh-elf-objcopy'
NM = '/usr/bin/sh-elf-nm'
LIBGCC = os.path.join(XGCC_B, 'libgcc.a')
STUB_INC = '/tmp/verify_gcc346/inc'        # stub stdint.h/math.h (shared)
WORK = '/tmp/verify_setregbit'             # own workdir (never touches gcc346's)
LINK_BASE = 0x4000                         # fixed link base

SRC_DIR = os.path.join(SAMPLES, 'src')
INC_DIR = os.path.join(SAMPLES, 'include')

# ---- function / RAM geometry ------------------------------------------------
ROM_ADDR = 0x4BBC                       # rx8_set_register_reg_bit_val
ENTRY_SYM = 'rx8_set_register_reg_bit_val'
CELL_ADDR = 0x2000                      # emulated RAM cell (16-bit register)
GUARD_PRE = 8                           # sentinel bytes before the buffer
GUARD_POST = 8                          # sentinel bytes after the buffer
SENTINEL = 0x5A                         # guard fill byte

N_DEFAULT = 4000                        # seeded random triples (>= 2000)
SEED = 0x4BBC

# Edge vectors per the target spec: mask 0x0001/0x8000/0xFFFF/0x7FFF,
# enable 0/1/0xFF (+ 32-bit truncation cases), cell 0/0xFFFF/patterns.
CELL_VALS = (0x0000, 0x0001, 0x7FFF, 0x8000, 0xFFFE, 0xFFFF, 0x5555, 0xAAAA)
MASKS     = (0x0001, 0x7FFF, 0x8000, 0xFFFF)
ENABLES   = (0x00000000, 0x00000001, 0x000000FF,
             0x00010000, 0x80000000, 0xFFFFFFFF)
SIZES     = [1, 2, 4, 8, 16, 64, 256]   # pattern-buffer lengths around the cell
PATTERNS  = ['zero', 'ones', 'inc', 'dec', 'beef', 'rand']

# =============================================================================
# Expected semantics — the reference both sides are checked against
# =============================================================================
def ref_setreg(init, mask, enable):
    """16-bit register result of rx8_set_register_reg_bit_val.

    `enable` is truncated to 16 bits (extu.w r6,r6): only the low half
    decides set-vs-clear, exactly like the reconstructed C.
    """
    if enable & 0xFFFF:
        return (init | mask) & 0xFFFF
    return (init & ~mask) & 0xFFFF


# =============================================================================
# Pattern fillers  (deterministic; 'rand' consumes the dedicated fill RNG)
# =============================================================================
FILL_RNG = make_rng(SEED ^ 0x5EED)      # dedicated stream, only for 'rand' fill


def pat_byte(pat, i):
    if pat == 'zero':
        return 0x00
    if pat == 'ones':
        return 0xFF
    if pat == 'inc':
        return i & 0xFF
    if pat == 'dec':
        return (0xFF - (i & 0xFF)) & 0xFF
    if pat == 'beef':
        return (0xDE, 0xAD, 0xBE, 0xEF)[i % 4]
    return FILL_RNG.getrandbits(8)      # 'rand'


def build_ram(init, size, pat):
    """RAM image around CELL_ADDR: sentinel guards, a `size`-byte pattern
    buffer before and after the cell, and the 16-bit big-endian cell."""
    ram = {}
    pre = CELL_ADDR - GUARD_PRE - size
    for i in range(GUARD_PRE):
        ram[CELL_ADDR - GUARD_PRE + i] = SENTINEL        # guard before
    for i in range(size):
        ram[pre + i] = pat_byte(pat, i)                  # pattern buffer before
    for i in range(size):
        ram[CELL_ADDR + 2 + i] = pat_byte(pat, i)        # pattern buffer after
    for i in range(GUARD_POST):
        ram[CELL_ADDR + 2 + size + i] = SENTINEL         # guard after
    ram[CELL_ADDR] = (init >> 8) & 0xFF                  # cell, big-endian
    ram[CELL_ADDR + 1] = init & 0xFF
    return ram


def read_cell(ram):
    return ((ram.get(CELL_ADDR, 0) << 8) | ram.get(CELL_ADDR + 1, 0)) & 0xFFFF


# =============================================================================
# Vector generation  (edges + pattern/size matrix + seeded random)
# =============================================================================
def gen_vectors(n):
    rng = make_rng(SEED)
    vecs = []

    def add(init, mask, enable, size, pat, desc):
        vecs.append({'init': init, 'mask': mask, 'enable': enable,
                     'size': size, 'pat': pat, 'desc': desc})

    # full cross-product of the boundary values from the target spec
    for c in CELL_VALS:
        for m in MASKS:
            for e in ENABLES:
                add(c, m, e, 4, 'zero',
                    'cell=%04X mask=%04X enable=%08X' % (c, m, e))
    # deterministic pattern x size matrix (random values from the same stream)
    for pat in PATTERNS:
        for size in SIZES:
            c = rng.getrandbits(16)
            m = rng.getrandbits(16)
            e = rng.getrandbits(32)
            add(c, m, e, size, pat,
                'pat=%-4s size=%-3d cell=%04X mask=%04X enable=%08X'
                % (pat, size, c, m, e))
    # seeded random triples
    for i in range(n):
        c = rng.getrandbits(16)
        m = rng.getrandbits(16)
        e = rng.getrandbits(32)
        size = rng.choice(SIZES)
        pat = rng.choice(PATTERNS)
        add(c, m, e, size, pat,
            'rnd#%d cell=%04X mask=%04X enable=%08X size=%d pat=%s'
            % (i, c, m, e, size, pat))
    return vecs


# =============================================================================
# Build: gcc 3.4.6 blob at 0x4000
# =============================================================================
_LINKER = (
    'OUTPUT_FORMAT(elf32-sh)\n'
    'MEMORY { RAM (rx) : ORIGIN = 0x%X, LENGTH = 0x1000 }\n'
    'SECTIONS {\n'
    '  .text : { *(.text) *(.text.*) *(.rodata) *(.rodata.*) *(.rdata) } > RAM\n'
    '  /DISCARD/ : { *(.comment) *(.note*) *(.symtab) *(.strtab) '
    '*(.shstrtab) *(.debug*) }\n}\n' % LINK_BASE)


def build_blob():
    """Compile with gcc 3.4.6, link at 0x4000, extract .text.
    Returns (blob_bytes, {symbol: linked_absolute_addr})."""
    os.makedirs(WORK, exist_ok=True)
    obj, elf, blb = (os.path.join(WORK, 'setreg.' + e)
                     for e in ('o', 'elf', 'bin'))
    subprocess.run(
        [XGCC, '-B', XGCC_B, '-m2e', '-O1', '-fomit-frame-pointer',
         '-c', os.path.join(SRC_DIR, 'rx8_set_register_reg_bit_val.c'),
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
# Evaluation
# =============================================================================
def run_pair(cpu, entry, base, vec):
    """Run the ROM bytes @0x4BBC and the gcc-3.4.6 blob on the same RAM image.

    Both sides use the *same* pointer convention: r4 = &cell (0x2000),
    r5 = mask, r6 = enable; the 16-bit result is written back through r4.
    Returns (rom_r0, blb_r0, rom_cell, blb_cell, pre, rom_post, overlay,
    blb_post)."""
    ram = build_ram(vec['init'], vec['size'], vec['pat'])

    rom_r0 = cpu.call(ROM_ADDR, r4=CELL_ADDR, r5=vec['mask'], r6=vec['enable'],
                      ram=dict(ram))
    rom_post = dict(cpu.ram)
    rom_cell = read_cell(rom_post)

    overlay = dict(base)                # blob code at LINK_BASE
    overlay.update(ram)                 # + cell / buffers / guards at 0x2000
    blb_r0 = cpu.call(entry, r4=CELL_ADDR, r5=vec['mask'], r6=vec['enable'],
                      ram=overlay)
    blb_post = dict(cpu.ram)
    blb_cell = read_cell(blb_post)

    return rom_r0, blb_r0, rom_cell, blb_cell, ram, rom_post, overlay, blb_post


def untouched(pre, post, cell_bytes):
    """True iff `post` differs from `pre` only in the two cell bytes."""
    if set(post) != set(pre):
        return False
    for k, v in pre.items():
        if k in cell_bytes:
            continue
        if post[k] != v:
            return False
    return True


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    blob, syms = build_blob()
    if ENTRY_SYM not in syms:
        sys.exit('verify_setregbit: entry symbol %r not found in blob '
                 '(syms=%r)' % (ENTRY_SYM, sorted(syms)))
    entry = syms[ENTRY_SYM]
    base = {LINK_BASE + i: blob[i] for i in range(len(blob))}
    cell_bytes = {CELL_ADDR, CELL_ADDR + 1}

    cpu = load_cpu()
    vecs = gen_vectors(n)
    n_edge = len(CELL_VALS) * len(MASKS) * len(ENABLES)
    n_matrix = len(PATTERNS) * len(SIZES)
    total = len(vecs)
    t0 = time.time()

    cell_bad, rom_ram_bad, blb_ram_bad, sem_bad, r0_bad = 0, 0, 0, 0, 0
    samples = []
    for v in vecs:
        rom_r0, blb_r0, rom_cell, blb_cell, pre, rom_post, ov, blb_post = \
            run_pair(cpu, entry, base, v)
        if rom_cell != blb_cell:
            cell_bad += 1
            if len(samples) < 5:
                samples.append('cell  %s ROM=0x%04X blob=0x%04X'
                               % (v['desc'], rom_cell, blb_cell))
        if rom_cell != ref_setreg(v['init'], v['mask'], v['enable']):
            sem_bad += 1
            if len(samples) < 5:
                samples.append('semantics ROM side: %s ROM=0x%04X exp=0x%04X'
                               % (v['desc'], rom_cell,
                                  ref_setreg(v['init'], v['mask'], v['enable'])))
        if blb_cell != ref_setreg(v['init'], v['mask'], v['enable']):
            sem_bad += 1
            if len(samples) < 5:
                samples.append('semantics blob side: %s blob=0x%04X exp=0x%04X'
                               % (v['desc'], blb_cell,
                                  ref_setreg(v['init'], v['mask'], v['enable'])))
        if rom_r0 != blb_r0:
            r0_bad += 1
            if len(samples) < 5:
                samples.append('r0    %s ROM=0x%08X blob=0x%08X'
                               % (v['desc'], rom_r0, blb_r0))
        if not untouched(pre, rom_post, cell_bytes):
            rom_ram_bad += 1
            if len(samples) < 5:
                samples.append('ram-write ROM side: %s' % v['desc'])
        if not untouched(ov, blb_post, cell_bytes):
            blb_ram_bad += 1
            if len(samples) < 5:
                samples.append('ram-write blob side: %s' % v['desc'])

    dt = time.time() - t0
    bad = cell_bad + sem_bad + r0_bad + rom_ram_bad + blb_ram_bad
    status = 'OK  ' if bad == 0 else 'FAIL'

    print('%s set_register_reg_bit_val @0x%X  (ptr r4 -> cell write-back, '
          'void, leaf)' % (status, ROM_ADDR))
    print('    signature confirmed: void f(uint16_t *reg_r4, uint16_t mask_r5,'
          ' int enable_r6)  [ROM and blob both r4=&cell convention;'
          ' blob size=%dB]' % len(blob))
    print('    n_total=%-5d (edges=%d  matrix=%d  random=%d)'
          % (total, n_edge, n_matrix, n))
    print('    patterns=%s  sizes=%s' % (PATTERNS, SIZES))
    print('    cell-rom-vs-blob=%-4d  semantics-rom-vs-ref=%-4d  '
          'r0-rom-vs-blob=%-4d' % (cell_bad, sem_bad, r0_bad))
    print('    rom-ram-write=%-4d  blob-ram-write=%-4d  %.2fs'
          % (rom_ram_bad, blb_ram_bad, dt))
    for s in samples:
        print('        ' + s)

    if bad:
        print('verify_setregbit: %d mismatch(es) total — FAIL' % bad)
        sys.exit(1)
    print('verify_setregbit: all OK (0 mismatch; ROM==blob==expected '
          'semantics; post-call RAM touched only at the cell)')
    print('semantics confirmed: enable truncated to 16 bits ->'
          ' *reg |= mask if enable&0xFFFF else *reg &= ~mask')


if __name__ == '__main__':
    main()
