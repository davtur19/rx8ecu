#!/usr/bin/env python3
"""
verify_interp_s16.py — era-ROM toolchain (gcc 3.4.6) validation:
rx8_interpolate_s16_table @0x2690 (INT16 cells, pure leaf).

Closes the "ROM -> abstract C -> era-ROM toolchain (gcc 3.4.6)" loop on the
*behavioural* plane for the SIGNED-16-bit-cell linear-interpolation leaf, using
the same proven pattern as verify_interp16.py / verify_interp8.py: build with
the archived sh-elf gcc 3.4.6, link at 0x4000, objcopy the .text blob, load the
blob into tools/sh2emu.py through the sparse ram overlay, and compare it
against the real ROM bytes at 0x2690 on the same input vectors.

THREE ARMS (the s16 sibling of the two-arm u8/u16 scripts):
  1. ROM   @0x2690 run on tools/sh2emu.py with the arbitrary-register
     call_leaf() driver (r0/r1/fr0 -> fr2);
  2. blob  gcc-3.4.6-compiled lift run with cpu.call(r4=, r5=, fr=) (-> fr0);
  3. oracle pure-Python expected value of the interpolation formula computed
     with the same single-rounding fp semantics (fsub once, fmac once).
All three must agree bit-exactly (f2bits) for 0 mismatch to pass.

Calling convention (deduced from the ROM disassembly @0x2690, NOT from the host
prototype — this is the non-ABI leaf style shared by all three siblings):

    ROM  in: r0 = cell index i (already found by axis-search), r1 = pointer to
              the int16 cell array, fr0 = t in [0,1)
         out: fr2 = interpolated float (fr0 left untouched for the 2-D callers)

    blob in: the same C compiled by gcc 3.4.6 uses the standard SH ABI
              r4 = index, r5 = cells-pointer, fr4 = t
         out: fr0 = interpolated float

The leaf is byte-identical in shape to the u16 leaf @0x26D0 except for the
*missing* `extu.w`: the 16-bit cell loads feed fpul sign-extended, so negative
cells round-trip correctly through float (the s16 signature).

fmaf(): the C source calls fmaf() to reproduce the ROM's single-rounding
'fmac'.  gcc 3.4.6 has no fmac emission for fmaf() on the sh-2e; it compiles
it to an external call (jsr) whose target address is a literal-pool word in
the blob's own .text (the pool the ROM function itself never touches — the ROM
leaf has NO pool constants, only fldi0).  The harness links a tiny fmaf() shim
(in /tmp/verify_interp_s16/work/fmaf_shim.c, never committed) that implements
`a*b+c`; gcc 3.4.6 recognises the sh-2 'fmac' instruction and compiles that
shim to a single `fmac`, so the shim is genuinely single-rounded and bit-exact
with the ROM path — no double-precision / soft-float involved.

Vectors: the four spec'ed int16 tables {0,1} {0,-1} {-32768,32767}
{32767,-32768} plus a longer synthetic signed extremes/pattern table (so
interior edge indices beyond {0,1} are exercised too); t covers the exact
subset {0, 0.5, 1.0} on every index (incl. the i=count-1 t=0 clamp-high
no-read-past-end fast path) AND continuous random t on the interior — the
random-t vectors push the single-rounding fmac path, which is exactly where a
twice-rounded C lift would diverge.

Comparison: all three arms' IEEE single-precision bit patterns must match.

Read-only w.r.t. the repo: the C lift is embedded below and written to /tmp
(the src/ lift is proposed separately — NOT committed by this script).
Exit code 0 iff 0 mismatches.

Usage:  python3 verify_interp_s16.py [N]   (default N = 3000)
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

from sh2emu import SH2, MASK, ts, f2bits, s16  # noqa: E402
from common import make_rng  # noqa: E402

# ---- era-ROM toolchain ------------------------------------------------------
XGCC = '/home/davide/gcc346-build/gcc/xgcc'
XGCC_B = '/home/davide/gcc346-build/gcc'
LD = '/usr/bin/sh-elf-ld'
OBJCOPY = '/usr/bin/sh-elf-objcopy'
NM = '/usr/bin/sh-elf-nm'

STUB_INC = '/tmp/verify_interp_s16/inc'    # stub stdint.h / math.h (never committed)
WORK = '/tmp/verify_interp_s16/work'       # objects / ls / blobs / lift / shim
LINK_BASE = 0x4000                         # fixed link base
SHIM_SRC = os.path.join(WORK, 'fmaf_shim.c')
LIFT_SRC = os.path.join(WORK, 'rx8_interpolate_s16_table.c')

SRC_DIR = os.path.join(SAMPLES, 'src')
INC_DIR = os.path.join(SAMPLES, 'include')

# The cells live in the sparse ram overlay so the emulator reads them.
CELL_BASE = 0x2000                         # the int16 table backing region

ROM_ADDR = 0x2690                          # the real ROM bytes @60E1D400.bin
ENTRY = 'rx8_interpolate_s16_table'        # blob symbol (gcc ABI)
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

# The proposed src/ lift, embedded here so the test is self-contained and
# reproducible (written to WORK, never committed by this script).  It includes
# "rx8_samples.h" exactly like the verified u16/u8 siblings, so the identical
# compile flags work.
_LIFT = (
    '/* rx8_interpolate_s16_table.c — INT16-TABLE LINEAR-INTERPOLATION LEAF\n'
    ' * ROM @0x2690. s16 sibling of the u16 leaf @0x26D0 / u8 leaf @0x26B0:\n'
    ' * same non-ABI r0/r1/fr0 -> fr2 convention, same t==0 fast path, the\n'
    ' * only difference being that the 16-bit loads feed fpul SIGN-extended\n'
    ' * (no `extu.w`), so negative cells round-trip correctly.  The combine is\n'
    ' * one `fmac fr0,fr1,fr2` (single rounding) -> fmaf() below.\n'
    ' */\n'
    '#include <stdint.h>\n'
    '#include <math.h>\n'
    '\n'
    '#include "rx8_samples.h"\n'
    '\n'
    '#define RX8_INTERP_S16_T_ZERO 0.0f\n'
    '\n'
    'float rx8_interpolate_s16_table(int32_t index, const int16_t *cells, float t)\n'
    '{\n'
    '    float v0;\n'
    '\n'
    '    /* Read cell[index] first, always — the sign-extended 16-bit load and\n'
    '     * the fpul store execute before the t==0 test (and its delay-slot\n'
    '     * float conversion) regardless of t.  This is the whole reason the\n'
    '     * clamp-high case never touches cells[count]. */\n'
    '    v0 = (float)cells[index];\n'
    '\n'
    '    if (t == RX8_INTERP_S16_T_ZERO) {\n'
    '        return v0;\n'
    '    }\n'
    '\n'
    '    {\n'
    '        const float v1 = (float)cells[index + 1];\n'
    '\n'
    '        /* v1 - v0 is one fsub (single rounding); fmaf(t, diff, v0) is the\n'
    '         * one fmac — t*(v1-v0) + v0 rounded once, exactly like the\n'
    '         * hardware. */\n'
    '        return fmaf(t, v1 - v0, v0);\n'
    '    }\n'
    '}\n')


class SH2L(SH2):
    """SH2 + call_leaf(): load arbitrary *initial registers* (r0-r15, fr0-fr15),
    required for the interp-s16 leaf's non-ABI entry (r0/r1/fr0 -> fr2), which
    cpu.call() cannot seed.  Line-for-line copy of SH2.call()'s body (the
    rosetta used by the u8/u16 harnesses and c/tests/test_interp_leaves.py).
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
    """Write the embedded lift + the fmaf shim to WORK, compile with gcc 3.4.6,
    link at LINK_BASE, objcopy the .text section, return (blob_bytes, syms)."""
    os.makedirs(STUB_INC, exist_ok=True)
    os.makedirs(WORK, exist_ok=True)
    with open(os.path.join(STUB_INC, 'stdint.h'), 'w') as f:
        f.write(_STDINT)
    with open(os.path.join(STUB_INC, 'math.h'), 'w') as f:
        f.write(_MATH)
    with open(LIFT_SRC, 'w') as f:
        f.write(_LIFT)
    with open(SHIM_SRC, 'w') as f:
        f.write(_SHIM)

    obj = os.path.join(WORK, 'interp.o')
    shm = os.path.join(WORK, 'fmaf_shim.o')
    elf = os.path.join(WORK, 'interp.elf')
    blb = os.path.join(WORK, 'blob.bin')

    subprocess.run(
        [XGCC, '-B', XGCC_B, '-m2e', '-O1', '-fomit-frame-pointer',
         '-c', LIFT_SRC, '-o', obj, '-I', STUB_INC, '-I', SRC_DIR, '-I', INC_DIR],
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
    """int16 cell array -> sparse ram bytes (big-endian 16-bit cells)."""
    m = {}
    for k, c in enumerate(cells):
        m[base + k * 2] = (c >> 8) & 0xFF
        m[base + k * 2 + 1] = c & 0xFF
    return m


# ============================================================================
# Oracle (arm 3): the interpolation formula with the ROM's exact single-
# rounding fp semantics — t rounded to f32, cells widened sign-extended,
# one fsub (v1-v0) and one fmac (t*diff+v0).
# ============================================================================
def oracle(i, t, cells):
    t_s = ts(t)
    v0 = ts(float(s16(cells[i])))          # sign-extended int16 -> float (exact)
    if t_s == 0.0:                         # ROM's fcmp/eq fr0,fldi0 path
        return v0
    v1 = ts(float(s16(cells[i + 1])))
    diff = ts(v1 - v0)                     # one fsub rounding
    return ts(t_s * diff + v0)             # one fmac rounding (fused)
    # NB: this is NOT the same as ts(ts(t_s*diff) + v0) — a twice-rounded C
    # `v0 + t*(v1-v0)` diverges from the ROM at the last bit ~1% of random t.


# ============================================================================
# Tables / vectors
# ============================================================================
# The four spec'ed int16 tables: zero-crossing pair, full negative->positive
# range, and the wrap pair INT16_MAX -> INT16_MIN (0x8000 == -32768).  Plus a
# longer synthetic signed extremes/pattern table so interior edge indices
# beyond {0,1} are exercised too (same "proven pattern" as the u8/u16 scripts).
TABLES = (
    [0, 1],
    [0, -1],
    [-32768, 32767],                       # INT16_MIN -> INT16_MAX
    [0x7FFF, 0x8000],                      # INT16_MAX -> INT16_MIN (wrap)
    [0, -32768, 32767, 1, -1, 32767, -32768, 0x7FFF],
)


def gen_vectors(cells):
    """Edge vectors: every index with t=0 (both clamped ends incl. the i=n-1
    no-read-past-end fast path), plus t at 0.5 and 1.0 across the interior.
    t in {0, 0.5, 1.0} is the exact-product subset for which the shim's single
    fmac and the ROM's fmac are provably identical (0*b and 1*b exact, 0.5*b is
    a power-of-two rescale of a float mantissa)."""
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

    tables = list(TABLES)

    # deterministic grid first, then seeded padding to exactly N.  The padding
    # draws continuous random t (the fmac single-rounding stress path).
    vecs = []
    for cells in tables:
        vecs += [(i, t, cells) for (i, t) in gen_vectors(cells)]
    rng = make_rng(ROM_ADDR)
    while len(vecs) < n:
        cells = tables[rng.randrange(len(tables))]
        i = rng.randrange(0, len(cells) - 1)
        vecs.append((i, rng.random(), cells))
    vecs = vecs[:n]

    mism = []
    for k, (i, t, cells) in enumerate(vecs):
        cm = cells_ram(cells)
        # arm 1 — ROM side: non-ABI r0/r1/fr0 -> fr2 (arbitrary-register driver)
        rom_cpu.call_leaf(ROM_ADDR, regs={0: i, 1: CELL_BASE},
                          fr={0: t}, ram=cm)
        rom_bits = f2bits(rom_cpu.fr[2])
        # the ROM leaf must leave fr0 (= t) untouched for the 2-D callers
        fr0_kept = f2bits(rom_cpu.fr[0]) == f2bits(ts(t))
        # arm 2 — blob side: gcc ABI r4/r5/fr4 -> fr0, code in the same ram
        mer = dict(base); mer.update(cm)
        blb_cpu.call(entry, r4=i, r5=CELL_BASE, ram=mer, fr={4: t})
        blb_bits = f2bits(blb_cpu.fr[0])
        # arm 3 — oracle: pure-Python interpolation formula
        exp_bits = f2bits(oracle(i, t, cells))

        if not (rom_bits == blb_bits == exp_bits) or not fr0_kept:
            mism.append(
                'vec#%d i=%d t=%.9g cells=%s ROM(fr2)=0x%08X blob(fr0)=0x%08X '
                'oracle=0x%08X fr0_kept=%s'
                % (k, i, t, cells, rom_bits, blb_bits, exp_bits, fr0_kept))
            if len(mism) >= 5:
                break

    total = len(mism)
    if total == 0:
        print('verify_interp_s16: ROM @0x%X vs gcc-3.4.6 blob @0x%X '
              '(entry 0x%X), %d vectors, 0 mismatches — OK'
              % (ROM_ADDR, LINK_BASE, entry, n))
    else:
        print('verify_interp_s16: %d vectors, %d mismatches — FAIL'
              % (n, total))
        for s in mism:
            print('    ' + s)
    sys.exit(0 if total == 0 else 1)


if __name__ == '__main__':
    main()
