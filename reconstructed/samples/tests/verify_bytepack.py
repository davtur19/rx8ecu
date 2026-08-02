#!/usr/bin/env python3
"""
verify_bytepack.py — era-ROM toolchain (sh-elf gcc 3.4.6) validation of the
two adjacent byte-packing leaves of the "converter/inverter" family:

    @0x552FE (14 bytes)  converter_0x552FE : uint8_t *f(uint8_t *dst,
                                                         uint8_t *src,
                                                         uint8_t value)
    @0x5530C (28 bytes)  inverter_0x5530C  : uint8_t *f(uint8_t *dst,
                                                         uint8_t *src,
                                                         uint16_t value)

Semantics (deduced from the disassembly, verified here)
---------------------------------------------------------
  @0x552FE:  mov.b @r5,r3 / add #1 / mov.b r3,@r5   (*src += 1)
             mov.b r6,@r4 / add #1,r4               (*dst++ = value8)
             rts / mov r4,r0                        (return dst+1)
  =>  *src += 1;  *dst++ = value;  return dst;

  @0x5530C:  mov.b @r5,r3 / add #1 / mov.b r3,@r5   (*src += 1)
             extu.w r6 / shlr8 / mov.b r2,@r4       (*dst = value >> 8)
             mov.b @r5,r2 / add #1 / mov.b r2,@r5   (*src += 1 again —
                                                     RELOAD after the store:
                                                     dst and src may alias)
             mov.b r6,@r4 / add #1,r4               (*dst++ = value & 0xFF)
             rts / mov r4,r0                        (return dst+2)
  =>  *src += 1;  *dst++ = value >> 8;  *src += 1;  *dst++ = value; return dst;

Both are pure pointer-convention leaves (same ABI on the ROM side and on the
gcc-3.4.6 blob side: r4=dst, r5=src, r6=value, result r0 = advanced dst), so
-- unlike verify_checksum.py -- there is no convention mismatch to bridge: the
ROM bytes and the blob are driven with the very same r4/r5/r6 register images
against the very same RAM overlay.

Method (mirrors verify_checksum.py / verify_gcc346.py)
-------------------------------------------------------
  (a) writes the C lifts (embed below) to /tmp/verify_bytepack/*.c,
  (b) compiles each with the era-ROM recipe `-m2e -O1 -fomit-frame-pointer`
      via /home/davide/gcc346-build/gcc/xgcc, links at 0x4000 with
      sh-elf-ld + libgcc 3.4.6, extracts .text,
  (c) drives the ROM bytes @0x552FE/0x5530C AND the blob @0x4000 on identical
      vectors; every vector carries a full RAM image built from:
        - dst buffer base 0x2000, src buffer base 0x3000,
        - buffer lengths 1..64, alignments 0..3,
        - deterministic fill patterns (0x00 / 0xFF / incremental / descending
          / 0xDEADBEEF / seeded random),
        - sentinel guard bytes before and after each buffer,
        - a dedicated aliasing group (dst == src, +/-1, +/-2) that exercises
          the reload path of the 16-bit function,
  (d) compares r0 AND the complete post-call RAM state restricted to the
      seeded data region (the blob lives in the overlay, so the ROM's RAM
      image has no code bytes), and checks neither side writes outside the
      seeded region,
  (e) as a third leg, compares both sides against a Python reference oracle
      of the deduced semantics.

Read-only w.r.t. the repo: everything written goes to /tmp/verify_bytepack;
verify_gcc346.py, README.md, Makefile and tools/ are NOT touched.  Exit code
is non-zero iff any active function reports a mismatch.

Usage:  python3 tests/verify_bytepack.py [N]   (default N = 3000 vectors/function)
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

from sh2emu import SH2  # noqa: E402
from common import load_cpu, make_rng  # noqa: E402

# ---- era-ROM toolchain (same binaries as verify_gcc346.py) ------------------
XGCC = '/home/davide/gcc346-build/gcc/xgcc'
XGCC_B = '/home/davide/gcc346-build/gcc'
LD = '/usr/bin/sh-elf-ld'
OBJCOPY = '/usr/bin/sh-elf-objcopy'
NM = '/usr/bin/sh-elf-nm'
LIBGCC = os.path.join(XGCC_B, 'libgcc.a')
STUB_INC = '/tmp/verify_gcc346/inc'        # stub stdint.h (shared, never committed)
WORK = '/tmp/verify_bytepack'              # own workdir (never touches gcc346's)
LINK_BASE = 0x4000                         # fixed link base

# ---- RAM geometry -----------------------------------------------------------
DST_BASE = 0x2000                      # emulated dst buffer base
SRC_BASE = 0x3000                      # emulated src buffer base
GUARD = 8                              # sentinel bytes before/after each buffer
SENTINEL = 0x5A                        # guard fill byte

N_DEFAULT = 3000                       # seeded vectors per function
LENGTHS = list(range(1, 65))           # buffer lengths 1..64
ALIGNS = [0, 1, 2, 3]                  # buffer offsets
PATTERNS = ['zero', 'ones', 'inc', 'dec', 'beef', 'rand']

EDGE8 = [0x00, 0x01, 0x7F, 0x80, 0xFE, 0xFF, 0x5A, 0xA5]
EDGE16 = [0x0000, 0x0001, 0x00FF, 0x0100, 0x7FFF, 0x8000,
          0xFF00, 0xFFFF, 0x1234, 0xABCD, 0x8001, 0x7FFE]

# =============================================================================
# Emulator-gap workaround — XTRCT (carried over from verify_gcc346.py; harmless
# here — none of the bytepack blobs emits xtrct — but keeps the emulator
# consistent with the verified baseline).
# =============================================================================
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

# =============================================================================
# C lifts (embedded; written to WORK, never into the repo)
# =============================================================================
SRC8 = r'''/* rx8_bytepack8.c -- C lift of ROM leaf @0x552FE (converter_0x552FE). */
#include <stdint.h>

uint8_t *rx8_bytepack8(uint8_t *dst, uint8_t *src, uint8_t value)
{
    *src += 1;
    *dst++ = value;
    return dst;
}
'''

SRC16 = r'''/* rx8_bytepack16.c -- C lift of ROM leaf @0x5530C (inverter_0x5530C). */
#include <stdint.h>

uint8_t *rx8_bytepack16(uint8_t *dst, uint8_t *src, uint16_t value)
{
    *src += 1;
    *dst++ = (uint8_t)(value >> 8);
    *src += 1;
    *dst++ = (uint8_t)value;
    return dst;
}
'''

# name, ROM phys addr, C file, entry symbol, value width, seed
FUNCS = [
    {'name': 'bytepack8', 'addr_rom': 0x552FE, 'src': 'rx8_bytepack8.c',
     'entry_sym': 'rx8_bytepack8', 'width': 8, 'seed': 0x552FE},
    {'name': 'bytepack16', 'addr_rom': 0x5530C, 'src': 'rx8_bytepack16.c',
     'entry_sym': 'rx8_bytepack16', 'width': 16, 'seed': 0x5530C},
]

_LINKER = (
    'OUTPUT_FORMAT(elf32-sh)\n'
    'MEMORY { RAM (rx) : ORIGIN = 0x%X, LENGTH = 0x1000 }\n'
    'SECTIONS {\n'
    '  .text : { *(.text) *(.text.*) *(.rodata) *(.rodata.*) *(.rdata) } > RAM\n'
    '  /DISCARD/ : { *(.comment) *(.note*) *(.symtab) *(.strtab) '
    '*(.shstrtab) *(.debug*) }\n}\n' % LINK_BASE)

_STDINT = (
    '#ifndef _STDINT_H\n#define _STDINT_H\n'
    'typedef signed char int8_t; typedef unsigned char uint8_t;\n'
    'typedef signed short int16_t; typedef unsigned short uint16_t;\n'
    'typedef signed int int32_t; typedef unsigned int uint32_t;\n'
    'typedef signed long long int64_t; typedef unsigned long long uint64_t;\n'
    '#define UINT16_MAX 65535\n#define UINT8_MAX 255\n#endif\n')

_blob_cache = {}


def ensure_stubs():
    os.makedirs(STUB_INC, exist_ok=True)
    p = os.path.join(STUB_INC, 'stdint.h')
    if not os.path.exists(p):
        with open(p, 'w') as f:
            f.write(_STDINT)


_LIFTS = {'bytepack8': SRC8, 'bytepack16': SRC16}


def write_lifts():
    os.makedirs(WORK, exist_ok=True)
    for cfg in FUNCS:
        with open(os.path.join(WORK, cfg['src']), 'w') as f:
            f.write(_LIFTS[cfg['name']])


def build_blob(cfg):
    """Compile lift with gcc 3.4.6, link at 0x4000, extract .text.
    Returns (blob_bytes, {symbol: linked_absolute_addr})."""
    os.makedirs(WORK, exist_ok=True)
    base = os.path.join(WORK, cfg['name'])
    obj, elf, blb = base + '.o', base + '.elf', base + '.bin'

    subprocess.run(
        [XGCC, '-B', XGCC_B, '-m2e', '-O1', '-fomit-frame-pointer',
         '-c', os.path.join(WORK, cfg['src']), '-o', obj,
         '-I', STUB_INC, '-I', WORK],
        check=True, capture_output=True)
    ld_script = os.path.join(WORK, 'link.ld')
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


def blob_for(cfg):
    key = cfg['name']
    if key not in _blob_cache:
        _blob_cache[key] = build_blob(cfg)
    return _blob_cache[key]


# =============================================================================
# RAM builder / pattern fillers  (deterministic; 'rand' has its own RNG)
# =============================================================================
FILL_RNG = make_rng(0x5EED)


def pat_byte(pat, i):
    if pat == 'zero':
        return 0x00
    if pat == 'ones':
        return 0xFF
    if pat == 'inc':
        return i & 0xFF
    if pat == 'dec':
        return (0xFF - (i & 0xFF)) & 0xFF
    if pat == 'beef':
        return (0xDE, 0xAD, 0xBE, 0xEF)[i % 4]
    return FILL_RNG.getrandbits(8)      # 'rand'


def build_ram(dst_addr, src_addr, length, pat):
    """Seed guards + `length`-byte buffers at dst_addr and src_addr (may
    overlap: seeding order is fixed and deterministic, both emulator runs and
    the oracle see the very same image)."""
    ram = {}
    for base, addr in ((DST_BASE, dst_addr), (SRC_BASE, src_addr)):
        for i in range(GUARD):
            ram[addr - GUARD + i] = SENTINEL
        for i in range(length):
            ram[addr + i] = pat_byte(pat, i)
        for i in range(GUARD):
            ram[addr + length + i] = SENTINEL
    return ram


# =============================================================================
# Vector generation (edges + dense matrix + aliasing group + random fill)
# =============================================================================
def gen_vectors(cfg, n):
    width = cfg['width']
    rng = make_rng(cfg['seed'])
    edges = EDGE8 if width == 8 else EDGE16
    vecs = []

    def add(dst, src, val, length, pat, tag):
        vecs.append({'dst': dst, 'src': src, 'val': val,
                     'length': length, 'pat': pat, 'desc': tag})

    for v in edges:
        add(DST_BASE, SRC_BASE, v, 4, 'zero', 'edge val=0x%04X' % v)

    # full deterministic matrix: patterns x lengths(1..64) x alignments(0..3)
    for pat in PATTERNS:
        for length in LENGTHS:
            for align in ALIGNS:
                val = rng.getrandbits(width)
                add(DST_BASE + align, SRC_BASE + align, val, length, pat,
                    'pat=%-4s len=%-3d align=%d val=0x%04X'
                    % (pat, length, align, val))

    # aliasing group: dst and src in the SAME region (exercises the reload
    # path of bytepack16 and the ordering of the *src increments)
    for delta in (0, 1, -1, 2, -2):
        for length in (4, 16):
            val = rng.getrandbits(width)
            add(DST_BASE, DST_BASE + delta, val, length, 'rand',
                'alias dst=0x%X src=0x%X val=0x%04X'
                % (DST_BASE, DST_BASE + delta, val))

    # seeded random stream (occasionally re-injecting aliasing)
    while len(vecs) < n:
        val = rng.getrandbits(width)
        length = rng.choice(LENGTHS)
        align = rng.choice(ALIGNS)
        pat = rng.choice(PATTERNS)
        if rng.random() < 0.2:
            delta = rng.choice((0, 1, -1, 2))
            dst = DST_BASE + align
            add(dst, dst + delta, val, length, pat,
                'rnd#%d alias d=0x%X s=0x%X val=0x%04X len=%d pat=%s'
                % (len(vecs), dst, dst + delta, val, length, pat))
        else:
            add(DST_BASE + align, SRC_BASE + align, val, length, pat,
                'rnd#%d val=0x%04X len=%d align=%d pat=%s'
                % (len(vecs), val, length, align, pat))
    return vecs


# =============================================================================
# Python reference oracle of the deduced semantics (handles aliasing naturally
# by simulating on a copy of the very same RAM image).
# =============================================================================
def oracle_run(width, dst, src, value, mem):
    m = dict(mem)
    if width == 8:
        m[src] = (m.get(src, 0) + 1) & 0xFF
        m[dst] = value & 0xFF
        return dst + 1, m
    m[src] = (m.get(src, 0) + 1) & 0xFF
    m[dst] = (value >> 8) & 0xFF
    m[src] = (m.get(src, 0) + 1) & 0xFF
    m[dst + 1] = value & 0xFF
    return dst + 2, m


# =============================================================================
# Evaluation
# =============================================================================
def run_function(cfg, n):
    width = cfg['width']
    blob, syms = blob_for(cfg)
    if cfg['entry_sym'] not in syms:
        raise RuntimeError('entry symbol %r not found in blob (syms=%r)'
                           % (cfg['entry_sym'], sorted(syms)))
    entry = syms[cfg['entry_sym']]
    code = {LINK_BASE + i: blob[i] for i in range(len(blob))}
    code_keys = set(code)

    cpu = load_cpu()
    vecs = gen_vectors(cfg, n)
    t0 = time.time()

    rb, rom_ram_bad, blb_ram_bad, orc_bad = 0, 0, 0, 0
    samples = []
    for v in vecs:
        ram = build_ram(v['dst'], v['src'], v['length'], v['pat'])
        data_keys = set(ram)
        r6 = v['val'] & ((1 << width) - 1)

        rom_r0 = cpu.call(cfg['addr_rom'], r4=v['dst'], r5=v['src'],
                          r6=r6, ram=dict(ram))
        rom_post = dict(cpu.ram)

        overlay = dict(code)
        overlay.update(ram)
        blb_r0 = cpu.call(entry, r4=v['dst'], r5=v['src'], r6=r6, ram=overlay)
        blb_post = dict(cpu.ram)

        exp_r0, exp_mem = oracle_run(width, v['dst'], v['src'], r6, ram)

        # 1) ROM vs blob: r0 + full data-region RAM state
        if rom_r0 != blb_r0:
            rb += 1
            if len(samples) < 5:
                samples.append('r0   %s ROM=0x%X blob=0x%X'
                               % (v['desc'], rom_r0, blb_r0))
        if any(rom_post.get(k, 0) != blb_post.get(k, 0) for k in data_keys):
            rb += 1
            if len(samples) < 5:
                samples.append('ram  %s' % v['desc'])

        # 2) neither side writes outside its writable region
        if not set(rom_post) <= data_keys:
            rom_ram_bad += 1
            if len(samples) < 5:
                samples.append('rom-write-outside: %s (keys=%s)'
                               % (v['desc'], sorted(set(rom_post) - data_keys)))
        if not set(blb_post) <= (data_keys | code_keys):
            blb_ram_bad += 1
            if len(samples) < 5:
                samples.append('blob-write-outside: %s (keys=%s)'
                               % (v['desc'], sorted(set(blb_post) - data_keys - code_keys)))

        # 3) reference oracle vs both sides
        if rom_r0 != exp_r0:
            orc_bad += 1
            if len(samples) < 5:
                samples.append('oracle-r0 ROM: %s got=0x%X exp=0x%X'
                               % (v['desc'], rom_r0, exp_r0))
        if any(rom_post.get(k, 0) != exp_mem.get(k, 0) for k in data_keys):
            orc_bad += 1
            if len(samples) < 5:
                samples.append('oracle-ram ROM: %s' % v['desc'])
        if blb_r0 != exp_r0:
            orc_bad += 1
            if len(samples) < 5:
                samples.append('oracle-r0 blob: %s got=0x%X exp=0x%X'
                               % (v['desc'], blb_r0, exp_r0))
        if any(blb_post.get(k, 0) != exp_mem.get(k, 0) for k in data_keys):
            orc_bad += 1
            if len(samples) < 5:
                samples.append('oracle-ram blob: %s' % v['desc'])

    dt = time.time() - t0
    return {'cfg': cfg, 'n': len(vecs), 'rb': rb,
            'rom_ram_bad': rom_ram_bad, 'blb_ram_bad': blb_ram_bad,
            'orc': orc_bad, 'time': dt, 'samples': samples}


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    ensure_stubs()
    write_lifts()

    total = 0
    for cfg in FUNCS:
        r = run_function(cfg, n)
        bad = r['rb'] + r['rom_ram_bad'] + r['blb_ram_bad'] + r['orc']
        total += bad
        status = 'OK  ' if bad == 0 else 'FAIL'
        print('%s %-10s @0x%05X  n=%-5d  ROM-vs-blob=%-4d  '
              'writes-outside=%-2d  oracle=%-4d  %.2fs'
              % (status, cfg['name'], cfg['addr_rom'], r['n'],
                 r['rb'], r['rom_ram_bad'] + r['blb_ram_bad'],
                 r['orc'], r['time']))
        for s in r['samples']:
            print('        ' + s)

    if total:
        print('\nverify_bytepack: %d mismatch(es) total — FAIL' % total)
        sys.exit(1)
    print('\nverify_bytepack: all OK (0 mismatch; r0 and RAM state match '
          'on both leaves)')
    print('    semantics: @0x552FE *src+=1; *dst++=v8; return dst'
          '    @0x5530C *src+=1; *dst++=v16>>8; *src+=1; *dst++=v16; return dst')


if __name__ == '__main__':
    main()
