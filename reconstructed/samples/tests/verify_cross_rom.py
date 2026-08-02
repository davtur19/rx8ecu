#!/usr/bin/env python3
"""
verify_cross_rom.py — cross-ROM validation of the reconstructed L-2 / L-1 C
functions against stock ROMs OTHER than the RE baseline 60E1D400.bin.

Read-only w.r.t. the repo (everything is written to /tmp).  It is the
cross-ROM companion of tests/verify_gcc346.py (which validates the 14
reconstructed functions against the single baseline ROM using the sh-elf
gcc-3.4.6 era-RX-8 toolchain).  This harness re-runs the exact same
ROM-vs-blob behavioural comparison, but a *per-ROM function-address map* so
that functions whose machine code is relocated between ROM families are
resolved to their own address on each image before the comparison.

WHY A PER-ROM ADDRESS MAP
-------------------------
The 9 stock ROMs (roms/stock/, catalogued in roms/ROMS.md) are all SH-2
Denso RX-8 PCM firmware, but they are not address-identical.  Cross-diff of
the baseline function addresses found:

  * 12 of 14 reconstructed functions are *byte-identical* at their baseline
    address on EVERY stock ROM (s32_saturate, add16/8bit saturate,
    multiply32_saturating, complement_shift_u16/u32, div32_signed/unsigned,
    shift_left_logical, shift_right_arithmetic/logical, shift_right_8) —
    so the baseline address remains valid.
  * immo_seed_mixer (baseline 0x366B8): *relocated* in every other ROM.
    The distinctive prologue words 0x91B1/0x7FF4 locate it at a single
    address per ROM (disassembled: byte-identical body).  This harness
    resolves it via that signature and tests the relocated copy.
  * idx_table (@0x68780..0x687F4): the baseline leaves dereference the
    internal RAM base constant 0xFFFFD998, which is present ONLY in
    60E1D400.bin; in all other families the same baseline addresses hold
    *calibration/table data*, i.e. the leaves are re-written (different
    layout) and are not relocatably locatable on the other 8 images.

For every ROM x function the harness reuses the L-2 era-gcc pipeline of
verify_gcc346.py (build / link / emulation), feeds >= N (1000) seeded
deterministic vectors and compares ROM bytes-vs-blob on r0 (and the RAM
slot side-effects for idx_table).  Where the baseline address is not the
function on a given ROM, it reports "addr non valido" and skips that cell
(no mismatch is attributed to a missing/cursor address).

Exit code is 0 iff every valid cell reports 0 mismatches (skipped cells do
not fail the run).
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
from common import make_rng  # noqa: E402

# ---------------------------------------------------------------------------
# era-ROM toolchain (gcc 3.4.6)
# ---------------------------------------------------------------------------
XGCC = '/home/davide/gcc346-build/gcc/xgcc'
XGCC_B = '/home/davide/gcc346-build/gcc'
LD = '/usr/bin/sh-elf-ld'
OBJCOPY = '/usr/bin/sh-elf-objcopy'
NM = '/usr/bin/sh-elf-nm'
CC_HOST = os.environ.get('CC', 'cc')
LIBGCC = os.path.join(XGCC_B, 'libgcc.a')

STUB_INC = '/tmp/verify_cross_rom/inc'
WORK = '/tmp/verify_cross_rom/work'
LINK_BASE = 0x4000

SRC_DIR = os.path.join(SAMPLES, 'src')
INC_DIR = os.path.join(SAMPLES, 'include')

# ROM set -------------------------------------------------------------------
STOCK = os.path.join(ROOT, 'roms', 'stock')
BASELINE = '60E1D400.bin'
# 3 diverse shipments: structurally-distinct 60E32000 (N3M5), the "mauss"
# N3YM N3YM, and a J-line N3J6 task image.
TEST_ROMS = ['60E32000_N3M5E.bin', '60E0E500.bin', '60E1C500_N3J6EB.bin']

# Cross-mode vector count (task: N>=1000).
N_PER = 1200

# ===========================================================================
# Emulator-gap workaround — XTRCT (same as verify_gcc.py)
# ===========================================================================
_SH2_exec_orig = SH2._exec
_SH2_exec_ref = _SH2_exec_orig


def _xtrct_fixed(self, op, pc):
    if (op & 0xF00F) == 0x200D:
        m = (op >> 4) & 0xF
        n = (op >> 8) & 0xF
        self.r[n] = (((self.r[m] << 16) & 0xFFFF0000)
                     | ((self.r[n] >> 16) & 0xFFFF)) & 0xFFFFFFFF
        return
    return _SH2_exec_ref(self, op, pc)


SH2._exec = _xtrct_fixed

# ===========================================================================
# Stub headers / linker script (identical to verify_gcc.py)
# ===========================================================================
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
_MATH = '#ifndef _MATH_H\n#define _MATH_H\nfloat fabsf(float x);\n#endif\n'
_LINKER = (
    'OUTPUT_FORMAT(elf32-sh)\n'
    'MEMORY { RAM (rx) : ORIGIN = 0x%X, LENGTH = 0x1000 }\n'
    'SECTIONS {\n'
    '  .text : { *(.text) *(.text.*) *(.rodata) *(.rodata.*) *(.rdata) } > RAM\n'
    '  /DISCARD/ : { *(.comment) *(.note*) *(.symtab) *(.strtab) '
    '*(.shstrtab) *(.debug*) }\n}\n' % LINK_BASE)

# ===========================================================================
# Function config (same geometry as verify_gcc.py)
# ===========================================================================
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
        'entry_sym': 'rx8_add_s32_saturate', 'oracle': 's32'},
    'immo_seed_mixer': {
        'addr_rom': 0x366B8, 'src': 'rx8_immo_seed_mixer.c', 'kind': 'r32x2',
        'entry_sym': 'rx8_immo_seed_mixer', 'oracle': 'mix',
        'signature': bytes.fromhex('91B17FF4')},
    'add16bit_saturate': {
        'addr_rom': 0x2460, 'src': 'rx8_add16bit_saturate.c', 'kind': 'r32x2',
        'entry_sym': 'rx8_add16bit_saturate', 'oracle': 'add16'},
    'add_saturate_8bit': {
        'addr_rom': 0x2478, 'src': 'rx8_add_saturate_8bit.c', 'kind': 'r32x2',
        'entry_sym': 'rx8_add_saturate_8bit', 'oracle': 'add8'},
    'multiply32_saturating': {
        'addr_rom': 0x231C, 'src': 'rx8_multiply32_saturating.c', 'kind': 'r32x2',
        'entry_sym': 'rx8_multiply32_saturating', 'oracle': 'mul'},
    'complement_shift_u16': {
        'addr_rom': 0x2430, 'src': 'rx8_complement_shift_u16.c', 'kind': 'r32',
        'entry_sym': 'rx8_complement_shift_u16', 'oracle': 'u16'},
    'complement_shift_u32': {
        'addr_rom': 0x2440, 'src': 'rx8_complement_shift_u32.c', 'kind': 'float',
        'entry_sym': 'rx8_complement_shift_u32', 'oracle': 'f32'},
    'idx_table': {
        'addr_rom': None, 'src': 'rx8_index_table.c', 'kind': 'ram',
        'entry_sym': None, 'oracle': 'idx',
        'leaves': {
            'clr': (0x0068780, 'rx8_index_table_clear'),
            'step': (0x006879C, 'rx8_index_table_step'),
            'step2': (0x00687C8, 'rx8_index_table_step2'),
            'dec': (0x00687F4, 'rx8_index_table_dec')}},
    'div32_signed': {
        'addr_rom': 0x3FE8, 'src': 'rx8_div32_signed.c', 'kind': 'r0r1',
        'entry_sym': 'rx8_div32_signed', 'oracle': 'div'},
    'div32_unsigned': {
        'addr_rom': 0x409C, 'src': 'rx8_div32_unsigned.c', 'kind': 'r0r1',
        'entry_sym': 'rx8_div32_unsigned', 'oracle': 'udiv'},
    'shift_left_logical': {
        'addr_rom': 0x4308, 'src': 'rx8_shift_left_logical.c', 'kind': 'r0r1',
        'entry_sym': 'rx8_shift_left_logical', 'oracle': 'shl'},
    'shift_right_arithmetic': {
        'addr_rom': 0x43C8, 'src': 'rx8_shift_right_arithmetic.c', 'kind': 'r0r1',
        'entry_sym': 'rx8_shift_right_arithmetic', 'oracle': 'sra'},
    'shift_right_logical': {
        'addr_rom': 0x44E0, 'src': 'rx8_shift_right_logical.c', 'kind': 'r0r1',
        'entry_sym': 'rx8_shift_right_logical_r0', 'oracle': 'srl'},
    'shift_right_8': {
        'addr_rom': 0x467A, 'src': 'rx8_shift_right_8.c', 'kind': 'r0',
        'entry_sym': 'rx8_shift_right_8', 'oracle': 's8'},
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

# Same targeted edge vectors as verify_gcc.py.
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
        (0x00000000, 0x00000000), (0x00000001, 0x00000000),
        (0x00000000, 0x00000001), (0x00000001, 0x00000001),
        (0xFFFFFFFF, 0xFFFFFFFF), (0xFFFFFFFF, 0x00000001),
        (0x00000001, 0xFFFFFFFF), (0xFFFFFFFF, 0x80000000),
        (0x00000001, 0x80000000), (0x80000000, 0x80000000),
        (0x7FFFFFFF, 0x7FFFFFFF), (0x80000000, 0x00000001),
        (0x00000001, 0x7FFFFFFF), (0x7FFFFFFF, 0xFFFFFFFF),
        (0x00000002, 0x00000005), (0x00000005, 0x00000011),
        (0x00000007, 0x00000064), (0x00000007, 0xFFFFFF9C),
        (0x80000000, 0x40000000), (0x80000001, 0x7FFFFFFF),
        (0xABCDEF01, 0x12345678), (0xDEADBEEF, 0xCAFEBABE),
        (0x12345678, 0x00000000), (0x12345678, 0x00000008),
        (0x12345678, 0x00000010), (0x12345678, 0x00000017),
        (0x12345678, 0x00000018), (0x12345678, 0x0000001F),
        (0x12345678, 0x00000020), (0x12345678, 0x00000021),
        (0x12345678, 0x0000003F), (0x12345678, 0xFFFFFFC0),
        (0x80000001, 0x00000001), (0x80000001, 0x0000001F),
        (0xFFFFFFFF, 0x00000000), (0xFFFFFFFF, 0x00000001),
        (0xFFFFFFFF, 0x0000001F), (0x00000001, 0x0000001F)],
    'r0':   [0, 1, 0x7F, 0x80, 0xFF, 0x100, 0x7FFF, 0x8000, 0xFFFF, 0x10000,
             0x7FFFFF00, 0x7FFFFFFF, 0x80000000, 0x80000001, 0x800000FF,
             0xFFFFFF00, 0xFFFF00FF, 0xFF00FFFF, 0xFFFFFFFF, 0xABCDEF01,
             0x12345678, 0xDEADBEEF, 0xCAFEBABE],
}

# ===========================================================================
# Toolchain build (identical to verify_gcc.py, cached)
# ===========================================================================
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


def gen_vectors(name, n):
    cfg = FUNCS[name]
    kind = cfg['kind']
    rng = make_rng(FUNCS_ORDER.index(name) * 0x100 + 0x11)  # deterministic
    vecs = []
    if kind in ('r32x2', 'r32'):
        cnt = 2 if kind == 'r32x2' else 1
        for edge in EDGES[kind]:
            vals = list(edge) if isinstance(edge, tuple) else [edge]
            vals += [0] * (cnt - len(vals))
            vecs.append({'r4': vals[0], **({'r5': vals[1]} if cnt == 2 else {}),
                         'desc': ('a=0x%08X b=0x%08X' % (vals[0], vals[1])
                                  if cnt == 2 else 'a=0x%08X' % vals[0])})
        for _ in range(n):
            vals = [rng.getrandbits(32) for _ in range(cnt)]
            vecs.append({'r4': vals[0], **({'r5': vals[1]} if cnt == 2 else {}),
                         'desc': ('a=0x%08X b=0x%08X' % (vals[0], vals[1])
                                  if cnt == 2 else 'a=0x%08X' % vals[0])})
        return vecs
    if kind in ('r0r1', 'r0'):
        cnt = 2 if kind == 'r0r1' else 1
        for edge in EDGES[kind]:
            vals = list(edge) if isinstance(edge, tuple) else [edge]
            vals += [0] * (cnt - len(vals))
            v = {'r0': vals[0], **({'r1': vals[1]} if cnt == 2 else {})}
            v['desc'] = ('r0=0x%08X r1=0x%08X' % (vals[0], vals[1])
                         if cnt == 2 else 'r0=0x%08X' % vals[0])
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
                         'desc': 't=0x%08X v=0x%08X a=0x%08X' % (tb, vb, ab)})
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
            vecs.append({'op': op, 'idx': rng.randint(0, 8),
                         'w': (rng.getrandbits(16), rng.getrandbits(16),
                               rng.getrandbits(16)),
                         'desc': 'op=%s idx=%d' % (op, 0)})
        return vecs
    raise RuntimeError('unsupported kind %r' % kind)


FUNCS_ORDER = list(FUNCS.keys())


# ===========================================================================
# Per-ROM address map
# ===========================================================================
def _find_sig(data, sig):
    hits = []
    i = data.find(sig)
    while i != -1:
        hits.append(i)
        i = data.find(sig, i + 1)
    return hits


def build_addr_map(rom_name, rom_data):
    """Return {func_name: (status, addr)} for a ROM.

    status in {'ok', 'skip'}:
      'ok'   -> addr is a valid function address on this ROM (to run ROM-vs-blob)
      'skip' -> the baseline address is NOT a valid function on this ROM
                (addr=0; explaining note is printed by the caller).
    """
    base = open(os.path.join(STOCK, BASELINE), 'rb').read()
    out = {}
    for name, cfg in FUNCS.items():
        if name == 'idx_table':
            if rom_name == BASELINE:
                out[name] = ('ok', cfg['leaves'])
            else:
                out[name] = ('skip', None)
            continue
        a = cfg['addr_rom']
        # Prologue/window check: the 64-byte window at a must equal the
        # baseline (function present & identical). A garbage/relocated cell
        # fails here.
        if rom_data[a:a + 64] == base[a:a + 64]:
            out[name] = ('ok', a)
            continue
        # Handle the known-relocated immo_seed_mixer via its relocation sig.
        if name == 'immo_seed_mixer' and 'signature' in cfg:
            hits = _find_sig(rom_data, cfg['signature'])
            if len(hits) == 1:
                out[name] = ('ok', hits[0])
                continue
        # else: the baseline address doesn't contain the function on this ROM
        out[name] = ('skip', None)
    return out


# ===========================================================================
# Evaluation
# ===========================================================================
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


def run_cell(rom_name, rom_data, name, addr_rom):
    """ROM-vs-blob for one (ROM, function) at addr_rom. Returns a dict."""
    cfg = FUNCS[name]
    kind = cfg['kind']
    blob, syms = blob_for(name)
    cpu = SH2(rom_data)
    vecs = gen_vectors(name, N_PER)
    rom_res, blb_res = [], []

    if kind == 'ram':
        leaves = addr_rom
        for v in vecs:
            rom_addr, symbol = leaves[v['op']]
            blb_addr = syms[symbol]
            seed = idx_seed(v['idx'], v['w'][0], v['w'][1], v['w'][2])
            cpu.call(rom_addr, r4=v['idx'], ram=dict(seed))
            rom_res.append(idx_read(cpu, v['idx']))
            m = dict(ram_overlay(blob)); m.update(seed)
            cpu.call(blb_addr, r4=v['idx'], ram=m)
            blb_res.append(idx_read(cpu, v['idx']))
    else:
        for v in vecs:
            if kind in ('r0r1', 'r0'):
                rom_res.append((call_regs(cpu, addr_rom,
                                          r0=v['r0'], r1=v.get('r1', 0)),))
            else:
                rom_res.append((call_int(cpu, addr_rom,
                                         **_em_args(kind, v)),))
            blb_res.append((call_int(cpu, syms.get(cfg['entry_sym'], LINK_BASE),
                                     ram=dict(ram_overlay(blob)),
                                     **_em_args(kind, v)),))

    rb = 0
    samples = []
    for i, (e, h) in enumerate(zip(rom_res, blb_res)):
        if e != h:
            rb += 1
            if len(samples) < 5:
                samples.append('vec#%d %s ROM=%r blob=%r'
                               % (i, vecs[i]['desc'], e, h))
    return {'name': name, 'n': len(vecs), 'rb': rb, 'samples': samples}


def main():
    ensure_stubs()
    roms = [(BASELINE, open(os.path.join(STOCK, BASELINE), 'rb').read())]
    for t in TEST_ROMS:
        roms.append((t, open(os.path.join(STOCK, t), 'rb').read()))

    # first report the relocation/anomaly matrix
    print('=== anomalie di indirizzo tra famiglie (rispetto a 60E1D400) ===')
    for rom_name, rd in roms:
        amap = build_addr_map(rom_name, rd)
        anomalies = [n for n, (s, a) in amap.items()
                     if s == 'skip' or (n == 'immo_seed_mixer' and s == 'ok'
                                        and a != FUNCS[n]['addr_rom'])]
        if not anomalies:
            print('  %-24s nessuna anomalia' % rom_name)
        else:
            for n in anomalies:
                s, a = amap[n]
                if n == 'immo_seed_mixer' and s == 'ok':
                    print('  %-24s %-20s -> 0x%06X (rilocato)' % (rom_name, n, a))
                else:
                    print('  %-24s %-20s -> SKIP: %s' % (rom_name, n, a))

    # run the matrix
    print('\n=== ROM x funzione (ROM-vs-blob, N>=1000) ===')
    header = '  %-24s' % 'ROM' + ''.join('%-24s' % n for n in FUNCS_ORDER)
    print(header)
    n_skipped = 0
    n_cells = 0
    mismatches = []
    for rom_name, rd in roms:
        amap = build_addr_map(rom_name, rd)
        row = ['  %-24s' % rom_name[:22]]
        for name in FUNCS_ORDER:
            status, addr = amap[name]
            if status != 'ok':
                n_skipped += 1
                note = 'skip'
                if name == 'idx_table':
                    note = 'skip(dati)'
                elif name == 'immo_seed_mixer':
                    note = 'skip(no sig)'
                row.append('%-24s' % note)
                continue
            n_cells += 1
            try:
                r = run_cell(rom_name, rd, name, addr)
            except Exception as e:
                mismatches.append('EXC %s/%s: %s' % (rom_name, name, e))
                row.append('%-24s' % ('ERR %d' % 1))
            else:
                if r['rb']:
                    mismatches.append('%s/%s %d mismatch' % (rom_name, name, r['rb']))
                    row.append('%-24s' % ('FAIL %d' % r['rb']))
                else:
                    row.append('%-24s' % ('OK %d' % r['n']))
        print(''.join(row))

    for m in mismatches:
        print('mismatch: ' + m)
    print('\ncelle attive (ROM x funzion run) = %d; saltate = %d; mismatch = %d'
          % (n_cells, n_skipped, len(mismatches)))
    if mismatches:
        print('verify_cross_rom: FAIL (%d mismatch cell)' % len(mismatches))
        sys.exit(1)
    print('verify_cross_rom: 0 mismatch su tutte le ROM testate')


if __name__ == '__main__':
    main()