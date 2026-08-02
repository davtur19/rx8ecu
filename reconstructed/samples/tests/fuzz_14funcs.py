#!/usr/bin/env python3
"""
fuzz_14funcs.py — high-intensity fuzz of the 14 Lotto-1 functions validated by
verify_gcc346.py.

Purpose
-------
verify_gcc346.py closes the "ROM -> abstract C -> era-ROM toolchain (gcc 3.4.6)"
loop with N=4000..20000 seeded vectors per function.  This script stress-tests
the SAME 14 functions with 50k..100k vectors per function using NEW rng seeds
(the harness seeds 0x2304/0x366B8/... are deliberately NOT reused) and a much
broader special-value set, hunting edge cases the seeded vector sets missed:

  * 0, +-1, +-2, powers of two, INT32_MIN/MAX, 0xFFFF/0x10000,
  * values with dense bit patterns,
  * pairs (a,-a), (a,a), (0,a), (a,0), (a,~a),
  * full cross-product of special values for every two-arg family,
  * float kind: raw 32-bit bit patterns (NaN/+-inf/denormals/-0/+-0) plus
    uniform randoms over wider ranges than the harness,
  * idx_table RAM family: indices 0..255 (full byte range, harness used 0..8)
    and 16-bit special words.

Methodology (copied and adapted from verify_gcc346.py)
-------------------------------------------------------
For every function:
  1. compile the reconstructed source with the era-ROM gcc 3.4.6 recipe
     `-m2e -O1 -fomit-frame-pointer` via /home/davide/gcc346-build/gcc/xgcc,
  2. link at 0x4000 pulling libgcc 3.4.6 helpers (___sdivsi3/___udivsi3/
     ___ashlsi3/___lshrsi3/___ashrsi3/___ashiftrt_r4_8),
  3. objcopy --only-section=.text -> self-contained blob,
  4. load the blob into tools/sh2emu.py through the sparse `ram` overlay,
  5. generate N vectors (edges grid + seeded random with NEW seed),
  6. run BOTH the real ROM bytes and the blob on the same vectors and compare
     r0 (and the RAM slot side-effects for idx_table).

ROM convention for the L-2 helpers (div32_*/shift_*): args in r0/r1, result in
r0 — the ROM side uses the call_regs() step-loop driver; the gcc-3.4.6 blob
uses the standard r4/r5 ABI via cpu.call().

Emulator-gap workaround (same as verify_gcc346.py): sh2emu.py's `xtrct` has the
two register roles swapped; the era-ROM gcc emits xtrct inside
rx8_multiply32_saturating, so the corrected semantics are patched onto the SH2
class once, before any call.

Timebox: per-function wall time is measured; if it exceeds FUZZ_TIMEBOX (~3 min)
the function is re-run with N reduced to 30k and the reduction is documented.

This script is read-only w.r.t. the repo: everything it writes goes to /tmp.
Exit code is non-zero iff any function reports mismatch(es).

Usage:  python3 tests/fuzz_14funcs.py [TARGET_N] [REDUCED_N]
        (defaults: 100000 / 30000)
"""
import os
import struct
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

# ---- era-ROM toolchain ------------------------------------------------------
XGCC = '/home/davide/gcc346-build/gcc/xgcc'
XGCC_B = '/home/davide/gcc346-build/gcc'
LD = '/usr/bin/sh-elf-ld'
OBJCOPY = '/usr/bin/sh-elf-objcopy'
NM = '/usr/bin/sh-elf-nm'
LIBGCC = os.path.join(XGCC_B, 'libgcc.a')

STUB_INC = '/tmp/verify_gcc346/inc'        # shared with verify_gcc346.py
WORK = '/tmp/fuzz_14funcs/work'            # fuzz-specific work dir
LINK_BASE = 0x4000

SRC_DIR = os.path.join(SAMPLES, 'src')
INC_DIR = os.path.join(SAMPLES, 'include')

# ============================================================================
# Emulator-gap workaround — XTRCT (documented above; copied from verify_gcc346)
# ============================================================================
_SH2_exec_ref = SH2._exec


def _xtrct_fixed(self, op, pc):
    if (op & 0xF00F) == 0x200D:                       # xtrct Rm,Rn
        m = (op >> 4) & 0xF
        n = (op >> 8) & 0xF
        self.r[n] = (((self.r[m] << 16) & 0xFFFF0000)
                     | ((self.r[n] >> 16) & 0xFFFF)) & 0xFFFFFFFF
        return
    return _SH2_exec_ref(self, op, pc)


SH2._exec = _xtrct_fixed

# ============================================================================
# Emulator-gap workaround — FPU overflow in ts()
# sh2emu.ts() uses struct.pack('>f'), which raises OverflowError when an FPU
# add/sub/mul/div result exceeds single-precision range (e.g. MAX_FLT+MAX_FLT).
# The real SH-2E FPU follows IEEE-754 and saturates to +-inf.  Patch the
# module-level `ts` global (referenced by _exec) to clamp overflow to +-inf.
# ============================================================================
import sh2emu  # noqa: E402  (module import for the ts global patch)

_sh2emu_ts_ref = sh2emu.ts


def _ts_clamped(x):
    try:
        return struct.pack('>f', x)
    except OverflowError:
        return b'\x7f\x80\x00\x00' if x > 0 else b'\xff\x80\x00\x00'


def _ts_ieee(x):
    return struct.unpack('>f', _ts_clamped(x))[0]


sh2emu.ts = _ts_ieee

# ============================================================================
# Stub headers / linker script (same as verify_gcc346.py)
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
    'float fabsf(float x);\n#endif\n')

_LINKER = (
    'OUTPUT_FORMAT(elf32-sh)\n'
    'MEMORY { RAM (rx) : ORIGIN = 0x%X, LENGTH = 0x1000 }\n'
    'SECTIONS {\n'
    '  .text : { *(.text) *(.text.*) *(.rodata) *(.rodata.*) *(.rdata) } > RAM\n'
    '  /DISCARD/ : { *(.comment) *(.note*) *(.symtab) *(.strtab) '
    '*(.shstrtab) *(.debug*) }\n}\n' % LINK_BASE)

# ============================================================================
# Function config — same 14 functions / kinds / addresses as verify_gcc346.py.
# The `fuzz_seed` values are NEW (distinct from the harness seeds in
# verify_gcc346.py), derived from a single master fuzz seed.
# ============================================================================
_FUZZ_MASTER = 0x5EEDF00D

# Index-table RAM family geometry (mirrors harness_idx_table.py).
IDX_BASE = 0xFFFFD998
IDX_STRIDE = 0x46C


def idx_paddr(idx):
    return (IDX_BASE + (idx & 0xFF) * IDX_STRIDE) & 0xFFFFFFFF


def idx_seed(idx, w0, w2, w4):
    a = idx_paddr(idx)
    return {a: (w0 >> 8) & 0xFF, a + 1: w0 & 0xFF,
            a + 2: (w2 >> 8) & 0xFF, a + 3: w2 & 0xFF,
            a + 4: (w4 >> 8) & 0xFF, a + 5: w4 & 0xFF}


def idx_read(cpu, idx):
    a = idx_paddr(idx)
    return ((cpu.ram.get(a, 0) << 8) | cpu.ram.get(a + 1, 0),
            (cpu.ram.get(a + 2, 0) << 8) | cpu.ram.get(a + 3, 0),
            (cpu.ram.get(a + 4, 0) << 8) | cpu.ram.get(a + 5, 0))


def f32b(x):   # IEEE-754 single big-endian bit pattern of a python float
    return struct.unpack('>I', struct.pack('>f', x))[0]


def bits2f(b):
    return struct.unpack('>f', struct.pack('>I', b & 0xFFFFFFFF))[0]


FUNCS = {
    's32_saturate': {
        'addr_rom': 0x2304, 'src': 'rx8_s32_saturate.c', 'kind': 'r32x2',
        'entry_sym': 'rx8_add_s32_saturate', 'fuzz_seed': _FUZZ_MASTER + 1,
    },
    'immo_seed_mixer': {
        'addr_rom': 0x366B8, 'src': 'rx8_immo_seed_mixer.c', 'kind': 'r32x2',
        'entry_sym': 'rx8_immo_seed_mixer', 'fuzz_seed': _FUZZ_MASTER + 2,
    },
    'add16bit_saturate': {
        'addr_rom': 0x2460, 'src': 'rx8_add16bit_saturate.c', 'kind': 'r32x2',
        'entry_sym': 'rx8_add16bit_saturate', 'fuzz_seed': _FUZZ_MASTER + 3,
    },
    'add_saturate_8bit': {
        'addr_rom': 0x2478, 'src': 'rx8_add_saturate_8bit.c', 'kind': 'r32x2',
        'entry_sym': 'rx8_add_saturate_8bit', 'fuzz_seed': _FUZZ_MASTER + 4,
    },
    'multiply32_saturating': {
        'addr_rom': 0x231C, 'src': 'rx8_multiply32_saturating.c', 'kind': 'r32x2',
        'entry_sym': 'rx8_multiply32_saturating', 'fuzz_seed': _FUZZ_MASTER + 5,
    },
    'complement_shift_u16': {
        'addr_rom': 0x2430, 'src': 'rx8_complement_shift_u16.c', 'kind': 'r32',
        'entry_sym': 'rx8_complement_shift_u16', 'fuzz_seed': _FUZZ_MASTER + 6,
    },
    'complement_shift_u32': {
        'addr_rom': 0x2440, 'src': 'rx8_complement_shift_u32.c', 'kind': 'float',
        'entry_sym': 'rx8_complement_shift_u32', 'fuzz_seed': _FUZZ_MASTER + 7,
    },
    'idx_table': {
        'addr_rom': None, 'src': 'rx8_index_table.c', 'kind': 'ram',
        'entry_sym': None, 'fuzz_seed': _FUZZ_MASTER + 8,
        'leaves': {
            'clr':   (0x0068780, 'rx8_index_table_clear'),
            'step':  (0x006879C, 'rx8_index_table_step'),
            'step2': (0x00687C8, 'rx8_index_table_step2'),
            'dec':   (0x00687F4, 'rx8_index_table_dec'),
        },
    },
    'div32_signed': {
        'addr_rom': 0x3FE8, 'src': 'rx8_div32_signed.c', 'kind': 'r0r1',
        'entry_sym': 'rx8_div32_signed', 'fuzz_seed': _FUZZ_MASTER + 9,
    },
    'div32_unsigned': {
        'addr_rom': 0x409C, 'src': 'rx8_div32_unsigned.c', 'kind': 'r0r1',
        'entry_sym': 'rx8_div32_unsigned', 'fuzz_seed': _FUZZ_MASTER + 10,
    },
    'shift_left_logical': {
        'addr_rom': 0x4308, 'src': 'rx8_shift_left_logical.c', 'kind': 'r0r1',
        'entry_sym': 'rx8_shift_left_logical', 'fuzz_seed': _FUZZ_MASTER + 11,
    },
    'shift_right_arithmetic': {
        'addr_rom': 0x43C8, 'src': 'rx8_shift_right_arithmetic.c',
        'kind': 'r0r1', 'entry_sym': 'rx8_shift_right_arithmetic',
        'fuzz_seed': _FUZZ_MASTER + 12,
    },
    'shift_right_logical': {
        'addr_rom': 0x44E0, 'src': 'rx8_shift_right_logical.c', 'kind': 'r0r1',
        'entry_sym': 'rx8_shift_right_logical_r0',
        'fuzz_seed': _FUZZ_MASTER + 13,
    },
    'shift_right_8': {
        'addr_rom': 0x467A, 'src': 'rx8_shift_right_8.c', 'kind': 'r0',
        'entry_sym': 'rx8_shift_right_8', 'fuzz_seed': _FUZZ_MASTER + 14,
    },
}

# ============================================================================
# Special-value catalogue (fuzz targets requested by the task)
# ============================================================================
POW2 = [1 << i for i in range(32)]

SPECIAL = [
    # 0, +-1, +-2
    0x00000000, 0x00000001, 0x00000002, 0xFFFFFFFF, 0xFFFFFFFE,
    0x00000003, 0xFFFFFFFD,
    # INT32_MIN / INT32_MAX and neighbours
    0x7FFFFFFF, 0x7FFFFFFE, 0x80000000, 0x80000001, 0x80000002,
    0x3FFFFFFF, 0x40000000, 0xC0000000, 0x20000000, 0xE0000000,
    # 0xFFFF / 0x10000 and byte boundaries
    0x0000FFFF, 0x00010000, 0xFFFF0000, 0x00007FFF, 0x00008000,
    0xFFFFFF00, 0xFFFFFF80, 0xFFFFFFF0, 0xFFFFFFFC,
    0x0000007F, 0x00000080, 0x000000FF, 0x00000100,
    0x00000010, 0x00000020, 0x0000001F, 0x00000021, 0x00000008, 0x00000004,
    # dense bit patterns
    0x55555555, 0xAAAAAAAA, 0x33333333, 0xCCCCCCCC,
    0xF0F0F0F0, 0x0F0F0F0F, 0xFF00FF00, 0x00FF00FF,
    0xDEADBEEF, 0xCAFEBABE, 0x12345678, 0x89ABCDEF,
    0x76543210, 0xFEEDFACE, 0x55AAAA55, 0x0FFFFFF0,
] + POW2

# Float bit patterns: 0/-0, 1/-1, 2/-2, 0.5, 3, NaN/-NaN, +-inf,
# float max/min-normal, denormals, dense raw words.
SPECIAL_F = [
    0x00000000, 0x80000000, 0x3F800000, 0xBF800000,
    0x40000000, 0xC0000000, 0x3F000000, 0x40400000,
    0x7FC00000, 0xFFC00000, 0x7F800000, 0xFF800000,
    0x7F7FFFFF, 0xFF7FFFFF, 0x00800000, 0x807FFFFF,
    0x00000001, 0x80000001, 0xFFFFFFFF, 0x7FFFFFFF,
    0x00000002, 0x0000FFFF, 0x00010000, 0x4B800000,
]

SPECIAL16 = [
    0x0000, 0x0001, 0x0002, 0x0004, 0x0008, 0x0010, 0x0020,
    0x007F, 0x0080, 0x00FF, 0x0100, 0x03FF, 0x0464, 0x0465,
    0x3FFF, 0x4000, 0x7FFF, 0x8000, 0x8001, 0xC000, 0xFFFE, 0xFFFF,
]

# Index values: full byte range covered by the random stream; edge grid pins
# the harness range (0..8) plus the wrap boundary (0xFF) and high byte.
IDX_EDGES = [0, 1, 2, 3, 7, 8, 9, 0x7F, 0x80, 0xFE, 0xFF]

FUZZ_TIMEBOX = 180.0    # seconds per function before N is reduced to REDUCED_N
TARGET_N = 100000       # default random vectors per function
REDUCED_N = 30000       # timebox fallback

# ============================================================================
# Toolchain build
# ============================================================================
_stub_done = [False]
_blob_cache = {}


def ensure_stubs():
    if _stub_done[0]:
        return
    os.makedirs(STUB_INC, exist_ok=True)
    with open(os.path.join(STUB_INC, 'stdint.h'), 'w') as f:
        f.write(_STDINT)
    with open(os.path.join(STUB_INC, 'math.h'), 'w') as f:
        f.write(_MATH)
    _stub_done[0] = True


def build_blob(name):
    """Compile src with gcc 3.4.6, link at 0x4000, extract .text blob.

    Returns (blob_bytes, {symbol: linked_absolute_addr})."""
    os.makedirs(WORK, exist_ok=True)
    cfg = FUNCS[name]
    base = os.path.join(WORK, name)
    obj, elf, blb = base + '.o', base + '.elf', base + '.bin'

    subprocess.run(
        [XGCC, '-B', XGCC_B, '-m2e', '-O1', '-fomit-frame-pointer',
         '-c', os.path.join(SRC_DIR, cfg['src']), '-o', obj,
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


def blob_for(name):
    if name not in _blob_cache:
        _blob_cache[name] = build_blob(name)
    return _blob_cache[name]


def ram_overlay(blob):
    return {LINK_BASE + i: blob[i] for i in range(len(blob))}


# ============================================================================
# Vector generation  (fuzz seeds — NOT the harness seeds)
# ============================================================================
def _desc(kind, *vals):
    if kind == 'r32x2':
        return 'a=0x%08X b=0x%08X' % vals
    if kind == 'r0r1':
        return 'r0=0x%08X r1=0x%08X' % vals
    if kind == 'r32':
        return 'a=0x%08X' % vals
    if kind == 'r0':
        return 'r0=0x%08X' % vals
    if kind == 'float':
        return 't=0x%08X v=0x%08X a=0x%08X' % vals
    raise RuntimeError('no desc for %r' % kind)


def gen_vectors(name, n_random):
    """Deterministic vector stream for one function.

    Returns (vecs, n_edges): vecs = edge grid (special-value cross products
    + structured pairs) followed by `n_random` seeded random vectors.  The
    total vector count is len(vecs); n_edges is the structured prefix.
    """
    cfg = FUNCS[name]
    kind = cfg['kind']
    rng = make_rng(cfg['fuzz_seed'])
    vecs = []
    M = 0xFFFFFFFF

    if kind in ('r32x2', 'r0r1'):
        keys = ('r4', 'r5') if kind == 'r32x2' else ('r0', 'r1')
        # edge grid: full cross product of special values
        for a in SPECIAL:
            for b in SPECIAL:
                vecs.append(dict(zip(keys, (a, b))))
        n_edges = len(SPECIAL) ** 2
        # structured pairs + pure random
        for _ in range(n_random):
            a = rng.getrandbits(32)
            mode = rng.randrange(6)
            if mode == 0:
                b = (-a) & M            # (a, -a)
            elif mode == 1:
                b = a                   # (a, a)
            elif mode == 2:
                b, a = a, 0             # (0, a)
            elif mode == 3:
                b = 0                   # (a, 0)
            elif mode == 4:
                b = (~a) & M            # (a, ~a) dense complement
            else:
                b = rng.getrandbits(32)  # both random
            vecs.append(dict(zip(keys, (a, b))))
        return vecs, n_edges

    if kind in ('r32', 'r0'):
        key = 'r4' if kind == 'r32' else 'r0'
        for a in SPECIAL:
            vecs.append({key: a})
        n_edges = len(SPECIAL)
        for _ in range(n_random):
            a = rng.getrandbits(32)
            mode = rng.randrange(3)
            if mode == 1:
                a = (-a) & M
            elif mode == 2:
                a = (~a) & M
            vecs.append({key: a})
        return vecs, n_edges

    if kind == 'float':
        for t in SPECIAL_F:
            for v in SPECIAL_F:
                for adj in SPECIAL_F:
                    vecs.append({'t': t, 'v': v, 'adj': adj})
        n_edges = len(SPECIAL_F) ** 3
        for _ in range(n_random):
            if rng.randrange(2):
                t = f32b(rng.uniform(-1000, 1000))
                v = f32b(rng.uniform(-1000, 1000))
                adj = f32b(rng.uniform(-500, 500))
            else:
                t, v, adj = (rng.getrandbits(32), rng.getrandbits(32),
                             rng.getrandbits(32))
            vecs.append({'t': t, 'v': v, 'adj': adj})
        return vecs, n_edges

    if kind == 'ram':
        ops = ['clr', 'step', 'step2', 'dec']
        for op in ops:
            for idx in IDX_EDGES:
                for w in SPECIAL16:
                    vecs.append({'op': op, 'idx': idx, 'w': (w, w, w)})
        n_edges = len(ops) * len(IDX_EDGES) * len(SPECIAL16)
        for _ in range(n_random):
            op = rng.choice(ops)
            idx = rng.randint(0, 255)
            mode = rng.randrange(4)
            if mode == 0:
                w0 = w2 = w4 = rng.choice(SPECIAL16)
            elif mode == 1:
                w0, w2, w4 = (0xFFFF, rng.getrandbits(16), 0)
            elif mode == 2:
                w0, w2, w4 = (rng.getrandbits(16), rng.choice(SPECIAL16),
                              rng.getrandbits(16))
            else:
                w0, w2, w4 = (rng.getrandbits(16), rng.getrandbits(16),
                              rng.getrandbits(16))
            vecs.append({'op': op, 'idx': idx, 'w': (w0, w2, w4)})
        return vecs, n_edges

    raise RuntimeError('unsupported kind %r' % kind)


# ============================================================================
# Per-function evaluation
# ============================================================================
def call_int(cpu, addr, **kw):
    cpu.call(addr, **kw)
    return cpu.r[0] & 0xFFFFFFFF


def call_regs(cpu, entry, r0=0, r1=0):
    """Run a ROM leaf whose args arrive in r0 (and r1), result in r0.

    Only the ROM side needs this — the gcc-3.4.6 blob uses the r4/r5 ABI."""
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


def _em_args(kind, v):
    if kind in ('r32x2', 'r32'):
        kw = {'r4': v['r4']}
        if 'r5' in v:
            kw['r5'] = v['r5']
        return kw
    if kind in ('r0r1', 'r0'):
        kw = {'r4': v['r0']}
        if 'r1' in v:
            kw['r5'] = v['r1']
        return kw
    if kind == 'float':
        return {'fr': {4: bits2f(v['t']), 5: bits2f(v['v']), 6: bits2f(v['adj'])}}
    raise RuntimeError('no arg mapper for %r' % kind)


def run_function(name, n_random, base, syms):
    """Evaluate ROM vs blob over gen_vectors(name, n_random).

    Returns (mismatches, total_vecs, n_edges).  mismatches is a list of
    (index, desc, expected_rom, got_blob)."""
    cfg = FUNCS[name]
    kind = cfg['kind']
    cpu = load_cpu()
    vecs, n_edges = gen_vectors(name, n_random)
    total = len(vecs)

    rom_res, blb_res = [], []
    if kind == 'ram':
        for v in vecs:
            rom_addr, symbol = cfg['leaves'][v['op']]
            blb_addr = syms[symbol]
            seed = idx_seed(v['idx'], v['w'][0], v['w'][1], v['w'][2])
            cpu.call(rom_addr, r4=v['idx'], ram=dict(seed))
            rom_res.append(idx_read(cpu, v['idx']))
            m = dict(base); m.update(seed)
            cpu.call(blb_addr, r4=v['idx'], ram=m)
            blb_res.append(idx_read(cpu, v['idx']))
    else:
        for v in vecs:
            if kind in ('r0r1', 'r0'):
                rom_res.append((call_regs(cpu, cfg['addr_rom'],
                                          r0=v['r0'], r1=v.get('r1', 0)),))
            else:
                rom_res.append((call_int(cpu, cfg['addr_rom'],
                                         **_em_args(kind, v)),))
            blb_res.append((call_int(cpu, syms.get(cfg['entry_sym'],
                                                   LINK_BASE),
                                     ram=dict(base), **_em_args(kind, v)),))

    mismatches = []
    for i, (e, h) in enumerate(zip(rom_res, blb_res)):
        if e != h:
            mismatches.append((i, vecs[i], e, h))
    return mismatches, total, n_edges


def format_desc(kind, v):
    if kind in ('r32x2', 'r0r1'):
        keys = ('r4', 'r5') if kind == 'r32x2' else ('r0', 'r1')
        return 'a=0x%08X b=0x%08X' % (v[keys[0]], v[keys[1]])
    if kind in ('r32', 'r0'):
        key = 'r4' if kind == 'r32' else 'r0'
        return 'a=0x%08X' % v[key]
    if kind == 'float':
        return 't=0x%08X v=0x%08X a=0x%08X' % (v['t'], v['v'], v['adj'])
    if kind == 'ram':
        return 'op=%s idx=%d w0=%04X w2=%04X w4=%04X' \
               % (v['op'], v['idx'], v['w'][0], v['w'][1], v['w'][2])
    return str(v)


def main():
    target = int(sys.argv[1]) if len(sys.argv) > 1 else TARGET_N
    reduced = int(sys.argv[2]) if len(sys.argv) > 2 else REDUCED_N
    ensure_stubs()

    total_mm = 0
    for name, cfg in FUNCS.items():
        blob, syms = blob_for(name)
        base = ram_overlay(blob)
        addr = cfg['addr_rom'] or 0x68780

        t0 = time.time()
        mm, total, n_edges = run_function(name, target, base, syms)
        dt = time.time() - t0
        red = False
        if dt > FUZZ_TIMEBOX:
            # timebox: reduce N to `reduced` and re-run
            t0 = time.time()
            mm, total, n_edges = run_function(name, reduced, base, syms)
            dt = time.time() - t0
            red = True

        total_mm += len(mm)
        status = 'OK  ' if not mm else 'FAIL'
        tbox = '  [timebox: N reduced to %d]' % reduced if red else ''
        print('%s %-22s @0x%-6X  n=%-7d edges=%-6d ROM-vs-blob=%-5d %.2fs%s'
              % (status, name, addr, total, n_edges, len(mm), dt, tbox))
        for i, (k, v, e, h) in enumerate(mm[:10]):
            print('    MISMATCH vec#%d %s  ROM=%r  blob=%r'
                  % (k, format_desc(cfg['kind'], v), e, h))
        if len(mm) > 10:
            print('    ... (%d more)' % (len(mm) - 10))

    if total_mm:
        print('\nfuzz_14funcs: %d mismatch(es) total — FAIL' % total_mm)
        sys.exit(1)
    print('\nfuzz_14funcs: all 14 functions OK (0 mismatch, N<=%d per function)'
          % max(target, reduced))


if __name__ == '__main__':
    main()
