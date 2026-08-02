#!/usr/bin/env python3
"""
verify_immo_exhaustive.py — exhaustive sweep of rx8_immo_seed_mixer @0x366B8.

The mixer (reconstructed/samples/src/rx8_immo_seed_mixer.c) is a pure
uint32 x uint32 -> uint32 function (EEPROM key word + rolling word).  This
harness closes the "ROM -> abstract C -> era-ROM toolchain (gcc 3.4.6) ->
SH-2E emulator" loop on a dense sub-domain with an EXHAUSTIVE first input:

    key_word      in [0, 0xFFFF] step 1   (all 2^16 low values)
    rolling_word  in a chosen seed set     (64 / 16 / 8 values, adaptive)

Pipeline (identical recipe to verify_gcc346.py):

  (a) compile samples/src/rx8_immo_seed_mixer.c with the era-ROM gcc 3.4.6
      `-m2e -O1 -fomit-frame-pointer` via /home/davide/gcc346-build/gcc/xgcc,
  (b) link at 0x4000 against libgcc 3.4.6, objcopy --only-section=.text,
  (c) patch the blob into a private copy of the ROM image at LINK_BASE and
      run BOTH the original ROM bytes at 0x366B8 and the blob on the very
      same SH-2E emulator over every (key_word, rolling_word) pair,
      comparing the r0 result.

Adaptive sizing: a 1000-pair timing probe is run first; the rolling-word
seed set is then 64, 16 or 8 values so that the whole sweep fits the
15-minute budget (65536 x 64 = ~4.2M pairs ~= 6-7 min on the reference box).

Distribution: the mixer's output is provably 24-bit (max 0xFFFFFF; the
byte-swap step drops byte 3), so result uniqueness is tracked in a 16 MiB
presence bitmap; range (min/max) and a 16-bucket histogram over the 24-bit
space are also reported.

The harness is read-only w.r.t. the repo: everything it writes goes to
/tmp, and the exit code is non-zero iff any mismatch is found.

Usage:  python3 verify_immo_exhaustive.py [N2]
        (N2 overrides the timing-probe seed-set choice)
"""
import os
import random
import subprocess
import sys
import time

TESTS = os.path.dirname(os.path.abspath(__file__))   # reconstructed/samples/tests
SAMPLES = os.path.dirname(TESTS)                      # reconstructed/samples
ROOT = os.path.dirname(os.path.dirname(SAMPLES))      # rx8ecu
sys.path.insert(0, TESTS)
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2  # noqa: E402
from common import load_cpu  # noqa: E402

# ---- era-ROM toolchain (same recipe as verify_gcc346.py) --------------------
XGCC = '/home/davide/gcc346-build/gcc/xgcc'
XGCC_B = '/home/davide/gcc346-build/gcc'
LD = '/usr/bin/sh-elf-ld'
OBJCOPY = '/usr/bin/sh-elf-objcopy'
NM = '/usr/bin/sh-elf-nm'
LIBGCC = os.path.join(XGCC_B, 'libgcc.a')   # 3.4.6 helpers (unused by the mixer)

STUB_INC = '/tmp/verify_immo_exhaustive/inc'        # stub headers (never committed)
WORK = '/tmp/verify_immo_exhaustive/work'           # objects / elfs / blobs
LINK_BASE = 0x4000                                  # fixed link base

SRC_DIR = os.path.join(SAMPLES, 'src')
INC_DIR = os.path.join(SAMPLES, 'include')

ROM_ADDR = 0x366B8                                  # rx8_immo_seed_mixer in the ROM
ENTRY_SYM = 'rx8_immo_seed_mixer'

# ---- sweep geometry ----------------------------------------------------------
N1 = 1 << 16                     # exhaustive first input: all 0..0xFFFF
SEED_SPECIFIC = [0x00000000, 0x00000001, 0x00000002, 0x00000003,
                 0x00001234, 0x0000FFFF, 0xDEADBEEF]       # low bytes 00 01 02 03 34 FF EF
TIME_BUDGET_S = 15 * 60
PROBE_N = 1000

# ============================================================================
# Stub headers / linker script (written once to /tmp)
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


def ensure_stubs():
    os.makedirs(STUB_INC, exist_ok=True)
    for name, body in (('stdint.h', _STDINT), ('math.h', _MATH)):
        p = os.path.join(STUB_INC, name)
        if not os.path.exists(p):
            with open(p, 'w') as f:
                f.write(body)


def build_blob():
    """Compile the mixer C with gcc 3.4.6, link at 0x4000, extract .text."""
    os.makedirs(WORK, exist_ok=True)
    base = os.path.join(WORK, 'immo_mixer')
    obj, elf, blb = base + '.o', base + '.elf', base + '.bin'

    subprocess.run(
        [XGCC, '-B', XGCC_B, '-m2e', '-O1', '-fomit-frame-pointer',
         '-c', os.path.join(SRC_DIR, 'rx8_immo_seed_mixer.c'), '-o', obj,
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
                and parts[2].lstrip('_') == ENTRY_SYM:
            entry = int(parts[0], 16)
            break
    return blob, entry


# ============================================================================
# Second-input seed set
# ============================================================================
def build_seed_set(n2):
    """n2 rolling-word seeds: the 7 specific values + dense fills.

    The mixer reads only rolling_word & 0xFF (byte rebuild step), so the
    effective second input is the low byte: dense fills are chosen with
    DISTINCT low bytes (shuffled deterministically) to maximize coverage of
    the effective 2^16 x 2^8 domain, while the upper 24 bits are varied to
    prove the ROM ignores them."""
    specific = list(SEED_SPECIFIC)
    used = {s & 0xFF for s in specific}
    free = [L for L in range(256) if L not in used]
    rng = random.Random(0x366B8)
    rng.shuffle(free)
    seeds = list(specific)
    for i, L in enumerate(free[:n2 - len(specific)]):
        hi = rng.getrandbits(24)                      # upper 24 bits vary too
        seeds.append(((hi ^ (i * 0x01010101)) & 0xFFFFFF) << 8 | L)
    assert len(seeds) == n2 and len({s & 0xFF for s in seeds}) == n2
    return seeds


def pick_n2(per_pair):
    """Choose the seed-set size so 65536*n2 fits the time budget."""
    for cand in (64, 16, 8):
        if per_pair * N1 * cand <= TIME_BUDGET_S:
            return cand
    return 8


# ============================================================================
# Sweep
# ============================================================================
def run_sweep(cpu_rom, cpu_blob, entry, n2):
    seeds = build_seed_set(n2)
    total = N1 * len(seeds)
    print('sweep: first input 0..0x%X (all %d low values) x %d rolling seeds'
          % (N1 - 1, N1, len(seeds)))
    print('seeds (32-bit, low byte distinct): %s' % ' '.join('%08X' % s for s in seeds))

    seen = bytearray(1 << 24)                 # output is provably 24-bit
    hist = [0] * 16                           # 16 buckets over [0, 2^24)
    mn, mx = 0xFFFFFF, 0
    mismatches = []
    n_seen = 0
    t0 = time.perf_counter()

    call_rom = cpu_rom.call
    call_blob = cpu_blob.call
    for j, b in enumerate(seeds, 1):
        row_mis = 0
        for a in range(N1):
            er = call_rom(ROM_ADDR, r4=a, r5=b)
            eb = call_blob(entry, r4=a, r5=b)
            if er != eb:
                row_mis += 1
                if len(mismatches) < 5:
                    mismatches.append(
                        'a=0x%04X b=0x%08X ROM=0x%06X blob=0x%06X'
                        % (a, b, er & 0xFFFFFF, eb & 0xFFFFFF))
            if er < mn:
                mn = er
            if er > mx:
                mx = er
            if not seen[er]:
                seen[er] = 1
                n_seen += 1
            hist[er >> 20] += 1
        dt = time.perf_counter() - t0
        eta = dt / j * (len(seeds) - j)
        print('  [%3d/%d] b=0x%08X  mismatches this row=%d  '
              'unique so far=%d  elapsed=%6.1fs  eta=%6.1fs'
              % (j, len(seeds), b, row_mis, n_seen, dt, eta))

    dt = time.perf_counter() - t0
    return {
        'n1': N1, 'n2': len(seeds), 'total': total, 'time': dt,
        'mismatches': mismatches, 'unique': n_seen,
        'mn': mn, 'mx': mx, 'hist': hist,
        'distinct_lows': len({s & 0xFF for s in seeds}),
    }


def per_pair_probe(cpu_rom, cpu_blob, entry):
    """Time PROBE_N pairs (ROM + blob call each) to size the sweep."""
    call_rom = cpu_rom.call
    call_blob = cpu_blob.call
    t0 = time.perf_counter()
    for i in range(PROBE_N):
        call_rom(ROM_ADDR, r4=i & 0xFFFF, r5=0xDEADBEEF)
        call_blob(entry, r4=i & 0xFFFF, r5=0xDEADBEEF)
    dt = time.perf_counter() - t0
    per = dt / PROBE_N
    print('probe: %d pairs in %.3fs -> %.1f us/pair (ROM+blob)'
          % (PROBE_N, dt, per * 1e6))
    return per


def main():
    n2_override = int(sys.argv[1]) if len(sys.argv) > 1 else None

    ensure_stubs()
    blob, entry = build_blob()
    print('blob: %d bytes, entry @0x%X (link base 0x%X)'
          % (len(blob), entry, LINK_BASE))

    # Two SH-2E instances: one over the stock ROM, one over a private ROM
    # copy with the blob patched in at LINK_BASE (both run the fast no-RAM
    # fetch path, so the sweep is ~2x faster than the ram-overlay route).
    cpu_rom = load_cpu()
    rom2 = bytearray(cpu_rom.rom)
    rom2[LINK_BASE:LINK_BASE + len(blob)] = blob
    cpu_blob = SH2(bytes(rom2))
    assert rom2[ROM_ADDR:ROM_ADDR + 4] != blob[:4], \
        'blob patch would overwrite the ROM function itself'

    # sanity: the 12 edge vectors of harness_seed_mixer.py must match
    edges = [(0, 0), (0xFFFFFFFF, 0xFFFFFFFF), (0xFFFFFFFF, 0),
             (0, 0xFFFFFFFF), (0x0000FF00, 0x000000FF),
             (0x00FF00FF, 0xFF00FF00), (0x0FE00000, 0), (0x001FC000, 0),
             (0x00100000, 0), (0xABCDEF01, 0x12345678),
             (0xDEADBEEF, 0xCAFEBABE), (0x6D7A64D0, 0x00000278)]
    bad = sum(1 for a, b in edges
              if cpu_rom.call(ROM_ADDR, r4=a, r5=b)
              != cpu_blob.call(entry, r4=a, r5=b))
    if bad:
        print('sanity: %d/%d edge mismatches — aborting' % (bad, len(edges)))
        sys.exit(1)
    print('sanity: %d edge vectors OK' % len(edges))

    per = per_pair_probe(cpu_rom, cpu_blob, entry)
    n2 = n2_override if n2_override else pick_n2(per)
    est = per * N1 * n2
    print('sizing: 65536 x %d pairs -> est %.0fs (budget %ds)%s'
          % (n2, est, TIME_BUDGET_S,
             '  [N2 overridden]' if n2_override else ''))
    if not n2_override and est > TIME_BUDGET_S:
        print('WARNING: estimate exceeds budget; continuing anyway')

    r = run_sweep(cpu_rom, cpu_blob, entry, n2)

    # ---- report ------------------------------------------------------------
    print()
    print('=' * 72)
    print('RESULT  rx8_immo_seed_mixer @0x%X  domain = %d x %d = %d pairs'
          % (ROM_ADDR, r['n1'], r['n2'], r['total']))
    print('effective domain: %d x %d (distinct rolling low bytes)'
          % (r['n1'], r['distinct_lows']))
    print('mismatches ROM-vs-blob : %d' % len(r['mismatches']))
    for m in r['mismatches']:
        print('    ' + m)
    print('distribution (ROM outputs, 24-bit space [0, 0x%X)):' % (1 << 24))
    print('  unique values : %d  (max possible %d)'
          % (r['unique'], r['total']))
    print('  range         : 0x%06X .. 0x%06X' % (r['mn'], r['mx']))
    print('  histogram     : ' + ' '.join('%7d' % h for h in r['hist']))
    print('                  ' + ' '.join('%5.1fM' % (i) for i in range(16)))
    print('  wall time     : %.1fs (%.1f us/pair)'
          % (r['time'], r['time'] / r['total'] * 1e6))

    if r['mismatches']:
        print('FAIL: %d mismatch(es)' % len(r['mismatches']))
        sys.exit(1)
    print('OK: exhaustive sub-domain equivalent (0 mismatch)')
    return r


if __name__ == '__main__':
    main()
