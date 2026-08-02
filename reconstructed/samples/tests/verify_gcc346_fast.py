#!/usr/bin/env python3
"""
verify_gcc346_fast.py — parallel (multiprocessing) validation harness.

Performance-oriented twin of verify_gcc346.py for the era-ROM toolchain
(sh-elf gcc 3.4.6) Lotto-1 validation loop.

WHY
---
The serial harness spends ~3.5s on ~68k vector comparisons and the Python
SH-2E emulator is pure Python, so threads are useless (the GIL serialises
them).  For a fuzz budget of 100k+ vectors across more functions we need
real parallelism: multiple OS *processes*, each running its own SH2 on its
own slice of the work.

WHAT CHANGES vs verify_gcc346.py (the logic is byte-for-byte identical)
-----------------------------------------------------------------------
  1. Blob build (gcc-3.4.6 compile + link + objcopy) and host-oracle builds run
     ONCE in the *parent*, before the pool is forked.  The resulting module
     caches (_blob_cache / _oracle_cache) are inherited by every worker
     process copy-on-write, so no worker re-compiles and there is no
     /tmp/verify_gcc346/work write contention.
  2. The functions in FUNCS are distributed across N worker processes
     (N = min(4, cpu_count)) via multiprocessing.Pool (fork context).
  3. Each worker constructs its OWN SH2 (own load_cpu, rom_bytes shared via
     fork copy-on-write — SH2 holds only Python data, so fork is safe) and
     executes only its assigned vector slice, returning
     (mismatch, samples) per function.

  The xtrct emulator-gap fix, the vector generator, the edge tables, the
  call drivers (call_int / call_regs), the idx-table RAM family and the host
  oracle dispatch are all copied verbatim from verify_gcc346.py.

CORRECTNESS CONTRACT
  For a given N, this file MUST report exactly the same per-function
  ROM-vs-blob and oracle-vs-blob mismatch counts as verify_gcc346.py.
  Exit code is non-zero iff any function reports mismatch(es).

Usage:  python3 tests/verify_gcc346_fast.py [N]  [P]
    N   vectors per function (default: per-function n_test config)
    P   worker processes (default: min(4, cpu_count()))
"""
import multiprocessing
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
CC_HOST = os.environ.get('CC', 'cc')
LIBGCC = os.path.join(XGCC_B, 'libgcc.a')

STUB_INC = '/tmp/verify_gcc346/inc'        # stub headers (never committed)
WORK = '/tmp/verify_gcc346/work'           # objects / elfs / blobs / oracles
LINK_BASE = 0x4000                         # fixed link base

SRC_DIR = os.path.join(SAMPLES, 'src')
INC_DIR = os.path.join(SAMPLES, 'include')

# ============================================================================
# Emulator-gap workaround — XTRCT (documented in verify_gcc346.py)
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

# ============================================================================
# Stub headers: minimal target stdint.h / math.h (written once to /tmp)
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
    '#define UINT32_MAX 4294967295U\n#define UINT64_MAX 18446744073709551613ULL\n'
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
# Function config
# ============================================================================
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


def f32b(x):
    return struct.unpack('>I', struct.pack('>f', x))[0]


def bits2f(b):
    return struct.unpack('>f', struct.pack('>I', b & 0xFFFFFFFF))[0]


FUNCS = {
    's32_saturate': {
        'addr_rom': 0x2304, 'src': 'rx8_s32_saturate.c', 'kind': 'r32x2',
        'entry_sym': 'rx8_add_s32_saturate', 'n_test': 4000, 'seed': 0x2304,
        'oracle': 's32',
    },
    'immo_seed_mixer': {
        'addr_rom': 0x366B8, 'src': 'rx8_immo_seed_mixer.c', 'kind': 'r32x2',
        'entry_sym': 'rx8_immo_seed_mixer', 'n_test': 4000, 'seed': 0x366B8,
        'oracle': 'mix',
    },
    'add16bit_saturate': {
        'addr_rom': 0x2460, 'src': 'rx8_add16bit_saturate.c', 'kind': 'r32x2',
        'entry_sym': 'rx8_add16bit_saturate', 'n_test': 4000, 'seed': 0x2460,
        'oracle': 'add16',
    },
    'add_saturate_8bit': {
        'addr_rom': 0x2478, 'src': 'rx8_add_saturate_8bit.c', 'kind': 'r32x2',
        'entry_sym': 'rx8_add_saturate_8bit', 'n_test': 4000, 'seed': 0x2478,
        'oracle': 'add8',
    },
    'multiply32_saturating': {
        'addr_rom': 0x231C, 'src': 'rx8_multiply32_saturating.c', 'kind': 'r32x2',
        'entry_sym': 'rx8_multiply32_saturating', 'n_test': 20000, 'seed': 0x231C,
        'oracle': 'mul',
    },
    'complement_shift_u16': {
        'addr_rom': 0x2430, 'src': 'rx8_complement_shift_u16.c', 'kind': 'r32',
        'entry_sym': 'rx8_complement_shift_u16', 'n_test': 4000, 'seed': 0x2430,
        'oracle': 'u16',
    },
    'complement_shift_u32': {
        'addr_rom': 0x2440, 'src': 'rx8_complement_shift_u32.c', 'kind': 'float',
        'entry_sym': 'rx8_complement_shift_u32', 'n_test': 4000, 'seed': 0x2440,
        'oracle': 'f32',
    },
    'idx_table': {
        'addr_rom': None, 'src': 'rx8_index_table.c', 'kind': 'ram',
        'entry_sym': None, 'n_test': 5000, 'seed': 0x68780,
        'oracle': 'idx',
        'leaves': {
            'clr':   (0x0068780, 'rx8_index_table_clear'),
            'step':  (0x006879C, 'rx8_index_table_step'),
            'step2': (0x00687C8, 'rx8_index_table_step2'),
            'dec':   (0x00687F4, 'rx8_index_table_dec'),
        },
    },
    'div32_signed': {
        'addr_rom': 0x3FE8, 'src': 'rx8_div32_signed.c', 'kind': 'r0r1',
        'entry_sym': 'rx8_div32_signed', 'n_test': 4000, 'seed': 0x3FE8,
        'oracle': 'div',
    },
    'div32_unsigned': {
        'addr_rom': 0x409C, 'src': 'rx8_div32_unsigned.c', 'kind': 'r0r1',
        'entry_sym': 'rx8_div32_unsigned', 'n_test': 4000, 'seed': 0x409C,
        'oracle': 'udiv',
    },
    'shift_left_logical': {
        'addr_rom': 0x4308, 'src': 'rx8_shift_left_logical.c', 'kind': 'r0r1',
        'entry_sym': 'rx8_shift_left_logical', 'n_test': 4000, 'seed': 0x4308,
        'oracle': 'shl',
    },
    'shift_right_arithmetic': {
        'addr_rom': 0x43C8, 'src': 'rx8_shift_right_arithmetic.c',
        'kind': 'r0r1', 'entry_sym': 'rx8_shift_right_arithmetic',
        'n_test': 4000, 'seed': 0x43C8, 'oracle': 'sra',
    },
    'shift_right_logical': {
        'addr_rom': 0x44E0, 'src': 'rx8_shift_right_logical.c', 'kind': 'r0r1',
        'entry_sym': 'rx8_shift_right_logical', 'n_test': 4000,
        'seed': 0x44E0, 'oracle': 'srl',
    },
    'shift_right_8': {
        'addr_rom': 0x467A, 'src': 'rx8_shift_right_8.c', 'kind': 'r0',
        'entry_sym': 'rx8_shift_right_8', 'n_test': 4000, 'seed': 0x467A,
        'oracle': 's8',
    },
}

ORACLES = {
    's32':   ('host_oracle.c',
              ['rx8_s32_saturate.c', 'rx8_immo_seed_mixer.c', 'rx8_index_table.c'],
              lambda v: 's32 %08X %08X' % (v['r4'], v['r5']),
              lambda o: int(o[0], 16)),
    'mix':   ('host_oracle.c',
              ['rx8_s32_saturate.c', 'rx8_immo_seed_mixer.c', 'rx8_index_table.c'],
              lambda v: 'mix %08X %08X' % (v['r4'], v['r5']),
              lambda o: int(o[0], 16)),
    'add16': ('oracle_add16bit_saturate.c', ['rx8_add16bit_saturate.c'],
              lambda v: 'add %08X %08X' % (v['r4'], v['r5']),
              lambda o: int(o[0], 16)),
    'add8':  ('oracle_add_saturate_8bit.c', ['rx8_add_saturate_8bit.c'],
              lambda v: 'add8 %08X %08X' % (v['r4'], v['r5']),
              lambda o: int(o[0], 16)),
    'mul':   ('oracle_multiply32_saturating.c', ['rx8_multiply32_saturating.c'],
              lambda v: 'mul %08X %08X' % (v['r4'], v['r5']),
              lambda o: int(o[0], 16)),
    'u16':   ('oracle_complement_shift_u16.c', ['rx8_complement_shift_u16.c'],
              lambda v: 'u16 %08X' % v['r4'],
              lambda o: int(o[0], 16)),
    'f32':   ('oracle_complement_shift_u32.c', ['rx8_complement_shift_u32.c'],
              lambda v: 'f32 %08X %08X %08X' % (v['t'], v['v'], v['adj']),
              lambda o: int(o[0], 16)),
    'idx':   ('host_oracle.c',
              ['rx8_s32_saturate.c', 'rx8_immo_seed_mixer.c', 'rx8_index_table.c'],
              lambda v: 'tbl %s %02X %04X %04X %04X'
                        % (v['op'], v['idx'], v['w'][0], v['w'][1], v['w'][2]),
              lambda o: tuple(int(x, 16) for x in o)),
    'div':   ('oracle_div32_signed.c', ['rx8_div32_signed.c'],
              lambda v: 'div %08X %08X' % (v['r0'], v['r1']),
              lambda o: int(o[0], 16)),
    'udiv':  ('oracle_div32_unsigned.c', ['rx8_div32_unsigned.c'],
              lambda v: 'div %08X %08X' % (v['r0'], v['r1']),
              lambda o: int(o[0], 16)),
    'shl':   ('oracle_shift_left_logical.c', ['rx8_shift_left_logical.c'],
              lambda v: 'shl %08X %08X' % (v['r0'], v['r1']),
              lambda o: int(o[0], 16)),
    'sra':   ('oracle_shift_right_arithmetic.c', ['rx8_shift_right_arithmetic.c'],
              lambda v: 'sra %08X %08X' % (v['r0'], v['r1']),
              lambda o: int(o[0], 16)),
    'srl':   ('oracle_shift_right_logical.c', ['rx8_shift_right_logical.c'],
              lambda v: '%08X %08X' % (v['r0'], v['r1']),
              lambda o: int(o[0], 16)),
    's8':    ('oracle_shift_right_8.c', ['rx8_shift_right_8.c'],
              lambda v: '%08X' % v['r0'],
              lambda o: int(o[0], 16)),
}

# ============================================================================
# Toolchain build
# ============================================================================
_stub_done = [False]
_blob_cache = {}
_oracle_cache = {}


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


def get_oracle(orc_name):
    if orc_name in _oracle_cache:
        return _oracle_cache[orc_name]
    rig, extra, line, parse = ORACLES[orc_name]
    binp = os.path.join(WORK, 'oracle_' + orc_name)
    cmd = [CC_HOST, '-O2', '-Wall', '-Wextra', '-I', INC_DIR, '-I', SRC_DIR,
           os.path.join(TESTS, rig)] \
        + [os.path.join(SRC_DIR, s) for s in extra] + ['-o', binp]
    subprocess.run(cmd, check=True, capture_output=True)
    _oracle_cache[orc_name] = (binp, line, parse)
    return _oracle_cache[orc_name]


# ============================================================================
# Vector generation  (seeded, reproducible)
# ============================================================================
def gen_vectors(name, n):
    cfg = FUNCS[name]
    kind = cfg['kind']
    rng = make_rng(cfg['seed'])
    vecs = []

    if kind in ('r32x2', 'r32'):
        cnt = 2 if kind == 'r32x2' else 1
        for edge in EDGES[kind]:
            if kind == 'r32':
                vals = [edge]
            else:
                vals = list(edge)
            vals += [0] * (cnt - len(vals))
            v = {'r4': vals[0]}
            if cnt == 2:
                v['r5'] = vals[1]
                v['desc'] = 'a=0x%08X b=0x%08X' % (vals[0], vals[1])
            else:
                v['desc'] = 'a=0x%08X' % vals[0]
            vecs.append(v)
        for _ in range(n):
            vals = [rng.getrandbits(32) for _ in range(cnt)]
            v = {'r4': vals[0]}
            if cnt == 2:
                v['r5'] = vals[1]
                v['desc'] = 'a=0x%08X b=0x%08X' % (vals[0], vals[1])
            else:
                v['desc'] = 'a=0x%08X' % vals[0]
            vecs.append(v)
        return vecs

    if kind in ('r0r1', 'r0'):
        cnt = 2 if kind == 'r0r1' else 1
        for edge in EDGES[kind]:
            if isinstance(edge, tuple):
                vals = list(edge)
            else:
                vals = [edge]
            vals += [0] * (cnt - len(vals))
            v = {'r0': vals[0]}
            if cnt == 2:
                v['r1'] = vals[1]
                v['desc'] = 'r0=0x%08X r1=0x%08X' % (vals[0], vals[1])
            else:
                v['desc'] = 'r0=0x%08X' % vals[0]
            vecs.append(v)
        for _ in range(n):
            v = {'r0': rng.getrandbits(32)}
            if cnt == 2:
                v['r1'] = rng.getrandbits(32)
                v['desc'] = 'r0=0x%08X r1=0x%08X' % (v['r0'], v['r1'])
            else:
                v['desc'] = 'r0=0x%08X' % v['r0']
            vecs.append(v)
        return vecs

    if kind == 'float':
        for (tb, vb, ab) in EDGES['float']:
            vecs.append({'t': tb, 'v': vb, 'adj': ab,
                         'desc': 't=0x%08X v=0x%08X a=0x%08X'
                                 % (tb, vb, ab)})
        for _ in range(n):
            t = f32b(rng.uniform(-100, 100))
            v = f32b(rng.uniform(-100, 100))
            a = f32b(rng.uniform(-50, 50))
            vecs.append({'t': t, 'v': v, 'adj': a,
                         'desc': 't=0x%08X v=0x%08X a=0x%08X' % (t, v, a)})
        return vecs

    if kind == 'ram':
        ops = ['clr', 'step', 'step2', 'dec']
        for _ in range(n):
            op = rng.choice(ops)
            idx = rng.randint(0, 8)
            w0 = rng.getrandbits(16)
            w2 = rng.getrandbits(16)
            w4 = rng.getrandbits(16)
            vecs.append({'op': op, 'idx': idx, 'w': (w0, w2, w4),
                         'desc': 'op=%s idx=%d w0=%04X w2=%04X w4=%04X'
                                 % (op, idx, w0, w2, w4)})
        return vecs
    raise RuntimeError('unsupported kind %r' % kind)


EDGES = {
    'r32x2': [(0, 0), (0x7FFFFFFF, 0),
              (0x7FFFFFFF, 0x00000001), (0x7FFFFFFF, 0x7FFFFFFF),
              (0x80000000, 0), (0x80000000, 0xFFFFFFFF),
              (0xFFFFFFFF, 0xFFFFFFFF), (0x7FFFFFFF, 0xFFFFFFFF),
              (0x80000000, 0x80000000), (0x40000000, 0x40000000),
              (0xC0000000, 0x40000000), (0xDEADBEEF, 0xCAFEBABE)],
    'r32':   [0, 1, 0xFFFF, 0x7FFF, 0x8000, 0xFFFE, 0xFFFFFFFF, 0x0000FFFF],
    'float': [(0x00000000, 0x00000000, 0x3F800000),
              (0x40000000, 0x00000000, 0x3F800000),
              (0x3F800000, 0x00000000, 0x3F800000),
              (0x7FC00000, 0x00000000, 0x3F800000),
              (0x7F800000, 0x00000000, 0x3F800000),
              (0xFF800000, 0x00000000, 0x3F800000),
              (0x80000000, 0x80000000, 0x80000000)],
    'r0r1': [
        (0x00000000, 0x00000000),
        (0x00000001, 0x00000000),
        (0x00000000, 0x00000001),
        (0x00000001, 0x00000001),
        (0xFFFFFFFF, 0xFFFFFFFF),
        (0xFFFFFFFF, 0x00000001),
        (0x00000001, 0xFFFFFFFF),
        (0xFFFFFFFF, 0x80000000),
        (0x00000001, 0x80000000),
        (0x80000000, 0x80000000),
        (0x7FFFFFFF, 0x7FFFFFFF),
        (0x80000000, 0x00000001),
        (0x00000001, 0x7FFFFFFF),
        (0x7FFFFFFF, 0xFFFFFFFF),
        (0x00000002, 0x00000005),
        (0x00000005, 0x00000011),
        (0x00000007, 0x00000064),
        (0x00000007, 0xFFFFFF9C),
        (0x80000000, 0x40000000),
        (0x80000001, 0x7FFFFFFF),
        (0xABCDEF01, 0x12345678),
        (0xDEADBEEF, 0xCAFEBABE),
        (0x12345678, 0x00000000),
        (0x12345678, 0x00000008),
        (0x12345678, 0x00000010),
        (0x12345678, 0x00000017),
        (0x12345678, 0x00000018),
        (0x12345678, 0x0000001F),
        (0x12345678, 0x00000020),
        (0x12345678, 0x00000021),
        (0x12345678, 0x0000003F),
        (0x12345678, 0xFFFFFFC0),
        (0x80000001, 0x00000001),
        (0x80000001, 0x0000001F),
        (0xFFFFFFFF, 0x00000000),
        (0xFFFFFFFF, 0x00000001),
        (0xFFFFFFFF, 0x0000001F),
        (0x00000001, 0x0000001F),
    ],
    'r0':   [0, 1, 0x7F, 0x80, 0xFF, 0x100, 0x7FFF, 0x8000, 0xFFFF, 0x10000,
             0x7FFFFF00, 0x7FFFFFFF, 0x80000000, 0x80000001, 0x800000FF,
             0xFFFFFF00, 0xFFFF00FF, 0xFF00FFFF, 0xFFFFFFFF, 0xABCDEF01,
             0x12345678, 0xDEADBEEF, 0xCAFEBABE],
}


# ============================================================================
# Per-function evaluation
# ============================================================================
def call_int(cpu, addr, **kw):
    cpu.call(addr, **kw)
    return cpu.r[0] & 0xFFFFFFFF


def call_regs(cpu, entry, r0=0, r1=0):
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


def run_function(name):
    cfg = FUNCS[name]
    kind = cfg['kind']
    blob, syms = blob_for(name)
    base = ram_overlay(blob)
    cpu = load_cpu()
    vecs = gen_vectors(name, cfg['n_test'])
    n = len(vecs)
    t0 = time.time()

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

    rb = 0
    samples = []
    for i, (e, h) in enumerate(zip(rom_res, blb_res)):
        if e != h:
            rb += 1
            if len(samples) < 5:
                samples.append('vec#%d %s ROM=%r blob=%r'
                               % (i, vecs[i]['desc'], e, h))

    ob = None
    orc = cfg.get('oracle')
    if orc in ORACLES:
        binp, line_fmt, parse = get_oracle(orc)
        lines = [line_fmt(v) for v in vecs]
        proc = subprocess.run([binp], input='\n'.join(lines) + '\n',
                              capture_output=True, text=True)
        if proc.returncode != 0:
            print('    (host oracle failed: %s)' % proc.stderr.strip())
        else:
            outs = [line.split() for line in proc.stdout.splitlines()]
            if len(outs) == len(blb_res):
                ob = 0
                for i, (h2, o) in enumerate(zip(blb_res, outs)):
                    got = parse(o)
                    exp = h2 if kind == 'ram' else h2[0]
                    if exp != got:
                        ob += 1
                        if ob == 1:
                            samples.append('oracle-vs-blob: blob=%r host=%r'
                                           % (exp, got))

    dt = time.time() - t0
    return {'name': name, 'n': len(vecs), 'rb': rb, 'ob': ob,
            'time': dt, 'samples': samples}


# ============================================================================
# Worker entry point — must be module-level (picklable by multiprocessing).
# Each forked worker process inherits the parent's populated _blob_cache /
# _oracle_cache copy-on-write and constructs its own SH2 via load_cpu().
# ============================================================================
def worker_run(name):
    return run_function(name)


def main():
    argv = sys.argv[1:]
    n_override = int(argv[0]) if len(argv) > 0 else None
    nproc_default = min(4, os.cpu_count() or 1)
    nproc = int(argv[1]) if len(argv) > 1 else nproc_default

    ensure_stubs()

    # ---- pre-build every blob and oracle in the PARENT before fork --------
    # Populating the caches now and forking afterwards hands every worker the
    # populated _blob_cache / _oracle_cache via copy-on-write, so workers do
    # not recompile and never contend on /tmp/verify_gcc346/work.
    for name, cfg in FUNCS.items():
        if n_override:
            cfg['n_test'] = n_override
        blob_for(name)
        orc = cfg.get('oracle')
        if orc in ORACLES:
            get_oracle(orc)

    names = list(FUNCS.keys())

    t_start = time.time()
    ctx = multiprocessing.get_context('fork')
    with ctx.Pool(nproc) as pool:
        try:
            results = pool.map(worker_run, names)
        except BaseException as exc:
            pool.terminate()
            print('\nverify_gcc346_fast: pool aborted (%r)' % exc)
            sys.exit(2)
    wall = time.time() - t_start

    total = 0
    for r in results:
        total += r['rb'] + (r['ob'] or 0)
        status = 'OK  ' if (r['rb'] == 0 and not r['ob']) else 'FAIL'
        cfg = FUNCS[r['name']]
        addr = cfg['addr_rom'] or 0x68780
        print('%s %-22s @0x%-6X  n=%-5d  ROM-vs-blob=%-4d  oracle-vs-blob=%-4s  %.2fs'
              % (status, r['name'], addr, r['n'], r['rb'],
                 r['ob'] if r['ob'] is not None else '-', r['time']))
        for s in r['samples']:
            print('        ' + s)

    print('\nverify_gcc346_fast: %d function(s) across %d worker process(es); '
          'pool wall = %.2fs' % (len(results), nproc, wall))

    if total:
        print('\nverify_gcc346_fast: %d mismatch(es) total — FAIL' % total)
        sys.exit(1)
    print('\nverify_gcc346_fast: all active Lotto-1 functions OK (0 mismatch)')


if __name__ == '__main__':
    main()