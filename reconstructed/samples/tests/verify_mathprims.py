#!/usr/bin/env python3
"""
verify_mathprims.py — era-ROM toolchain (gcc 3.4.6) validation of the
rx8_math_primitives_2490 float/fixed-point family (@0x2490/@0x2500/@0x2510).

Closes the "ROM -> abstract C -> era-ROM toolchain" loop on the *behavioural*
plane for the last three scalar math leaves of c/math_primitives.c, exactly on
the recipe already used by verify_gcc346.py for the Lotto-1 families:

  (a) writes the minimal target stubs stdint.h / math.h once in
      /tmp/verify_gcc346/inc  (recreated if missing; gcc 3.4.6 was configured
      --without-headers),
  (b) compiles samples/src/rx8_math_primitives_2490.c with the era-ROM recipe
      `-m2e -O1 -fomit-frame-pointer` via /home/davide/gcc346-build/gcc/xgcc
      (sh-elf gcc 3.4.6),
  (c) links the object at 0x4000 with the same trivial linker script (libgcc
      pulled only if referenced — none of the three leaves needs it, they are
      pure FPU + integer code),
  (d) `objcopy --only-section=.text` extracts the self-contained blob,
  (e) loads the blob into tools/sh2emu.py through the sparse `ram` overlay,
  (f) runs BOTH the real ROM bytes at 0x2490/0x2500/0x2510 and the blob on the
      very same vectors and compares the results bit-exact (r0; fr0 bits for
      0x2500).  Every function is run with cpu.call(r4=,r5=,r6=,fr={},ram={})
      and the SENTINEL (pr=0xEEEE0000) pattern — identical driver on both sides.

WHY NOT EXCLUDED (step 4 of the task): all three functions are pure register
leaves — no globals, no RAM side-effects, no non-standard ABI.  They take
three arguments each, but that IS the standard SH-2E ABI:
   * 0x2490  float number(fr4), float scalar(fr5), float offset(fr6) -> r0
   * 0x2500  float mult(fr4), float off(fr5), uint8_t raw(r4)        -> fr0
   * 0x2510  int32 a(r4), int32 b(r5), uint16_t frac(r6)             -> r0
(gcc 3.4.6 SH ABI passes the 1st..4th int args in r4..r7 and the floats in
fr4/fr5/..., so the compiled blob uses exactly the same register conventions
the ROM reads.)  No exclusion criterion applies.

FP EXACTNESS — the compiled blobs reproduce the ROM instruction-for-instruction:
   * 0x2490 -> fsub/fdiv/fadd(+0.5f)/ftrc + two signed clamps (cmp/gt, cmp/pz);
   * 0x2500 -> extu.b + lds/float + ONE fused `fmac` (gcc 3.4.6 contracts the
     `(double)` exact intermediate back to fmac, i.e. a single rounding);
   * 0x2510 -> the whole fmul/fsub/fsub/fmul/trunc chain with float
     intermediates (separate single roundings each, like the ROM).
  No `xtrct` is emitted by gcc here, so no emulator monkeypatch is needed.

TEST DOMAINS (mirror harness_math_primitives_2490.py, which already validated
ROM-vs-host-C on these):
   * 0x2490: |number|,|offset| <= 1e6 and 2e-3 <= |scalar| <= 1e4 -> the ftrc
     operand stays < 2^31; f32 overflow of the quotient is also avoided.
   * 0x2500: |mult|*255+|off| kept below FLT_MAX (no f32 overflow).
   * 0x2510: dense full-range int32 a/b and 32-bit frac (both sides `extu.w`
     and `ftrc` wrap identically in the emulator, so the comparison is exact
     even outside the documented firmware domain); plus the edge set pinned to
     |a|,|b| <= 2^30, frac in 0..256.
  Both sides run in the SAME emulator, so the ftrc/overflow semantics are
  identical by construction; the domains above keep every value well-defined
  on top of that.

Usage:  python3 tests/verify_mathprims.py [N]   (default N = 4000 per fn)
Exit: 0 all active functions OK; 1 any mismatch.  Read-only w.r.t. the repo
(all artifacts go to /tmp).
"""
import os
import random
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

# ---- era-ROM toolchain (same as verify_gcc346.py) ---------------------------
XGCC = '/home/davide/gcc346-build/gcc/xgcc'
XGCC_B = '/home/davide/gcc346-build/gcc'
LD = '/usr/bin/sh-elf-ld'
OBJCOPY = '/usr/bin/sh-elf-objcopy'
NM = '/usr/bin/sh-elf-nm'
LIBGCC = os.path.join(XGCC_B, 'libgcc.a')

STUB_INC = '/tmp/verify_gcc346/inc'        # stub headers (shared, never committed)
WORK = '/tmp/verify_mathprims/work'
LINK_BASE = 0x4000

SRC = os.path.join(SAMPLES, 'src', 'rx8_math_primitives_2490.c')

N_DEFAULT = 4000

# ============================================================================
# Stub headers — recreated if missing (gcc 3.4.6 configured --without-headers)
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
# kind:
#   'f16'  float*3 (fr4/fr5/fr6) -> r0   (0x2490)
#   'f8f'  r4=raw u8 + fr4/fr5 (mult/off) -> fr0 bits (0x2500)
#   'fps'  int32*3 (r4/r5/r6) -> r0      (0x2510)
FUNCS = {
    'floatToFP_16bit': {
        'addr_rom': 0x2490, 'kind': 'f16',
        'entry_sym': 'rx8_float_to_fixed_16bit', 'n_test': N_DEFAULT,
        'seed': 0x2490,
    },
    'fixedPointToFloat_8bit': {
        'addr_rom': 0x2500, 'kind': 'f8f',
        'entry_sym': 'rx8_fixed_point_to_float_8bit', 'n_test': N_DEFAULT,
        'seed': 0x2500,
    },
    'fixedPointScaling': {
        'addr_rom': 0x2510, 'kind': 'fps',
        'entry_sym': 'rx8_fixed_point_scaling', 'n_test': N_DEFAULT,
        'seed': 0x2510,
    },
}

# ----------------------------------------------------------------------------
# IEEE-754 single bit patterns (same constants as harness_math_primitives_2490)
# ----------------------------------------------------------------------------
_ZERO = 0x00000000
_NZERO = 0x80000000
_ONE = 0x3F800000
_NEGONE = 0xBF800000
_HALF = 0x3F000000
_QTR = 0x3E800000
_P10000 = 0x461C4000              # 1.0e4
_N10000 = 0xC61C4000              # -1.0e4
_P1E30 = 0x731D254A               # ~1.0e30
_N1E30 = 0xF31D254A               # ~-1.0e30
_DEN = 0x00000001                 # min denormal
_SMALL = 0x15A92A40               # ~1.0e-30
_P1EM3 = 0x3A83126F               # ~1.0e-3 (0x2490 scalar floor)
_P1E5 = 0x47C35000                # 1.0e5
_PINF = 0x7F800000
_NINF = 0xFF800000
_QNAN = 0x7FC00000

# 0x2490 edge cross-product: number x scalar x offset (quotient stays < 2^31,
# |scalar| >= 1e-3 and != 0).
_F16_NUMS = [_ZERO, _NZERO, _ONE, _NEGONE, _HALF, _P10000, _N10000,
             0x41A00000,   # 20.0
             0xC1A00000,   # -20.0
             0x49A5E354]   # ~1.3e6
_F16_SCALS = [_ONE, _NEGONE, _HALF, _QTR, 0x40000000,  # 2.0
              _P1EM3, _P1E5, 0x42C80000,               # 100.0
              -0x42C80000, 0x431E0000,                 # 158.0
              _P10000, _N10000]
_F16_OFFS = [_ZERO, _NZERO, _ONE, _NEGONE, _P10000, _N10000, _HALF,
             0xC1200000,   # -10.0
             0x49742400]   # ~1.0e6
EDGE_F16 = [(nb, sb, ob) for nb in _F16_NUMS for sb in _F16_SCALS
            for ob in _F16_OFFS]

# 0x2500 edge cross-product: mult x off x raw.
_MVALS = [_ZERO, _NZERO, _ONE, _NEGONE, _HALF, _P10000, _P1E30, _N1E30,
          _SMALL, _DEN, _PINF, _NINF, _QNAN]
_OVALS = [_ZERO, _NZERO, _ONE, _NEGONE, _P1E30, _N1E30, _SMALL, _PINF,
          _NINF, _QNAN]
_RAWS = [0x00, 0x01, 0x7F, 0x80, 0xFF, 0x10, 0xEF]
EDGE_F8F = [(m, o, r) for m in _MVALS for o in _OVALS for r in _RAWS]

# 0x2510 edge cross-product: a x b x frac (full-range int32; both sides extu.w
# and ftrc wrap identically in the emulator, so this is exact everywhere).
_AB = [0x00000000, 0x00000001, 0xFFFFFFFF, 0x7FFFFFFF, 0x80000000,
       0x3FFFFFFF, 0xC0000000, 0x20000000, 0xE0000000, 0x00008000,
       0xFFFF8000, 0x40000000, 0x12345678, 0xEDCBA987]
_FRACS = [0x0000, 0x0001, 0x007F, 0x0080, 0x00FF, 0x0100, 0x8000, 0xFFFF]
EDGE_FPS = [(a, b, f) for a in _AB for b in _AB for f in _FRACS]


def f2b(x):
    return struct.unpack('>I', struct.pack('>f', x))[0]


def b2f(b):
    return struct.unpack('>f', struct.pack('>I', b & 0xFFFFFFFF))[0]


# ============================================================================
# Toolchain build
# ============================================================================
_blob_cache = {}


def ensure_stubs():
    os.makedirs(STUB_INC, exist_ok=True)
    with open(os.path.join(STUB_INC, 'stdint.h'), 'w') as f:
        f.write(_STDINT)
    with open(os.path.join(STUB_INC, 'math.h'), 'w') as f:
        f.write('#ifndef _MATH_H\n#define _MATH_H\n'
                'float fabsf(float x);\n#endif\n')


def build_blob():
    """Compile the whole source with gcc 3.4.6, link at 0x4000, extract .text.

    Returns (blob_bytes, {symbol: linked_absolute_addr}).  All three leaves
    live in one object, so one build serves all three entries."""
    os.makedirs(WORK, exist_ok=True)
    base = os.path.join(WORK, 'mathprims')
    obj, elf, blb = base + '.o', base + '.elf', base + '.bin'

    subprocess.run(
        [XGCC, '-B', XGCC_B, '-m2e', '-O1', '-fomit-frame-pointer',
         '-c', SRC, '-o', obj,
         '-I', STUB_INC, '-I', os.path.join(SAMPLES, 'src'),
         '-I', os.path.join(SAMPLES, 'include')],
        check=True, capture_output=True)

    ld_script = os.path.join(WORK, 'link346.ld')
    if not os.path.exists(ld_script):
        with open(ld_script, 'w') as f:
            f.write(_LINKER)
    # libgcc.a is harmless here: the three leaves are pure FPU + integer code
    # and reference no ___* helper, so nothing gets pulled from it.
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


def blob_for():
    if 'b' not in _blob_cache:
        _blob_cache['b'] = build_blob()
    return _blob_cache['b']


def ram_overlay(blob):
    return {LINK_BASE + i: blob[i] for i in range(len(blob))}


# ============================================================================
# Vector generation (seeded, reproducible)
# ============================================================================
def rflt(rng):
    """Random single-precision value with realistic firmware magnitudes."""
    return f2b(rng.choice([rng.uniform(-1e4, 1e4), rng.uniform(-2, 2),
                           rng.uniform(0, 300), rng.uniform(-300, 0)]))


def rflt16(rng):
    """Random 0x2490 number/offset in [-1e6, 1e6]."""
    return f2b(rng.uniform(-1e6, 1e6))


def rscalar(rng):
    """Random 0x2490 scalar: magnitude in [2e-3, 1e4], random sign, never 0."""
    mag = rng.uniform(2e-3, 1e4)
    return f2b(-mag if rng.random() < 0.5 else mag)


def gen_vectors(name, n):
    cfg = FUNCS[name]
    kind = cfg['kind']
    rng = make_rng(cfg['seed'])
    vecs = []

    if kind == 'f16':
        vecs = [{'number': nb, 'scalar': sb, 'offset': ob,
                 'desc': 'n=%08X s=%08X o=%08X' % (nb, sb, ob)}
                for nb, sb, ob in EDGE_F16]
        for _ in range(n):
            nb = rflt16(rng); sb = rscalar(rng); ob = rflt16(rng)
            vecs.append({'number': nb, 'scalar': sb, 'offset': ob,
                         'desc': 'n=%08X s=%08X o=%08X' % (nb, sb, ob)})
        return vecs

    if kind == 'f8f':
        vecs = [{'mult': m, 'off': o, 'raw': r,
                 'desc': 'm=%08X o=%08X r=%02X' % (m, o, r)}
                for m, o, r in EDGE_F8F]
        for _ in range(n):
            m = rflt(rng); o = rflt(rng); r = rng.getrandbits(8)
            vecs.append({'mult': m, 'off': o, 'raw': r,
                         'desc': 'm=%08X o=%08X r=%02X' % (m, o, r)})
        return vecs

    if kind == 'fps':
        vecs = [{'a': a, 'b': b, 'frac': f,
                 'desc': 'a=%08X b=%08X f=%04X' % (a & 0xFFFFFFFF,
                                                   b & 0xFFFFFFFF, f & 0xFFFF)}
                for a, b, f in EDGE_FPS]
        for _ in range(n):
            a = rng.getrandbits(32)
            b = rng.getrandbits(32)
            f = rng.getrandbits(32)
            vecs.append({'a': a, 'b': b, 'frac': f,
                         'desc': 'a=%08X b=%08X f=%08X' % (a, b, f)})
        return vecs

    raise RuntimeError('unsupported kind %r' % kind)


# ============================================================================
# Per-function evaluation (identical driver on both sides: cpu.call + SENTINEL)
# ============================================================================
def call_int(cpu, addr, **kw):
    cpu.call(addr, **kw)
    return cpu.r[0] & 0xFFFFFFFF


def run_function(name, cpu):
    cfg = FUNCS[name]
    kind = cfg['kind']
    blob, syms = blob_for()
    base = ram_overlay(blob)
    vecs = gen_vectors(name, cfg['n_test'])
    n = len(vecs)
    t0 = time.time()

    rom_res, blb_res = [], []
    for v in vecs:
        if kind == 'f16':
            fr = {4: b2f(v['number']), 5: b2f(v['scalar']), 6: b2f(v['offset'])}
            rom_res.append(call_int(cpu, cfg['addr_rom'], fr=fr))
            blb_res.append(call_int(cpu, syms[cfg['entry_sym']],
                                    fr=fr, ram=dict(base)))
        elif kind == 'f8f':
            fr = {4: b2f(v['mult']), 5: b2f(v['off'])}
            cpu.call(cfg['addr_rom'], r4=v['raw'], fr=fr)
            rom_res.append(f2b(cpu.fr[0]))
            cpu.call(syms[cfg['entry_sym']], r4=v['raw'], fr=fr, ram=dict(base))
            blb_res.append(f2b(cpu.fr[0]))
        elif kind == 'fps':
            kw = dict(r4=v['a'], r5=v['b'], r6=v['frac'])
            rom_res.append(call_int(cpu, cfg['addr_rom'], **kw))
            blb_res.append(call_int(cpu, syms[cfg['entry_sym']],
                                    ram=dict(base), **kw))
        else:
            raise RuntimeError('unsupported kind %r' % kind)

    mismatches = 0
    samples = []
    for i, (e, h) in enumerate(zip(rom_res, blb_res)):
        if e != h:
            mismatches += 1
            if len(samples) < 5:
                samples.append('vec#%d %s ROM=%08X blob=%08X'
                               % (i, vecs[i]['desc'], e, h))

    dt = time.time() - t0
    return {'name': name, 'n': n, 'mismatch': mismatches, 'time': dt,
            'samples': samples}


def main():
    n_override = int(sys.argv[1]) if len(sys.argv) > 1 else None
    ensure_stubs()
    cpu = load_cpu()

    total = 0
    for name, cfg in FUNCS.items():
        if n_override:
            cfg['n_test'] = n_override
        r = run_function(name, cpu)
        total += r['mismatch']
        status = 'OK  ' if r['mismatch'] == 0 else 'FAIL'
        print('%s %-22s @0x%-6X  n=%-6d  ROM-vs-blob=%d  %.2fs'
              % (status, name, cfg['addr_rom'], r['n'], r['mismatch'],
                 r['time']))
        for s in r['samples']:
            print('        ' + s)

    if total:
        print('\nverify_mathprims: %d mismatch(es) total — FAIL' % total)
        sys.exit(1)
    print('\nverify_mathprims: rx8_math_primitives_2490 family OK '
          '(0 mismatch, era-ROM blob == ROM bytes)')


if __name__ == '__main__':
    main()
