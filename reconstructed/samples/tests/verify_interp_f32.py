#!/usr/bin/env python3
"""
verify_interp_f32.py — era-ROM toolchain (gcc 3.4.6) validation of the
FLOAT32-cell linear-interpolation leaf @0x2678.

Closes the "ROM -> abstract C -> era-ROM toolchain (gcc 3.4.6)" loop on the
*behavioural* plane for the f32 linear-interpolation leaf, using the same proven
pattern as verify_interp8.py / verify_interp16.py (which validated the u8/u16
siblings @0x26B0 / @0x26D0): build the lift with the archived sh-elf gcc 3.4.6,
link at 0x4000, objcopy the .text blob, load the blob into tools/sh2emu.py
through the sparse ram overlay, and compare it instruction-for-instruction
against the real ROM bytes at 0x2678 on the same input vectors.

Calling convention (deduced from the ROM disassembly @0x2678, NOT from the
host prototype — this is the exact non-ABI leaf style of the u8/u16 siblings):

    ROM  in: r0 = f32 cell index i, r1 = pointer to the f32 array, fr0 = t
         out: fr2 = interpolated float (fr0 left untouched for the 2-D callers)

    blob in: the same behaviour compiled by gcc 3.4.6 uses the standard SH ABI
              r4 = cells-pointer, fr4 = t            (f(float,const float*))
         out: fr0 = interpolated float

So the ROM side is driven with the arbitrary-register call_leaf() driver
(identical to the u8/u16 harnesses), while the blob side uses cpu.call(r4=, fr=).

fmaf(): there is NO dedicated C for this leaf in the repo — the lift is written
to /tmp (never committed) as /tmp/verify_interp_f32/work/2678.c.  The ROM body is
a SINGLE-rounding fused 'fmac'  (fr2 = t*(tab[idx+1]-tab[idx]) + tab[idx]) with a
t==0 fast-path returning raw tab[idx] (bt.s, no fmac touch).  to reproduce the
fused single rounding in gcc 3.4.6 (which does not auto-fuse mul+add into fmac
here) the lift emits fmaf((tab[1]-tab[0]), t, tab[0]) and the harness links a
tiny fmaf() shim (in /tmp/verify_interp_f32/work/fmaf_shim.c, never committed)
that implements `a*b+c`.  gcc 3.4.6 recognises the sh-2 'fmac' instruction and
compiles that shim itself to a single 'fmac', so the shim is genuinely
single-rounded and bit-exact with the ROM path — no double-precision / soft-float
involved.  Plain `a*b+c` in the lift would dual-round (fmul then fadd) and
diverge bit-exactly.  The t==0 fast path is replicated in C (`if (t == 0.0f)
return tab[0];`) — fmaf(diff,0,tab[0]) would NaN on diff==inf (inf*0).

Vectors: f32 table pairs (0,1), (0,-1), (FLT_MAX,-FLT_MAX), (-1e38,1e38), and
denormal/edge pairs, each exercised at t in {0.0, 0.5, 1.0}; then padded to
N = 3000 with seeded-random (table idx, t in {0.0,0.5,1.0}).
r0 is always 0 (index-0 pair interpolation).  Both ROM and blob compute the
interpolation; the fused single rounding makes any t in {0,0.5,1} exact
(0*b and 1*b exact; 0.5*b is a power-of-two rescale of a float mantissa).

Comparison: ROM fr2 bits vs blob fr0 bits — the raw IEEE single-precision bit
patterns must match for 0 mismatch to pass.

Read-only w.r.t. the repo: everything it writes goes to /tmp.  Exit code 0 iff
0 mismatches.

Usage:  python3 verify_interp_f32.py [N]   (default N = 3000)
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

STUB_INC = '/tmp/verify_interp_f32/inc'    # stub stdint.h / math.h (never committed)
WORK = '/tmp/verify_interp_f32/work'       # objects / blobs / shim / lift
LINK_BASE = 0x4000                         # fixed link base
SHIM_SRC = os.path.join(WORK, 'fmaf_shim.c')
SRC = os.path.join(WORK, '2678.c')         # the f32 interp lift (net/no repo)

# The f32 table lives in the sparse-ram overlay so the emulator reads it.
CELL_BASE = 0x2000                         # the f32 table backing region

ROM_ADDR = 0x2678                          # the real ROM bytes @60E1D400.bin
ENTRY = 'f'                                # blob symbol (gcc ABI)
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

# The reconstructed lift for @0x2678 (fmaf so gcc forks a single fmac).  The
# ROM has a t==0 fast path (bt.s) that returns raw tab[0] WITHOUT touching the
# fmac — replicated here, because fmaf(diff,0,tab[0]) would yield NaN whenever
# diff overflows to inf (inf*0).  fcmp/eq + bt compile naturally at -O1.
_LIFT = (
    '#include <math.h>\n'
    'float f(float t, const float *tab)\n'
    '{\n'
    '    if (t == 0.0f)\n'
    '        return tab[0];\n'
    '    return fmaf(tab[1] - tab[0], t, tab[0]);\n'
    '}\n')


class SH2L(SH2):
    """SH2 + call_leaf(): load arbitrary *initial registers* (r0-r15, fr0-fr15),
    required for the interp leaf's non-ABI entry (r0/r1/fr0 -> fr2), which
    cpu.call() cannot seed.  Line-for-line copy of SH2.call()'s body (the rosetta
    used by c/tests/test_interp_leaves.py).
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
    """Compile the lift + the fmaf shim with gcc 3.4.6, link at LINK_BASE,
    objcopy the .text section, return (blob_bytes, {sym: addr})."""
    os.makedirs(STUB_INC, exist_ok=True)
    os.makedirs(WORK, exist_ok=True)
    with open(os.path.join(STUB_INC, 'stdint.h'), 'w') as f:
        f.write(_STDINT)
    with open(os.path.join(STUB_INC, 'math.h'), 'w') as f:
        f.write(_MATH)
    with open(SHIM_SRC, 'w') as f:
        f.write(_SHIM)
    with open(SRC, 'w') as f:
        f.write(_LIFT)

    obj = os.path.join(WORK, 'f32leaf.o')
    shm = os.path.join(WORK, 'fmaf_shim.o')
    elf = os.path.join(WORK, 'f32leaf.elf')
    blb = os.path.join(WORK, 'blob.bin')

    subprocess.run(
        [XGCC, '-B', XGCC_B, '-m2e', '-O1', '-fomit-frame-pointer',
         '-c', SRC, '-o', obj, '-I', STUB_INC],
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


def cells_ram(a, b, base=CELL_BASE):
    """Two f32 values -> sparse ram bytes (each 4 bytes, the emulator's float
    storage order is the same byte-order as rdf() uses)."""
    m = {}
    for off, v in ((0, a), (4, b)):
        m.update({base + off + i: c for i, c in
                  enumerate(struct.pack('>f', ts(v)))})
    return m


# ============================================================================
# Table / vector generation
# ============================================================================
FLT_MAX = 3.4028234663852886e+38  # IEEE-754 single-precision max

# f32 table pairs (each a 2-float interpolation: out = a + (b-a)*t).
# (0,1) / (0,-1): unit endpoints. (FLT_MAX,-FLT_MAX) & (-1e38,1e38): extremes
# (bit-exact overflow => both sides produce the same fma result). denormal/edge.
TABLES = [
    (0.0, 1.0),
    (0.0, -1.0),
    (1.0, 0.0),
    (-1.0, 1.0),
    (FLT_MAX, -FLT_MAX),
    (-FLT_MAX, FLT_MAX),
    (1e38, -1e38),
    (-1e38, 1e38),
    (1.17549435e-38, -1.17549435e-38),   # subnormal-ish / denormal edge
    (0.5, 2.0),
    (3.0, -7.0),
]

T_CHOICES = (0.0, 0.5, 1.0)              # exact-product subset

gen_vectors = None  # (kept for symmetry with the u8/u16; built inline below)


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    blob, syms = build_blob()
    entry = syms.get(ENTRY, LINK_BASE)
    base = {LINK_BASE + i: blob[i] for i in range(len(blob))}

    # ROM instance is only needed for the real-rom read; the f32 cells live in
    # the sparse overlay so we don't read tables from the ROM image.
    with open(os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin'), 'rb') as f:
        rom = f.read()
    rom_cpu = SH2L(rom)
    blb_cpu = SH2L(rom)                     # fresh SH2 instance for the blob

    # deterministic grid first, then seeded padding to exactly N
    vecs = [(0, t, pair) for pair in TABLES for t in T_CHOICES]
    rng = make_rng(0x2678)
    while len(vecs) < n:
        pair = TABLES[rng.randrange(len(TABLES))]
        vecs.append((0, rng.choice(T_CHOICES), pair))
    vecs = vecs[:n]

    rom_res, blb_res = [], []
    for i, t, pair in vecs:
        cm = cells_ram(pair[0], pair[1])
        # ROM side: non-ABI r0/r1/fr0 -> fr2 (arbitrary-register driver)
        rom_cpu.call_leaf(ROM_ADDR, regs={0: i, 1: CELL_BASE},
                          fr={0: t}, ram=cm)
        rom_res.append(f2bits(rom_cpu.fr[2]))
        # blob side: gcc ABI r4=ptr/fr4=t -> fr0, code in the same ram overlay
        merr = dict(base); merr.update(cm)
        blb_cpu.call(entry, r4=CELL_BASE, ram=merr, fr={4: t})
        blb_res.append(f2bits(blb_cpu.fr[0]))

    mism = []
    for k, (e, h) in enumerate(zip(rom_res, blb_res)):
        if e != h:
            i, t, pair = vecs[k]
            mism.append('vec#%d i=%d t=%g pair=(%g,%g) '
                        'ROM(fr2)=0x%08X blob(fr0)=0x%08X'
                        % (k, i, t, pair[0], pair[1], e, h))
            if len(mism) >= 5:
                break

    total = len(mism)
    if total == 0:
        print('verify_interp_f32: ROM @0x%X vs gcc-3.4.6 blob @0x%X '
              '(entry 0x%X), %d vectors, 0 mismatches — OK'
              % (ROM_ADDR, LINK_BASE, entry, n))
    else:
        print('verify_interp_f32: %d vectors, %d mismatches — FAIL'
              % (n, total))
        for s in mism:
            print('    ' + s)
    sys.exit(0 if total == 0 else 1)


if __name__ == '__main__':
    main()