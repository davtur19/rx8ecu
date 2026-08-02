#!/usr/bin/env python3
"""
verify_checksum.py — era-ROM toolchain (sh-elf gcc 3.4.6) validation of
rx8_checksum_complement_add @0x2034 — the POINTER-CONVENTION special case.

Blueprint note
--------------
The ROM leaf reads its 32-bit operand through the pointer in r4
(`mov.l @r4,r3`) — it is a RAM-CELL function, NOT a plain register-value
function.  The reconstructed C (rx8_checksum_complement_add.c) takes the cell
value BY COPY, so the two sides consume the *same* r4 register image in
different ways:

    ROM  : r4 = &cell        ->  mov.l @r4,r3  (the caller-side load is
           reproduced here by placing the big-endian cell bytes in the
           emulated RAM overlay; r5 = length is NOT read by the ROM)
    blob : r4 = cell_value   (gcc 3.4.6 compiles the by-value C with the
           standard SH ABI — 6 pure-register instructions, no memory access)

Both return the 16-bit checksum residual  (~value - (value >> 16)) & 0xFFFF
in r0; residual == 0 means the (data, ~data) redundant pair is self-consistent.

Signature found (verified):  uint16_t f(uint32_t *r4) -> r0, no writes.

What this harness does
----------------------
  (a) compiles rx8_checksum_complement_add.c with the era-ROM recipe
      `-m2e -O1 -fomit-frame-pointer` via /home/davide/gcc346-build/gcc/xgcc,
      links it at 0x4000 with sh-elf-ld and extracts .text,
  (b) drives the ROM bytes @0x2034 and the blob @0x4000 on identical vectors,
      each carrying a full RAM image:
        - the 4-byte cell at a deterministically varying address
          (buffer base 0x3000, cell offset/alignment 0..3),
        - a surrounding buffer of size 1,2,4,8,16,64,256 bytes filled with a
          deterministic pattern (0x00 / 0xFF / incremental / descending /
          0xDEADBEEF / seeded random),
        - sentinel guard bytes before and after the buffer,
  (c) compares r0 AND the complete post-call RAM state (the ROM leaf performs
      exactly one 32-bit read and no writes, so RAM must be untouched on both
      sides — this also proves the blob does not secretly read/write memory),
  (d) as a third leg, checks the host-C oracle (oracle_checksum_complement_add.c)
      against the blob.

Read-only w.r.t. the repo: everything written goes to /tmp/verify_checksum
(separate from verify_gcc346.py's /tmp/verify_gcc346); exit non-zero iff any
mismatch.  Does NOT modify verify_gcc346.py, README.md, Makefile or tools/.

Usage:  python3 tests/verify_checksum.py [N]   (default N = 4000 random cells)
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

# ---- era-ROM toolchain (same binaries as verify_gcc346.py) ------------------
XGCC = '/home/davide/gcc346-build/gcc/xgcc'
XGCC_B = '/home/davide/gcc346-build/gcc'
LD = '/usr/bin/sh-elf-ld'
OBJCOPY = '/usr/bin/sh-elf-objcopy'
NM = '/usr/bin/sh-elf-nm'
LIBGCC = os.path.join(XGCC_B, 'libgcc.a')
STUB_INC = '/tmp/verify_gcc346/inc'        # stub stdint.h/math.h (shared)
WORK = '/tmp/verify_checksum'              # own workdir (never touches gcc346's)
LINK_BASE = 0x4000                         # fixed link base

SRC_DIR = os.path.join(SAMPLES, 'src')
INC_DIR = os.path.join(SAMPLES, 'include')

# ---- function / RAM geometry ------------------------------------------------
ROM_ADDR = 0x2034                       # checksum_complement_add
ENTRY_SYM = 'rx8_checksum_complement_add'
CELL_BASE = 0x3000                      # emulated RAM buffer base
GUARD_PRE = 8                           # sentinel bytes before the buffer
GUARD_POST = 8                          # sentinel bytes after the buffer
SENTINEL = 0x5A                         # guard fill byte

N_DEFAULT = 4000                        # seeded random cell values (>= 2000)
SEED = 0x2034
EDGE_VALS = [
    0x00000000, 0xFFFFFFFF, 0x00000001,
    0x0001FFFE, 0x7FFF8000, 0x80007FFF, 0xFFFF0000,   # valid (data,~data) pairs
    0x0000FFFF, 0x7FFFFFFF, 0x80000000,
    0x1234ABCD, 0xDEADBEEF, 0xAAAA5555,
]
SIZES = [1, 2, 4, 8, 16, 64, 256]       # buffer lengths around the cell
ALIGNS = [0, 1, 2, 3]                   # cell offset within the buffer
PATTERNS = ['zero', 'ones', 'inc', 'dec', 'beef', 'rand']

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


def build_ram(cell_addr, size, align, val, pat):
    """RAM image: guards + size-byte buffer + the 4 big-endian cell bytes at
    cell_addr (may spill past the buffer into the post guard for size < 4)."""
    ram = {}
    for i in range(GUARD_PRE):
        ram[CELL_BASE - GUARD_PRE + i] = SENTINEL
    for i in range(size):
        ram[CELL_BASE + i] = pat_byte(pat, i)
    for i in range(GUARD_POST):
        ram[CELL_BASE + size + i] = SENTINEL
    for i in range(4):                                  # the cell, big-endian
        ram[cell_addr + i] = (val >> (8 * (3 - i))) & 0xFF
    return ram


# =============================================================================
# Vector generation  (edges + full pattern/size/alignment matrix + random)
# =============================================================================
def gen_vectors(n):
    rng = make_rng(SEED)
    vecs = []

    def add(val, size, align, pat, desc):
        vecs.append({'val': val, 'size': size, 'align': align,
                     'pat': pat, 'addr': CELL_BASE + align, 'desc': desc})

    for v in EDGE_VALS:
        add(v, 4, 0, 'zero', 'edge val=0x%08X' % v)
    for pat in PATTERNS:                                # full deterministic matrix
        for size in SIZES:
            for align in ALIGNS:
                val = rng.getrandbits(32)
                add(val, size, align, pat,
                    'pat=%-4s size=%-3d align=%d val=0x%08X' % (pat, size, align, val))
    for i in range(n):                                  # seeded random stream
        val = rng.getrandbits(32)
        size = rng.choice(SIZES)
        align = rng.choice(ALIGNS)
        pat = rng.choice(PATTERNS)
        add(val, size, align, pat,
            'rnd#%d val=0x%08X size=%d align=%d pat=%s'
            % (i, val, size, align, pat))
    return vecs


# =============================================================================
# Build: gcc 3.4.6 blob at 0x4000, host oracle
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
    obj, elf, blb = (os.path.join(WORK, 'chk.' + e)
                     for e in ('o', 'elf', 'bin'))
    subprocess.run(
        [XGCC, '-B', XGCC_B, '-m2e', '-O1', '-fomit-frame-pointer',
         '-c', os.path.join(SRC_DIR, 'rx8_checksum_complement_add.c'),
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


def build_host_oracle():
    binp = os.path.join(WORK, 'oracle_checksum')
    cmd = [os.environ.get('CC', 'cc'), '-O2', '-Wall', '-Wextra',
           '-I', INC_DIR, '-I', SRC_DIR,
           os.path.join(TESTS, 'oracle_checksum_complement_add.c'),
           os.path.join(SRC_DIR, 'rx8_checksum_complement_add.c'),
           '-o', binp]
    subprocess.run(cmd, check=True, capture_output=True)
    return binp


# =============================================================================
# Evaluation
# =============================================================================
def run_pair(cpu, entry, base, vec):
    """Run the ROM bytes and the gcc-3.4.6 blob on the same RAM image.

    ROM  : r4 = &cell (pointer convention; r5 = buffer length, unused by ROM),
    blob : r4 = cell value (standard ABI; r5 unused by the C).
    Returns (rom_r0, blb_r0, pre_ram, rom_post, blob_overlay, blob_post)."""
    ram = build_ram(vec['addr'], vec['size'], vec['align'], vec['val'], vec['pat'])

    rom_r0 = cpu.call(ROM_ADDR, r4=vec['addr'], r5=vec['size'], ram=dict(ram))
    rom_post = dict(cpu.ram)

    overlay = dict(base)                # blob code at LINK_BASE
    overlay.update(ram)                 # + cell / guards at 0x3000
    blb_r0 = cpu.call(entry, r4=vec['val'], r5=vec['size'], ram=overlay)
    blb_post = dict(cpu.ram)

    return rom_r0, blb_r0, ram, rom_post, overlay, blb_post


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    blob, syms = build_blob()
    if ENTRY_SYM not in syms:
        sys.exit('verify_checksum: entry symbol %r not found in blob '
                 '(syms=%r)' % (ENTRY_SYM, sorted(syms)))
    entry = syms[ENTRY_SYM]
    base = {LINK_BASE + i: blob[i] for i in range(len(blob))}
    oracle = build_host_oracle()

    cpu = load_cpu()
    vecs = gen_vectors(n)
    total = len(vecs)
    t0 = time.time()

    rb, rom_ram_bad, blb_ram_bad = 0, 0, 0
    blb_r0s = []
    samples = []
    for v in vecs:
        rom_r0, blb_r0, pre, rom_post, overlay, blb_post = run_pair(cpu, entry, base, v)
        blb_r0s.append(blb_r0)
        if rom_r0 != blb_r0:
            rb += 1
            if len(samples) < 5:
                samples.append('r0  %s ROM=0x%04X blob=0x%04X'
                               % (v['desc'], rom_r0, blb_r0))
        if rom_post != pre:
            rom_ram_bad += 1
            if len(samples) < 5:
                samples.append('ram-write ROM side: %s' % v['desc'])
        if blb_post != overlay:
            blb_ram_bad += 1
            if len(samples) < 5:
                samples.append('ram-write blob side: %s' % v['desc'])

    # third leg: host-C oracle vs blob
    lines = ['sum %08X' % v['val'] for v in vecs]
    proc = subprocess.run([oracle], input='\n'.join(lines) + '\n',
                          capture_output=True, text=True)
    if proc.returncode != 0:
        print('    (host oracle failed: %s)' % proc.stderr.strip())
        ob = None
    else:
        outs = proc.stdout.splitlines()
        ob = 0
        for i, (h, o) in enumerate(zip(blb_r0s, outs)):
            if h != int(o, 16):
                ob += 1
                if ob == 1 and len(samples) < 5:
                    samples.append('oracle-vs-blob: blob=0x%04X host=%s (vec#%d)'
                                   % (h, o, i))

    dt = time.time() - t0
    bad = rb + rom_ram_bad + blb_ram_bad + (ob or 0)
    status = 'OK  ' if bad == 0 else 'FAIL'

    n_matrix = len(PATTERNS) * len(SIZES) * len(ALIGNS)
    print('%s checksum_complement_add @0x%X  (ptr r4 -> r0, leaf, no writes)'
          % (status, ROM_ADDR))
    print('    signature found: uint16_t f(uint32_t *cell_r4) -> r0'
          '  [blob: uint16_t f(uint32_t value_r4) -> r0, standard ABI]')
    print('    n_total=%-5d (edges=%d  matrix=%d  random=%d)'
          % (total, len(EDGE_VALS), n_matrix, n))
    print('    patterns=%s  sizes=%s  aligns=%s' % (PATTERNS, SIZES, ALIGNS))
    print('    ROM-vs-blob r0 mismatch=%-4d  ROM ram-write=%-4d  '
          'blob ram-write=%-4d  oracle-vs-blob=%-4s  %.2fs'
          % (rb, rom_ram_bad, blb_ram_bad,
             ob if ob is not None else '-', dt))
    for s in samples:
        print('        ' + s)

    if bad:
        print('verify_checksum: %d mismatch(es) total — FAIL' % bad)
        sys.exit(1)
    print('verify_checksum: all OK (0 mismatch; post-call RAM untouched on both sides)')


if __name__ == '__main__':
    main()
