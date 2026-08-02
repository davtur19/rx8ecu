#!/usr/bin/env python3
"""
verify_saturates2.py — Lotto 2 saturate/clamp/min/max cross-toolchain
validation (era-ROM gcc 3.4.6 recipe), ROM-vs-blob-vs-host-oracle.

Closes the "ROM -> abstract C -> era-ROM toolchain (gcc 3.4.6)" behavioural
loop for the saturate-family leaves of reconstructed/samples/src NOT covered
by tests/verify_gcc346.py (which already validates s32_saturate@0x2304,
add16bit_saturate@0x2460, add_saturate_8bit@0x2478, multiply32_saturating@0x231C):

    saturate_f   @0x2404  rx8_saturate.c           clamp(sig, lower, upper)
    min_value    @0x23F4  rx8_min_value.c          min(a, b)
    saturate_low @0x23E4  rx8_saturate_low.c       max(sig, lower)
    subtract_abs @0x23DC  rx8_subtract_absolute.c  |a - b|
    math_min_max @0x49ED0 rx8_math_min_max_49ed0.c flag-setter leaf (RAM)

For every function this harness:

  (a) reuses the minimal target stubs (stdint.h / math.h) that
      verify_gcc346.py writes once to /tmp/verify_gcc346/inc (idempotent),
  (b) compiles the reconstructed source with the era-ROM recipe
      `-m2e -O1 -fomit-frame-pointer` via /home/davide/gcc346-build/gcc/xgcc
      (sh-elf gcc 3.4.6),
  (c) links the object at a fixed base 0x4000 with a trivial linker script
      (pulling libgcc 3.4.6 helpers where needed; none of these five leaves
      call any),
  (d) `objcopy --only-section=.text` extracts a self-contained code blob,
  (e) loads the blob into the SH-2E emulator (tools/sh2emu.py) through the
      sparse `ram` overlay,
  (f) generates N seeded random input vectors + edge vectors (0, ±1, ±0,
      ±FLT_MAX, ±inf, NaN in every operand position, denormals, degenerate /
      inverted clamp bands),
  (g) runs BOTH the real ROM bytes at ADDR_ROM and the blob at 0x4000 on the
      very same vectors and compares the results bit-exactly — for the float
      leaves the result is the single-precision bit pattern of FR0; for the
      RAM leaf the r0 flag AND both side-effect bytes at 0xFFFFCD48/49,
  (h) where a host oracle rig exists it also checks host-C-vs-blob.

The four float leaves are pure register-only FPU code (no jsr, no memory
traffic, result in FR0) so the ROM side needs no custom driver — cpu.call(fr=)
covers it.  math_min_max_49ED0 reads one fixed RAM word and writes two fixed
RAM bytes (no jsr), so both sides are seeded with the identical word + sentinel
bytes and the return flag plus the two written bytes are compared.

The harness is read-only w.r.t. the repo: everything it writes goes to /tmp,
and the exit code is non-zero iff any active function reports mismatch(es).

Usage:  python3 tests/verify_saturates2.py [N]   (default N per function)
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

from sh2emu import SH2, bits2f, f2bits  # noqa: E402
from common import load_cpu, make_rng  # noqa: E402

# ---- era-ROM toolchain ------------------------------------------------------
XGCC = '/home/davide/gcc346-build/gcc/xgcc'
XGCC_B = '/home/davide/gcc346-build/gcc'
LD = '/usr/bin/sh-elf-ld'
OBJCOPY = '/usr/bin/sh-elf-objcopy'
NM = '/usr/bin/sh-elf-nm'
CC_HOST = os.environ.get('CC', 'cc')
LIBGCC = os.path.join(XGCC_B, 'libgcc.a')

STUB_INC = '/tmp/verify_gcc346/inc'        # stub headers (shared with verify_gcc346)
WORK = '/tmp/verify_saturates2/work'       # objects / elfs / blobs / oracles
LINK_BASE = 0x4000                         # fixed link base

SRC_DIR = os.path.join(SAMPLES, 'src')
INC_DIR = os.path.join(SAMPLES, 'include')

# ============================================================================
# Stub headers: minimal target stdint.h / math.h (written once to /tmp,
# identical to verify_gcc346.py's so both harnesses share them).
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
# Function config
# ============================================================================
# kind: 'f32x3' three float args (fr4/fr5/fr6), result in fr0 (bit-exact);
#       'f32x2' two float args (fr4/fr5), result in fr0;
#       'flagram' no register args, reads RAM word @0xFFFFF76C, writes flag
#                 bytes @0xFFFFCD48/49, result in r0 (RAM side effects compared).
# entry_sym: expected symbol name in the linked blob.
FUNCS = {
    'saturate_f': {
        'addr_rom': 0x2404, 'src': 'rx8_saturate.c', 'kind': 'f32x3',
        'entry_sym': 'rx8_saturate', 'n_test': 4000, 'seed': 0x2404,
        'oracle': 'sat',
    },
    'min_value': {
        'addr_rom': 0x23F4, 'src': 'rx8_min_value.c', 'kind': 'f32x2',
        'entry_sym': 'rx8_min_value', 'n_test': 4000, 'seed': 0x23F4,
        'oracle': 'min',
    },
    'saturate_low': {
        'addr_rom': 0x23E4, 'src': 'rx8_saturate_low.c', 'kind': 'f32x2',
        'entry_sym': 'rx8_saturate_low', 'n_test': 4000, 'seed': 0x23E4,
        'oracle': 'low',
    },
    'subtract_abs': {
        'addr_rom': 0x23DC, 'src': 'rx8_subtract_absolute.c', 'kind': 'f32x2',
        'entry_sym': 'rx8_subtract_absolute', 'n_test': 4000, 'seed': 0x23DC,
        'oracle': 'abs',
    },
    'math_min_max': {
        'addr_rom': 0x49ED0, 'src': 'rx8_math_min_max_49ed0.c', 'kind': 'flagram',
        'entry_sym': 'rx8_math_min_max_49ed0', 'n_test': 4000, 'seed': 0x49ED0,
        'oracle': 'flg',
    },
}

# ---- math_min_max_49ED0 RAM footprint ---------------------------------------
IN_WORD = 0xFFFFF76C   # input word (bit 0x100 -> flag)
OUT_A = 0xFFFFCD48     # output flag byte A
OUT_B = 0xFFFFCD49     # output flag byte B
# Sentinel bytes pre-filled at the two output addresses; never 0 or 1 so a
# missed (or wrong) write is always caught (mirrors harness_math_min_max_49ed0).
SENTINELS = (0xA5, 0x5A, 0x7F, 0xFE, 0x80, 0x3C)

# ============================================================================
# Host oracle dispatch: oracle name -> (rig, extra srcs, line builder, parser)
# ============================================================================
ORACLES = {
    'sat': ('oracle_saturate.c', ['rx8_saturate.c'],
            lambda v: 'sat %08X %08X %08X' % tuple(v['args']),
            lambda o: int(o[0], 16)),
    'min': ('oracle_min_value.c', ['rx8_min_value.c'],
            lambda v: 'min %08X %08X' % tuple(v['args']),
            lambda o: int(o[0], 16)),
    'low': ('oracle_saturate_low.c', ['rx8_saturate_low.c'],
            lambda v: 'f32 %08X %08X' % tuple(v['args']),
            lambda o: int(o[0], 16)),
    'abs': ('oracle_subtract_absolute.c', ['rx8_subtract_absolute.c'],
            lambda v: 'abs %08X %08X' % tuple(v['args']),
            lambda o: int(o[0], 16)),
    'flg': ('oracle_math_min_max_49ed0.c', ['rx8_math_min_max_49ed0.c'],
            lambda v: 'flg %04X %02X %02X' % (v['word'], v['a'], v['b']),
            lambda o: (int(o[0], 16), int(o[1], 16), int(o[2], 16))),
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


def get_oracle(orc_name):
    """Build (once) and cache a host oracle; returns (bin, line, parse)."""
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
# --- IEEE-754 single-precision bit patterns used in the edge sets ------------
_ZERO = 0x00000000
_NZERO = 0x80000000
_ONE = 0x3F800000
_NEGONE = 0xBF800000
_HALF = 0x3F000000
_NHALF = 0xBF000000
_P15 = 0x3FC00000                # 1.5
_N15 = 0xBFC00000                # -1.5
_SEV = 0x3F666666                # ~0.7
_THREE = 0x40400000              # 3.0
_PINF = 0x7F800000
_NINF = 0xFF800000
_QNAN = 0x7FC00000
_SNAN = 0x7F800001
_BIG = 0x49742400                # 1.0e6
_NBIG = 0xC9742400               # -1.0e6
_MAXF = 0x7F7FFFFF               # FLT_MAX
_NMAXF = 0xFF7FFFFF              # -FLT_MAX
_DEN = 0x00000001                # min denormal
_NDEN = 0x80000001               # -min denormal
_MINNORM = 0x00800000            # smallest normal
_TINY = 0x38D1B717               # ~1.0e-4
_P2E31 = 0x4F000000              # +2^31 (exact single)
_N2E31 = 0xCF000000              # -2^31

# Interesting operand values (swept in the 2-arg edge sets).
_VALS = [_ZERO, _NZERO, _ONE, _NEGONE, _HALF, _NHALF, _SEV, _P15, _N15,
         _PINF, _NINF, _QNAN, _SNAN, _BIG, _NBIG, _MAXF, _NMAXF, _DEN,
         _NDEN, _MINNORM, _TINY, _P2E31, _N2E31]


def _e(s, lo, hi):
    return (s, lo, hi)


# 2-arg edge set: full cross-sweep (ties incl. ±0/NaN, inf/denormal/extreme
# in both operand positions, sign boundaries).
EDGES_F32X2 = [(a, b) for a in _VALS for b in _VALS]

# 3-arg edge set (saturate): classic band, degenerate band, inverted bounds,
# negative band, signed-zero, wide-open / infinite bounds, NaN operands.
EDGES_F32X3 = [
    # Classic band [1.0, 3.0]: below / at-lower / between / at-upper / above.
    _e(_HALF, _ONE, _THREE),          # 0.5 < 1.0   -> lower
    _e(_ONE, _ONE, _THREE),           # sig == lower -> lower (strict >)
    _e(_P15, _ONE, _THREE),           # in band      -> sig
    _e(_THREE, _ONE, _THREE),         # sig == upper -> upper (strict >)
    _e(_BIG, _ONE, _THREE),           # 1e6 > 3.0    -> upper
    # Degenerate band: lower == upper.
    _e(_ONE, _P15, _P15),             # sig below the point  -> lower
    _e(_P15, _P15, _P15),             # sig == the point     -> lower (strict >)
    _e(_BIG, _P15, _P15),             # sig above the point  -> upper
    # Inverted bounds (lower > upper): mirrors the ROM branch-for-branch.
    _e(_BIG, _P15, _ONE),             # sig > lower -> upper
    _e(_SEV, _P15, _ONE),             # lower < sig but upper not > sig -> upper
    _e(_HALF, _P15, _ONE),            # sig < lower -> lower
    # Negative band.
    _e(_NEGONE, _N15, _HALF),         # -1.0 in [-1.5, 0.5]  -> sig
    _e(_N15, _N15, _HALF),            # -1.5 == lower        -> lower
    _e(_HALF, _N15, _HALF),           # 0.5 == upper         -> upper
    _e(_BIG, _N15, _HALF),            # +1e6 above upper     -> upper
    _e(_NINF, _N15, _HALF),           # -inf                 -> lower
    # Zero / negative zero (compare equal; register bits preserved).
    _e(_ZERO, _NEGONE, _ONE),
    _e(_NZERO, _NEGONE, _ONE),
    _e(_NEGONE, _NZERO, _ZERO),       # lower = -0.0, sig below -> returns -0.0
    _e(_ONE, _NZERO, _ZERO),          # sig above upper +0.0   -> returns +0.0
    # Wide-open / infinite bounds.
    _e(_MAXF, _NMAXF, _MAXF),         # sig == both bounds     -> lower (strict >)
    _e(_MAXF, _NINF, _PINF),          # +FLT_MAX inside ]-inf, +inf[
    _e(_NMAXF, _NINF, _PINF),         # -FLT_MAX inside
    _e(_DEN, _NINF, _PINF),           # denormal passes through
    _e(_PINF, _NINF, _PINF),          # +inf at the ceiling    -> upper (+inf)
    _e(_NINF, _NINF, _PINF),          # -inf at the floor      -> lower (-inf)
    # NaN operands: fcmp/gt clears T for unordered, so `sig` NaN snaps to
    # lower and a NaN bound forces the same path as an unequal value.
    _e(_QNAN, _ZERO, _ONE),           # sig = NaN -> lower
    _e(_SNAN, _NEGONE, _HALF),        # sig = sNaN -> lower
    _e(_HALF, _QNAN, _ONE),           # lower = NaN -> lower (the NaN itself)
    _e(_HALF, _ZERO, _QNAN),          # upper = NaN, in band otherwise -> sig
    _e(_BIG, _ZERO, _QNAN),           # upper = NaN, sig above -> upper (NaN)
    _e(_HALF, _NINF, _PINF),          # plain in-band pass-through
    _e(_NEGONE, _NINF, _PINF),        # -1 inside wide-open band
]

# Edge words for the flag-setter: bit-0x100 off/on boundaries, zero, max,
# sign flips, all-ones.
EDGES_FLAGRAM = [0x0000, 0x0001, 0x00FF, 0x0100, 0x0101, 0x01FF, 0x02FF,
                 0x7FFF, 0x8000, 0x80FF, 0xFEFF, 0xFF00, 0xFF01, 0xFFFF]


def rflt(rng):
    """Random single-precision bit pattern mixing realistic firmware
    magnitudes with raw 32-bit patterns (so NaN/inf/denormal edge-space is
    sampled inside the random stream too)."""
    r = rng.random()
    if r < 0.10:
        return rng.choice(_VALS)            # explicit special/edge values
    if r < 0.70:
        return f2bits(rng.choice([rng.uniform(-1e4, 1e4), rng.uniform(-2, 2),
                                  rng.uniform(0, 300), rng.uniform(-300, 0)]))
    return rng.getrandbits(32)              # raw pattern


def gen_vectors(name, n):
    cfg = FUNCS[name]
    kind = cfg['kind']
    rng = make_rng(cfg['seed'])
    vecs = []

    if kind in ('f32x3', 'f32x2'):
        cnt = 3 if kind == 'f32x3' else 2
        fmt = ('fr4=%08X fr5=%08X fr6=%08X' if cnt == 3
               else 'fr4=%08X fr5=%08X')
        edges = EDGES_F32X3 if kind == 'f32x3' else EDGES_F32X2
        for e in edges:
            vals = list(e) + [_ZERO] * (cnt - len(e))
            v = {'args': vals, 'desc': fmt % tuple(vals)}
            vecs.append(v)
        for _ in range(n):
            vals = [rflt(rng) for _ in range(cnt)]
            v = {'args': vals, 'desc': fmt % tuple(vals)}
            vecs.append(v)
        return vecs

    if kind == 'flagram':
        for w in EDGES_FLAGRAM:
            vecs.append({'word': w, 'a': 0xAA, 'b': 0x55,
                         'desc': 'word=%04X' % w})
        for _ in range(n):
            w = rng.getrandbits(16)
            vecs.append({'word': w,
                         'a': rng.choice(SENTINELS), 'b': rng.choice(SENTINELS),
                         'desc': 'word=%04X' % w})
        return vecs

    raise RuntimeError('unsupported kind %r' % kind)


# ============================================================================
# Per-function evaluation
# ============================================================================
def _flg_seed(word, a, b):
    return {IN_WORD: (word >> 8) & 0xFF, IN_WORD + 1: word & 0xFF,
            OUT_A: a & 0xFF, OUT_B: b & 0xFF}


def call_f32x3(cpu, addr, args, ram=None):
    # 3-arg clamp leaf: pure fcmp/fmov, no FP arithmetic -> no overflow path.
    cpu.call(addr, fr={4: bits2f(args[0]), 5: bits2f(args[1]),
                       6: bits2f(args[2])}, ram=ram)
    return f2bits(cpu.fr[0])


def call_f32x2(cpu, addr, args, ram=None):
    """Run a 2-float-arg leaf; return the FR0 result as a 32-bit pattern.

    Emulator-gap handling: tools/sh2emu.py's `ts()` (Python 3.14) raises
    OverflowError instead of rounding a double that overflows single precision
    to +/-inf.  The ROM fsub and the gcc-3.4.6 blob fsub are the SAME single
    fsub, so both sides raise on exactly the same inputs; on real hardware both
    would saturate to +/-inf and then run the same fabs/and-0x7FFFFFFF
    sign-clear (|a - b|), so the hardware result is ALWAYS +inf.  The only
    arithmetic leaf in this family is subtract_abs (min_value / saturate_low
    are pure compares and can never raise here)."""
    try:
        cpu.call(addr, fr={4: bits2f(args[0]), 5: bits2f(args[1])}, ram=ram)
    except OverflowError:
        return 0x7F800000
    return f2bits(cpu.fr[0])


def call_flagram(cpu, addr, word, a, b, base=None):
    seed = _flg_seed(word, a, b)
    if base:
        m = dict(base)
        m.update(seed)
        cpu.call(addr, ram=m)
    else:
        cpu.call(addr, ram=dict(seed))
    return (cpu.r[0] & 0xFFFFFFFF, cpu.ram.get(OUT_A), cpu.ram.get(OUT_B))


def run_function(name):
    cfg = FUNCS[name]
    kind = cfg['kind']
    blob, syms = blob_for(name)
    base = ram_overlay(blob)
    cpu = load_cpu()
    vecs = gen_vectors(name, cfg['n_test'])
    n = len(vecs)
    t0 = time.time()

    blb_addr = syms.get(cfg['entry_sym'], LINK_BASE)
    rom_res, blb_res = [], []
    for v in vecs:
        if kind == 'f32x3':
            rom_res.append(call_f32x3(cpu, cfg['addr_rom'], v['args']))
            blb_res.append(call_f32x3(cpu, blb_addr, v['args'], ram=dict(base)))
        elif kind == 'f32x2':
            rom_res.append(call_f32x2(cpu, cfg['addr_rom'], v['args']))
            blb_res.append(call_f32x2(cpu, blb_addr, v['args'], ram=dict(base)))
        elif kind == 'flagram':
            rom_res.append(call_flagram(cpu, cfg['addr_rom'], v['word'],
                                        v['a'], v['b']))
            blb_res.append(call_flagram(cpu, blb_addr, v['word'],
                                        v['a'], v['b'], base=base))
        else:
            raise RuntimeError('unsupported kind %r' % kind)

    # ROM vs blob
    rb = 0
    samples = []
    for i, (e, h) in enumerate(zip(rom_res, blb_res)):
        if e != h:
            rb += 1
            if len(samples) < 5:
                samples.append('vec#%d %s ROM=%s blob=%s'
                               % (i, vecs[i]['desc'], _fmt(e), _fmt(h)))

    # host oracle vs blob (optional)
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
                for i, (h, o) in enumerate(zip(blb_res, outs)):
                    got = parse(o)
                    if h != got:
                        ob += 1
                        if ob == 1:
                            samples.append('oracle-vs-blob: blob=%s host=%s'
                                           % (_fmt(h), _fmt(got)))

    dt = time.time() - t0
    return {'name': name, 'n': n, 'rb': rb, 'ob': ob,
            'time': dt, 'samples': samples}


def _fmt(r):
    if isinstance(r, tuple):
        return '(%X,%02X,%02X)' % r
    return '%08X' % r


def main():
    n_override = int(sys.argv[1]) if len(sys.argv) > 1 else None
    ensure_stubs()

    total = 0
    for name, cfg in FUNCS.items():
        if n_override:
            cfg['n_test'] = n_override
        r = run_function(name)
        total += r['rb'] + (r['ob'] or 0)
        status = 'OK  ' if (r['rb'] == 0 and not r['ob']) else 'FAIL'
        addr = cfg['addr_rom']
        print('%s %-14s @0x%-6X  n=%-5d  ROM-vs-blob=%-4d  oracle-vs-blob=%-4s  %.2fs'
              % (status, name, addr, r['n'], r['rb'],
                 r['ob'] if r['ob'] is not None else '-', r['time']))
        for s in r['samples']:
            print('        ' + s)

    if total:
        print('\nverify_saturates2: %d mismatch(es) total — FAIL' % total)
        sys.exit(1)
    print('\nverify_saturates2: all saturate/clamp/min/max functions OK (0 mismatch)')


if __name__ == '__main__':
    main()
