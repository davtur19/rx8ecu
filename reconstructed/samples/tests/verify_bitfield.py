#!/usr/bin/env python3
"""
verify_bitfield.py — Lotto-2 validation of rx8_bitfield_extract_merge @0x48C8.

Target: rx8_bitfield_extract_merge @0x48C8 (roms/stock/60E1D400.bin)
Source : reconstructed/samples/src/rx8_bitfield_extract_merge.c
  frexp-style float decomposition: x = sig * 2^e, sig in [1.0, 2.0), into a
  (exponent word, significand word) pair for checkFloatValidity @0x46CC.

Calling convention (deduced from the ROM disassembly at 0x48C8, and confirmed
against the single caller checkFloatValidity @0x46CC):
  - float argument arrives in FR4 (FPU register).  gcc-3.4.6 emits `flds fr4,
    fpul; sts fpul,r2` to read it, and the ROM reads the same FR4.
  - result pointer:  NON-ABI on the ROM side.  The caller pushes it on the
    stack BEFORE the jsr:
        mov.l r15,@-r15      ; delay slot: push &(8-byte buffer)
    so the ROM reads the pointer with `mov.l @r15,rN`.  On the era-ROM
    (gcc 3.4.6) blob side the same C compiles to the STANDARD SH-2E ABI
    instead: `float fr4, uint32_t* r4`.

Method (mirrors verify_gcc346.py / verify_bytepack.py)
-------------------------------------------------------
  (a) writes stub stdint.h once (shared /tmp/verify_gcc346/inc),
  (b) compiles the reconstructed source with the era-ROM recipe
      -m2e -O1 -fomit-frame-pointer via the archived sh-elf gcc 3.4.6, links
      at 0x4000 (+libgcc 3.4.6), extracts the self-contained .text blob,
  (c) drives the REAL ROM bytes @0x48C8 and the blob @0x4000 side by side on
      the same vectors:
        ROM :  fr4 = float ;                 [r15] = 4-byte ptr to out buffer
        blob:  fr4 = float ;  r4   = ptr to out buffer
      The caller-supplied "8-byte buffer" is a RAM address (0xFFFFDF80) in the
      emulated overlay; both sides write out[0] (exponent) and out[1]
      (significand) there, and the harness compares the 8 written bytes,
  (d) a pure-Python oracle of the described semantics cross-checks both sides.

Emulator-gap note: the tools/sh2emu.py `xtrct` register-role fix is carried
over from verify_gcc346.py.  This blob emits no xtrct (the source has no 64-bit
shift), so it is inert — kept only for consistency with the verified baseline.

Exclusions: NONE.  NaN/Inf (exponent 0xFF path) are exercised on both sides —
the emulator does not crash on the FR4->general handoff and both sides agree;
NaN loses its sign in the fixed outputs by design.

Read-only w.r.t. the repo: everything written goes to /tmp.  verify_gcc346.py /
README.md / Makefile / tools/ are NOT touched.  Exit 0 iff 0 mismatches.

Usage:  python3 tests/verify_bitfield.py [N]   (default N = 3000)
"""
import os
import struct
import subprocess
import sys

TESTS = os.path.dirname(os.path.abspath(__file__))   # reconstructed/samples/tests
SAMPLES = os.path.dirname(TESTS)                      # reconstructed/samples
ROOT = os.path.dirname(os.path.dirname(SAMPLES))      # rx8ecu
sys.path.insert(0, TESTS)
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2  # noqa: E402
from common import load_cpu, make_rng  # noqa: E402

# ---- era-ROM toolchain ------------------------------------------------------
# NOTE: the brief named /home/davide/gcc346-build/gcc/gucc, but that driver is
# not present in the build tree.  xgcc — the real sh-elf gcc 3.4.6 driver used
# by every sibling Lotto-2 verify_*.py — is the identical compiler and is used
# here instead (same recipe, same -B path).
XGCC = '/home/davide/gcc346-build/gcc/xgcc'
XGCC_B = '/home/davide/gcc346-build/gcc'
LD = '/usr/bin/sh-elf-ld'
OBJCOPY = '/usr/bin/sh-elf-objcopy'
NM = '/usr/bin/sh-elf-nm'
LIBGCC = os.path.join(XGCC_B, 'libgcc.a')

STUB_INC = '/tmp/verify_gcc346/inc'      # stub stdint.h (shared, never committed)
WORK = '/tmp/verify_gcc346/work'         # objects / elf / blobs
LINK_BASE = 0x4000                       # fixed link base

ADDR_ROM = 0x48C8
ENTRY_SYM = 'rx8_bitfield_extract_merge'

SRC_DIR = os.path.join(SAMPLES, 'src')
INC_DIR = os.path.join(SAMPLES, 'include')

# ---- ROM-side emulated stack / output buffer --------------------------------
R15 = 0xFFFFDF00      # caller-supplied stack pointer (sh2emu.call default)
OUT = 0xFFFFDF80      # the "8-byte buffer" the result pointer targets

N_DEFAULT = 3000
SEED = ADDR_ROM

# IEEE-754 field masks + output-word constants (see source header).
SIGN_M   = 0x80000000
EXP_M    = 0x7F800000
SIG_MASK = 0x007FFFFF
SIG_IM   = 0x80000000     # implicit leading 1 at bit 31 of significand
EXP_SAT  = 0x00007FFF     # exponent word for Inf / NaN
EXP_ZERO = 0x00008001     # exponent word for +/-0.0 (sentinel -32767)
SIG_NAN  = 0xFFFFFFFF     # significand word for NaN

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

_LINKER = (
    'OUTPUT_FORMAT(elf32-sh)\n'
    'MEMORY { RAM (rx) : ORIGIN = 0x%X, LENGTH = 0x1000 }\n'
    'SECTIONS {\n'
    '  .text : { *(.text) *(.text.*) *(.rodata) *(.rodata.*) *(.rdata) } > RAM\n'
    '  /DISCARD/ : { *(.comment) *(.note*) *(.symtab) *(.strtab) '
    '*(.shstrtab) *(.debug*) }\n}\n' % LINK_BASE)

# ============================================================================
# Emulator-gap workaround (documented at function level) — inert for this blob.
# ============================================================================
_SH2_exec_orig = SH2._exec
_SH2_exec_ref = _SH2_exec_orig


def _xtrct_fixed(self, op, pc):
    if (op & 0xF00F) == 0x200D:                       # xtrct Rm,Rn
        m = (op >> 4) & 0xF
        n = (op >> 8) & 0xF
        self.r[n] = (((self.r[m] << 16) & 0xFFFF0000)
                     | ((self.r[n] >> 16) & 0xFFFF)) & 0xFFFFFFFF
        return
    return _SH2_exec_ref(self, op, pc)


SH2._exec = _xtrct_fixed


def bits2f(b):
    return struct.unpack('>f', struct.pack('>I', b & 0xFFFFFFFF))[0]


def ptr_bytes(addr, ptr):
    """4 bytes (big-endian) of `ptr` stored at `addr` (the pushed pointer)."""
    return {addr + i: (ptr >> (8 * (3 - i))) & 0xFF for i in range(4)}


# ============================================================================
# Pure-Python oracle of the deduced semantics (frexp-style decomposition).
# ============================================================================
def oracle(bits):
    exp8 = (bits & EXP_M) >> 23
    mant = bits & SIG_MASK
    sign = bits & SIGN_M
    if exp8 == 0xFF:
        if mant == 0:                     # +/-Inf
            return (EXP_SAT | sign) & 0xFFFFFFFF, 0
        return EXP_SAT, SIG_NAN           # NaN: sign dropped
    if exp8 == 0:
        if mant == 0:                     # +/-0.0
            return (EXP_ZERO | sign) & 0xFFFFFFFF, 0
        frac = mant << 9
        e = 0
        while not (frac & SIG_IM):
            e -= 1
            frac <<= 1
        frac |= SIG_IM                 # implicit leading 1 after normalisation
        e -= 127
    else:
        e = exp8 - 127
        frac = (mant << 8) | SIG_IM
    return ((e & 0xFFFF) | sign) & 0xFFFFFFFF, frac & 0xFFFFFFFF


# ============================================================================
# Vector generation  (edge set + exponent sweep + seeded random bit patterns)
# ============================================================================
def gen_edge_bits():
    """Named special values / mask boundaries that exercise every branch."""
    return [
        0x00000000, 0x80000000,            # +0.0, -0.0
        0x00000001, 0x80000001,            # +min subnormal, -min subnormal
        0x00000002, 0x000FFFFF, 0x00200000, 0x00400000, 0x80400000,
        0x007FFFFF, 0x807FFFFF,            # subnormal sweep + boundary
        0x00800000, 0x80800000,            # min normal, -min normal
        0x00800001,                        # min normal + 1 ulp
        0x3F800000, 0xBF800000,            # +1.0, -1.0
        0x3F000000, 0x40000000,            # 0.5, 2.0
        0xC0200000, 0x40490FDB, 0x4048F5C3, 0x49742400,
        0x7F000000, 0xFF000000,            # exp 0xFE, mantissa 0, +/-
        0x7EFFFFFF, 0xFEFFFFFF,            # exp 0xFE, mantissa all-ones, +/-
        0x7F7FFFFF, 0xFF7FFFFF,            # +max normal, -max normal
        0x7F800001, 0xFF800001,            # signaling NaN (+ and - sign)
        0x7FC00000, 0xFFC00000,            # quiet NaN (+/-) — sign dropped
        0x7FFFFFFF, 0xFFFFFFFF,
        0x7FBFFFFF, 0xFFBFFFFF,            # NaN mantissa all-ones, no quiet bit
        0xDEADBEEF, 0xCAFEBABE, 0x12345678, 0xABCDEF01,
    ]


def gen_sweep():
    """One vector per exponent byte (0..0xFF) with a fixed random mantissa,
    hitting every exponent boundary (0x00 subnormal/zero, 0xFF Inf/NaN and the
    normal range 1..254) deterministically."""
    rng = make_rng(SEED ^ 0x5EED)
    mant = rng.getrandbits(23)
    sign = rng.getrandbits(1)
    return [(0x80000000 if sign else 0) | (exp << 23) | mant
            for exp in range(0x100)]


def gen_vectors(n):
    rng = make_rng(SEED)
    bits = gen_edge_bits() + gen_sweep()
    for _ in range(n):
        bits.append(rng.getrandbits(32))
    return bits


# ============================================================================
# Toolchain build
# ============================================================================
def ensure_stubs():
    os.makedirs(STUB_INC, exist_ok=True)
    p = os.path.join(STUB_INC, 'stdint.h')
    if not os.path.exists(p):
        with open(p, 'w') as f:
            f.write(_STDINT)


def build_blob():
    """Compile rx8_bitfield_extract_merge.c with gcc 3.4.6, link at 0x4000,
    extract .text.  Returns (blob_bytes, entry_addr)."""
    os.makedirs(WORK, exist_ok=True)
    base = os.path.join(WORK, 'bitfield')
    obj, elf, blb = base + '.o', base + '.elf', base + '.bin'

    subprocess.run(
        [XGCC, '-B', XGCC_B, '-m2e', '-O1', '-fomit-frame-pointer',
         '-c', os.path.join(SRC_DIR, 'rx8_bitfield_extract_merge.c'), '-o', obj,
         '-I', STUB_INC, '-I', SRC_DIR, '-I', INC_DIR],
        check=True, capture_output=True)

    ld_script = os.path.join(WORK, 'link346.ld')
    if not os.path.exists(ld_script):
        with open(ld_script, 'w') as f:
            f.write(_LINKER)
    subprocess.run([LD, '-T', ld_script, obj, LIBGCC, '-o', elf],
                   check=True, capture_output=True)
    subprocess.run([OBJCOPY, '-O', 'binary', '--only-section=.text', elf, blb],
                   check=True, capture_output=True)

    with open(blb, 'rb') as f:
        blob = f.read()
    nmproc = subprocess.run([NM, elf], capture_output=True, text=True)
    entry = LINK_BASE
    for line in nmproc.stdout.splitlines():
        parts = line.split()
        if (len(parts) == 3 and parts[1] == 'T'
                and parts[2].lstrip('_') == ENTRY_SYM):
            entry = int(parts[0], 16)
    return blob, entry


def overlay(blob):
    return {LINK_BASE + i: blob[i] for i in range(len(blob))}


# ============================================================================
# Per-side runners (both write the 8-byte result buffer at OUT)
# ============================================================================
def rom_run(cpu, bits):
    """ROM bytes: float in fr4; result pointer pushed at [r15] (NON-ABI)."""
    cpu.call(ADDR_ROM, fr={4: bits2f(bits)}, ram=ptr_bytes(R15, OUT))
    return cpu.rd(OUT, 4), cpu.rd(OUT + 4, 4)


def blob_run(cpu, bits, base, entry):
    """Blob: float in fr4; result pointer in r4 (standard SH-2E ABI)."""
    cpu.call(entry, fr={4: bits2f(bits)}, r4=OUT, ram=dict(base))
    return cpu.rd(OUT, 4), cpu.rd(OUT + 4, 4)


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    ensure_stubs()
    blob, entry = build_blob()
    base = overlay(blob)

    cpu = load_cpu()                       # one CPU; call() resets state per run
    vecs = gen_vectors(n)
    mismatches = []
    for i, bits in enumerate(vecs):
        r = rom_run(cpu, bits)
        h = blob_run(cpu, bits, base, entry)
        o = oracle(bits)
        if r != h or r != o:
            mismatches.append(
                'vec#%d bits=0x%08X ROM=%08X,%08X blob=%08X,%08X oracle=%08X,%08X'
                % (i, bits, r[0], r[1], h[0], h[1], o[0], o[1]))
            if len(mismatches) >= 5:
                break

    name = 'bitfield_extract_merge'
    status = 'OK  ' if not mismatches else 'FAIL'
    print('%s %-22s @0x%-6X  n=%-5d  ROM-vs-blob/v-oracle mismatches=%d'
          % (status, name, ADDR_ROM, len(vecs), len(mismatches)))
    for s in mismatches[:5]:
        print('        ' + s)

    if mismatches:
        print('\nverify_bitfield: %d mismatch(es) — FAIL' % len(mismatches))
        sys.exit(1)
    print('\nverify_bitfield: %s OK (0 mismatch; %d edge + %d sweep + %d random)'
          % (name, len(gen_edge_bits()), len(gen_sweep()), n))
    sys.exit(0)


if __name__ == '__main__':
    main()