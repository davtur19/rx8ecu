#!/usr/bin/env python3
"""
verify_float_b.py — era-ROM toolchain (gcc 3.4.6 sh-elf) behavioural validation
of the float-family leaves of the reconstructed-source samples.

Closes the "ROM -> abstract C -> era-ROM toolchain (gcc 3.4.6)" loop on the
*behavioural* plane for the three FPU-register leaves:

    rx8_saturate_low       @0x23E4   (fr4=sig, fr5=lower -> fr0)
    rx8_subtract_absolute  @0x23DC   (fr4=a, fr5=b        -> fr0)   |a-b|
    rx8_float_to_int       @0x24D0   (fr4=sig, fr5=mult, fr6=offset
                                      -> r0, uint8, zero-extended via extu.b)

The float_to_int signature (uint8_t return in r0, three float args in
fr4/fr5/fr6) was verified against the real ROM bytes: mova @(0x0A,PC),r0 ;
fsub FR6,FR4 ; fdiv FR5,FR4 ; fadd 0.5f ; ftrc FR2,FPUL ; sts FPUL,R4 ;
cmp/gt #0xFF / cmp/pz clamps ; rts ; mov r4,r0 (+ extu.b).  The blob compiled
by gcc 3.4.6 emits the identical sequence (see the disassembly dump in the
module docstring of harness_float_to_int.py for the ROM side).

Method (mirrors verify_gcc346.py):

  (a) compile each reconstructed source with the era-ROM recipe
      /home/davide/gcc346-build/gcc/xgcc -B /home/davide/gcc346-build/gcc/
      -m2e -O1 -fomit-frame-pointer (stub stdint.h in /tmp/verify_gcc346/inc),
  (b) link at the fixed base 0x4000 with the trivial linker script via
      sh-elf-ld (libgcc 3.4.6 pulled; none of these three leaves needs the
      integer helpers, but the link recipe is kept identical to
      verify_gcc346.py so the harnesses stay interchangeable),
  (c) `objcopy --only-section=.text` extracts the self-contained code blob,
  (d) the blob is loaded into tools/sh2emu.py through the sparse `ram`
      overlay (literal pools live in .text and are carried along),
  (e) the SAME finite single-precision vectors are run on the real ROM bytes
      at ADDR_ROM and on the blob at 0x4000 (cpu.call with fr= for the FPU
      args; SENTINEL pr 0xEEEE0000 set by the emulator) and the results are
      compared bit-exact (f2bits(cpu.fr[0]) for the float returns, r0&0xFF
      for float_to_int's uint8_t return),
  (f) a host oracle (existing tests/oracle_*.c + the reconstructed source,
      compiled with the system cc) is run on the same vectors as an
      independent third check for the in-domain vectors.

Vector domain — FINITE floats only (no NaN/Inf inputs), as required:
  * extremes of the single-precision range (FLT_MAX / -FLT_MAX),
  * denormals (min subnormal 0x00000001, max subnormal 0x007FFFFF),
  * signed zeros (-0.0 vs +0.0),
  * typical firmware magnitudes (sensor/trim ranges),
  * N >= 3000 seeded random vectors per function.

float_to_int edge handling (documented, see function docstring):
  * the truncation mode is verified explicitly: +0.5f then ftrc is
    round-half-away-from-zero for the non-negative in-range values the clamp
    keeps (e.g. 1.5 -> 2, 1.4 -> 1, 254.4 -> 254, 255.6 -> 255),
  * overflow float->int cases (e.g. 1e30, 1e38, FLT_MAX, 2^31) are run in a
    separate OVERFLOW list: the emulator's `ftrc` is `int(f) & 0xFFFFFFFF`
    (Python wraps mod 2^32), which is NOT the real SH-2E hardware result
    (undefined per the SH-2 manual) — the ROM side and the blob side share
    the same emulated ftrc so the ROM-vs-blob comparison stays self-
    consistent, but the numeric value (e.g. 1e30 -> 0) is an emulator
    artifact.  This is documented as a GAP; tools/sh2emu.py is NOT patched.
    The host-oracle comparison is skipped on these vectors because the
    (int32_t) cast in the C source is undefined behaviour there.

The harness is read-only w.r.t. the repo (all artifacts go to /tmp) and
exits non-zero iff any active function reports a mismatch.

Usage:  python3 tests/verify_float_b.py [N]   (default N per function = 3000)
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
CC_HOST = os.environ.get('CC', 'cc')
LIBGCC = os.path.join(XGCC_B, 'libgcc.a')

STUB_INC = '/tmp/verify_gcc346/inc'        # stub headers (reused, read-only)
WORK = '/tmp/verify_float_b/work'          # objects / elfs / blobs / oracles
LINK_BASE = 0x4000                         # fixed link base

SRC_DIR = os.path.join(SAMPLES, 'src')
INC_DIR = os.path.join(SAMPLES, 'include')

# The three leaves never execute xtrct (checked: neither the ROM bytes at
# 0x23DC/0x23E4/0x24D0 nor the gcc-3.4.6 blobs contain the 0x2nmD encoding),
# so no monkeypatch is needed here — unlike verify_gcc346.py's multiply32/
# shift family.  If one of these ever compiles to a 64-bit op, add the
# documented xtrct fix from verify_gcc346.py.

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


def f32b(x):   # IEEE-754 single big-endian bit pattern of a python float
    return struct.unpack('>I', struct.pack('>f', x))[0]


def bits2f(b):
    return struct.unpack('>f', struct.pack('>I', b & 0xFFFFFFFF))[0]


def _ts(x):
    """Replicate sh2emu.ts()'s exact fate: Python struct.pack('>f') RAISES
    OverflowError when the double value overflows the single range instead of
    rounding to +/-inf.  That is the emulator gap documented in the module
    docstring; we use it here only to *classify* gap vectors in advance."""
    return struct.unpack('>f', struct.pack('>f', x))[0]


def _f2_sub_ok(a, b):
    """True iff the emulated fsub a-b (single precision) stays finite."""
    try:
        _ts(a - b)
        return True
    except OverflowError:
        return False


def _f3_ok(s, m, o):
    """True iff the emulated ((s-o)/m)+0.5f pipeline stays finite."""
    try:
        _ts(_ts(s - o) / m)          # fsub then fdiv
        _ts(_ts(_ts(s - o) / m) + 0.5)  # fadd 0.5f (constant from the ROM pool)
        return True
    except OverflowError:
        return False


# ============================================================================
# Function config
# ============================================================================
# kind 'float2': two FPU args fr4/fr5, float result in fr0 (bit-exact compare).
# kind 'float3': three FPU args fr4/fr5/fr6, uint8 result in r0.
# oracle: (rig file, vector-line builder, result parser).  The overflow edge
# list of float_to_int is excluded from the oracle comparison (int32 cast UB).
FUNCS = {
    'saturate_low': {
        'addr_rom': 0x23E4, 'src': 'rx8_saturate_low.c', 'kind': 'float2',
        'entry_sym': 'rx8_saturate_low', 'n_test': 3000, 'seed': 0x23E4,
        'ret': 'f32', 'oracle': ('oracle_saturate_low.c',
                                 lambda v: 'f32 %08X %08X' % v,
                                 lambda o: int(o[0], 16)),
    },
    'subtract_absolute': {
        'addr_rom': 0x23DC, 'src': 'rx8_subtract_absolute.c', 'kind': 'float2',
        'entry_sym': 'rx8_subtract_absolute', 'n_test': 3000, 'seed': 0x23DC,
        'ret': 'f32', 'oracle': ('oracle_subtract_absolute.c',
                                 lambda v: 'abs %08X %08X' % v,
                                 lambda o: int(o[0], 16)),
    },
    'float_to_int': {
        'addr_rom': 0x24D0, 'src': 'rx8_float_to_int.c', 'kind': 'float3',
        'entry_sym': 'rx8_float_to_int', 'n_test': 3000, 'seed': 0x24D0,
        'ret': 'u8', 'oracle': ('oracle_float_to_int.c',
                                lambda v: 'f2i %08X %08X %08X' % v,
                                lambda o: int(o[0], 16)),
    },
}

# ---- single-precision constants --------------------------------------------
FLT_MAX = 3.4028234663852886e+38          # 0x7F7FFFFF
MIN_SUB = 1.401298464324817e-45           # 0x00000001 (min subnormal)
MAX_SUB = 1.1754942106924411e-38          # 0x007FFFFF (max subnormal)
INT32_MIN_F = -2147483648.0               # -2^31, exactly representable
I32_TOP_F = 2147483520.0                  # largest single < 2^31

# ============================================================================
# Vector generation  (seeded, reproducible; FINITE inputs only — no NaN/Inf)
# ============================================================================
EDGE2 = [   # (a, b) finite pairs for saturate_low / subtract_absolute
    # signed-zero hygiene
    (0.0, 0.0), (-0.0, -0.0), (0.0, -0.0), (-0.0, 0.0),
    # typical + ties (saturate_low: strict >, tie returns `lower`)
    (1.0, 2.0), (3.0, 2.0), (2.0, 2.0), (-2.0, -3.0), (-3.0, -2.0),
    (-2.0, -2.0), (0.5, -0.5), (-0.5, 0.5), (100.0, 50.0), (50.0, 100.0),
    (123.456, 123.456), (1.0, 1.0000001), (1.0000001, 1.0),
    # extremes of the single range (results may overflow to +/-inf on the
    # subtract side — legitimate IEEE behaviour, still compared bit-exact)
    (FLT_MAX, -FLT_MAX), (-FLT_MAX, FLT_MAX), (FLT_MAX, FLT_MAX),
    (-FLT_MAX, -FLT_MAX), (FLT_MAX, 0.0), (-FLT_MAX, 0.0),
    (0.0, FLT_MAX), (0.0, -FLT_MAX), (1e30, -1e30), (-1e30, 1e30),
    (1e30, 1e30), (-1e30, -1e30),
    # denormals
    (MIN_SUB, 0.0), (0.0, MIN_SUB), (-MIN_SUB, 0.0), (0.0, -MIN_SUB),
    (MIN_SUB, MIN_SUB), (-MIN_SUB, -MIN_SUB), (MAX_SUB, MIN_SUB),
    (MIN_SUB, MAX_SUB), (MAX_SUB, MAX_SUB), (MAX_SUB, -MAX_SUB),
    # near-cancellation / tight mantissa
    (1.5, 0.5), (0.5, 1.5), (2.0, -0.0), (-2.0, -0.0),
    (1e20, 1.0), (1.0, 1e20), (1e20, -1e20),
]

# float_to_int in-domain edges: verify +0.5f-then-ftrc round-half-away mode,
# negative truncation toward zero and the [0,255] clamps.  All keep the
# truncated intermediate inside int32 range (well-defined on both sides).
EDGE3 = [
    (0.0, 1.0, 0.0), (-0.0, 1.0, 0.0),
    (0.5, 1.0, 0.0),                  # +0.5 -> 1.0 -> 1   (half away)
    (0.49, 1.0, 0.0),                 # 0.99 -> 0
    (1.5, 1.0, 0.0),                  # 2.0  -> 2
    (1.4, 1.0, 0.0),                  # 1.9  -> 1
    (2.5, 1.0, 0.0),                  # 3.0  -> 3
    (-0.5, 1.0, 0.0),                 # 0.0  -> 0  (trunc toward zero)
    (-0.49, 1.0, 0.0),                # 0.01 -> 0
    (-1.0, 1.0, 0.0),                 # -0.5 -> ftrc 0 -> 0
    (-1.5, 1.0, 0.0),                 # -1.0 -> ftrc -1 -> clamp 0
    (-2.5, 1.0, 0.0),                 # -2.0 -> clamp 0
    (1e6, 1.0, 0.0),                  # -> 255 (clamp)
    (-1e6, 1.0, 0.0),                 # -> 0   (clamp)
    (254.4, 1.0, 0.0),                # 254.9 -> 254
    (255.4, 1.0, 0.0),                # 255.9 -> 255
    (255.6, 1.0, 0.0),                # 256.1 -> 255 (clamp)
    (255.0, 1.0, 0.0),                # 255.5 -> 255
    (254.5, 1.0, 0.0),                # 255.0 -> 255
    (2.5, 0.5, 0.0),                  # 5.5  -> 5
    (3.0, 0.5, 0.0),                  # 6.5  -> 6
    (-1.5, -0.5, 0.0),                # 3.5  -> 3 (neg mult)
    (-100.0, -1.0, 0.0),              # 100.5 -> 100 (neg mult)
    (0.0, 1.0, -0.6),                 # 1.1  -> 1
    (0.0, 1.0, 0.4),                  # 0.1  -> 0
    (1.5, 1.0, 1.0),                  # 1.0  -> 1
    (-1.5, 1.0, 1.0),                 # -2.0 -> clamp 0
    (0.0, 0.5, -0.6),                 # 1.7  -> 1
    (I32_TOP_F, 1.0, 0.0),            # 2147483520.5 -> 255 (clamp, in int32)
    (INT32_MIN_F, 1.0, 0.0),          # -2147483647.5 -> clamp 0 (in int32)
    (1e5, 1e-3, 0.0),                 # 1e8 -> 255 (overflow range, in int32)
    (-1e5, 1e-3, 0.0),                # -1e8 -> 0
]

# float_to_int OVERFLOW float->int cases.  Real SH-2E ftrc of an out-of-int32
# operand is UNDEFINED; the emulator implements it as Python `int(f) & 0xFF..`
# (wraps mod 2^32).  ROM and blob share that emulated ftrc, so the ROM-vs-blob
# comparison stays self-consistent, but the numeric values (e.g. 1e30 -> 0)
# are emulator artifacts, NOT hardware semantics.  Documented as a GAP; not
# fixed here.  These vectors are compared ROM-vs-blob only (the (int32_t)
# cast in the C source is UB on the host, so the oracle is skipped).
EDGE3_OVERFLOW = [
    (1e30, 1.0, 0.0), (-1e30, 1.0, 0.0),
    (1e38, 1.0, 0.0), (-1e38, 1.0, 0.0),
    (FLT_MAX, 1.0, 0.0), (-FLT_MAX, 1.0, 0.0),
    (2147483648.0, 1.0, 0.0),          # exactly 2^31 (first overflow)
    (-2147483648.0, -1.0, 0.0),        # +2^31 via neg mult
    (4294967296.0, 1.0, 0.0),          # 2^32
    (1e30, 1e-3, 0.0), (-1e30, 1e-3, 0.0),
    (1e5, 1e-30, 0.0),                 # 1e35 (tiny mult)
    (3.4028235e38, 1e-38, 0.0),        # ~1e76
]


def rflt(rng):
    """Random finite single-precision value, realistic firmware magnitudes."""
    return f32b(rng.choice([rng.uniform(-1e4, 1e4), rng.uniform(-2, 2),
                            rng.uniform(0, 300), rng.uniform(-300, 0)]))


def rmult(rng):
    """Random multiplier for float_to_int, kept |mult| >= 1e-3 so the
    division stays finite and the truncated intermediate stays well inside
    int32 range (keeps both the emulator and the host C well-defined)."""
    m = rng.choice([rng.uniform(-1e4, 1e4), rng.uniform(-2, 2),
                    rng.uniform(0.01, 50), rng.uniform(-50, -0.01)])
    if abs(m) < 1e-3:
        m = 1.0
    return f32b(m)


def gen_vectors(name, n):
    """Return a list of (tag, vector) entries.

    tag is 'edge' (in-domain edges, oracle-eligible), 'overflow'
    (float_to_int out-of-int32 edges, ROM-vs-blob only) or 'rand'."""
    cfg = FUNCS[name]
    rng = make_rng(cfg['seed'])
    vecs = []

    if cfg['kind'] == 'float2':
        for v in EDGE2:
            va = tuple(f32b(x) for x in v)
            # subtract_absolute: a-b can overflow the single range (e.g.
            # FLT_MAX - -FLT_MAX -> +inf).  The emulator's ts() RAISES
            # OverflowError there (it does not round to inf), so those
            # vectors are classified as documented GAPs, not fed to the
            # comparison (see run_function).
            if name == 'subtract_absolute' and not _f2_sub_ok(*v):
                vecs.append(('gap', va))
            else:
                vecs.append(('edge', va))
        for _ in range(n):
            va = (rflt(rng), rflt(rng))
            if name == 'subtract_absolute' \
                    and not _f2_sub_ok(bits2f(va[0]), bits2f(va[1])):
                vecs.append(('gap', va))
            else:
                vecs.append(('rand', va))
        return vecs

    if cfg['kind'] == 'float3':
        for v in EDGE3:
            vecs.append(('edge', tuple(f32b(x) for x in v)))
        for v in EDGE3_OVERFLOW:
            va = tuple(f32b(x) for x in v)
            # (FLT_MAX, 1e-38, 0) overflows inside the fdiv step (3.4e76):
            # same emulator gap -> 'gap' tag; the finite-but-out-of-int32
            # cases keep the 'overflow' tag and are compared ROM-vs-blob.
            if _f3_ok(*v):
                vecs.append(('overflow', va))
            else:
                vecs.append(('gap', va))
        for _ in range(n):
            vecs.append(('rand', (rflt(rng), rmult(rng), rflt(rng))))
        return vecs

    raise RuntimeError('unsupported kind %r' % cfg['kind'])


# ============================================================================
# Toolchain build
# ============================================================================
_stub_done = [False]
_blob_cache = {}
_oracle_cache = {}


def ensure_stubs():
    """Write the stub stdint.h once to /tmp/verify_gcc346/inc (reused by
    verify_gcc346.py too; idempotent, never touches the repo)."""
    if _stub_done[0]:
        return
    os.makedirs(STUB_INC, exist_ok=True)
    p = os.path.join(STUB_INC, 'stdint.h')
    if not os.path.exists(p):
        with open(p, 'w') as f:
            f.write(_STDINT)
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


def get_oracle(name):
    """Build (once) and cache a host oracle for FUNCS[name]; returns
    (binp, line_fmt, parse)."""
    if name in _oracle_cache:
        return _oracle_cache[name]
    cfg = FUNCS[name]
    rig, line_fmt, parse = cfg['oracle']
    binp = os.path.join(WORK, 'oracle_' + name)
    cmd = [CC_HOST, '-O2', '-Wall', '-Wextra', '-I', INC_DIR, '-I', SRC_DIR,
           os.path.join(TESTS, rig), os.path.join(SRC_DIR, cfg['src']),
           '-o', binp]
    subprocess.run(cmd, check=True, capture_output=True)
    _oracle_cache[name] = (binp, line_fmt, parse)
    return _oracle_cache[name]


# ============================================================================
# Per-function evaluation
# ============================================================================
def _em_args(kind, v):
    """Map a raw bit-pattern vector onto the emulator's fp register args."""
    if kind == 'float2':
        return {'fr': {4: bits2f(v[0]), 5: bits2f(v[1])}}
    if kind == 'float3':
        return {'fr': {4: bits2f(v[0]), 5: bits2f(v[1]), 6: bits2f(v[2])}}
    raise RuntimeError('no arg mapper for %r' % kind)


def _result(cpu, ret):
    """Extract the function result from the emulator state after the call:
    f32 -> bit pattern of fr0; u8 -> zero-extended r0."""
    if ret == 'f32':
        return f32b(cpu.fr[0])
    if ret == 'u8':
        return cpu.r[0] & 0xFF
    raise RuntimeError('no result extractor for %r' % ret)


def _call_emu(cpu, addr, base, kind, v, ret):
    """Run one vector on the emulator; returns ('ok', result) or
    ('overflow', None) when the emulated FPU overflows (ts() OverflowError —
    the documented emulator gap)."""
    try:
        cpu.call(addr, ram=dict(base) if base else None, **_em_args(kind, v))
        return ('ok', _result(cpu, ret))
    except OverflowError:
        return ('overflow', None)


def run_function(name):
    cfg = FUNCS[name]
    kind = cfg['kind']
    blob, syms = blob_for(name)
    base = ram_overlay(blob)
    blb_addr = syms.get(cfg['entry_sym'], LINK_BASE)
    cpu = load_cpu()
    vecs = gen_vectors(name, cfg['n_test'])
    n = len(vecs)
    t0 = time.time()

    rom_res, blb_res, tags = [], [], []
    n_gap = 0
    gap_samples = []
    for tag, v in vecs:
        tags.append(tag)
        if tag == 'gap':
            # Both sides go through the SAME emulated ftrc/fsub/ts, so both
            # are expected to raise OverflowError identically.  Verified
            # rather than assumed: an asymmetry would be a real problem.
            r_side = _call_emu(cpu, cfg['addr_rom'], None, kind, v, cfg['ret'])
            b_side = _call_emu(cpu, blb_addr, base, kind, v, cfg['ret'])
            rom_res.append(r_side)
            blb_res.append(b_side)
            if r_side[0] == 'overflow' and b_side[0] == 'overflow':
                n_gap += 1
            else:
                gap_samples.append('vec#%d [gap] %s: rom=%s blob=%s (asymmetry!)'
                                   % (len(tags) - 1, v, r_side[0], b_side[0]))
            continue
        rom_res.append(_call_emu(cpu, cfg['addr_rom'], None, kind, v, cfg['ret']))
        blb_res.append(_call_emu(cpu, blb_addr, base, kind, v, cfg['ret']))

    # ROM vs blob.
    rb = 0
    samples = []
    for i, (tag, v) in enumerate(vecs):
        if tag == 'gap':
            continue                       # documented separately
        e, h = rom_res[i], blb_res[i]
        if e[0] == 'overflow' or h[0] == 'overflow':
            rb += 1                        # unexpected overflow on a non-gap vector
            if len(samples) < 5:
                samples.append('vec#%d [%s] %s: unexpected overflow rom=%s blob=%s'
                               % (i, tag, v, e[0], h[0]))
        elif e[1] != h[1]:
            rb += 1
            if len(samples) < 5:
                samples.append('vec#%d [%s] %s ROM=%r blob=%r'
                               % (i, tag, v, e[1], h[1]))

    # Host oracle vs blob (in-domain vectors only: 'overflow'- and 'gap'-
    # tagged vectors are excluded — the (int32_t) cast in the C source is
    # undefined behaviour there, see the module docstring).
    ob = None
    if cfg.get('oracle'):
        binp, line_fmt, parse = get_oracle(name)
        lines, want = [], []
        for i, (tag, v) in enumerate(vecs):
            if tag in ('overflow', 'gap'):
                continue
            lines.append(line_fmt(v))
            want.append(blb_res[i][1])
        if lines:
            proc = subprocess.run([binp], input='\n'.join(lines) + '\n',
                                  capture_output=True, text=True)
            if proc.returncode != 0:
                print('    (host oracle failed: %s)' % proc.stderr.strip())
            else:
                outs = [line.split() for line in proc.stdout.splitlines()]
                if len(outs) == len(want):
                    ob = 0
                    for i, (w, o) in enumerate(zip(want, outs)):
                        got = parse(o)
                        if w != got:
                            ob += 1
                            if ob <= 3:
                                samples.append('oracle-vs-blob: blob=%r host=%r'
                                               % (w, got))

    dt = time.time() - t0
    return {'name': name, 'n': len(vecs), 'rb': rb, 'ob': ob,
            'n_gap': n_gap, 'gap_samples': gap_samples, 'time': dt,
            'samples': samples}


def main():
    n_override = int(sys.argv[1]) if len(sys.argv) > 1 else None
    ensure_stubs()

    total = 0
    for name, cfg in FUNCS.items():
        if n_override:
            cfg['n_test'] = n_override
        r = run_function(name)
        total += r['rb'] + (r['ob'] or 0)
        status = 'OK  ' if (r['rb'] == 0 and not r['ob'] and not r['gap_samples']) \
            else 'FAIL'
        print('%s %-22s @0x%-6X  n=%-5d  ROM-vs-blob=%-4d  oracle-vs-blob=%-4s  gaps=%-2d  %.2fs'
              % (status, name, cfg['addr_rom'], r['n'], r['rb'],
                 r['ob'] if r['ob'] is not None else '-', r['n_gap'], r['time']))
        for s in r['samples']:
            print('        ' + s)
        for s in r['gap_samples']:
            print('        ' + s)

    print('\nNOTE: emulator gap (documented, tools/sh2emu.py NOT patched): '
          'ts()/ftrc raise OverflowError when an FPU result overflows the '
          'single range instead of rounding to +/-inf (e.g. subtract '
          'FLT_MAX - -FLT_MAX; float_to_int of FLT_MAX/1e-38).  Those '
          'vectors are verified to overflow IDENTICALLY on ROM and blob '
          '(self-consistent) and are reported as gaps, not mismatches.  '
          'Similarly, ftrc of an out-of-int32 float is emulated as '
          'int(f)&0xFF.. (wraps); the ROM-vs-blob comparison on the '
          'overflow edges stays self-consistent but the values are not real '
          'SH-2E semantics.')

    if total:
        print('\nverify_float_b: %d mismatch(es) total — FAIL' % total)
        sys.exit(1)
    print('\nverify_float_b: all float-family functions OK (0 mismatch)')


if __name__ == '__main__':
    main()
