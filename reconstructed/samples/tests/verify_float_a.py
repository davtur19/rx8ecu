#!/usr/bin/env python3
"""
verify_float_a.py — era-ROM float-leaf validation (sh-elf gcc 3.4.6).

Closes the "ROM -> abstract C -> era-ROM toolchain (gcc 3.4.6)" loop on the
*behavioural* plane for the two register-only FPU leaves whose result is a
single float returned in FR0 (fr-convention):

  rx8_min_value @0x23F4   (fr4 = a, fr5 = b           -> fr0)
  rx8_saturate @0x2404    (fr4 = sig, fr5 = lower, fr6 = upper -> fr0)

For every function this harness:

  (a) creates the minimal target stubs stdint.h / math.h once in
      /tmp/verify_gcc346/inc (the archived gcc 3.4.6 was configured
      --without-headers; the stubs already exist there, they are only
      re-created if missing),
  (b) compiles the reconstructed source with the era-ROM recipe
      `-m2e -O1 -fomit-frame-pointer` via /home/davide/gcc346-build/gcc/xgcc,
  (c) links the object at a fixed base 0x4000 with a trivial linker script,
      pulling the libgcc 3.4.6 helpers that the leaf may compile to,
  (d) `objcopy --only-section=.text` extracts a self-contained code blob,
  (e) loads the blob into the same SH-2E emulator (tools/sh2emu.py) through
      the sparse `ram` overlay,
  (f) generates N seeded finite float vectors (NO NaN/Inf for now) covering
      the extremes ±FLT_MAX, denormals, -0.0, ±0.5, 0, 1, -1, 3.14 and
      mixed magnitudes,
  (g) runs BOTH the real ROM bytes at ADDR_ROM and the blob at 0x4000 on the
      very same vectors (fp args via fr=, result read back from fr0; r0 must
      agree as well) and compares the single-precision results bit-exact.

Emulator-gap workaround (documented, same patch as verify_gcc346.py):
tools/sh2emu.py's `xtrct` has the two shifts' register roles swapped.  These
two leaves never execute xtrct, but the patch is applied to the SH2 class once
before any call so the harness stays in step with the era-toolchain gap.

The harness is read-only w.r.t. the repo: everything it writes goes to /tmp,
and the exit code is non-zero iff any function reports mismatch(es).

Usage:  python3 tests/verify_float_a.py [N]   (default N random per function)
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
LIBGCC = os.path.join(XGCC_B, 'libgcc.a')

STUB_INC = '/tmp/verify_gcc346/inc'        # stub headers (already there; re-created if missing)
WORK = '/tmp/verify_float_a/work'          # objects / elfs / blobs
LINK_BASE = 0x4000                         # fixed link base

SRC_DIR = os.path.join(SAMPLES, 'src')
INC_DIR = os.path.join(SAMPLES, 'include')

# ============================================================================
# Emulator-gap workaround — XTRCT (documented, same as verify_gcc346.py)
# Real semantics (Renesas SH-2 manual XTRCT `0010nnnnmmmm1101`, destination
# n = bits 11-8, source m = bits 7-4):
#     R[n] = ((R[m] << 16) & 0xFFFF0000) | ((R[n] >> 16) & 0x0000FFFF)
# ============================================================================
_SH2_exec_orig = SH2._exec


def _xtrct_fixed(self, op, pc):
    if (op & 0xF00F) == 0x200D:                       # xtrct Rm,Rn
        m = (op >> 4) & 0xF
        n = (op >> 8) & 0xF
        self.r[n] = (((self.r[m] << 16) & 0xFFFF0000)
                     | ((self.r[n] >> 16) & 0xFFFF)) & 0xFFFFFFFF
        return
    return _SH2_exec_orig(self, op, pc)


SH2._exec = _xtrct_fixed

# ============================================================================
# Stub headers (re-created only if missing; stdint.h / math.h from the era-ROM
# recipe — the archived gcc 3.4.6 was configured --without-headers)
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
# Both leaves are register-only FPU functions: fp args arrive in fr4..fr6 and
# the result is returned in fr0 (the fr-convention).  r0 is untouched by the
# ROM code, so r0 must read back 0 on both sides.
FUNCS = {
    'min_value': {
        'addr_rom': 0x23F4, 'src': 'rx8_min_value.c', 'nargs': 2,
        'entry_sym': 'rx8_min_value', 'n_test': 4000, 'seed': 0x23F4,
        'edges': 'min',
    },
    'saturate': {
        'addr_rom': 0x2404, 'src': 'rx8_saturate.c', 'nargs': 3,
        'entry_sym': 'rx8_saturate', 'n_test': 4000, 'seed': 0x2404,
        'edges': 'sat',
    },
}

# ============================================================================
# Finite edge values — IEEE-754 single-precision bit patterns.
# NOTE: by design this harness covers only the FINITE domain (no NaN/Inf for
# now); the NaN/Inf operand-order cases are pinned by harness_min_value.py and
# harness_saturate.py (host-C vs ROM) and can be added here later.
# ============================================================================
_ZERO    = 0x00000000
_NZERO   = 0x80000000              # -0.0
_ONE     = 0x3F800000
_NEGONE  = 0xBF800000
_HALF    = 0x3F000000              # +0.5
_NHALF   = 0xBF000000              # -0.5
_PI      = 0x4048F5C3              # 3.14f
_NPI     = 0xC048F5C3              # -3.14f
_P15     = 0x3FC00000              # 1.5
_N15     = 0xBFC00000              # -1.5
_BIG     = 0x49742400              # 1.0e6
_MAXF    = 0x7F7FFFFF              # +FLT_MAX
_NMAXF   = 0xFF7FFFFF              # -FLT_MAX
_MINNORM = 0x00800000              # smallest normal (FLT_MIN)
_NMINNORM = 0x80800000             # -FLT_MIN
_MAXDEN  = 0x007FFFFF              # largest denormal
_MINDEN  = 0x00000001              # min denormal
_MIDDEN  = 0x00400000              # mid denormal
_NP1     = 0x3F800001              # 1.0000001
_C100    = 0x42C80000              # 100.0
_N43     = 0xC42C0000              # -43.0 (typical sensor magnitude)

# Interesting finite values swept through the edge sets below.
F = [_ZERO, _NZERO, _ONE, _NEGONE, _HALF, _NHALF, _PI, _NPI,
     _MAXF, _NMAXF, _MINNORM, _NMINNORM, _MAXDEN, _MINDEN, _MIDDEN,
     _P15, _N15, _BIG, _NP1, _C100, _N43]

# --- rx8_min_value @0x23F4  (a in fr4, b in fr5) -----------------------------
EDGE_MIN = []
# Ties: identical operands (incl. ±0.0 and the extremes) round-trip bit-exact.
for v in F:
    EDGE_MIN.append((v, v))
# Sign boundary: +0.0 vs -0.0 in both orders (b wins on the fcmp/gt tie).
EDGE_MIN += [(_ZERO, _NZERO), (_NZERO, _ZERO), (_ONE, _NZERO), (_NZERO, _ONE)]
# Extremes and denormals against each other.
EDGE_MIN += [(_MAXF, _NMAXF), (_NMAXF, _MAXF), (_MAXF, _MINDEN),
             (_MINDEN, _MAXF), (_MAXDEN, _MINNORM), (_MINNORM, _MAXDEN),
             (_MAXF, _MAXF), (_NMAXF, _NMAXF)]
# Cross-sweep: every interesting value against a fixed small set.
for x in F:
    for y in (_ZERO, _ONE, _NEGONE, _MAXF, _MINDEN, _NMAXF):
        EDGE_MIN.append((x, y))

# --- rx8_saturate @0x2404  (sig in fr4, lower in fr5, upper in fr6) ----------
EDGE_SAT = [
    # Classic band [1.0, 1.5]: below / at-lower / in-band / at-upper / above.
    (_HALF, _ONE, _P15), (_ONE, _ONE, _P15), (_NP1, _ONE, _P15),
    (_P15, _ONE, _P15), (_BIG, _ONE, _P15),
    # Degenerate band: lower == upper.
    (_ONE, _P15, _P15), (_P15, _P15, _P15), (_BIG, _P15, _P15),
    # Inverted bounds (lower > upper): mirrors the ROM branch-for-branch.
    (_BIG, _P15, _ONE), (_NP1, _P15, _ONE), (_HALF, _P15, _ONE),
    # Negative band.
    (_NEGONE, _N15, _HALF), (_N15, _N15, _HALF), (_HALF, _N15, _HALF),
    (_BIG, _N15, _HALF), (_N43, _N15, _HALF),
    # Zero / negative-zero interplay (fcmp treats them equal; register bits
    # are returned verbatim).
    (_ZERO, _NEGONE, _ONE), (_NZERO, _NEGONE, _ONE),
    (_NEGONE, _NZERO, _ZERO), (_ONE, _NZERO, _ZERO),
    (_NZERO, _NZERO, _ZERO), (_ZERO, _NZERO, _NZERO),
    # Extremes.
    (_MAXF, _NMAXF, _MAXF), (_MAXF, _NMAXF, _NMAXF), (_MAXF, _MAXF, _MAXF),
    (_NMAXF, _NMAXF, _MAXF), (_MAXF, _ZERO, _MAXF), (_NMAXF, _NMAXF, _ZERO),
    # Denormals pass through the clamps untouched.
    (_MINDEN, _ZERO, _ONE), (_ONE, _MINDEN, _MAXF), (_ZERO, _MINDEN, _MINDEN),
    (_MINDEN, _MINDEN, _MINDEN), (_MAXDEN, _MINDEN, _MAXDEN),
    (_MAXF, _MINDEN, _MAXF), (_MIDDEN, _NMAXF, _MAXF),
    # Concrete magnitudes (pi / sensor-like).
    (_PI, _ZERO, _C100), (_ZERO, _PI, _C100), (_PI, _PI, _PI),
    (_NPI, _PI, _C100), (_C100, _N43, _C100), (_N43, _N43, _C100),
]
# Cross-sweeps: sig across all interesting values with a wide and a tight band.
for x in F:
    EDGE_SAT.append((x, _NMAXF, _MAXF))     # wide-open finite band
    EDGE_SAT.append((x, _ZERO, _ONE))       # tight [0,1] band


def rflt(rng):
    """Random single-precision bit pattern over the FINITE domain."""
    r = rng.random()
    if r < 0.35:
        # realistic firmware magnitudes
        return f2bits(rng.choice([rng.uniform(-1e4, 1e4), rng.uniform(-2, 2),
                                  rng.uniform(0, 300), rng.uniform(-300, 0)]))
    if r < 0.65:
        # arbitrary bit pattern, forced finite (exponent != 0xFF)
        b = rng.getrandbits(32)
        if ((b >> 23) & 0xFF) == 0xFF:
            b &= 0x807FFFFF
            b |= (rng.randrange(0, 0xFF) << 23)
        return b
    # exponent-biased (log-ish) finite values incl. denormals (e == 0)
    return (rng.getrandbits(1) << 31) | (rng.randrange(0, 0xFF) << 23) \
        | rng.getrandbits(23)


def gen_vectors(cfg, n):
    rng = make_rng(cfg['seed'])
    if cfg['edges'] == 'min':
        vecs = [{'ab': [a, b], 'desc': 'a=%08X b=%08X' % (a, b)}
                for (a, b) in EDGE_MIN]
        for _ in range(n):
            a, b = rflt(rng), rflt(rng)
            vecs.append({'ab': [a, b], 'desc': 'a=%08X b=%08X' % (a, b)})
        return vecs

    # saturate: half the random triples get a coherent band (lo <= hi), the
    # rest are fully random (covers inverted/degenerate bands too).
    vecs = [{'ab': [s, l, u], 'desc': 'sig=%08X lo=%08X hi=%08X' % (s, l, u)}
            for (s, l, u) in EDGE_SAT]
    for _ in range(n):
        if rng.random() < 0.5:
            a, b = rflt(rng), rflt(rng)
            if bits2f(a) <= bits2f(b):
                lo, hi = a, b
            else:
                lo, hi = b, a
            s = rflt(rng)
            vecs.append({'ab': [s, lo, hi],
                         'desc': 'sig=%08X lo=%08X hi=%08X' % (s, lo, hi)})
        else:
            s, l, u = rflt(rng), rflt(rng), rflt(rng)
            vecs.append({'ab': [s, l, u],
                         'desc': 'sig=%08X lo=%08X hi=%08X' % (s, l, u)})
    return vecs


# ============================================================================
# Toolchain build
# ============================================================================
_stub_done = [False]
_blob_cache = {}


def ensure_stubs():
    if _stub_done[0]:
        return
    os.makedirs(STUB_INC, exist_ok=True)
    p = os.path.join(STUB_INC, 'stdint.h')
    if not os.path.exists(p):
        with open(p, 'w') as f:
            f.write(_STDINT)
    p = os.path.join(STUB_INC, 'math.h')
    if not os.path.exists(p):
        with open(p, 'w') as f:
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
# Per-function evaluation
# ============================================================================
def run_function(name):
    cfg = FUNCS[name]
    blob, syms = blob_for(name)
    base = ram_overlay(blob)
    blb_addr = syms.get(cfg['entry_sym'], LINK_BASE)
    cpu = load_cpu()
    vecs = gen_vectors(cfg, cfg['n_test'])
    n = len(vecs)
    t0 = time.time()

    mism = 0
    samples = []
    for i, v in enumerate(vecs):
        fr = {4 + j: bits2f(b) for j, b in enumerate(v['ab'])}
        # real ROM bytes
        cpu.call(cfg['addr_rom'], fr=fr)
        rom = (cpu.r[0] & 0xFFFFFFFF, f2bits(cpu.fr[0]))
        # era-ROM gcc 3.4.6 blob (same fr-convention; loaded via ram overlay)
        cpu.call(blb_addr, fr=fr, ram=dict(base))
        blb = (cpu.r[0] & 0xFFFFFFFF, f2bits(cpu.fr[0]))
        if rom != blb:
            mism += 1
            if len(samples) < 5:
                samples.append('vec#%d %s  ROM=(r0=%08X fr0=%08X) '
                               'blob=(r0=%08X fr0=%08X)'
                               % (i, v['desc'], rom[0], rom[1], blb[0], blb[1]))

    dt = time.time() - t0
    return {'name': name, 'n': n, 'mism': mism, 'time': dt, 'samples': samples}


def main():
    n_override = int(sys.argv[1]) if len(sys.argv) > 1 else None
    ensure_stubs()

    total = 0
    for name, cfg in FUNCS.items():
        if n_override:
            cfg['n_test'] = n_override
        r = run_function(name)
        total += r['mism']
        status = 'OK  ' if r['mism'] == 0 else 'FAIL'
        print('%s %-22s @0x%-6X  n=%-5d  ROM-vs-blob=%d  %.2fs'
              % (status, name, cfg['addr_rom'], r['n'], r['mism'], r['time']))
        for s in r['samples']:
            print('        ' + s)

    if total:
        print('\nverify_float_a: %d mismatch(es) total — FAIL' % total)
        sys.exit(1)
    print('\nverify_float_a: all float leaves OK (0 mismatch)')


if __name__ == '__main__':
    main()
