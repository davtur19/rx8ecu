#!/usr/bin/env python3
"""
verify_shifts2.py — shift-family coverage audit + era-ROM validation (round 2).

Round 1 (verify_gcc346.py) already validated the 4 variable/fixed-count shift
primitives and the two complement-pack siblings:

    shift_left_logical    @0x4308   (r0/r1 -> r0)
    shift_right_arithmetic@0x43C8   (r0/r1 -> r0)
    shift_right_logical   @0x44E0   (r0/r1 -> r0)
    shift_right_8         @0x467A   (r0   -> r0)
    complement_shift_u16  @0x2430   (r4   -> r0)
    complement_shift_u32  @0x2440   (fr4.. -> r0)

This round audits the whole reconstructed/samples/src/ for any *other* shift /
rotate function and validates the ones that are pure and NOT yet covered.

AUDIT RESULT (per-function evidence below in AUDIT):
  * src/ contains NO additional bit-shift primitive beyond the 6 already in
    verify_gcc346.py: the four names that match `grep -iE 'rot'` are Wankel
    *rotor* engine functions (0x12BC8, 0x13C2C, 0x189EE, 0x18CC0) that
    manipulate rotor-sync state machines, not bit-rotation instructions.
  * The ROM symbol table (symbols/symbols_60E1D400_merged.csv) lists exactly
    one shift-family function that is pure and NOT yet covered:

        complement_shift_u8 @0x2420   (r4 -> r0, 8-bit value/complement pack)

    Disassembly of roms/stock/60E1D400.bin @0x2420:
        2420 extu.b r4,r3    ; val  = r4 & 0xFF
        2422 shll8  r3       ; val  = val << 8
        2424 not    r4,r2    ; comp = ~r4
        2426 extu.b r2,r2    ; comp = comp & 0xFF
        2428 mov    r3,r4
        242a add    r2,r4    ; r4 = val + comp   (== OR: disjoint bit fields)
        242c rts
        242e mov    r4,r0
    => r0 = ((val & 0xFF) << 8) | (~val & 0xFF)
    Pure: no jsr/bsr, no mova/global references (verified, see build below).

VALIDATION under test
  * C lift (this file embeds it and writes it to /tmp; src/ stays untouched):
        uint8_t -> (val<<8)|~val  [redundant-storage byte encoder]
  * compiled with the era-ROM recipe: /home/davide/gcc346-build/gcc/xgcc
    -m2e -O1 -fomit-frame-pointer, linked at 0x4000 with libgcc 3.4.6,
    .text extracted via objcopy, loaded into tools/sh2emu.py.
  * convention: r4 ABI (extu.b r4) -> r0 result, identical to the already
    covered complement_shift_u16; N >= 3000 with the full count-edge set
    {0,1,7,8,15,16,23,24,31,32,63,-1} plus 8-bit value edges + seeded random.

Read-only w.r.t. the repo (everything written goes to /tmp). Exit code is
non-zero iff any active function reports mismatch(es).

Usage:  python3 tests/verify_shifts2.py [N]   (default N per function)
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

# ---- era-ROM toolchain ------------------------------------------------------
XGCC = '/home/davide/gcc346-build/gcc/xgcc'
XGCC_B = '/home/davide/gcc346-build/gcc'
LD = '/usr/bin/sh-elf-ld'
OBJCOPY = '/usr/bin/sh-elf-objcopy'
NM = '/usr/bin/sh-elf-nm'
LIBGCC = os.path.join(XGCC_B, 'libgcc.a')   # pull ___ashlsi3 etc. if needed

STUB_INC = '/tmp/verify_gcc346/inc'         # existing era-ROM stub headers
WORK = '/tmp/verify_shifts2/work'           # objects / elfs / blobs
LINK_BASE = 0x4000                          # fixed link base

SRC_DIR = os.path.join(SAMPLES, 'src')
INC_DIR = os.path.join(SAMPLES, 'include')
ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')

# ============================================================================
# Audit: shift/rotate-like functions in reconstructed/samples/src/
# (name, ROM address, src file, status).
# ============================================================================
AUDIT = [
    # -- shift family, already covered by verify_gcc346.py (round 1) ------
    ('shift_left_logical',      0x4308, 'rx8_shift_left_logical.c',       'covered (verify_gcc346.py)'),
    ('shift_right_arithmetic',  0x43C8, 'rx8_shift_right_arithmetic.c',   'covered (verify_gcc346.py)'),
    ('shift_right_logical',     0x44E0, 'rx8_shift_right_logical.c',      'covered (verify_gcc346.py)'),
    ('shift_right_8',           0x467A, 'rx8_shift_right_8.c',            'covered (verify_gcc346.py)'),
    ('complement_shift_u16',    0x2430, 'rx8_complement_shift_u16.c',     'covered (verify_gcc346.py)'),
    ('complement_shift_u32',    0x2440, 'rx8_complement_shift_u32.c',     'covered (verify_gcc346.py)'),
    # -- 'rot' name matches: Wankel *rotor* engine functions, NOT bit-rotates
    ('calc_rotor_sync_idle_gate_b',   0x12BC8, 'rx8_calc_rotor_sync_idle_gate_b.c',  'excluded: rotor engine state machine'),
    ('calc_ignition_all_rotors_13c2c', 0x13C2C, 'rx8_calc_ignition_all_rotors_13c2c.c', 'excluded: rotor engine ignition calc'),
    ('rotor_sync_position_detector',   0x189EE, 'rx8_rotor_sync_position_detector.c',  'excluded: rotor engine state machine'),
    ('omp_rotor_overshoot_detector',   0x18CC0, 'rx8_omp_rotor_overshoot_detector.c',  'excluded: rotor engine state machine'),
    # -- the one pure shift-family function NOT covered anywhere -----------
    ('complement_shift_u8',     0x2420, '<embedded lift>',                'VALIDATED HERE (new)'),
]

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
# Function config — only the uncovered pure shift family function.
# kind 'r32': one 32-bit ABI argument (r4), result r0 (same as the covered
# complement_shift_u16; the ROM reads its input with `extu.b r4`).
# ============================================================================
FUNCS = {
    'complement_shift_u8': {
        'addr_rom': 0x2420, 'kind': 'r32',
        'entry_sym': 'rx8_complement_shift_u8', 'n_test': 4000, 'seed': 0x2420,
    },
}

# Embedded C lift (written to /tmp/work; src/ untouched).  Behaviourally
# identical to the ROM: `extu.b` masks to the low byte, `shll8` shifts it up,
# `not`+`extu.b` builds the masked complement, `add` == OR (disjoint bits).
_C_U8 = (
    '#include <stdint.h>\n'
    '/* 0x2420 — pack a byte with its ones complement: (val<<8)|~val */\n'
    'uint32_t rx8_complement_shift_u8(uint32_t val)\n'
    '{\n'
    '    uint32_t value = (uint32_t)(val & 0xFFu) << 8;\n'
    '    uint32_t comp  = (uint32_t)(~val) & 0xFFu;\n'
    '    return value | comp;\n'
    '}\n')


def ensure_stubs():
    os.makedirs(STUB_INC, exist_ok=True)
    p = os.path.join(STUB_INC, 'stdint.h')
    if not os.path.exists(p):
        with open(p, 'w') as f:
            f.write(_STDINT)


def build_blob(name):
    """Compile the embedded lift with gcc 3.4.6, link at 0x4000, extract .text.
    Returns (blob_bytes, {symbol: linked_absolute_addr})."""
    os.makedirs(WORK, exist_ok=True)
    cfg = FUNCS[name]
    base = os.path.join(WORK, name)
    srcf, obj, elf, blb = base + '.c', base + '.o', base + '.elf', base + '.bin'

    with open(srcf, 'w') as f:
        f.write(_C_U8)

    subprocess.run(
        [XGCC, '-B', XGCC_B, '-m2e', '-O1', '-fomit-frame-pointer',
         '-c', srcf, '-o', obj, '-I', STUB_INC, '-I', SRC_DIR, '-I', INC_DIR],
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
            syms[parts[2].lstrip('_')] = int(parts[0], 16)
    return blob, syms


def ram_overlay(blob):
    return {LINK_BASE + i: blob[i] for i in range(len(blob))}


# ============================================================================
# Vector generation (seeded, reproducible)
# ============================================================================
def gen_vectors(n):
    rng = make_rng(0x2420)
    # count-edge set {0,1,7,8,15,16,23,24,31,32,63,-1} used as raw words (the
    # ROM masks to 8 bits, so high bits are dropped), plus 8-bit value edges.
    edges = [0, 1, 7, 8, 15, 16, 23, 24, 31, 32, 63, 0xFFFFFFFF,   # cnt set
             0x7F, 0x80, 0xFF, 0x100, 0x7FFF, 0x8000, 0xFFFF,
             0x7FFFFFFF, 0x80000000, 0xABCDEF01, 0xDEADBEEF, 0xCAFEBABE]
    vecs = [{'r4': e, 'desc': 'a=0x%08X' % e} for e in edges]
    for _ in range(n):
        v = rng.getrandbits(32)
        vecs.append({'r4': v, 'desc': 'a=0x%08X' % v})
    return vecs


def call_int(cpu, addr, **kw):
    cpu.call(addr, **kw)
    return cpu.r[0] & 0xFFFFFFFF


# ============================================================================
# Per-function evaluation
# ============================================================================
def run_function(name):
    cfg = FUNCS[name]
    blob, syms = build_blob(name)
    base = ram_overlay(blob)
    cpu = load_cpu()
    vecs = gen_vectors(cfg['n_test'])
    t0 = time.time()

    entry = syms.get(cfg['entry_sym'], LINK_BASE)
    rom_res, blb_res = [], []
    for v in vecs:
        # ROM side: r4 ABI -> r0; blob side: same C compiled by gcc 3.4.6,
        # standard r4 ABI, driven with cpu.call() and the blob overlay.
        rom_res.append(call_int(cpu, cfg['addr_rom'], r4=v['r4']))
        blb_res.append(call_int(cpu, entry, r4=v['r4'], ram=dict(base)))

    mism = 0
    samples = []
    for i, (e, h) in enumerate(zip(rom_res, blb_res)):
        if e != h:
            mism += 1
            if len(samples) < 5:
                samples.append('vec#%d %s ROM=0x%08X blob=0x%08X'
                               % (i, vecs[i]['desc'], e, h))

    return {'name': name, 'n': len(vecs), 'mism': mism, 'samples': samples,
            'time': time.time() - t0}


def main():
    n_override = int(sys.argv[1]) if len(sys.argv) > 1 else None
    ensure_stubs()

    # ---- audit report -----------------------------------------------------
    print('AUDIT  shift/rotate functions in reconstructed/samples/src/:')
    for name, addr, src, status in AUDIT:
        print('  %-32s @0x%-6X  %-40s  %s'
              % (name, addr, src, status))

    # ---- purity spot-check of the ROM function under test -----------------
    obj = subprocess.run(
        ['sh-elf-objdump', '-D', '-b', 'binary', '-m', 'sh2e',
         '--start-address=0x2420', '--stop-address=0x2430', ROM],
        capture_output=True, text=True)
    calls = [ln for ln in obj.stdout.splitlines()
             if '\t' in ln and ('jsr' in ln or 'bsr' in ln or 'mova' in ln)]
    print('\nPURITY complement_shift_u8@0x2420: pure=%s'
          % ('no' if calls else 'yes'))
    for ln in calls:
        print('   ' + ln.strip())

    # ---- validation --------------------------------------------------------
    total = 0
    for name in FUNCS:
        if n_override:
            FUNCS[name]['n_test'] = n_override
        r = run_function(name)
        total += r['mism']
        status = 'OK  ' if r['mism'] == 0 else 'FAIL'
        print('\n%s %-20s @0x%-6X  n=%-5d  ROM-vs-blob=%-4d  %.2fs'
              % (status, r['name'], FUNCS[name]['addr_rom'], r['n'],
                 r['mism'], r['time']))
        for s in r['samples']:
            print('        ' + s)

    if total:
        print('\nverify_shifts2: %d mismatch(es) total — FAIL' % total)
        sys.exit(1)
    print('\nverify_shifts2: all new shift-family functions OK (0 mismatch)')


if __name__ == '__main__':
    main()
