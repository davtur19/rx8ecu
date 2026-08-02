#!/usr/bin/env python3
"""
verify_firstorder.py — era-ROM toolchain (gcc 3.4.6) behavioural validation of
the reconstructed first-order IIR filter rx8_first_order_filter @0x23B0.

Closes the "ROM -> abstract C -> era-ROM toolchain (gcc 3.4.6)" loop on the
*behavioural* plane for the register-only FPU leaf:

    rx8_first_order_filter  @0x23B0   (fr4=sig, fr5=sigprev, fr6=ff, fr7=min
                                       -> fr0; single float result)

The ROM path (40 bytes, 12 FPU ops, 2 branches) is:

    flds   FR5,FPUL             ; FPUL = bits(sigprev)
    mov.l  @(0x24,PC),R4        ; R4 = 0x7F800000 (single exp mask)
    sts    FPUL,R0
    and    R4,R0                ; R0 = exponent field of sigprev
    cmp/eq R4,R0                ; T = (exponent all ones -> inf/NaN)
    bt/s   .snap                ; bootstrap: no valid history -> pass sig
    fsub   FR4,FR5              ;   (delay) FR5 = sigprev - sig
    fldi1  FR0
    fsub   FR6,FR0              ; FR0 = 1.0 - ff
    fmov   FR4,FR6              ; FR6 = sig
    fmac   FR0,FR5,FR6          ; FR6 = (1-ff)*(sigprev-sig) + sig  (fused)
    fmov   FR4,FR5              ; FR5 = sig
    fsub   FR6,FR5              ; FR5 = sig - filtered
    fabs   FR5                  ; FR5 = |sig - filtered|
    fcmp/gt FR5,FR7             ; T = (min > |sig - filtered|)
    bf/s   .ret                 ; small change -> keep the filtered value
    nop
.snap: fmov FR4,FR6             ; deadband (or bootstrap) -> FR6 = sig
.ret:  rts
       fmov   FR6,FR0           ;   (delay) FR0 = result

i.e. a first-order IIR low-pass with a minimum-change deadband:
    filtered = fmaf(1-ff, sigprev - sig, sig)      (single-rounding FMAC)
    result   = (min > |sig - filtered|) ? sig : filtered
and a not-finite(sigprev) bootstrap that passes the raw sig through.

Method (mirrors verify_float_a.py / verify_float_b.py):

  (a) compiles the reconstructed source with the era-ROM recipe
      /home/davide/gcc346-build/gcc/xgcc -B /home/davide/gcc346-build/gcc/
      -m2e -O1 -fomit-frame-pointer, using the /tmp/verify_gcc346/inc stub
      headers.  gcc 3.4.6 has NO builtin fmaf()/isfinite() and no libm on the
      target, so this harness extends the stub math.h (the same "aggiungi
      math.h" idea as verify_float_a.py) with:
        * static inline fmaf(a,b,c)  -> a*b+c, which gcc 3.4.6 -m2e -O1
          compiles to the FUSED `fmac FR0,Rm,Rn` (single rounding, exactly the
          ROM's fmac — verified on the -S output);
        * static inline isfinite(x)  -> union bit test on the exponent field
          (0x7F800000), which compiles to exactly the ROM's flds/sts/and/
          cmp-eq sequence;
        * float fabsf(float)         -> compiles to the hardware `fabs`.
      The repo source src/rx8_first_order_filter.c is NOT modified.
  (b) links the object at the fixed base 0x4000 with the trivial linker script
      via sh-elf-ld (libgcc 3.4.6 pulled; this leaf needs none of the integer
      helpers), pulls the literal pool along,
  (c) `sh-elf-objcopy --only-section=.text` extracts the self-contained blob,
  (d) loads the blob into tools/sh2emu.py through the sparse `ram` overlay,
  (e) runs the SAME single-precision vectors on the real ROM bytes at 0x23B0
      and on the blob at 0x4000 (cpu.call with fr={4..7}, result read from
      fr0) and compares f2bits() bit-exact — the required comparison.  r0 is
      NOT compared: the ROM clobbers it with the exponent-mask scratch while
      the blob leaves its own scratch there; only fr0 carries the result.

Vector domain:
  * FINITE single-precision inputs only for the main comparison (the task
    excludes NaN/Inf): ±FLT_MAX, ±FLT_MIN, denormals, ±0.0, typical sensor
    magnitudes, filter-factor and deadband edge cases, plus N=4000 seeded
    random vectors (reproducible, make_rng(0x23B0)).
  * A small NON-FINITE bootstrap-pin set (sigprev = ±inf/NaN, expected result
    == sig) is run as a clearly-separated extra block: the emulator handles
    those bits deterministically and both sides share the same emulated NaN,
    so ROM-vs-blob is still a meaningful self-consistent check.  These are
    reported separately and any mismatch there also fails the run.
  * Overflow to ±inf inside the filter (e.g. sigprev=FLT_MAX, sig=-FLT_MAX ->
    sigprev-sig overflows the single range) does NOT crash the current
    emulator: tools/sh2emu.py::ts() saturates to +/-inf (round-to-nearest,
    exactly what the SH-2E FPU produces), so those vectors are compared
    bit-exact like any other.  For robustness against an older emulator that
    instead propagated OverflowError (the gap documented in verify_float_b.py),
    a defensive per-side guard classifies such vectors as 'gap' and verifies
    BOTH sides raise identically (self-consistent, reported, not a mismatch).

The harness is read-only w.r.t. the repo: everything it writes goes to /tmp,
and the exit code is non-zero iff any comparison reports a mismatch.

Usage:  python3 tests/verify_firstorder.py [N]   (default N = 4000 random)
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

from sh2emu import bits2f, f2bits  # noqa: E402
from common import load_cpu, make_rng  # noqa: E402

# ---- era-ROM toolchain ------------------------------------------------------
XGCC = '/home/davide/gcc346-build/gcc/xgcc'
XGCC_B = '/home/davide/gcc346-build/gcc'
LD = '/usr/bin/sh-elf-ld'
OBJCOPY = '/usr/bin/sh-elf-objcopy'
NM = '/usr/bin/sh-elf-nm'
LIBGCC = os.path.join(XGCC_B, 'libgcc.a')

STUB_INC = '/tmp/verify_gcc346/inc'        # shared stub headers (see docstring)
WORK = '/tmp/verify_firstorder/work'       # objects / elfs / blobs
LINK_BASE = 0x4000                         # fixed link base
ADDR_ROM = 0x23B0                          # rx8_first_order_filter in 60E1D400.bin

SRC_DIR = os.path.join(SAMPLES, 'src')
INC_DIR = os.path.join(SAMPLES, 'include')
SRC = 'rx8_first_order_filter.c'
ENTRY = 'rx8_first_order_filter'

# ============================================================================
# Stub headers — same spirit as verify_gcc346.py/verify_float_a.py but with
# fmaf()/isfinite() added: gcc 3.4.6 has no builtin for either and no libm on
# the target.  The static-inline forms compile to the fused `fmac` and to the
# ROM's exact exponent-field bit test (verified on the -S output).
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

# fmaf as `a*b+c`: gcc 3.4.6 -m2e -O1 turns this into the fused FMAC
# (`fmac fr0,fr5,fr1`) — a single rounding, exactly the ROM's fmac.
# isfinite as a union bit test on the exponent field (0x7F800000): compiles to
# the ROM's flds/sts/and/cmp-eq bootstrap exactly.
_MATH = (
    '#ifndef _MATH_H\n#define _MATH_H\n'
    'union _rx8_fb { float f; unsigned int u; };\n'
    'static inline int isfinite(float x) '
    '{ union _rx8_fb u; u.f = x; return (u.u & 0x7F800000u) != 0x7F800000u; }\n'
    'static inline float fmaf(float a, float b, float c) { return a * b + c; }\n'
    'float fabsf(float x);\n#endif\n')

_LINKER = (
    'OUTPUT_FORMAT(elf32-sh)\n'
    'MEMORY { RAM (rx) : ORIGIN = 0x%X, LENGTH = 0x1000 }\n'
    'SECTIONS {\n'
    '  .text : { *(.text) *(.text.*) *(.rodata) *(.rodata.*) *(.rdata) } > RAM\n'
    '  /DISCARD/ : { *(.comment) *(.note*) *(.symtab) *(.strtab) '
    '*(.shstrtab) *(.debug*) }\n}\n' % LINK_BASE)

# ============================================================================
# IEEE-754 single-precision bit patterns (big-endian value order)
# ============================================================================
_PINF = 0x7F800000
_NINF = 0xFF800000
_QNAN = 0x7FC00000
_SNAN = 0x7F800001
_ZERO = 0x00000000
_NZERO = 0x80000000              # -0.0
_ONE = 0x3F800000
_NEGONE = 0xBF800000
_HALF = 0x3F000000               # 0.5
_NHALF = 0xBF000000              # -0.5
_SEV = 0x3F666666                # ~0.7 (typical filter factor)
_TINY = 0x38D1B717               # ~1.0e-4 (typical deadband)
_PI = 0x4048F5C3                 # 3.14f
_NPI = 0xC048F5C3
_P15 = 0x3FC00000                # 1.5
_N15 = 0xBFC00000                # -1.5
_BIG = 0x49742400                # 1.0e6
_NBIG = 0xC9742400               # -1.0e6
_MAXF = 0x7F7FFFFF               # +FLT_MAX
_NMAXF = 0xFF7FFFFF              # -FLT_MAX
_MINNORM = 0x00800000            # FLT_MIN (smallest normal)
_NMINNORM = 0x80800000
_MAXDEN = 0x007FFFFF             # largest denormal
_MINDEN = 0x00000001             # min denormal
_MIDDEN = 0x00400000             # mid denormal
_NP1 = 0x3F800001                # 1.0000001
_C100 = 0x42C80000               # 100.0
_N43 = 0xC42C0000                # -43.0 (typical sensor magnitude)
_TWO = 0x40000000                # 2.0
_NTWO = 0xC0000000               # -2.0

# Finite interesting values swept through the edge sets below.
F = [_ZERO, _NZERO, _ONE, _NEGONE, _HALF, _NHALF, _SEV, _PI, _NPI,
     _MAXF, _NMAXF, _MINNORM, _NMINNORM, _MAXDEN, _MINDEN, _MIDDEN,
     _P15, _N15, _BIG, _NP1, _C100, _N43]

# ============================================================================
# Edge vectors
# ============================================================================
EDGE = []

# --- deadband / filter-factor behavioural pins ------------------------------
# sig=1.5, prev=0.5, ff=0.5 -> filtered = 0.5*(0.5-1.5)+1.5 = 1.0, so
# |sig-filtered| = 0.5 exactly.  min < 0.5 -> keep filtered; min == 0.5
# (fcmp/gt strict) -> keep filtered; min > 0.5 -> snap to sig.
EDGE += [(_P15, _HALF, _HALF, _ZERO),     # 0 > 0.5? no   -> filtered 1.0
         (_P15, _HALF, _HALF, 0x3ECCCCCD),  # ~0.4 < 0.5  -> filtered 1.0
         (_P15, _HALF, _HALF, _HALF),     # 0.5 > 0.5? no -> filtered 1.0
         (_P15, _HALF, _HALF, _SEV)]      # 0.7 > 0.5     -> sig 1.5
# ff=1 -> filtered == sig -> always sig (|diff| == 0, min > 0 never true).
EDGE += [(_P15, _N15, _ONE, _ZERO), (_P15, _N15, _ONE, _MAXF),
         (_N43, _C100, _ONE, _TINY), (_ZERO, _MAXF, _ONE, _ZERO)]
# ff=0 -> filtered == (sigprev - sig) + sig == sigprev (bit-exact passthrough
# of prev once ff reaches exactly 0: fmaf(1, prev-sig, sig) == prev).
EDGE += [(_P15, _N15, _ZERO, _ZERO), (_P15, _N15, _ZERO, _MAXF),
         (_BIG, _NBIG, _ZERO, _ZERO), (_NZERO, _ZERO, _ZERO, _ZERO)]
# Huge deadband -> always snap to sig; min=0 -> always keep filtered (strict).
EDGE += [(_P15, _N15, _HALF, _MAXF), (_N15, _P15, _HALF, _MAXF),
         (_N43, _C100, _HALF, _MAXF), (_P15, _N15, _HALF, _ZERO),
         (_N43, _C100, _SEV, _ZERO)]
# Identical in/out (sig == sigprev) -> filtered == sig always.
EDGE += [(_P15, _P15, _HALF, _ZERO), (_P15, _P15, _HALF, _ONE),
         (_N43, _N43, _SEV, _MAXF), (_ZERO, _ZERO, _HALF, _ZERO),
         (_MAXF, _MAXF, _ONE, _ZERO)]

# --- signed-zero hygiene (fcmp treats ±0 equal; bits returned verbatim) -----
EDGE += [(_ZERO, _NZERO, _HALF, _ZERO), (_NZERO, _ZERO, _HALF, _ZERO),
         (_NZERO, _NZERO, _HALF, _ZERO), (_ZERO, _ZERO, _HALF, _ZERO),
         (_NZERO, _NZERO, _HALF, _MAXF), (_ONE, _NZERO, _HALF, _ZERO),
         (_NZERO, _ONE, _HALF, _ZERO), (_NEGONE, _NZERO, _HALF, _ZERO)]

# --- extremes / denormals (results may saturate to ±inf — still compared
#     bit-exact; the emulator's ts() rounds to inf like the SH-2E FPU) -------
for s in (_MAXF, _NMAXF, _ZERO, _ONE, _BIG, _NBIG):
    for p in (_MAXF, _NMAXF, _ZERO, _ONE):
        for ff in (_ZERO, _HALF, _ONE, _TWO, _NTWO):
            EDGE.append((s, p, ff, _ZERO))
            EDGE.append((s, p, ff, _MAXF))
EDGE += [(_MINDEN, _MAXDEN, _HALF, _ZERO), (_MAXDEN, _MINDEN, _HALF, _ZERO),
         (_MINDEN, _ZERO, _HALF, _MINDEN), (_ZERO, _MINDEN, _HALF, _MINDEN),
         (_MIDDEN, _MIDDEN, _HALF, _ZERO), (_MAXDEN, _MAXDEN, _HALF, _ZERO),
         (_MINDEN, _MAXF, _ONE, _ZERO), (_MAXF, _MINDEN, _ZERO, _ZERO),
         (_NMINNORM, _MINNORM, _HALF, _ZERO), (_MINNORM, _NMINNORM, _HALF, _TINY)]

# --- cross-sweeps ------------------------------------------------------------
for x in F:                                   # sig across all interesting values
    for p in (_ZERO, _ONE, _NEGONE, _MAXF, _MINDEN, _NMAXF):
        EDGE.append((x, p, _HALF, _ZERO))
for p in F:                                   # prev across all interesting values
    for s in (_ZERO, _ONE, _NEGONE):
        EDGE.append((s, p, _SEV, _TINY))

# --- NON-FINITE bootstrap pins (extra, self-consistent; the required domain
#     is finite-only, see module docstring).  sigprev not finite -> result
#     must be the raw sig, bit-exact. ---------------------------------------
EDGE_NONFINITE = []
for p in (_PINF, _NINF, _QNAN, _SNAN):
    for s in (_ZERO, _ONE, _NEGONE, _P15, _MAXF, _PINF, _QNAN):
        EDGE_NONFINITE.append((s, p, _HALF, _ZERO))
EDGE_NONFINITE.append((_MAXF, _NINF, _HALF, _MAXF))
EDGE_NONFINITE.append((_ZERO, _PINF, _ONE, _ZERO))


def rflt(rng):
    """Random FINITE single-precision bit pattern (verify_float_a.py recipe):
    realistic firmware magnitudes, arbitrary finite patterns, exponent-biased
    incl. denormals."""
    r = rng.random()
    if r < 0.35:
        return f2bits(rng.choice([rng.uniform(-1e4, 1e4), rng.uniform(-2, 2),
                                  rng.uniform(0, 300), rng.uniform(-300, 0)]))
    if r < 0.65:
        b = rng.getrandbits(32)
        if ((b >> 23) & 0xFF) == 0xFF:                 # force finite
            b &= 0x807FFFFF
            b |= (rng.randrange(0, 0xFF) << 23)
        return b
    return (rng.getrandbits(1) << 31) | (rng.randrange(0, 0xFF) << 23) \
        | rng.getrandbits(23)


def gen_random(n):
    """N random vectors: sig/prev realistic finite magnitudes; ff mostly a
    true filter factor in [0,1] with excursions; min mostly a small deadband
    with excursions."""
    rng = make_rng(ADDR_ROM)
    vecs = []
    for _ in range(n):
        r = rng.random()
        if r < 0.8:
            ff = f2bits(rng.uniform(0.0, 1.0))
        else:
            ff = f2bits(rng.choice([rng.uniform(-2, 2), rng.uniform(0, 5)]))
        r = rng.random()
        if r < 0.7:
            mn = f2bits(rng.uniform(0.0, 1000.0))
        elif r < 0.9:
            mn = f2bits(rng.uniform(0.0, 1e-3))
        else:
            mn = rflt(rng)
        vecs.append((rflt(rng), rflt(rng), ff, mn))
    return vecs


# ============================================================================
# Toolchain build
# ============================================================================
_stub_done = [False]
_blob_cache = {}


def ensure_stubs():
    """Write the stub headers once to /tmp/verify_gcc346/inc.  stdint.h only
    if missing (shared with the other harnesses); math.h is (re)written with
    the fmaf/isfinite/fabsf stubs this leaf needs — additive w.r.t. the
    fabsf-only stub of verify_gcc346.py, and verify_gcc346.py re-writes its
    own at startup anyway."""
    if _stub_done[0]:
        return
    os.makedirs(STUB_INC, exist_ok=True)
    p = os.path.join(STUB_INC, 'stdint.h')
    if not os.path.exists(p):
        with open(p, 'w') as f:
            f.write(_STDINT)
    with open(os.path.join(STUB_INC, 'math.h'), 'w') as f:
        f.write(_MATH)
    _stub_done[0] = True


def build_blob():
    """Compile src with gcc 3.4.6, link at 0x4000, extract .text blob.

    Returns (blob_bytes, {symbol: linked_absolute_addr})."""
    os.makedirs(WORK, exist_ok=True)
    base = os.path.join(WORK, 'first_order_filter')
    obj, elf, blb = base + '.o', base + '.elf', base + '.bin'

    subprocess.run(
        [XGCC, '-B', XGCC_B, '-m2e', '-O1', '-fomit-frame-pointer',
         '-c', os.path.join(SRC_DIR, SRC), '-o', obj,
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


def blob_for():
    if not _blob_cache:
        _blob_cache['blob'], _blob_cache['syms'] = build_blob()
    return _blob_cache['blob'], _blob_cache['syms']


def ram_overlay(blob):
    return {LINK_BASE + i: blob[i] for i in range(len(blob))}


# ============================================================================
# Per-vector evaluation
# ============================================================================
def _run_side(cpu, addr, base, bits):
    """Run one vector on one side; returns ('ok', fr0_bits) or
    ('overflow', None) when the (old) emulator propagates OverflowError on a
    single-range overflow.  The current tools/sh2emu.py ts() saturates to
    +/-inf instead, so 'overflow' is a defensive, normally-dormant path."""
    fr = {4 + j: bits2f(b) for j, b in enumerate(bits)}
    try:
        cpu.call(addr, fr=fr, ram=dict(base) if base else None)
        return ('ok', f2bits(cpu.fr[0]))
    except OverflowError:
        return ('overflow', None)


def run_function(n_random, report_gaps=True):
    blob, syms = blob_for()
    base = ram_overlay(blob)
    blb_addr = syms.get(ENTRY, LINK_BASE)
    cpu = load_cpu()
    vecs = list(EDGE) + gen_random(n_random)
    t0 = time.time()

    mism = 0
    n_gap = 0
    asym = 0
    samples = []
    for i, bits in enumerate(vecs):
        rom = _run_side(cpu, ADDR_ROM, None, bits)
        blb = _run_side(cpu, blb_addr, base, bits)
        if rom[0] == 'overflow' or blb[0] == 'overflow':
            if rom[0] == 'overflow' and blb[0] == 'overflow':
                n_gap += 1          # self-consistent on both sides
            else:
                asym += 1
                if len(samples) < 5:
                    samples.append('vec#%d %s overflow asymmetry: rom=%s blob=%s'
                                   % (i, _desc(bits), rom[0], blb[0]))
            continue
        if rom[1] != blb[1]:
            mism += 1
            if len(samples) < 5:
                samples.append('vec#%d %s  ROM=%08X blob=%08X'
                               % (i, _desc(bits), rom[1], blb[1]))

    # ---- non-finite bootstrap pins (separate, self-consistent extra) -------
    nf_mism = 0
    nf_samples = []
    for i, bits in enumerate(EDGE_NONFINITE):
        rom = _run_side(cpu, ADDR_ROM, None, bits)
        blb = _run_side(cpu, blb_addr, base, bits)
        if rom[0] == 'overflow' or blb[0] == 'overflow':
            nf_mism += 1            # never expected on this path (bootstrap
            if len(nf_samples) < 5: #  returns sig before any FPU overflow)
                nf_samples.append('vec#%d %s unexpected overflow' % (i, _desc(bits)))
            continue
        if rom[1] != blb[1]:
            nf_mism += 1
            if len(nf_samples) < 5:
                nf_samples.append('vec#%d %s  ROM=%08X blob=%08X'
                                  % (i, _desc(bits), rom[1], blb[1]))

    dt = time.time() - t0
    return {'n': len(vecs), 'n_edges': len(EDGE), 'mism': mism,
            'n_gap': n_gap, 'asym': asym, 'nf': (len(EDGE_NONFINITE), nf_mism),
            'nf_samples': nf_samples, 'time': dt, 'samples': samples}


def _desc(bits):
    return 'sig=%08X sigprev=%08X ff=%08X min=%08X' % bits


def main():
    n_override = int(sys.argv[1]) if len(sys.argv) > 1 else 4000
    ensure_stubs()

    r = run_function(n_override)
    total = r['mism'] + r['asym'] + r['nf'][1]
    status = 'OK  ' if total == 0 else 'FAIL'
    print('%s %-22s @0x%-6X  n=%-5d (%-3d edge)  ROM-vs-blob=%d  '
          'gaps=%d  nonfinite-bootstrap=%d/%d  %.2fs'
          % (status, ENTRY, ADDR_ROM, r['n'], r['n_edges'], r['mism'],
             r['n_gap'], r['nf'][0] - r['nf'][1], r['nf'][0], r['time']))
    for s in r['samples']:
        print('        ' + s)
    for s in r['nf_samples']:
        print('        ' + s)

    if r['n_gap']:
        print('NOTE: %d vector(s) overflowed the single range on BOTH sides '
              '(self-consistent, reported not mismatched).  The current '
              'tools/sh2emu.py ts() rounds single-range overflow to +/-inf, '
              'so this counter is normally 0; it only trips against the older '
              'emulator that propagated OverflowError (the gap documented in '
              'verify_float_b.py).' % r['n_gap'])

    if total:
        print('\nverify_firstorder: %d mismatch(es) total — FAIL' % total)
        sys.exit(1)
    print('\nverify_firstorder: rx8_first_order_filter @0x23B0 '
          'ROM-vs-gcc3.4.6-blob OK (0 mismatch)')


if __name__ == '__main__':
    main()
