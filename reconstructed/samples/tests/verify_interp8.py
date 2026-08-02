#!/usr/bin/env python3
"""
verify_interp8.py — era-ROM toolchain (gcc 3.4.6) validation of Lotto 2:
rx8_interpolate_u8_table @0x26B0.

Closes the "ROM -> abstract C -> era-ROM toolchain (gcc 3.4.6)" loop on the
*behavioural* plane for the UINT8-cell linear-interpolation leaf, using the
same proven pattern as verify_gcc346.py / verify_interp16.py (which validated
the u16 sibling @0x26D0): build with the archived sh-elf gcc 3.4.6, link at
0x4000, objcopy the .text blob, load the blob into tools/sh2emu.py through the
sparse ram overlay, and compare it instruction-for-instruction against the real
ROM bytes at 0x26B0 on the same input vectors.

Calling convention (deduced from the ROM disassembly @0x26B0, NOT from the
host prototype — this is the non-ABI leaf style shared by both siblings):

    ROM  in: r0 = cell index i (already found by axis-search), r1 = pointer to
              the u8 cell array, fr0 = t in [0,1)
         out: fr2 = interpolated float (fr0 left untouched for the 2-D callers)

    blob in: the same C compiled by gcc 3.4.6 uses the standard SH ABI
              r4 = index, r5 = cells-pointer, fr4 = t
         out: fr0 = interpolated float

So the ROM side is driven with the arbitrary-register call_leaf() driver
(identical to the u8/u16 harnesses and c/tests/test_interp_leaves.py), while
the blob side uses cpu.call(r4=, r5=, fr=).

fmaf(): the C source calls fmaf() to reproduce the ROM's single-rounding
'fmac'.  gcc 3.4.6 has no fmac emission for fmaf() on the sh-2e; it compiles
it to an external call (jsr).  The harness therefore links a tiny fmaf() shim
(in /tmp/verify_interp8/work/fmaf_shim.c, never committed) that implements
`a*b+c`.  gcc 3.4.6 recognises that the sh-2 has the 'fmac' instruction and
compiles this shim itself to a single `fmac` (see blob disassembly @0x4038), so
the shim is genuinely single-rounded and bit-exact with the ROM path — no
double-precision / soft-float involved.

Vectors: edge indices (0..count-1) with t=0.0 (both clamp ends, incl. the
i=count-1 no-read-past-end fast path), t at 0.5 and 1.0 across the interior,
over several u8 cell arrays (all-zero, all-0xFF, a synthetic extremes/pattern
array and real ROM descriptor tables), then padded to N = 3000 with
seeded-random (i in-range, t in {0, 0.5, 1.0}).

Only t in {0, 0.5, 1.0} is used — the exact-product subset for which the shim's
single fmac and the ROM's fmac are provably identical (0*b and 1*b are exact,
0.5*b is a power-of-two rescale of a float mantissa).

Comparison: ROM fr2 bits vs blob fr0 bits — the raw IEEE single-precision bit
patterns must match for 0 mismatch to pass.

Read-only w.r.t. the repo: everything it writes goes to /tmp.  Exit code 0 iff
0 mismatches.

Usage:  python3 verify_interp8.py [N]   (default N = 3000)
"""
import os
import struct
import subprocess
import sys

TESTS = os.path.dirname(os.path.abspath(__file__))      # .../samples/tests
SAMPLES = os.path.dirname(TESTS)                          # .../samples
ROOT = os.path.dirname(os.path.dirname(SAMPLES))          # rx8ecu
sys.path.insert(0, TESTS)
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2, MASK, ts, f2bits  # noqa: E402
from common import make_rng  # noqa: E402

# ---- era-ROM toolchain ------------------------------------------------------
XGCC = '/home/davide/gcc346-build/gcc/xgcc'
XGCC_B = '/home/davide/gcc346-build/gcc'
LD = '/usr/bin/sh-elf-ld'
OBJCOPY = '/usr/bin/sh-elf-objcopy'
NM = '/usr/bin/sh-elf-nm'

STUB_INC = '/tmp/verify_interp8/inc'      # stub stdint.h / math.h (never committed)
WORK = '/tmp/verify_interp8/work'         # objects / ls / blobs / shim
LINK_BASE = 0x4000                         # fixed link base
SHIM_SRC = os.path.join(WORK, 'fmaf_shim.c')

SRC_DIR = os.path.join(SAMPLES, 'src')
INC_DIR = os.path.join(SAMPLES, 'include')
SRC = os.path.join(SRC_DIR, 'rx8_interpolate_u8_table.c')

# The cells live in the sparse ram overlay so the emulator reads them.
CELL_BASE = 0x2000                         # the u8 table backing region

ROM_ADDR = 0x26B0                          # the real ROM bytes @60E1D400.bin
ENTRY = 'rx8_interpolate_u8_table'         # blob symbol (gcc ABI)
N_DEFAULT = 3000

# ============================================================================
# Stub headers (the archived gcc 3.4.6 was configured --without-headers)
# ============================================================================
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
    'float fabsf(float x);\n'
    'float fmaf(float a, float b, float c);\n'          # shim, linked in
    '#endif\n')

_LINKER = (
    'OUTPUT_FORMAT(elf32-sh)\n'
    'MEMORY { RAM (rx) : ORIGIN = 0x%X, LENGTH = 0x1000 }\n'
    'SECTIONS {\n'
    '  .text : { *(.text) *(.text.*) *(.rodata) *(.rodata.*) *(.rdata) } > RAM\n'
    '  /DISCARD/ : { *(.comment) *(.note*) *(.symtab) *(.strtab) '
    '*(.shstrtab) *(.debug*) }\n}\n' % LINK_BASE)

_SHIM = (
    '/* fmaf() shim — the era toolchain has no libm. */\n'
    'float fmaf(float a, float b, float c) { return a * b + c; }\n')


class SH2L(SH2):
    """SH2 + call_leaf(): load arbitrary *initial registers* (r0-r15, fr0-fr15),
    required for the interp-u8 leaf's non-ABI entry (r0/r1/fr0 -> fr2), which
    cpu.call() cannot seed.  Line-for-line copy of SH2.call()'s body (the rosetta
    used by harness_interpolate_u8_table.py and c/tests/test_interp_leaves.py).
    """

    def call_leaf(self, entry, regs=None, fr=None, ram=None):
        self.ram = dict(ram or {})
        self.r = [0] * 16
        for k, v in (regs or {}).items():
            self.r[k] = v & MASK
        self.r[15] = 0xFFFFDF00
        self.fr = [0.0] * 16
        for k, v in (fr or {}).items():
            self.fr[k] = ts(v)
        self.pr = self.SENT; self.T = 0; self.macl = 0; self.mach = 0
        self.gbr = 0; self.fpul = 0; self.fpscr = 0
        self.pc = entry & MASK
        steps = 0
        while True:
            if self.pc == self.SENT:
                return self.r[0] & MASK
            steps += 1
            if steps > 500000:
                raise RuntimeError("runaway at 0x%X" % self.pc)
            op = self.rd(self.pc, 2)
            br = self._delayed(op)
            if br is None:
                self._exec(op, self.pc); self.pc = (self.pc + 2) & MASK
            else:
                target, take = br
                self._exec(self.rd(self.pc + 2, 2), self.pc + 2)
                self.pc = target if take else (self.pc + 4) & MASK


# ============================================================================
# Toolchain build (once) — object, link, objcopy .text blob, read symbols
# ============================================================================
def build_blob():
    """Compile the reconstructed source + the fmaf shim with gcc 3.4.6, link at
    LINK_BASE, objcopy the .text section, return (blob_bytes, {sym: addr})."""
    os.makedirs(STUB_INC, exist_ok=True)
    os.makedirs(WORK, exist_ok=True)
    with open(os.path.join(STUB_INC, 'stdint.h'), 'w') as f:
        f.write(_STDINT)
    with open(os.path.join(STUB_INC, 'math.h'), 'w') as f:
        f.write(_MATH)
    with open(SHIM_SRC, 'w') as f:
        f.write(_SHIM)

    obj = os.path.join(WORK, 'interp.o')
    shm = os.path.join(WORK, 'fmaf_shim.o')
    elf = os.path.join(WORK, 'interp.elf')
    blb = os.path.join(WORK, 'blob.bin')

    subprocess.run(
        [XGCC, '-B', XGCC_B, '-m2e', '-O1', '-fomit-frame-pointer',
         '-c', SRC, '-o', obj, '-I', STUB_INC, '-I', SRC_DIR, '-I', INC_DIR],
        check=True, capture_output=True)
    subprocess.run(
        [XGCC, '-B', XGCC_B, '-m2e', '-O1', '-fomit-frame-pointer',
         '-c', SHIM_SRC, '-o', shm],
        check=True, capture_output=True)

    lds = os.path.join(WORK, 'link.ld')
    if not os.path.exists(lds):
        with open(lds, 'w') as f:
            f.write(_LINKER)
    subprocess.run([LD, '-T', lds, obj, shm, '-o', elf],
                   check=True, capture_output=True)
    subprocess.run([OBJCOPY, '-O', 'binary', '--only-section=.text', elf, blb],
                   check=True, capture_output=True)

    with open(blb, 'rb') as f:
        blob = f.read()
    syms = {}
    nm = subprocess.run([NM, elf], capture_output=True, text=True)
    for line in nm.stdout.splitlines():
        p = line.split()
        if len(p) == 3 and p[1] == 'T':
            try:
                syms[p[2].lstrip('_')] = int(p[0], 16)
            except ValueError:
                pass
    return blob, syms


def cells_ram(cells, base=CELL_BASE):
    """u8 cell array -> sparse ram bytes (one 8-bit cell per address)."""
    return {base + k: c & 0xFF for k, c in enumerate(cells)}


# ============================================================================
# Table / vector generation
# ============================================================================
# Real u8-cell arrays from 1-D map descriptors read from 60E1D400.bin
# (values pointer at desc+8, u16 count at desc+0) — reused from the u8 harness.
DESCRIPTORS = (0x69A54, 0x69C4C, 0x69970, 0x69984)

# Synthetic extremes / pattern arrays: both uint8 endpoints, steep deltas,
# plus all-0 and all-0xFF degenerate tables.
PATTERN = [0x00, 0xFF, 0x80, 0x01, 0xFE, 0x7F, 0x40, 0xBF, 0x00, 0xFF]
ALLZ = [0x00] * 7
ALLF = [0xFF] * 7


def real_tables(cpu):
    rom = cpu.rom
    out = []
    for d in DESCRIPTORS:
        count = struct.unpack_from('>H', rom, d)[0]
        vp = struct.unpack_from('>I', rom, d + 8)[0]
        cells = list(rom[vp:vp + count])
        out.append(cells)
    return out


def gen_vectors(cells):
    """Edge vectors: every index with t=0 (both clamped ends incl. the i=n-1
    read-past-end fast path), plus t at 0.5 and 1.0 across the interior.
    Only 0/0.5/1 are used — the exact-product subset for which the shim's single
    fmac and the ROM fmac are provably identical (0*b and 1*b exact, 0.5*b is a
    power-of-two rescale of a float mantissa)."""
    n = len(cells)
    vs = []
    for i in range(n):
        vs.append((i, 0.0))                 # incl. i=n-1, t=0 safe clamp
    for i in range(n - 1):
        vs.append((i, 0.5))                 # exact-product midpoint
        vs.append((i, 1.0))                 # exact-product ceiling
    return vs


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    blob, syms = build_blob()
    entry = syms.get(ENTRY, LINK_BASE)
    base = {LINK_BASE + i: blob[i] for i in range(len(blob))}

    with open(os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin'), 'rb') as f:
        rom = f.read()
    rom_cpu = SH2L(rom)
    blb_cpu = SH2L(rom)                     # fresh SH2 instance for the blob

    tables = real_tables(rom_cpu) + [PATTERN, ALLZ, ALLF]

    # deterministic grid first, then seeded padding to exactly N
    vecs = []
    for cells in tables:
        vecs += [(i, t, cells) for (i, t) in gen_vectors(cells)]
    rng = make_rng(0x26B0)
    while len(vecs) < n:
        cells = tables[rng.randrange(len(tables))]
        i = rng.randrange(0, len(cells) - 1)
        vecs.append((i, rng.choice((0.0, 0.5, 1.0)), cells))
    vecs = vecs[:n]

    rom_res, blb_res = [], []
    for i, t, cells in vecs:
        cm = cells_ram(cells)
        # ROM side: non-ABI r0/r1/fr0 -> fr2 (arbitrary-register driver)
        rom_cpu.call_leaf(ROM_ADDR, regs={0: i, 1: CELL_BASE},
                          fr={0: t}, ram=cm)
        rom_res.append(f2bits(rom_cpu.fr[2]))
        # blob side: gcc ABI r4/r5/fr4 -> fr0, code in the same ram overlay
        mer = dict(base); mer.update(cm)
        blb_cpu.call(entry, r4=i, r5=CELL_BASE, ram=mer, fr={4: t})
        blb_res.append(f2bits(blb_cpu.fr[0]))

    mism = []
    for k, (e, h) in enumerate(zip(rom_res, blb_res)):
        if e != h:
            i, t, cells = vecs[k]
            mism.append('vec#%d i=%d t=%g cells=%s ROM(fr2)=0x%08X blob(fr0)=0x%08X'
                        % (k, i, t, cells, e, h))
            if len(mism) >= 5:
                break

    total = len(mism)
    if total == 0:
        print('verify_interp8: ROM @0x%X vs gcc-3.4.6 blob @0x%X '
              '(entry 0x%X), %d vectors, 0 mismatches — OK'
              % (ROM_ADDR, LINK_BASE, entry, n))
    else:
        print('verify_interp8: %d vectors, %d mismatches — FAIL'
              % (n, total))
        for s in mism:
            print('    ' + s)
    sys.exit(0 if total == 0 else 1)


if __name__ == '__main__':
    main()