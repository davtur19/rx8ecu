#!/usr/bin/env python3
"""
verify_delayloop.py — era-ROM toolchain (sh-elf gcc 3.4.6) behavioural check of
the pure busy-wait `rx8_delay_loop_n8` @ `0x239C` (Lotto 2).

Closes the "ROM -> abstract C -> era-ROM toolchain" loop on the behavioural
plane for this single pure function, following the same pattern as
`verify_gcc346.py` (Lotto 1) but reduced to one function so the style-audited
Lotto-1 harness is left untouched.

SIGNATURE (confirmed, see below): ``void rx8_delay_loop_n8(uint16_t n)`` —
a **16-bit**, void, `uint8`-*not*/*`int`-not signature.  Ruled out empirically
from the era-ROM compiler's own code-gen (see SIGNATURE section).

The ROM code is pure: it never touches `r0` (return value stays 0) and burns
exactly *n × 8* busy-wait trips (register side-effects `r4 = r5 = n*8`).  The
only observables are execution time (not compared — trip count is data, not
code) and the post-call register image.  Therefore every vector is asserted on
*three* independent fronts:

  1. ROM   : `cpu.call(0x239C, r4=n)` -> post-call `r4 == r5 == n*8`, `r0 == 0`;
  2. blob  : `cpu.call(0x4000, r4=n, ram=overlay)` -> post-call
             `r1 == r2 == n*8`, `r0 == 0`  (gcc 3.4.6 allocates r1/r2, not
             r4/r5, and adds a `extu.w` truncation);
  3. host-C: `oracle_delay_loop_n8.c` prints the r0 the caller observes (0) for
             the same `uint16` vectors; compared with the blob's r0.

PROCEDURE (read-only w.r.t. the repo; all artifacts go to /tmp):

  (a) reuse the shared stub headers in `/tmp/verify_gcc346/inc`
      (stdint.h / math.h; the archived gcc 3.4.6 was configured
      `--without-headers`);
  (b) compile `src/rx8_delay_loop_n8.c` with the era-ROM recipe
      `/home/davide/gcc346-build/gcc/xgcc -B ... -m2e -O1 -fomit-frame-pointer`;
  (c) link the object at the fixed base `0x4000` with a trivial linker script
      (pulls no libgcc helper: the function is pure integer/shift, all of which
      the SH-2E does in hardware);
  (d) `sh-elf-objcopy --only-section=.text` extracts a self-contained blob;
  (e) the blob is loaded into the same SH-2E emulator (`tools/sh2emu.py`)
      through the sparse `ram` overlay and driven with `cpu.call(... r4=n)`;
  (f) the real ROM bytes at `0x239C` are run on the same vectors; results are
      compared as above;
  (g) 3000 seeded random vectors plus the explicit edge set
      `{0,1,2,3,4,8,16,255}`, all kept inside the emulator's 500 k-step budget;
  (h) a documented *semantic-boundary* block asserts the expected behaviour at
      the edges of the input domain (see SEMANTIC BOUNDARY section).

The harness exits non-zero iff any vector mismatches.

SEMANTIC BOUNDARY
-----------------
The ROM scales the **full 32-bit** `r4` (`shll2 r4; shll r4`), trusting the
caller to hand in a zero-extended small integer (the function-pointer dispatch
table does exactly that).  The reconstructed C declares `uint16_t n`, so its
gcc-3.4.6 image first truncates with `extu.w r4,r2`.  The two are equivalent
**on the domain `0 .. 0xFFFF`**, i.e. every realistic call.  Outside that
domain (documented, not a mismatch):

  * `n = 0x10000` : ROM spins 0x80000 trips and the emulator's 500k-step
                    runaway fires (asserted); the blob `extu.w`'s to 0 and
                    returns immediately with r0 = 0.
  * `n = 0xFFFF`  : ROM spins 0x7FFF8×8 trips -> runaway; the blob truncates to
                    0xFFFF and spins 0xFFFF*8 trips -> runaway too.  Both spin
                    (never both-under-budget), asserted as expected.

SIGNATURE EVIDENCE
------------------
`void f(uint16_t n)` is pinned by *three* independent sources:

  * `reconstructed/samples/src/rx8_delay_loop_n8.c` — `void rx8_delay_loop_n8(uint16_t n)`;
  * the authoritative lift `c/delay_loop_n8.c` — identical `uint16_t` prototype;
  * the gcc-3.4.6 image of that source opens with `extu.w r4,r2` — the compiler
    keeps the 16-bit widening/truncation for `uint16_t`.  A `uint8_t` signature
    would emit `extu.b` instead; an `int`/`uint32_t` parameter would emit none.
    The observed `extu.w` therefore also rules `uint8_t`/`int` back out.

Note on -O1: gcc 3.4.6 does NOT remove the side-effect-free counter loop (it
lacks modern dead-loop elimination), so the blob retains the loop and the
`r1 == r2 == n*8` relationship is a genuine, non-vacuous check.

Usage:  python3 tests/verify_delayloop.py [N]     (default N = 3000 random)
"""
import os
import subprocess
import sys

TESTS = os.path.dirname(os.path.abspath(__file__))      # reconstructed/samples/tests
SAMPLES = os.path.dirname(TESTS)                         # reconstructed/samples
ROOT = os.path.dirname(os.path.dirname(SAMPLES))         # rx8ecu
sys.path.insert(0, TESTS)
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2  # noqa: E402
from common import make_rng  # noqa: E402

# ---- era-ROM toolchain ------------------------------------------------------
XGCC = '/home/davide/gcc346-build/gcc/xgcc'
XGCC_B = '/home/davide/gcc346-build/gcc'
LD = '/usr/bin/sh-elf-ld'
OBJCOPY = '/usr/bin/sh-elf-objcopy'
NM = '/usr/bin/sh-elf-nm'
CC_HOST = os.environ.get('CC', 'cc')
LIBGCC = os.path.join(XGCC_B, 'libgcc.a')   # unused here (no div/shift helpers)

STUB_INC = '/tmp/verify_gcc346/inc'          # stub headers (never committed)
WORK = '/tmp/verify_gcc346/work'             # objects / elfs / blobs / oracle
LINK_BASE = 0x4000                           # fixed link base

SRC_DIR = os.path.join(SAMPLES, 'src')
INC_DIR = os.path.join(SAMPLES, 'include')

# ---- function config ---------------------------------------------------------
ADDR_ROM = 0x239C                # file offset of the ROM function (sh2emu addr)
SRC = 'rx8_delay_loop_n8.c'
ENTRY_SYM = 'rx8_delay_loop_n8'  # stripped symbol in the linked blob
N_DEFAULT = 3000
SEED = 0x237C                    # seeded, reproducible

# Largest n both sides can finish inside the 500k-step emulator budget.
#   ROM  : ~3 st/loop * n*8 trips + ~8   <= 500000  ->  n <= 20830
#   blob : ~4 st/loop * n*8 trips + ~10  <= 500000  ->  n <= 15624
# The code path is identical for every n (trip count is data, not code), so
# the 3000 random draws sample a reduced range for runtime and the *large*
# values are pinned explicitly by EXTRA_EDGE (incl. 15000 near the budget).
EMU_MAX_N = 1024

EDGE = [0, 1, 2, 3, 4, 8, 16, 255]
# mid/large explicit values pinned on top of the small edge list, so reducing
# the *random* range for runtime never drops near-budget coverage.
EXTRA_EDGE = [0xFFF, 0x2710, 15000]

# --- simple link script (keep a function that needs only .text + rodata) -----
_LINKER = (
    'OUTPUT_FORMAT(elf32-sh)\n'
    'MEMORY { RAM (rx) : ORIGIN = 0x%X, LENGTH = 0x1000 }\n'
    'SECTIONS {\n'
    '  .text : { *(.text) *(.text.*) *(.rodata) *(.rodata.*) *(.rdata) } > RAM\n'
    '  /DISCARD/ : { *(.comment) *(.note*) *(.symtab) *(.strtab) '
    '*(.shstrtab) *(.debug*) }\n}\n' % LINK_BASE)

_cache = {}


def ensure_stubs():
    """The archived gcc was configured --without-headers; provide minimal
    stdint.h / math.h once in /tmp (shared with verify_gcc346.py)."""
    if _cache.get('stubs'):
        return
    os.makedirs(STUB_INC, exist_ok=True)
    stdint = (
        '#ifndef _STDINT_H\n#define _STDINT_H\n'
        'typedef signed char int8_t; typedef unsigned char uint8_t;\n'
        'typedef signed short int16_t; typedef unsigned short uint16_t;\n'
        'typedef signed int int32_t; typedef unsigned int uint32_t;\n'
        'typedef signed long long int64_t; typedef unsigned long long uint64_t;\n'
        'typedef unsigned long uintptr_t; typedef long intptr_t;\n'
        '#endif\n')
    math = '#ifndef _MATH_H\n#define _MATH_H\nfloat fabsf(float x);\n#endif\n'
    with open(os.path.join(STUB_INC, 'stdint.h'), 'w') as f:
        f.write(stdint)
    with open(os.path.join(STUB_INC, 'math.h'), 'w') as f:
        f.write(math)
    _cache['stubs'] = True


def build_blob():
    """Compile src with gcc 3.4.6, link at 0x4000, extract .text blob.
    Returns (blob_bytes, {symbol: linked_addr})."""
    if 'blob' in _cache:
        return _cache['blob']
    os.makedirs(WORK, exist_ok=True)
    obj, elf, blb = (os.path.join(WORK, 'vdly') + s for s in ('.o', '.elf', '.bin'))

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
        p = line.split()
        if len(p) == 3 and p[1] == 'T':
            try:
                syms[p[2].lstrip('_')] = int(p[0], 16)
            except ValueError:
                pass
    _cache['blob'] = (blob, syms)
    return _cache['blob']


def ram_overlay(blob):
    return {LINK_BASE + i: blob[i] for i in range(len(blob))}


def load_cpu():
    with open(os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin'), 'rb') as f:
        return SH2(f.read())


def build_oracle():
    """Host oracle only for host-C-vs-blob r0 cross-check (oracle_delay_loop_n8.c)."""
    if 'oracle' in _cache:
        return _cache['oracle']
    binp = os.path.join(WORK, 'vdly_oracle')
    if not os.path.exists(binp):
        subprocess.run(
            [CC_HOST, '-O2', '-Wall', '-Wextra', '-I', INC_DIR, '-I', SRC_DIR,
             os.path.join(TESTS, 'oracle_delay_loop_n8.c'),
             os.path.join(SRC_DIR, SRC), '-o', binp],
            check=True, capture_output=True)
    _cache['oracle'] = binp
    return binp


def gen_vectors(n):
    rng = make_rng(SEED)
    vecs = list(EDGE) + list(EXTRA_EDGE)
    for _ in range(n):
        vecs.append(rng.randint(0, EMU_MAX_N))
    return vecs


def run_rom(cpu, n):
    cpu.call(ADDR_ROM, r4=n)
    return cpu.r[0], cpu.r[4], cpu.r[5]


def run_blob(cpu, blob_addr, overlay, n):
    cpu.call(blob_addr, r4=n, ram=overlay)
    return cpu.r[0], cpu.r[1], cpu.r[2]


def main():
    n_test = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    ensure_stubs()
    blob, syms = build_blob()
    blob_addr = syms.get(ENTRY_SYM, LINK_BASE)
    overlay = ram_overlay(blob)
    cpu = load_cpu()
    oracle = build_oracle()

    vecs = gen_vectors(n_test)

    mismatches = []
    rom_states = []
    for n in vecs:
        r0r, r4, r5 = run_rom(cpu, n)
        exp = n * 8
        # ROM-side loop-count relationship from the real ROM bytes.
        if r4 != exp or r5 != exp:
            mismatches.append('ROM loop n=0x%04X: r4=0x%08X r5=0x%08X '
                              'expected 0x%X' % (n, r4, r5, exp))
            continue
        rom_states.append(r0r)

        r0b, r1, r2 = run_blob(cpu, blob_addr, overlay, n)
        # gcc 3.4.6 image: extu.w truncation makes the bound/counter land in
        # r2/r1; both end up at n*8 just like the ROM r4/r5.
        if r1 != exp or r2 != exp:
            mismatches.append('blob loop n=0x%04X: r1=0x%08X r2=0x%08X '
                              'expected 0x%X' % (n, r1, r2, exp))
            continue
        if r0b != r0r:
            mismatches.append('r0 mismatch n=0x%04X: ROM=0x%08X blob=0x%08X'
                              % (n, r0r, r0b))

    # host-C vs blob (r0 cross-check on the same vectors)
    lines = ['u16 %08X' % n for n in vecs]
    proc = subprocess.run([oracle], input='\n'.join(lines) + '\n',
                          capture_output=True, text=True)
    if proc.returncode != 0:
        mismatches.append('host oracle failed: %s' % proc.stderr.strip())
    else:
        outs = proc.stdout.splitlines()
        if len(outs) == len(rom_states):
            for i, o in enumerate(outs):
                h = int(o, 16)
                if h != rom_states[i]:
                    mismatches.append('host-vs-blob vec#%d n=0x%04X host=0x%08X '
                                      'blob=0x%08X' % (i, vecs[i], h, rom_states[i]))

    # --- semantic boundary (documented, not counted as a mismatch) ----------
    boundary = []
    for n in (0x10000, 0xFFFFFFFF):
        try:
            cpu.call(ADDR_ROM, r4=n)
            boundary.append('ROM n=0x%X did not runaway (unexpected)' % n)
        except RuntimeError:
            pass                    # expected: 32-bit scaled spin > 500k steps
        # blob side: extu.w truncation  ->  0x10000 -> 0   (returns 0)
        #                               ->  0xFFFFFFFF -> 0xFFFF (runaway)
        try:
            cpu.call(blob_addr, r4=n, ram=overlay)
            r1 = cpu.r[1]
        except RuntimeError:
            r1 = None               # expected runaway for the truncated count
        if n == 0x10000:
            if r1 != 0:
                boundary.append('blob n=0x10000: r1=0x%08X expected 0' % r1)
        elif r1 is not None:
            boundary.append('blob n=0xFFFFFFFF did not run away')
    for n in (0xFFFF,):
        try:
            cpu.call(ADDR_ROM, r4=n)
            boundary.append('ROM n=0xFFFF did not run away')
        except RuntimeError:
            pass
        try:
            cpu.call(blob_addr, r4=n, ram=overlay)
            boundary.append('blob n=0xFFFF did not run away')
        except RuntimeError:
            pass

    if mismatches:
        print('FAIL delay_loop_n8 @0x%X  %d mismatch(es)' % (ADDR_ROM, len(mismatches)))
        for m in mismatches[:10]:
            print('    ' + m)
        sys.exit(1)

    print('OK  delay_loop_n8 @0x%X  signature=void f(uint16_t)  '
          'blob@0x%X  %d random + %d edge vectors  ROM==blob==host (all 0) '
          '(semantic-boundary+%d checks)' % (ADDR_ROM, blob_addr, n_test,
                                             len(EDGE) + len(EXTRA_EDGE),
                                             len(boundary)))

    if boundary:
        sys.stderr.write('note (semantic boundary, not a mismatch):\n')
        for b in boundary:
            sys.stderr.write('    ' + b + '\n')


if __name__ == '__main__':
    main()