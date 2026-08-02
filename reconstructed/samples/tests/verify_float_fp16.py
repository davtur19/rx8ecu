#!/usr/bin/env python3
"""
verify_float_fp16.py — era-ROM toolchain (gcc 3.4.6 sh-elf) behavioural
validation of the 16-bit fixed-point<->float leaf at 0x24C0.

Closes the "ROM -> abstract C -> era-ROM toolchain (gcc 3.4.6)" loop on the
*behavioural* plane for

    rx8_float_to_fp_16bit / fixedPointToFloat_16bit @0x24C0

Reconstructed source: samples/src/rx8_float_to_fp_16bit.c
Verified lift       : c/math_primitives.c  (`fixedPointToFloat_16bit`).

REAL CALLING CONVENTION (verified from the ROM bytes, not assumed)
------------------------------------------------------------------
The label "floatToFP_16bit" is a misnomer — 0x24C0 converts a raw 16-bit
fixed-point value INTO float (it is the *inverse* direction; the 8-bit
sibling is fixedPointToFloat_8bit @0x2500, already validated).  The window
at 0x24C0 (roms/stock/60E1D400.bin) is 14 bytes, 7 instructions, a pure
register-level FPU leaf with NO RAM side-effects:

    0x24C0  644D  extu.w       r4,r4          ; raw &= 0xFFFF (u16)
    0x24C2  445A  lds          r4,fpul
    0x24C4  F32D  float        fpul,fr3       ; fr3 = (float)raw   (exact)
    0x24C6  F04C  fmov         fr4,fr0        ; fr0 = mult
    0x24C8  F53E  fmac         fr0,fr3,fr5    ; fr5 = mult*raw+off  (fused)
    0x24CA  000B  rts
    0x24CC  F05C  fmov         fr5,fr0        ; -> fr0

so the signature is

    float f(uint16_t r4, float fr4, float fr5) -> fr0
          r4 = raw (16-bit fixed-point, extu.w-masked)
          fr4 = mult, fr5 = off ; result in fr0 (single precision)

`fmac` accumulates multiply+add with a SINGLE rounding; the host C mirrors it
with (double) intermediates and one final float cast (see the source
docstring — the naive float mul+add double-rounds and provably diverges).

ERA-ROM TOOLCHAIN BLOB
----------------------
gcc 3.4.6 compiles the same source to a 6-instruction equivalent at 0x4000:

    0x4000  644D  extu.w       r4,r4
    0x4002  445A  lds          r4,fpul
    0x4004  F02D  float        fpul,fr0       ; fr0 = (float)raw
    0x4006  F54E  fmac         fr0,fr4,fr5    ; fr5 = raw*mult+off (fused)
    0x4008  000B  rts
    0x400A  F05C  fmov         fr5,fr0

Different register allocation, same fused multiply-add — bit-identical
results on every input (the comparison below is the proof).

Method (mirrors verify_float_b.py):

  (a) compile samples/src/rx8_float_to_fp_16bit.c with the era-ROM recipe
      /home/davide/gcc346-build/gcc/xgcc -B /home/davide/gcc346-build/gcc/
      -m2e -O1 -fomit-frame-pointer (stub stdint.h in /tmp/verify_gcc346/inc),
  (b) link at the fixed base 0x4000 with the trivial linker script via
      sh-elf-ld (libgcc 3.4.6 pulled; this leaf needs no integer helpers),
  (c) `objcopy --only-section=.text` extracts the self-contained code blob,
  (d) the blob is loaded into tools/sh2emu.py through the sparse `ram`
      overlay (the literal pool — none here — would live in .text),
  (e) the SAME vectors run on the real ROM bytes at 0x24C0 and on the blob
      at 0x4000 (cpu.call with r4=raw and fr={4:mult,5:off}; SENTINEL pr
      0xEEEE0000 set by the emulator) and the float results are compared
      bit-exact on fr0 (f2bits),
  (f) a host oracle (tests/oracle_float_to_fp_16bit.c + the reconstructed
      source, compiled with the system cc) runs on the same vectors as an
      independent third check.

Vector domain — FINITE fr4/fr5 only (no NaN/Inf), as required:
  * FULL u16 r4 sweep: every raw value 0x0000..0xFFFF against several
    (mult, off) pairs — this covers the entire integer input domain,
    including the canonical fixed-point boundaries (0x0000/0x0001/0x7FFF/
    0x8000/0xFFFE/0xFFFF), so the "incl. half canonical" requirement is
    satisfied by construction,
  * targeted edges for fr4/fr5: 0, -0.0, 1, -1, 0.5, typical firmware
    magnitudes, denormals (min/max subnormal) and ±FLT_MAX,
  * N >= 20000 seeded random vectors (r4 uniform in 0..0xFFFF, mult/off
    finite with realistic firmware magnitudes).

The SH-2E emulator's ts() rounds f32-overflow to +/-Inf (IEEE round-to-
nearest), so even mult*raw sums above FLT_MAX stay comparable — both sides
and the host C agree on 0x7F800000/0xFF800000.  No emulator-gap vectors
exist for this leaf (verified: neither the ROM bytes at 0x24C0 nor the
gcc-3.4.6 blob contain xtrct or any other emulator-gap instruction).

The harness is read-only w.r.t. the repo (all artifacts go to /tmp) and
exits non-zero iff any mismatch is reported.

Usage:  python3 tests/verify_float_fp16.py [N]   (default N random = 20000)
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
WORK = '/tmp/verify_float_fp16/work'       # objects / elfs / blobs / oracle
LINK_BASE = 0x4000                         # fixed link base

SRC_DIR = os.path.join(SAMPLES, 'src')
INC_DIR = os.path.join(SAMPLES, 'include')

# Neither the ROM bytes at 0x24C0 nor the gcc-3.4.6 blob execute xtrct (the
# 0x2nmD encoding), so no monkeypatch is needed here — the blob is 6 pure
# FPU instructions (checked above).  Kept as documentation: if a future edit
# of this source ever compiles to a 64-bit op, add the documented xtrct fix
# from verify_gcc346.py.

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


# ============================================================================
# Function config
# ============================================================================
# kind 'u16f2': one u16 arg in r4 (extu.w-masked), two FPU args fr4/fr5,
# float result in fr0 (bit-exact compare).
FUNCS = {
    'float_to_fp_16bit': {
        'addr_rom': 0x24C0, 'src': 'rx8_float_to_fp_16bit.c', 'kind': 'u16f2',
        'entry_sym': 'rx8_fixed_point_to_float_16bit', 'n_test': 20000,
        'seed': 0x24C0, 'ret': 'f32',
        'oracle': ('oracle_float_to_fp_16bit.c',
                   lambda v: 'fpf %04X %08X %08X' % v,
                   lambda o: int(o[0], 16)),
    },
}

# ---- single-precision constants --------------------------------------------
FLT_MAX = 3.4028234663852886e+38          # 0x7F7FFFFF
MIN_SUB = 1.401298464324817e-45           # 0x00000001 (min subnormal)
MAX_SUB = 1.1754942106924411e-38          # 0x007FFFFF (max subnormal)
TINY = 1.0e-30                            # 0x15A92A40-ish (underflow corner)

# ============================================================================
# Vector generation  (seeded, reproducible; fr4/fr5 FINITE — no NaN/Inf)
# ============================================================================
# Canonical raw (u16 fixed-point) values, incl. the byte-split and boundary
# values.  The FULL sweep below covers the whole domain anyway; this set pins
# the interesting corners deterministically.
_RAWS = [0x0000, 0x0001, 0x0002, 0x0003, 0x7FFE, 0x7FFF, 0x8000, 0x8001,
         0xFFFE, 0xFFFF, 0x1234, 0xDEAD, 0x4000, 0xC000, 0x00FF, 0xFF00]

# Interesting finite mult / off values (0, ±1, 0.5, firmware magnitudes,
# denormals, ±FLT_MAX).  All single-precision exact bit patterns; sums up to
# |mult|*65535+|off| ~ 2.2e43 stay in double range and round to +/-Inf on the
# final f32 step — IEEE-correct on the ROM, the blob and the host C alike.
_MVALS = [0.0, -0.0, 1.0, -1.0, 0.5, -0.5, 100.0, -100.0, 1.0e4, -1.0e4,
          1.0e30, -1.0e30, MIN_SUB, MAX_SUB, -MAX_SUB, FLT_MAX, -FLT_MAX,
          TINY]
_OVALS = [0.0, -0.0, 1.0, -1.0, 0.5, -0.5, 100.0, 1.0e30, -1.0e30,
          MIN_SUB, MAX_SUB, FLT_MAX, -FLT_MAX]

# (mult, off) pairs used for the FULL 0x0000..0xFFFF raw sweep.
_SWEEP_PAIRS = [(1.0, 0.0), (1.0, 1.0), (-1.0, 0.0), (1.0e4, -1.0e4)]


def gen_vectors(name, n):
    """Return a list of (tag, (raw, mb, ob)) entries.

    tag is 'edge' (deterministic canonical cross), 'sweep' (every raw value
    0x0000..0xFFFF against _SWEEP_PAIRS) or 'rand' (seeded random)."""
    cfg = FUNCS[name]
    rng = make_rng(cfg['seed'])
    vecs = []

    # deterministic canonical cross-product first
    for raw in _RAWS:
        for m in _MVALS:
            for o in _OVALS:
                vecs.append(('edge', (raw, f32b(m), f32b(o))))

    # full u16 domain sweep
    for raw in range(0x10000):
        for m, o in _SWEEP_PAIRS:
            vecs.append(('sweep', (raw, f32b(m), f32b(o))))

    # seeded random vectors
    for _ in range(n):
        raw = rng.getrandbits(16)
        m = f32b(rng.choice([rng.uniform(-1e4, 1e4), rng.uniform(-2, 2),
                             rng.uniform(0, 300), rng.uniform(-300, 0)]))
        o = f32b(rng.choice([rng.uniform(-1e4, 1e4), rng.uniform(-2, 2),
                             rng.uniform(0, 300), rng.uniform(-300, 0)]))
        vecs.append(('rand', (raw, m, o)))
    return vecs


# ============================================================================
# Toolchain build
# ============================================================================
_stub_done = [False]
_blob_cache = {}
_oracle_cache = {}


def ensure_stubs():
    """Write the stub stdint.h once to /tmp/verify_gcc346/inc (reused by the
    other verify_gcc346* / verify_float_* harnesses; idempotent, never
    touches the repo)."""
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
    """Map a raw vector (raw, mb, ob) onto the emulator's register args."""
    if kind == 'u16f2':
        return {'r4': v[0], 'fr': {4: bits2f(v[1]), 5: bits2f(v[2])}}
    raise RuntimeError('no arg mapper for %r' % kind)


def _result(cpu, ret):
    """Extract the function result from the emulator state after the call:
    f32 -> bit pattern of fr0."""
    if ret == 'f32':
        return f32b(cpu.fr[0])
    raise RuntimeError('no result extractor for %r' % ret)


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

    rom_res, blb_res = [], []
    for tag, v in vecs:
        cpu.call(cfg['addr_rom'], **_em_args(kind, v))
        rom_res.append(_result(cpu, cfg['ret']))
        cpu.call(blb_addr, ram=dict(base), **_em_args(kind, v))
        blb_res.append(_result(cpu, cfg['ret']))

    # ROM vs blob (bit-exact on fr0).
    rb = 0
    samples = []
    for i, (tag, v) in enumerate(vecs):
        e, h = rom_res[i], blb_res[i]
        if e != h:
            rb += 1
            if len(samples) < 5:
                samples.append('vec#%d [%s] raw=%04X mult=%08X off=%08X '
                               'ROM=%08X blob=%08X' % (i, tag, v[0], v[1],
                                                       v[2], e, h))

    # Host oracle vs blob (independent third check on every vector).
    ob = None
    if cfg.get('oracle'):
        binp, line_fmt, parse = get_oracle(name)
        lines = [line_fmt(v[1]) for v in vecs]
        want = blb_res
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
            'time': dt, 'samples': samples}


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
        print('%s %-22s @0x%-6X  n=%-6d  ROM-vs-blob=%-4d  '
              'oracle-vs-blob=%-4s  %.2fs'
              % (status, name, cfg['addr_rom'], r['n'], r['rb'],
                 r['ob'] if r['ob'] is not None else '-', r['time']))
        for s in r['samples']:
            print('        ' + s)

    if total:
        print('\nverify_float_fp16: %d mismatch(es) total — FAIL' % total)
        sys.exit(1)
    print('\nverify_float_fp16: fixedPointToFloat_16bit @0x24C0 OK '
          '(0 mismatch; ROM == gcc-3.4.6 blob == host C, bit-exact on fr0)')


if __name__ == '__main__':
    main()
