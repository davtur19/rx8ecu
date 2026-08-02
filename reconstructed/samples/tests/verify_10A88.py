#!/usr/bin/env python3
"""
verify_10A88.py — Lotto-2 validation for ROM @0x10A88 (22 B, pure leaf).

Target: calc_manifold_pressure_error_diff_10A88
  file roms/stock/60E1D400.bin, VMA 0x60E2DE88 (file offset 0x10A88).

  mov.l @(pc),r2   r2 = 0xFFE20000            (-0x1E0000; -30.0 Q16.16)
  mov r5,r3 / sub r4,r3 / mov r3,r4            r4 = b - a   (32-bit wrap)
  cmp/gt r2,r4    T = s32(r4) > s32(r2)   ->   T = d > -0x1E0000
  bt.s return      if T: return d
  mov.l @(pc),r1   r1 = 0x01680000            (360.0 Q16.16)
  add r1,r4         r4 = d + 0x01680000
  rts / mov r4,r0  -> r0

  Semantics:  d = b - a;  return d > -0x1E0000 ? d : d + 0x01680000;
  (one-sided Q16.16 wrap: difference below -30.0 gets +360.0 added).

There is no dedicated C in reconstructed/samples/src yet — the C lift is
embedded below, compiled with the era-ROM toolchain (gcc 3.4.6, -m2e -O1
-fomit-frame-pointer, linked at 0x4000) and the resulting blob is compared
against the REAL ROM bytes on the SAME vectors (r0).  A pure-Python oracle
cross-checks the blob as well.

Read-only w.r.t. the repo: everything written goes to /tmp.  Exit 0 iff
0 mismatches.

Usage:  python3 verify_10A88.py [N]
"""
import os
import random
import subprocess
import sys

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
LIBGCC = os.path.join(XGCC_B, 'libgcc.a')

STUB_INC = '/tmp/verify_gcc346/inc'
WORK = '/tmp/verify_10A88'
LINK_BASE = 0x4000

ADDR_ROM = 0x10A88
ENTRY_SYM = 'calc_manifold_pressure_error_diff_10A88'

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
# Embedded C lift — behavioral transcription of ROM @0x10A88.
# (0xFFE20000 = -0x1E0000 = -30.0 in Q16.16; 0x01680000 = 360.0 in Q16.16.)
# ============================================================================
C_LIFT = r'''
/* calc_manifold_pressure_error_diff_10A88 — lift of ROM @0x10A88 (60E1D400.bin,
 * VMA 0x60E2DE88, 22 B pure leaf).  Semantics:
 *   d = b - a;  return d > -0x1E0000 ? d : d + 0x01680000;   (signed d)
 * one-sided Q16.16 wrap: when the difference drops below -30.0, add +360.0. */
#include <stdint.h>

int32_t calc_manifold_pressure_error_diff_10A88(int32_t a, int32_t b)
{
    int32_t d = b - a;
    if (d > (int32_t)0xFFE20000)        /* d > -0x1E0000  (signed) */
        return d;
    return d + (int32_t)0x01680000;
}
'''

# ============================================================================
# Vector generation  (seeded, reproducible)
# ============================================================================
# Fixed edge vectors first: clamp boundary d == -0x1E0000 (and +-1), the wrap
# target 0x14A0000, signed overflow of the difference (INT_MIN/MAX combos) and
# the standard SH-2E edge pairs.
EDGES = [
    (0x00000000, 0x00000000),
    (0x7FFFFFFF, 0x00000000),          # d = -INT_MAX
    (0x80000000, 0x00000000),          # d = +2^31 (wrap, negative)
    (0x7FFFFFFF, 0x00000001),
    (0x7FFFFFFF, 0x7FFFFFFF),          # d = 0
    (0x80000000, 0x80000000),          # d = 0
    (0xFFFFFFFF, 0xFFFFFFFF),          # d = 0
    (0x80000000, 0x7FFFFFFF),          # d = -1 (INT_MAX - INT_MIN wraps)
    (0x7FFFFFFF, 0x80000000),          # d = +1 (INT_MIN - INT_MAX wraps)
    # clamp boundary d == -0x1E0000 (equal: NOT >, so add 0x1680000)
    (0x00000000, 0xFFE20000),          # d = -0x1E0000 -> 0x14A0000
    (0x00000000, 0xFFE20001),          # d = -0x1E0000+1 -> keep d
    (0x00000000, 0xFFE1FFFF),          # d = -0x1E0000-1 -> 0x14A0000-1
    (0x001E0000, 0x00000000),          # d = -0x1E0000 (via a) -> 0x14A0000
    (0xFFE20000, 0x00000000),          # d = +0x1E0000 -> keep
    (0xFFE20001, 0x00000000),          # d = +0x1E0000-1 -> keep
    (0xFFE1FFFF, 0x00000000),          # d = +0x1E0000+1 -> keep
    # wrap target neighbourhood (result after the +0x1680000 correction)
    (0x001E0001, 0x00000000),          # d = -0x1E0000-1 -> 0x14A0000-1
    (0x001E0100, 0x00000000),          # d = -0x1E0100 -> +0x1680000
    # far below the threshold (still a single +360 wrap, saturating not used)
    (0x01860000, 0x00000000),          # d = -0x1860000 -> -0x1E0000+0x1680000... no
    (0xDEADBEEF, 0xCAFEBABE),
    (0x00000000, 0xFFFFFFFF),          # d = -1 -> keep
    (0x00000000, 0x80000000),          # d = INT_MIN -> INT_MIN+0x1680000
    # +/-1 raw inputs (task-spec edges)
    (0x00000001, 0x00000000),          # d = -1 -> keep
    (0x00000000, 0x00000001),          # d = +1 -> keep
    # the +360.0 wrap constant itself: +/-0x1680000 (task-spec edges)
    (0x00000000, 0x01680000),          # d = +0x1680000 -> keep
    (0x01680000, 0x00000000),          # d = -0x1680000 -> -0x1680000+0x1680000 = 0
    (0x01680001, 0x00000000),          # d = -0x1680000-1 -> 0xFFFFFFFF (-1)
    (0x01680000, 0x01680000),          # d = 0 -> keep
]

MASK = 0xFFFFFFFF
C1 = 0xFFE20000                        # -0x1E0000 as u32
C2 = 0x01680000


def oracle(a, b):
    """Pure-Python oracle: exact int32 wrap semantics of the ROM."""
    d = (b - a) & MASK
    sd = d - 0x100000000 if d & 0x80000000 else d
    if sd > -0x1E0000:
        return d
    return (d + C2) & MASK


def gen_vectors(n):
    rng = make_rng(ADDR_ROM)
    vecs = [{'a': a, 'b': b, 'desc': 'a=0x%08X b=0x%08X' % (a, b)}
            for (a, b) in EDGES]
    for _ in range(n):
        a, b = rng.getrandbits(32), rng.getrandbits(32)
        vecs.append({'a': a, 'b': b, 'desc': 'a=0x%08X b=0x%08X' % (a, b)})
    return vecs

# ============================================================================
# Toolchain build
# ============================================================================
def ensure_stubs():
    os.makedirs(STUB_INC, exist_ok=True)
    p = os.path.join(STUB_INC, 'stdint.h')
    if not os.path.exists(p):
        with open(p, 'w') as f:
            f.write(_STDINT)


def build_blob():
    """Compile the embedded C lift with gcc 3.4.6, link at 0x4000, extract
    the self-contained .text blob.  Returns (blob_bytes, entry_addr)."""
    os.makedirs(WORK, exist_ok=True)
    src = os.path.join(WORK, '10A88.c')
    obj = os.path.join(WORK, '10A88.o')
    elf = os.path.join(WORK, '10A88.elf')
    blb = os.path.join(WORK, '10A88.bin')

    with open(src, 'w') as f:
        f.write(C_LIFT)

    subprocess.run(
        [XGCC, '-B', XGCC_B, '-m2e', '-O1', '-fomit-frame-pointer',
         '-c', src, '-o', obj, '-I', STUB_INC],
        check=True, capture_output=True)

    ld_script = os.path.join(WORK, 'link346.ld')
    if not os.path.exists(ld_script):
        with open(ld_script, 'w') as f:
            f.write(_LINKER)
    subprocess.run([LD, '-T', ld_script, obj, '-o', elf],
                   check=True, capture_output=True)
    subprocess.run([OBJCOPY, '-O', 'binary', '--only-section=.text', elf, blb],
                   check=True, capture_output=True)

    with open(blb, 'rb') as f:
        blob = f.read()
    nm = subprocess.run([NM, elf], capture_output=True, text=True)
    entry = LINK_BASE
    for line in nm.stdout.splitlines():
        parts = line.split()
        if (len(parts) == 3 and parts[1] == 'T'
                and parts[2].lstrip('_') == ENTRY_SYM):
            entry = int(parts[0], 16)
    return blob, entry


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 4000
    ensure_stubs()
    blob, entry = build_blob()
    overlay = {LINK_BASE + i: blob[i] for i in range(len(blob))}

    cpu = load_cpu()
    vecs = gen_vectors(n)
    rom_res, blb_res = [], []
    for v in vecs:
        rom_res.append(cpu.call(ADDR_ROM, r4=v['a'], r5=v['b']))
        blb_res.append(cpu.call(entry, r4=v['a'], r5=v['b'], ram=dict(overlay)))

    mismatch = 0
    samples = []
    for i, (r, b) in enumerate(zip(rom_res, blb_res)):
        exp = oracle(vecs[i]['a'], vecs[i]['b'])
        if r != b or r != exp:
            mismatch += 1
            if len(samples) < 5:
                samples.append('vec#%d %s ROM=0x%08X blob=0x%08X oracle=0x%08X'
                               % (i, vecs[i]['desc'], r, b, exp))

    name = 'calc_manifold_pressure_error_diff_10A88'
    status = 'OK  ' if mismatch == 0 else 'FAIL'
    print('%s %-22s @0x%-6X  n=%-5d  ROM-vs-blob/vs-oracle mismatches=%d'
          % (status, name, ADDR_ROM, len(vecs), mismatch))
    for s in samples:
        print('        ' + s)

    if mismatch:
        print('\nverify_10A88: %d mismatch(es) — FAIL' % mismatch)
        sys.exit(1)
    print('\nverify_10A88: %s OK (0 mismatch; %d edge + %d random)'
          % (name, len(EDGES), n))
    sys.exit(0)


if __name__ == '__main__':
    main()
