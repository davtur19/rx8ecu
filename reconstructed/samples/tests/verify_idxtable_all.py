#!/usr/bin/env python3
"""
verify_idxtable_all.py — full family validation of the rx8_index_table helpers
@0x68780 zone against the era-ROM toolchain (sh-elf gcc 3.4.6).

Family census (ROM 60E1D400.bin, zone 0x68774..0x6884A):

    reconstructed leaves (samples/src/rx8_index_table.c)
      0x68780  clear   word@p = word@p+2 = word@p+4 = 0
      0x6879C  step    word@p   = (word@p+4 >= 0x0464) ? 0 : word@p+4 + 1
      0x687C8  step2   separate ROM copy of `step` (identical logic)
      0x687F4  dec     word@p+4 = (word@p == 0) ? 0x0464 : word@p - 1

    discovered leaves (in the same table zone, not yet lifted to c/)
      0x68774  wrapper `clear(0)` — bsr 0x68780 with r4 = 0
      0x68820  step3   word@p+2 = (word@p+4 >= 0x0464) ? 0 : word@p+4 + 1
              (a `step` variant writing the reserved +2 word; referenced from
               the function-pointer pool at 0x695C0 alongside 0x687C8/0x687F4)
    The two discovered leaves are validated here with a temp C model written to
    /tmp/verify_gcc346/work (never committed); the four reconstructed leaves use
    the repo source verbatim.

For every leaf the harness closes the "ROM -> C -> era-ROM gcc 3.4.6" loop:

  (a) writes the temp extra-leaf model to /tmp once,
  (b) compiles samples/src/rx8_index_table.c + the temp model with
      /home/davide/gcc346-build/gcc/xgcc -m2e -O1 -fomit-frame-pointer
      (same recipe as tests/verify_gcc346.py, stub headers in
      /tmp/verify_gcc346/inc),
  (c) links at base 0x4000 with the trivial linker script (same as
      verify_gcc346.py) — the leaves are self-contained (no libgcc helpers are
      emitted for mulu/add/cmp; the ROM side needs no tables because the C only
      references the RAM base constant RX8_IDX_TABLE_BASE),
  (d) objcopy --only-section=.text extracts the code blob,
  (e) loads the blob into the SH-2E emulator through the sparse `ram` overlay,
  (f) runs BOTH the real ROM bytes at ADDR_ROM and the blob at 0x4000 on the
      very same seeded slot vectors and compares the RAM side-effects (the
      three managed 16-bit words of the addressed slot).

RAM-state contract: these leaves are `void`; the observable behaviour is the
slot state, exactly like verify_gcc346.py's 'ram' kind (which compares only
idx_read).  r0 is NOT a return value here (the ROM leaf leaves an incidental
value in r0 — e.g. the stored word — while the gcc-3.4.6 void blob leaves a
compiler-layout-dependent value), so r0 is captured and reported as
diagnostics but is not a pass/fail criterion.  Indices 9..255 wrap the slot
pointer through 32-bit arithmetic identically on both sides (both emulated, so
no host mmap limit applies).

Usage:  python3 tests/verify_idxtable_all.py [N]    (default N per leaf)
Exit 0 iff every leaf reports 0 mismatches.
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

# ---- era-ROM toolchain (identical to verify_gcc346.py) ---------------------
XGCC = '/home/davide/gcc346-build/gcc/xgcc'
XGCC_B = '/home/davide/gcc346-build/gcc'
LD = '/usr/bin/sh-elf-ld'
OBJCOPY = '/usr/bin/sh-elf-objcopy'
NM = '/usr/bin/sh-elf-nm'
LIBGCC = os.path.join(XGCC_B, 'libgcc.a')

STUB_INC = '/tmp/verify_gcc346/inc'        # stub headers (never committed)
WORK = '/tmp/verify_gcc346/work'           # objects / elfs / blobs / temp model
LINK_BASE = 0x4000

SRC_DIR = os.path.join(SAMPLES, 'src')
INC_DIR = os.path.join(SAMPLES, 'include')

# ---- idx-table family geometry (mirrors verify_gcc346.py / harness_idx_table.py)
IDX_BASE = 0xFFFFD998
IDX_STRIDE = 0x46C
IDX_LIMIT = 0x0464
# Realistic firmware range is slots 0..8 (9 slots); indices 9..255 wrap.
SLOTS = 9

# Emulator-gap workaround inherited from verify_gcc346.py: this family's blob
# never executes xtrct, but the monkeypatch is applied once up front so a
# future reader can run the same emulator instance against other families too.
_SH2_exec_ref = SH2._exec


def _xtrct_fixed(self, op, pc):
    if (op & 0xF00F) == 0x200D:                       # xtrct Rm,Rn
        m = (op >> 4) & 0xF
        n = (op >> 8) & 0xF
        self.r[n] = (((self.r[m] << 16) & 0xFFFF0000)
                     | ((self.r[n] >> 16) & 0xFFFF)) & 0xFFFFFFFF
        return
    return _SH2_exec_ref(self, op, pc)


SH2._exec = _xtrct_fixed

# ============================================================================
# Stub headers (same content as verify_gcc346.py — written once to /tmp)
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

# Temp C model of the two discovered leaves (never committed to the repo).
_EXTRA_MODEL = r'''
/* temp model of the two discovered idx-table leaves (written by
 * verify_idxtable_all.py to /tmp, never committed).  Semantics were pinned
 * directly against the ROM emulator before this harness was written.
 *   0x68774  clear0 wrapper: rx8_index_table_clear(0)
 *   0x68820  step3: word@p+2 = (word@p+4 >= 0x0464) ? 0 : word@p+4 + 1
 */
#include <stdint.h>
#include "rx8_samples.h"
#include "rx8_hw.h"

typedef struct {
    uint16_t counter;
    uint16_t reserved;
    uint16_t limit;
} rx8_index_slot_t;

static rx8_index_slot_t *rx8_index_slot_ptr(uint32_t idx)
{
    uint32_t addr = RX8_IDX_TABLE_BASE
                  + (uint32_t)(idx & 0xFFu) * RX8_IDX_TABLE_STRIDE;
    return (rx8_index_slot_t *)(uintptr_t)addr;
}

void rx8_index_table_clear0_wrapper(void)        /* 0x68774 */
{
    rx8_index_table_clear(0);
}

void rx8_index_table_step3(uint32_t idx)         /* 0x68820 */
{
    rx8_index_slot_t *s = rx8_index_slot_ptr(idx);
    s->reserved = (s->limit >= RX8_IDX_TABLE_LIMIT) ? 0
                  : (uint16_t)(s->limit + 1u);
}
'''

# ============================================================================
# Family configuration: (rom addr, blob symbol, slot touched by the leaf)
# ============================================================================
# word_sel is which of the three slot words the leaf reads/writes:
#   'w0' for step/step2/step3 (read w4, write w0/w2), 'w4' for dec, 'all' for
#   clear/clear0 — used to build the targeted word-edge vector set.
LEAVES = {
    'clear':   {'rom': 0x0068774, 'sym': 'rx8_index_table_clear0_wrapper',
                'word_sel': 'all', 'r4_ignored': True,   'extra': True},
    'clr':     {'rom': 0x0068780, 'sym': 'rx8_index_table_clear',
                'word_sel': 'all', 'r4_ignored': False,  'extra': False},
    'step':    {'rom': 0x006879C, 'sym': 'rx8_index_table_step',
                'word_sel': 'w0', 'r4_ignored': False,   'extra': False},
    'step2':   {'rom': 0x00687C8, 'sym': 'rx8_index_table_step2',
                'word_sel': 'w0', 'r4_ignored': False,   'extra': False},
    'dec':     {'rom': 0x00687F4, 'sym': 'rx8_index_table_dec',
                'word_sel': 'w4', 'r4_ignored': False,   'extra': False},
    'step3':   {'rom': 0x0068820, 'sym': 'rx8_index_table_step3',
                'word_sel': 'w0', 'r4_ignored': False,   'extra': True},
}
SEED = 0x68780

# ============================================================================
# Toolchain build
# ============================================================================
_stub_done = [False]
_blob_cache = {}


def ensure_stubs():
    if _stub_done[0]:
        return
    os.makedirs(STUB_INC, exist_ok=True)
    with open(os.path.join(STUB_INC, 'stdint.h'), 'w') as f:
        f.write(_STDINT)
    with open(os.path.join(STUB_INC, 'math.h'), 'w') as f:
        f.write(_MATH)
    # temp model of the discovered leaves (repo stays clean)
    with open(os.path.join(WORK, 'idx_extra_model.c'), 'w') as f:
        f.write(_EXTRA_MODEL)
    _stub_done[0] = True


def build_blob():
    """Compile rx8_index_table.c + the temp extra model with gcc 3.4.6, link
    at 0x4000, extract .text blob.

    Returns (blob_bytes, {symbol: linked_absolute_addr}).  All six leaves live
    in one linked image so a single blob/overlay serves every entry."""
    os.makedirs(WORK, exist_ok=True)
    name = 'idxtable_all'
    obj = os.path.join(WORK, name + '.o')
    elf = os.path.join(WORK, name + '.elf')
    blb = os.path.join(WORK, name + '.bin')

    srcs = [os.path.join(SRC_DIR, 'rx8_index_table.c'),
            os.path.join(WORK, 'idx_extra_model.c')]
    subprocess.run(
        [XGCC, '-B', XGCC_B, '-m2e', '-O1', '-fomit-frame-pointer',
         '-c'] + srcs + ['-o', obj,
         '-I', STUB_INC, '-I', SRC_DIR, '-I', INC_DIR],
        check=True, capture_output=True)

    ld_script = os.path.join(WORK, 'link346.ld')
    if not os.path.exists(ld_script):
        with open(ld_script, 'w') as f:
            f.write(_LINKER)
    # None of the six leaves emits a libgcc helper (only mulu/add/cmp/mov.w),
    # but libgcc.a is linked anyway so a future family member that does divide
    # or variable-shift keeps working with the same harness.
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
    if 'blob' not in _blob_cache:
        _blob_cache['blob'] = build_blob()
    return _blob_cache['blob']


def ram_overlay(blob):
    return {LINK_BASE + i: blob[i] for i in range(len(blob))}


# ============================================================================
# Slot seeding / reading (big-endian, identical to verify_gcc346.py)
# ============================================================================
def paddr(idx):
    return (IDX_BASE + (idx & 0xFF) * IDX_STRIDE) & 0xFFFFFFFF


def seed_slot(idx, w0, w2, w4):
    a = paddr(idx)
    return {a: (w0 >> 8) & 0xFF, a + 1: w0 & 0xFF,
            a + 2: (w2 >> 8) & 0xFF, a + 3: w2 & 0xFF,
            a + 4: (w4 >> 8) & 0xFF, a + 5: w4 & 0xFF}


def read_slot(cpu, idx):
    a = paddr(idx)
    return tuple((cpu.ram.get(a + k, 0) << 8) | cpu.ram.get(a + k + 1, 0)
                 for k in (0, 2, 4))


# ============================================================================
# Vector generation (seeded, reproducible).  Edge indices per the task spec:
#   0, len-1 (= SLOTS-1 = 8), len (= SLOTS = 9 -> wraps), -1 (= 0xFF -> wraps),
#   half (= SLOTS//2 = 4)  — plus a couple of extra wrap indices for coverage.
# ============================================================================
IDX_EDGES = [0, 1, SLOTS // 2, SLOTS - 1, SLOTS, 0x7F, 0xFF]
W_EDGES_W0 = [0x0000, 0x0001, IDX_LIMIT - 1, IDX_LIMIT, IDX_LIMIT + 1,
              0x7FFF, 0x8000, 0xFFFE, 0xFFFF]
W_EDGES_W4 = [0x0000, 0x0001, IDX_LIMIT - 1, IDX_LIMIT, IDX_LIMIT + 1,
              0x7FFF, 0x8000, 0xFFFE, 0xFFFF]
W_EDGES_ALL = [0x0000, 0x0001, 0x1234, IDX_LIMIT, 0x7FFF, 0x8000, 0xFFFF]


def gen_vectors(name, n):
    """Edge vectors (deterministic) + n seeded random vectors."""
    cfg = LEAVES[name]
    rng = make_rng(SEED ^ (list(LEAVES).index(name) * 0x101) & 0xFFFFFFFF)
    vecs = []

    if cfg['word_sel'] == 'w0':       # step/step2/step3: w4 is the source
        for idx in IDX_EDGES:
            for w4 in W_EDGES_W0:
                vecs.append((idx, 0x5555, 0xAAAA, w4))
    elif cfg['word_sel'] == 'w4':     # dec: w0 is the source
        for idx in IDX_EDGES:
            for w0 in W_EDGES_W4:
                vecs.append((idx, w0, 0xAAAA, 0x5555))
    else:                             # clear/clear0: all words irrelevant
        for idx in IDX_EDGES:
            for w0 in W_EDGES_ALL:
                vecs.append((idx, w0, 0xBBBB, 0xCCCC))

    for _ in range(n):
        idx = rng.choice([rng.randint(0, SLOTS - 1)] * 90
                         + [rng.randint(SLOTS, 255)] * 10)   # 90% real, 10% wrap
        vecs.append((idx, rng.getrandbits(16), rng.getrandbits(16),
                     rng.getrandbits(16)))
    return vecs


def desc(idx, w0, w2, w4):
    return 'idx=%d (%04X,%04X,%04X) slot@%08X' % (idx, w0, w2, w4, paddr(idx))


# ============================================================================
# Per-leaf evaluation
# ============================================================================
def run_leaf(name, n):
    cfg = LEAVES[name]
    blob, syms = blob_for()
    base = ram_overlay(blob)
    cpu = load_cpu()
    vecs = gen_vectors(name, n)
    rom_addr = cfg['rom']
    blb_addr = syms[cfg['sym']]
    t0 = time.time()

    rb = 0
    samples = []
    for i, (idx, w0, w2, w4) in enumerate(vecs):
        s = seed_slot(idx, w0, w2, w4)
        # ROM side (real bytes).
        cpu.call(rom_addr, r4=0 if cfg['r4_ignored'] else idx, ram=dict(s))
        e = read_slot(cpu, idx)
        r0_rom = cpu.r[0] & 0xFFFFFFFF
        # blob side (gcc 3.4.6 of the same C).
        m = dict(base)
        m.update(s)
        cpu.call(blb_addr, r4=0 if cfg['r4_ignored'] else idx, ram=m)
        b = read_slot(cpu, idx)
        r0_blob = cpu.r[0] & 0xFFFFFFFF
        if e != b:
            rb += 1
            if len(samples) < 5:
                samples.append('vec#%d %s ROM=%04X,%04X,%04X (r0=%08X) '
                               'blob=%04X,%04X,%04X (r0=%08X)'
                               % (i, desc(idx, w0, w2, w4), e[0], e[1], e[2],
                                  r0_rom, b[0], b[1], b[2], r0_blob))

    return {'name': name, 'n': len(vecs), 'rb': rb, 'time': time.time() - t0,
            'samples': samples}


def main():
    n_override = int(sys.argv[1]) if len(sys.argv) > 1 else None
    ensure_stubs()

    # default: >= 2000 random per leaf as required by the task spec
    n_def = 2500
    total = 0
    for name in LEAVES:
        cfg = LEAVES[name]
        n = n_override or n_def
        r = run_leaf(name, n)
        total += r['rb']
        status = 'OK  ' if r['rb'] == 0 else 'FAIL'
        tag = 'extra' if cfg['extra'] else 'recon'
        print('%s %-8s %-5s @0x%-6X  n=%-5d  ROM-vs-blob=%-4d  %.2fs'
              % (status, name, tag, cfg['rom'], r['n'], r['rb'], r['time']))
        for s in r['samples']:
            print('        ' + s)

    if total:
        print('\nverify_idxtable_all: %d mismatch(es) total — FAIL' % total)
        sys.exit(1)
    print('\nverify_idxtable_all: idx_table family @0x68780 (4 reconstructed '
          '+ clear0/step3 discovered) 0 mismatch')


if __name__ == '__main__':
    main()
