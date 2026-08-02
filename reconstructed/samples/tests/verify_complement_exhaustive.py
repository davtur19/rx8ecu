#!/usr/bin/env python3
"""
verify_complement_exhaustive.py — exhaustive sweep of the complement_shift family.

Covers the three "complement_shift" ROM primitives that were already validated
randomly by verify_shifts2.py (u8) and verify_gcc346.py (u16, u32) — here the
effective input domains are swept EXHAUSTIVELY (or densely for the 3-float u32):

    complement_shift_u8   @0x2420   (r4 -> r0,  8-bit value/complement pack)
    complement_shift_u16  @0x2430   (r4 -> r0, 16-bit value/complement pack)
    complement_shift_u32  @0x2440   (fr4/fr5/fr6 -> r0, float deadband test)

DOMAIN SWEEPS
  * u8  : ALL 256 low-byte values (0..0xFF) + a documented upper-bit-injection
          set (32-bit registers with garbage high bits) proving the leading
          `extu.b` masks them away.
  * u16 : ALL 65536 low-word values (0..0xFFFF) + upper-bit injections.  A
          1000-pair timing probe runs first: if the full sweep would exceed
          10 min the sweep degrades to 16384 values + a documented dense edge
          set (never the case on the reference box: ~0.4 s for the full set).
  * u32 : 100k seeded random single-precision triples (bounded — the emulator
          cannot round a finite double whose magnitude exceeds the single range,
          a documented gap) + ~800 dense boundary edges (both deadband edges,
          +/- 1 ulp) + the harness NaN/inf/denormal/signed-zero EDGE set.

PIPELINE (identical recipe to verify_gcc346.py / verify_immo_exhaustive.py):
  (a) compile the lift with era-ROM gcc 3.4.6 `-m2e -O1 -fomit-frame-pointer`
      (the u8 lift is embedded here, as in verify_shifts2.py — there is no
      samples/src/rx8_complement_shift_u8.c),
  (b) link at 0x4000 against libgcc 3.4.6, objcopy --only-section=.text,
  (c) patch the blob into a PRIVATE copy of the ROM image at LINK_BASE and run
      BOTH the original ROM bytes and the blob on the same SH-2E emulator over
      every vector, comparing the r0 result (fast no-RAM fetch path).

Read-only w.r.t. the repo (everything written goes to /tmp). Exit code is
non-zero iff any function reports mismatch(es).

Usage:  python3 tests/verify_complement_exhaustive.py [U16N]
        (U16N overrides the u16 sweep size, bypassing the adaptive probe)
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

# ---- era-ROM toolchain (same recipe as verify_gcc346.py) --------------------
XGCC = '/home/davide/gcc346-build/gcc/xgcc'
XGCC_B = '/home/davide/gcc346-build/gcc'
LD = '/usr/bin/sh-elf-ld'
OBJCOPY = '/usr/bin/sh-elf-objcopy'
NM = '/usr/bin/sh-elf-nm'
LIBGCC = os.path.join(XGCC_B, 'libgcc.a')   # 3.4.6 helpers (unused by this family)

STUB_INC = '/tmp/verify_complement_exhaustive/inc'   # stub headers (never committed)
WORK = '/tmp/verify_complement_exhaustive/work'      # objects / elfs / blobs
LINK_BASE = 0x4000                                   # fixed link base

SRC_DIR = os.path.join(SAMPLES, 'src')
INC_DIR = os.path.join(SAMPLES, 'include')

TIME_BUDGET_S = 10 * 60                              # u16 full-sweep budget
U16_FULL = 0x10000                                   # all 0..0xFFFF
U16_FALLBACK = 0x4000                                # 16384 + edges if budget miss
PROBE_N = 1000

# ============================================================================
# Stub headers (reuse the /tmp/verify_gcc346/inc set; create if missing)
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
# u8 lift embedded (no samples/src/rx8_complement_shift_u8.c exists), as in
# verify_shifts2.py: `extu.b` masks to the low byte, `shll8` shifts it up,
# `not`+`extu.b` builds the masked complement, `add`/`or` combines (disjoint).
_C_U8 = (
    '#include <stdint.h>\n'
    '/* 0x2420 — pack a byte with its ones complement: ((val&0xFF)<<8)|(~val&0xFF) */\n'
    'uint32_t rx8_complement_shift_u8(uint32_t val)\n'
    '{\n'
    '    uint32_t value = (uint32_t)(val & 0xFFu) << 8;\n'
    '    uint32_t comp  = (uint32_t)(~val) & 0xFFu;\n'
    '    return value | comp;\n'
    '}\n')

FUNCS = {
    'complement_shift_u8': {
        'addr_rom': 0x2420, 'src': None, 'c_lift': _C_U8,
        'entry_sym': 'rx8_complement_shift_u8', 'kind': 'r32',
    },
    'complement_shift_u16': {
        'addr_rom': 0x2430, 'src': 'rx8_complement_shift_u16.c', 'c_lift': None,
        'entry_sym': 'rx8_complement_shift_u16', 'kind': 'r32',
    },
    'complement_shift_u32': {
        'addr_rom': 0x2440, 'src': 'rx8_complement_shift_u32.c', 'c_lift': None,
        'entry_sym': 'rx8_complement_shift_u32', 'kind': 'float',
    },
}

# ============================================================================
# f32 helpers (dense-edge generation for the u32 deadband test)
# ============================================================================
def f2b(x):   # IEEE-754 single bit pattern (big-endian) of a python float
    return struct.unpack('>I', struct.pack('>f', x))[0]


def b2f(b):   # python float holding exactly the single value of bit pattern b
    return struct.unpack('>f', struct.pack('>I', b & 0xFFFFFFFF))[0]


def f32(x):
    return b2f(f2b(x))                                   # round to single


def nextup32(x):
    return b2f((f2b(x) + 1) & 0xFFFFFFFF)                # next single toward +inf


def nextdown32(x):
    return b2f((f2b(x) - 1) & 0xFFFFFFFF)                # next single toward -inf


# ============================================================================
# Toolchain build
# ============================================================================
def ensure_stubs():
    os.makedirs(STUB_INC, exist_ok=True)
    p = os.path.join(STUB_INC, 'stdint.h')
    if not os.path.exists(p):
        with open(p, 'w') as f:
            f.write(_STDINT)


def build_blob(name):
    """Compile the lift (embedded C for u8, samples/src for u16/u32), link at
    0x4000, extract .text.  Returns (blob_bytes, entry_abs_addr)."""
    os.makedirs(WORK, exist_ok=True)
    cfg = FUNCS[name]
    base = os.path.join(WORK, name)
    srcf = base + '.c'
    obj, elf, blb = base + '.o', base + '.elf', base + '.bin'

    if cfg['c_lift'] is not None:
        with open(srcf, 'w') as f:
            f.write(cfg['c_lift'])
        compile_src = srcf
    else:
        compile_src = os.path.join(SRC_DIR, cfg['src'])

    subprocess.run(
        [XGCC, '-B', XGCC_B, '-m2e', '-O1', '-fomit-frame-pointer',
         '-c', compile_src, '-o', obj,
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
    entry = LINK_BASE
    for line in nm.stdout.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[1] == 'T' \
                and parts[2].lstrip('_') == cfg['entry_sym']:
            entry = int(parts[0], 16)
            break
    return blob, entry


# ============================================================================
# Vector generation
# ============================================================================
# Upper-bit injection patterns: the leading extu.b / extu.w must make these
# behave exactly like their low byte / low word.
HI32 = [0x00000100, 0x7FFF0000, 0x80000000, 0xFFFF0000, 0xABCDEF01,
        0xDEADBEEF, 0x12345678, 0xFFFFFFFF, 0x8000FFFF]

# Dense-edge base set for the u32 deadband (f32-exact dyadic values).
F32_BASE = [-100.0, -10.0, -1.0, -0.5, 0.0, 0.5, 1.0, 10.0, 100.0]

# u32 harness EDGE set (bit patterns: threshold, value, adjustment) — pins the
# NaN / inf / denormal / signed-zero behaviour of the deadband test.
U32_EDGE_BITS = [
    (0x00000000, 0x00000000, 0x3F800000),   # 0,0,1      inside
    (0x40000000, 0x00000000, 0x3F800000),   # 2,0,1      outside (above)
    (0x3F800000, 0x00000000, 0x3F800000),   # 1,0,1      exact boundary -> 0
    (0x7FC00000, 0x00000000, 0x3F800000),   # NaN threshold -> 0
    (0x7F800000, 0x00000000, 0x3F800000),   # +inf threshold -> 1
    (0xFF800000, 0x00000000, 0x3F800000),   # -inf threshold -> 1
    (0x80000000, 0x80000000, 0x80000000),   # all -0 -> 0
    (0x00000000, 0x7F800001, 0x3F800000),   # sNaN value -> 0
    (0x3F800000, 0x00000000, 0x00000001),   # denormal adjustment -> 1
    (0x00000000, 0x00000001, 0x00000000),   # denormal value: +den > 0 -> 1
    (0x7F7FFFFF, 0x00000000, 0x00000000),   # maxfloat, adj 0 (no overflow) -> 1
    (0x00000000, 0x7F7FFFFF, 0x3F800000),   # maxfloat - 1 -> maxfloat > 0 -> 1
    (0x00000000, 0x00000000, 0x7F800000),   # adj +inf -> inside -> 0
    (0x00000000, 0x00000000, 0x7FC00000),   # adj NaN -> 0
    (0x00800000, 0x00000000, 0x00000000),   # min normal, adj 0 -> 1
]


def gen_u8():
    """ALL 256 low-byte values + upper-bit injections (prove extu.b masks)."""
    vecs = list(range(256))
    vecs += HI32
    return vecs


def gen_u16_edges():
    """Dense edge set used when the full sweep is degraded (and always used as
    an extra belt over the full sweep)."""
    return [0, 1, 2, 3, 7, 8, 15, 16, 31, 32, 63, 127, 128, 255, 256, 257,
            511, 512, 1023, 1024, 2047, 2048, 4095, 4096, 8191, 8192,
            16383, 16384, 32767, 32768, 32769, 49151, 65533, 65534, 65535] \
        + HI32


def gen_u16(n):
    """ALL n consecutive low words 0..n-1 (n == 0x10000 normally), plus the
    boundary edges and upper-bit injections on top."""
    vecs = list(range(n))
    return vecs


def gen_u32(rand_n):
    """~rand_n seeded random triples + dense deadband-boundary edges + the
    NaN/inf/denormal EDGE set.  Random operands are bounded (the emulator
    cannot round a finite double beyond the single range — documented gap)."""
    rng = make_rng(0x2440)
    vecs = []

    # (a) dense boundary edges: for every (t, v) pair compute adj = v-t and
    #     adj = t-v in single precision, then test {adj, nextdown(adj),
    #     nextup(adj)} — this pins both deadband edges +/- 1 ulp.
    for t in F32_BASE:
        for v in F32_BASE:
            for adj in (f32(v - t), f32(t - v)):
                vecs.append((t, v, adj))
                vecs.append((t, v, nextdown32(adj)))
                vecs.append((t, v, nextup32(adj)))
    # (b) t == v with zero / negative / denormal adjustment.
    for t in F32_BASE:
        for adj in (-1.0, -0.0, 0.0, nextup32(0.0)):
            vecs.append((t, t, adj))
    # (c) NaN / inf / denormal / signed-zero / max-magnitude bit patterns.
    for tb, vb, ab in U32_EDGE_BITS:
        vecs.append((b2f(tb), b2f(vb), b2f(ab)))

    # (d) seeded random triples across several magnitude regimes (bounded, see
    #     docstring; sums stay <= ~2e20 << single max ~3.4e38).
    regimes = [(60, 100.0, 50.0),     # typical PID magnitudes
               (20, 1e5, 5e4),
               (15, 1e20, 5e19),      # coarse f32 rounding region
               (5, 1.0, 0.5)]         # near-zero / sub-1
    for frac, vmax, amax in regimes:
        cnt = int(rand_n * frac / 100)
        for _ in range(cnt):
            t = rng.uniform(-vmax, vmax)
            v = rng.uniform(-vmax, vmax)
            a = rng.uniform(-amax, amax)
            vecs.append((f32(t), f32(v), f32(a)))

    return vecs


# ============================================================================
# Sweep driver
# ============================================================================
def sweep(name, cpu_rom, cpu_blob, entry, vectors):
    """Run ROM and blob on the same vectors, compare r0.  Returns result dict."""
    cfg = FUNCS[name]
    t0 = time.perf_counter()
    mism = []
    rom_res = []          # all results (for u8/u16 distribution reporting)
    n_out1 = 0
    for i, v in enumerate(vectors):
        if cfg['kind'] == 'float':
            t, val, adj = v
            er = cpu_rom.call(cfg['addr_rom'], r4=0,
                              fr={4: t, 5: val, 6: adj})
            eb = cpu_blob.call(entry, r4=0, fr={4: t, 5: val, 6: adj})
        else:
            er = cpu_rom.call(cfg['addr_rom'], r4=v)
            eb = cpu_blob.call(entry, r4=v)
        if er != eb:
            if len(mism) < 5:
                mism.append('vec#%d input=0x%08X ROM=0x%08X blob=0x%08X'
                            % (i, v if isinstance(v, int) else
                               '%s,%s,%s' % tuple('%08X' % f2b(x) for x in v),
                               er, eb))
        else:
            if cfg['kind'] != 'float':
                rom_res.append(er)
            else:
                n_out1 += er
    dt = time.perf_counter() - t0
    uniq = len(set(rom_res)) if cfg['kind'] != 'float' else None
    return {'name': name, 'n': len(vectors), 'mism': len(mism),
            'mism_samples': mism, 'time': dt, 'unique': uniq,
            'out1': n_out1 if cfg['kind'] == 'float' else None}


def per_pair_probe(cpu_rom, cpu_blob, entry, kind):
    """Time PROBE_N pairs (ROM + blob each) to size the u16 sweep."""
    t0 = time.perf_counter()
    for i in range(PROBE_N):
        if kind == 'float':
            cpu_rom.call(0x2440, r4=0, fr={4: 1.5, 5: 2.0, 6: 0.5})
            cpu_blob.call(entry, r4=0, fr={4: 1.5, 5: 2.0, 6: 0.5})
        else:
            cpu_rom.call(0x2430, r4=i & 0xFFFF)
            cpu_blob.call(entry, r4=i & 0xFFFF)
    dt = time.perf_counter() - t0
    per = dt / PROBE_N
    print('probe: %d pairs in %.3fs -> %.1f us/pair (ROM+blob)'
          % (PROBE_N, dt, per * 1e6))
    return per


# ============================================================================
# Semantics (observed from the ROM disassembly, confirmed by the sweep)
# ============================================================================
SEMANTICS = {
    'complement_shift_u8':
        'r0 = ((x & 0xFF) << 8) | ((~x) & 0xFF)   [byte + ones-complement '
        'pack; for x in 0..255: (x<<8) | (0xFF - x)]',
    'complement_shift_u16':
        'r0 = ((x & 0xFFFF) << 16) | ((~x) & 0xFFFF)   [word + ones-complement '
        'pack; for x in 0..65535: (x<<16) | (0xFFFF - x)]',
    'complement_shift_u32':
        'r0 = ((value - adjustment) > threshold) or (threshold > (value + '
        'adjustment))  [single-precision deadband test, returns 1 when '
        '|threshold - value| > adjustment; NaN -> 0]',
}


def main():
    u16_override = int(sys.argv[1]) if len(sys.argv) > 1 else None
    ensure_stubs()

    # ---- build blobs ------------------------------------------------------
    blobs, entries = {}, {}
    for name in FUNCS:
        blob, entry = build_blob(name)
        blobs[name] = blob
        entries[name] = entry
        print('blob %-20s: %3d bytes, entry @0x%X' % (name, len(blob), entry))

    # ---- emulator instances ----------------------------------------------
    cpu_rom = load_cpu()
    cpus = {}
    for name, blob in blobs.items():
        rom2 = bytearray(cpu_rom.rom)
        assert LINK_BASE + len(blob) < FUNCS[name]['addr_rom'] or \
            LINK_BASE > FUNCS[name]['addr_rom'] + 0x40, \
            'blob patch would overwrite the ROM function'
        rom2[LINK_BASE:LINK_BASE + len(blob)] = blob
        cpus[name] = SH2(bytes(rom2))

    # ---- u16 timing probe (task rule: measure 1000 calls first) ----------
    per = per_pair_probe(cpu_rom, cpus['complement_shift_u16'],
                         entries['complement_shift_u16'], 'r32')
    if u16_override:
        u16_n = u16_override
        u16_mode = 'overridden=%d' % u16_n
    elif per * U16_FULL <= TIME_BUDGET_S:
        u16_n = U16_FULL
        u16_mode = 'exhaustive (est %.1fs <= %ds budget)' % (per * U16_FULL,
                                                             TIME_BUDGET_S)
    else:
        u16_n = U16_FALLBACK
        u16_mode = ('degraded 16384+edges (est %.1fs > %ds budget)'
                    % (per * U16_FULL, TIME_BUDGET_S))

    # ---- sweeps -----------------------------------------------------------
    results = []
    results.append(sweep('complement_shift_u8', cpu_rom,
                         cpus['complement_shift_u8'],
                         entries['complement_shift_u8'], gen_u8()))
    results.append(sweep('complement_shift_u16', cpu_rom,
                         cpus['complement_shift_u16'],
                         entries['complement_shift_u16'],
                         gen_u16(u16_n) + [v for v in gen_u16_edges()
                                           if v >= u16_n]))
    u32_vecs = gen_u32(100000)
    results.append(sweep('complement_shift_u32', cpu_rom,
                         cpus['complement_shift_u32'],
                         entries['complement_shift_u32'], u32_vecs))

    # ---- report -----------------------------------------------------------
    print()
    print('=' * 76)
    print('RESULT  complement_shift family — exhaustive / dense sweep')
    print('-' * 76)
    print('%-22s %-22s %10s %10s %10s'
          % ('function', 'domain', 'N', 'mismatch', 'time'))
    for r in results:
        cfg = FUNCS[r['name']]
        if r['name'] == 'complement_shift_u8':
            dom = '0..0xFF + hi-bits'
        elif r['name'] == 'complement_shift_u16':
            dom = '0..0x%X (%s)' % (u16_n - 1, u16_mode)
        else:
            dom = '100k rnd + ~%.0fk dense edge' % (len(u32_vecs) / 1000)
        print('%-22s %-22s %10d %10d %10.2fs'
              % (r['name'], dom, r['n'], r['mism'], r['time']))
        for m in r['mism_samples']:
            print('        ' + m)
        if r['unique'] is not None:
            print('  %s: %d/%d unique outputs'
                  % (r['name'], r['unique'], r['n']))
        if r['out1'] is not None:
            print('  %s: %d/%d outputs = 1 (outside deadband)'
                  % (r['name'], r['out1'], r['n']))

    print('-' * 76)
    for name in FUNCS:
        print('semantics %-20s' % name)
        print('    %s' % SEMANTICS[name])

    total = sum(r['mism'] for r in results)
    if total:
        print('\nverify_complement_exhaustive: %d mismatch(es) total — FAIL'
              % total)
        sys.exit(1)
    print('\nverify_complement_exhaustive: complement_shift family '
          'exhaustive OK (0 mismatch)')


if __name__ == '__main__':
    main()
