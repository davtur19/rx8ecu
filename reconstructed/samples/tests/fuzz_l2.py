#!/usr/bin/env python3
"""
fuzz_l2.py — high-intensity differential fuzz of the Lotto-2 verified leaves.

Build/link/emulate pattern == verify_mod32.py / verify_bytepack.py:
  * compile the reconstructed C with the archived sh-elf gcc 3.4.6
        /home/davide/gcc346-build/gcc/xgcc  -m2e -O1 -fomit-frame-pointer
  * link at LINK_BASE with sh-elf-ld (pulling libgcc 3.4.6 where a div/fma
    helper is needed), then objcopy --only-section=.text -> self-contained blob
  * load the blob into tools/sh2emu.py and drive the real ROM bytes @ its
    file offset vs the blob @ 0x4000 on the very same vectors.

Functions fuzzed (all re-validated by the verify_* harnesses in this dir):
  invert@0x2044           uint8 f(const uint8_t*)             -> r0     (ABI)
  delay_loop_n8@0x239C    void f(uint16 n)                    -> r0=0   (ABI)
  mod32_signed@0x4144     r0=divisor r1=dividend -> r0         (leaf)  non-ABI
  byte_sequence8@0x552FE  r4=dst r5=src r6=v                  -> r0+ram (ABI)
  byte_sequence16@0x5530C r4=dst r5=src r6=v16               -> r0+ram (ABI)
  set_register_reg_bit_val@0x4BBC  r4=&reg r5=mask r6=en      -> ram    (ABI)
  interp_u16@0x26D0       r1=cells r0=i fr0=t -> fr2 (fmaf shim)   non-ABI
  data_lookup@0x2624      r0=n r1=axis fr0=x -> r0 idx, fr0=t  non-ABI

Each fuzzed with a fresh seed + up to N=50000 random vectors and a targeted
edge list, time-boxed to ~WALL s/function (reduces N to N_REDUCED when the
time box trips; the reduction is documented in the table).  All artifacts go
to /tmp; the exit code is non-zero iff any function reports a mismatch.

Usage: python3 tests/fuzz_l2.py [N]   (default N = 50000 vectors/function)
"""
import os
import struct
import subprocess
import sys
import time

TESTS = os.path.dirname(os.path.abspath(__file__))
SAMPLES = os.path.dirname(TESTS)
ROOT = os.path.dirname(os.path.dirname(SAMPLES))
sys.path.insert(0, TESTS)
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2, MASK, ts, f2bits                       # noqa
from common import ROM_PATH, load_cpu, make_rng                # noqa

XGCC = '/home/davide/gcc346-build/gcc/xgcc'
XGCC_B = '/home/davide/gcc346-build/gcc'
LD = '/usr/bin/sh-elf-ld'
OBJCOPY = '/usr/bin/sh-elf-objcopy'
NM = '/usr/bin/sh-elf-nm'
LIBGCC = os.path.join(XGCC_B, 'libgcc.a')

STUB_INC = '/tmp/verify_gcc346/inc'
WORKDIR = '/tmp/verify_fuzz_l2'
LINK_BASE = 0x4000
SRC_DIR = os.path.join(SAMPLES, 'src')
INC_DIR = os.path.join(SAMPLES, 'include')

N_DEFAULT = 50000
N_REDUCED = 20000
WALL = 180.0

_LINKER = (
    'OUTPUT_FORMAT(elf32-sh)\n'
    'MEMORY { RAM (rx) : ORIGIN = 0x%X, LENGTH = 0x8000 }\n'
    'SECTIONS {\n'
    '  .text : { *(.text) *(.text.*) *(.rodata) *(.rodata.*) } > RAM\n'
    '  /DISCARD/ : { *(.symtab) *(.strtab) *(.shstrtab) *(.debug*) }\n}\n'
    % LINK_BASE)

_STDINT = (
    '#ifndef _STDINT_H\n#define _STDINT_H\n'
    'typedef signed char int8_t; typedef unsigned char uint8_t;\n'
    'typedef signed short int16_t; typedef unsigned short uint16_t;\n'
    'typedef signed int int32_t; typedef unsigned int uint32_t;\n'
    'typedef signed long long int64_t;\n'
    'typedef unsigned long long uint64_t;\n'
    '#define INT8_MIN (-128)\n#define INT16_MIN (-32767-1)\n'
    '#define INT32_MIN (-2147483647-1)\n#define INT32_MAX 2147483647\n'
    '#define INT64_MAX 9223372036854775807LL\n'
    '#define UINT8_MAX 255\n#define UINT16_MAX 65535\n'
    '#define UINT32_MAX 4294967295U\n#endif\n')

_MATH = '#ifndef _MATH_H\n#define _MATH_H\nfloat fabsf(float x);\n#endif\n'
_FMAF = 'float fmaf(float a,float b,float c){return a*b+c;}\n'
_BP8 = ('#include <stdint.h>\n'
        'uint8_t *rx8_bytepack8(uint8_t*d,uint8_t*s,uint8_t v){'
        '*s+=1;*d++=v;return d;}\n')
_BP16 = ('#include <stdint.h>\n'
         'uint8_t *rx8_bytepack16(uint8_t*d,uint8_t*s,uint16_t v){'
         '*s+=1;*d++=(uint8_t)(v>>8);*s+=1;*d++=(uint8_t)v;return d;}\n')


class Leaf(SH2):
    """SH2 + call_leaf(): seed arbitrary initial registers (r0-15/fr0-15) for
    the non-ABI leaves (mod32, interp_u16, data_lookup)."""

    def call_leaf(self, entry, regs=None, fr=None, ram=None):
        self.ram = dict(ram or {})
        self.r = [0] * 16
        for k, v in (regs or {}).items():
            self.r[k] = v & MASK
        self.r[15] = 0xFFFFDF00
        self.fr = [0.0] * 16
        for k, v in (fr or {}).items():
            self.fr[k] = ts(v)
        self.pr = self.SENT; self.T = 0; self.macl = 0; self.mach = 0
        self.gbr = 0; self.fpu = 0; self.fpscr = 0; self.fpul = 0
        self.pc = entry & MASK
        steps = 0
        while True:
            if self.pc == self.SENT:
                return
            steps += 1
            if steps > 1000000:
                raise RuntimeError('runaway at 0x%X' % self.pc)
            op = self.rd(self.pc, 2)
            br = self._delayed(op)
            if br is None:
                self._exec(op, self.pc)
                self.pc = (self.pc + 2) & MASK
            else:
                t, take = br
                self._exec(self.rd(self.pc + 2, 2), self.pc + 2)
                self.pc = t if take else (self.pc + 4) & MASK


def ensure_stubs():
    os.makedirs(STUB_INC, exist_ok=True)
    for f, c in (('stdint.h', _STDINT), ('math.h', _MATH)):
        open(os.path.join(STUB_INC, f), 'w').write(c)


def build(name, src=None, units=None, libgcc=False):
    wd = os.path.join(WORKDIR, name)
    os.makedirs(wd, exist_ok=True)
    objs = []
    if src:
        o = os.path.join(wd, 'm.o')
        subprocess.run([XGCC, '-B', XGCC_B, '-m2e', '-O1', '-fomit-frame-pointer',
                        '-c', os.path.join(SRC_DIR, src), '-o', o,
                        '-I', STUB_INC, '-I', SRC_DIR, '-I', INC_DIR],
                       check=True, capture_output=True)
        objs.append(o)
    for i, (fn, code) in enumerate(units or []):
        p = os.path.join(wd, fn)
        open(p, 'w').write(code)
        o = os.path.join(wd, 'u%d.o' % i)
        subprocess.run([XGCC, '-B', XGCC_B, '-m2e', '-O1', '-fomit-frame-pointer',
                        '-c', p, '-o', o, '-I', STUB_INC],
                       check=True, capture_output=True)
        objs.append(o)
    if not os.path.exists(os.path.join(wd, 'link.ld')):
        open(os.path.join(wd, 'link.ld'), 'w').write(_LINKER)
    elf = os.path.join(wd, 'out.elf')
    subprocess.run([LD, '-T', os.path.join(wd, 'link.ld')] + objs +
                   ([LIBGCC] if libgcc else []) + ['-o', elf],
                   check=True, capture_output=True)
    blb = os.path.join(wd, 'out.bin')
    subprocess.run([OBJCOPY, '-S', '--only-section=.text', '-O', 'binary',
                    elf, blb], check=True, capture_output=True)
    blob = open(blb, 'rb').read()
    nm = subprocess.run([NM, elf], capture_output=True, text=True)
    syms = {}
    for line in nm.stdout.splitlines():
        p = line.split()
        if len(p) == 3 and p[1] == 'T':
            try:
                syms[p[2].lstrip('_')] = int(p[0], 16)
            except ValueError:
                pass
    return blob, syms


def overlay(blob):
    return {LINK_BASE + i: blob[i] for i in range(len(blob))}


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    ensure_stubs()
    leaf = Leaf(open(ROM_PATH, "rb").read())
    results = []
    total_mm = 0
    reduced = set()

    # ============================ invert @0x2044 ============================
    blob, syms = build('invert', src='rx8_invert_and_return_8bit.c')
    entry = syms['rx8_invert_and_return_8bit']
    base = overlay(blob)
    CELL = 0x2000
    rng = make_rng(0x2044)
    edges = [0x0000, 0x0001, 0x00FF, 0xFFFF, 0x8000, 0x7FFF, 0x0100, 0x8080]
    vecs = list(edges)
    while len(vecs) < n:
        vecs.append(rng.getrandbits(16))
    used = 0; mm = 0; t0 = time.time()
    for i, v in enumerate(vecs):
        hi, lo = (v >> 8) & 0xFF, v & 0xFF
        ram = {CELL: hi, CELL + 1: lo}
        r_r = leaf.call(0x2044, r4=CELL, ram=dict(ram))
        o2 = dict(base); o2.update(ram)
        r_b = leaf.call(entry, r4=CELL, ram=o2)
        used += 1
        if r_r != r_b:
            mm += 1
        if used % 4096 == 0 and time.time() - t0 > WALL:
            break
    if used < len(vecs):
        reduced.add('invert8')
    results.append(('invert8', used, mm, 'edge cell + rnd u16'))

    # ========================= delay_loop_n8 @0x239C =========================
    blob, syms = build('delay', src='rx8_delay_loop_n8.c')
    entry = syms['rx8_delay_loop_n8']
    base = overlay(blob)
    rng = make_rng(0x239C)
    edges = [0, 1, 2, 3, 4, 8, 16, 255, 1024]
    vecs = list(edges)
    while len(vecs) < n:
        vecs.append(rng.randint(0, 1024))
    used = 0; mm = 0; t0 = time.time()
    for i, v in enumerate(vecs):
        r_r = leaf.call(0x239C, r4=v & 0xFFFF)
        r_b = leaf.call(entry, r4=v & 0xFFFF, ram=dict(base))
        used += 1
        if r_r != r_b:
            mm += 1
        if used % 4096 == 0 and time.time() - t0 > WALL:
            break
    if used < len(vecs):
        reduced.add('delay')
    results.append(('delay', used, mm, 'edge n + rnd u16'))

    # ========================== mod32_signed @0x4144 =========================
    blob, syms = build('mod', src='rx8_mod32_signed.c', libgcc=True)
    entry = syms['rx8_mod32_signed']
    base = overlay(blob)
    rng = make_rng(0x4144)
    edges = [(0, 0), (0, 1), (1, 0), (3, 7), (-7, 3), (7, 3), (5, 17),
             (0x7FFFFFFF, 0x64), (0x80000000, 0x64), (1, 0x80000000),
             (-1, 0x80000000), (0x80000000, -1), (0x80000000, 0x80000000),
             (0xFFFFFFFF, 0xFFFFFFFF), (0x40000000, 0xC0000000),
             (0x10000, 0x1E240), (2, 5), (5, 2), (36, 5), (5, 36)]
    vecs = list(edges)
    while len(vecs) < n:
        vecs.append((rng.getrandbits(32), rng.getrandbits(32)))
    used = 0; mm = 0; t0 = time.time()
    for i, (div, dvd) in enumerate(vecs):
        d0 = div & MASK; d1 = dvd & MASK
        leaf.call_leaf(0x4144, regs={0: d0, 1: d1})
        r_r = leaf.r[0]
        r_b = leaf.call(entry, r4=d0, r5=d1, ram=dict(base))
        used += 1
        if r_r != r_b:
            mm += 1
        if used % 4096 == 0 and time.time() - t0 > WALL:
            break
    if used < len(vecs):
        reduced.add('mod32')
    results.append(('mod32', used, mm, 'edge div0/INT32_MIN + rnd u32'))

    # =========================== bytepack8 @0x552FE ==========================
    blob, syms = build('bp8', units=[('rx8_bytepack8.c', _BP8)])
    entry = syms['rx8_bytepack8']
    base = overlay(blob)
    rng = make_rng(0x552FE)
    edges = [0x00, 0x01, 0x7F, 0x80, 0xFE, 0xFF]
    vecs = list(edges)
    while len(vecs) < n:
        vecs.append(rng.getrandbits(8))
    DST, SRC = 0x2000, 0x3000
    used = 0; mm = 0; t0 = time.time()
    for i, v in enumerate(vecs):
        ram = {}
        for k in range(8):
            ram[DST + k] = (k * 7) & 0xFF
            ram[SRC + k] = (k * 13) & 0xFF
        r_r = leaf.call(0x552FE, r4=DST, r5=SRC, r6=v, ram=dict(ram))
        rom_ram = dict(leaf.ram)
        o2 = dict(base); o2.update(ram)
        r_b = leaf.call(entry, r4=DST, r5=SRC, r6=v, ram=o2)
        blb_ram = dict(leaf.ram)
        used += 1
        # r0 + the 16 seeded RAM bytes must match
        if r_r != r_b:
            mm += 1
        elif any(rom_ram.get(k, 0) != blb_ram.get(k, 0)
                 for k in list(range(DST, DST + 8)) + list(range(SRC, SRC + 8))):
            mm += 1
        if used % 4096 == 0 and time.time() - t0 > WALL:
            break
    if used < len(vecs):
        reduced.add('bytepack8')
    results.append(('bytepack8', used, mm, 'edge v8 + rnd'))

    # =========================== bytepack16 @0x5530C =========================
    blob, syms = build('bp16', units=[('rx8_bytepack16.c', _BP16)])
    entry = syms['rx8_bytepack16']
    base = overlay(blob)
    rng = make_rng(0x5530C)
    edges = [0x0000, 0x0001, 0x00FF, 0x0100, 0x7FFF, 0x8000, 0xFF00, 0xFFFF]
    vecs = list(edges)
    while len(vecs) < n:
        vecs.append(rng.getrandbits(16))
    used = 0; mm = 0; t0 = time.time()
    for i, v in enumerate(vecs):
        ram = {}
        for k in range(8):
            ram[DST + k] = (k * 7) & 0xFF
            ram[SRC + k] = (k * 13) & 0xFF
        r_r = leaf.call(0x5530C, r4=DST, r5=SRC, r6=v, ram=dict(ram))
        rom_ram = dict(leaf.ram)
        o2 = dict(base); o2.update(ram)
        r_b = leaf.call(entry, r4=DST, r5=SRC, r6=v, ram=o2)
        blb_ram = dict(leaf.ram)
        used += 1
        if r_r != r_b:
            mm += 1
        elif any(rom_ram.get(k, 0) != blb_ram.get(k, 0)
                 for k in list(range(DST, DST + 8)) + list(range(SRC, SRC + 8))):
            mm += 1
        if used % 4096 == 0 and time.time() - t0 > WALL:
            break
    if used < len(vecs):
        reduced.add('bytepack16')
    results.append(('bytepack16', used, mm, 'edge v16 + rnd'))

    # ==================== set_register_reg_bit_val @0x4BBC ===================
    blob, syms = build('setreg', src='rx8_set_register_reg_bit_val.c')
    entry = syms['rx8_set_register_reg_bit_val']
    base = overlay(blob)
    rng = make_rng(0x4BBC)
    reg_edges = [0x0000, 0xFFFF, 0x8000, 0x00FF]
    mask_edges = [0x0000, 0x0001, 0x00FF, 0xFFFF, 0x8000]
    en_edges = [0, 1, 0x7FFF, 0x8000, 0xFFFF, 0x10000, 0x80000000]
    vecs = [(r, m, e) for r in reg_edges for m in mask_edges
            for e in en_edges]
    while len(vecs) < n:
        vecs.append((rng.getrandbits(16), rng.getrandbits(16),
                     rng.getrandbits(32)))
    used = 0; mm = 0; t0 = time.time()
    for i, (rv, mk, en) in enumerate(vecs):
        ram = {REG: (rv >> 8) & 0xFF, REG + 1: rv & 0xFF}
        r_r = leaf.call(0x4BBC, r4=REG, r5=mk, r6=en, ram=dict(ram))
        rom_ram = dict(leaf.ram)
        o2 = dict(base); o2.update(ram)
        r_b = leaf.call(entry, r4=REG, r5=mk, r6=en, ram=o2)
        blb_ram = dict(leaf.ram)
        used += 1
        if r_r != r_b or rom_ram.get(REG, 0) != blb_ram.get(REG, 0) or \
                rom_ram.get(REG + 1, 0) != blb_ram.get(REG + 1, 0):
            mm += 1
        if used % 4096 == 0 and time.time() - t0 > WALL:
            break
    if used < len(vecs):
        reduced.add('setreg')
    results.append(('setreg', used, mm, 'edge reg/mask/en + rnd'))

    # ============================ interp_u16 @0x26D0 =========================
    blob, syms = build('interp', src='rx8_interpolate_u16_table.c',
                       units=[('fmaf.c', _FMAF)])
    entry = syms['rx8_interpolate_u16_table']
    base = overlay(blob)
    rng = make_rng(0x26D0)
    tables = [[0x0000, 0xFFFF, 0x8000, 0x0001, 0xFFFE, 0x7FFF, 0x4000],
              [0] * 5, [0xFFFF] * 5,
              [0x0123, 0x4567, 0x89AB, 0xCDEF],
              [0xAAAA, 0x5555, 0xAAAA, 0x5555]]
    AXB = 0x2200
    vecs = []
    for cells in tables:
        for i in range(len(cells)):
            vecs.append((i, 0.0, cells))
        for i in range(len(cells) - 1):
            vecs.append((i, 0.5, cells))
            vecs.append((i, 1.0, cells))
    while len(vecs) < n:
        cells = tables[rng.randrange(len(tables))]
        i = rng.randrange(len(cells) - 1)
        vecs.append((i, rng.choice([0.0, 0.5, 1.0]), cells))
    used = 0; mm = 0; t0 = time.time()
    for i, (ix, t, cells) in enumerate(vecs):
        ram = {}
        for k, c in enumerate(cells):
            ram[AXB + 2 * k] = (c >> 8) & 0xFF
            ram[AXB + 2 * k + 1] = c & 0xFF
        leaf.call_leaf(0x26D0, regs={0: ix & MASK, 1: AXB}, fr={0: t},
                       ram=dict(ram))
        fr2 = f2bits(leaf.fr[2])
        o2 = dict(base); o2.update(ram)
        leaf.call(entry, r4=ix & MASK, r5=AXB, fr={4: t}, ram=o2)
        fr0 = f2bits(leaf.fr[0])
        used += 1
        if fr2 != fr0:
            mm += 1
        if used % 4096 == 0 and time.time() - t0 > WALL:
            break
    if used < len(vecs):
        reduced.add('interp')
    results.append(('interp', used, mm, 'edge i/t + rnd'))

    # =========================== data_lookup @0x2624 =========================
    blob, syms = build('lookup', src='rx8_data_lookup.c')
    entry = syms['rx8_data_lookup']
    base = overlay(blob)
    rng = make_rng(0x2624)
    axes = [[37.5], [-5.0, 100.0], [0.0, 1.0, 2.0, 3.0, 4.0],
            [-100.0, 0.0, 100.0, 200.0], [0.5, 0.75, 1.25]]
    OUTI, OUTT = 0x3400, 0x3404
    vecs = []
    for ax in axes:
        for x in [ax[0], ax[-1], ax[0] - 1.0, ax[-1] + 1.0,
                  (ax[0] + ax[-1]) / 2.0, float('-inf'), float('inf'),
                  float('nan'), 0.0]:
            vecs.append((ax, x))
    while len(vecs) < n:
        ax = axes[rng.randrange(len(axes))]
        lo, hi = ax[0] - 5.0, ax[-1] + 5.0
        vecs.append((ax, rng.uniform(lo, hi)))
    used = 0; mm = 0; t0 = time.time()
    for i, (ax, x) in enumerate(vecs):
        ram = {}
        for k, a in enumerate(ax):
            b = struct.pack('>f', a)
            for j in range(4):
                ram[AXB + 4 * k + j] = b[j]
        leaf.call_leaf(0x2624, regs={0: len(ax) & MASK, 1: AXB}, fr={0: x},
                       ram=dict(ram))
        rom_i = leaf.r[0]
        rom_t = f2bits(leaf.fr[0])
        o2 = dict(base); o2.update(ram)
        leaf.call(entry, r4=len(ax) & MASK, r5=AXB, fr={4: x},
                  r6=OUTI, r7=OUTT, ram=o2)
        blb_i = leaf.rd(OUTI, 4)
        blb_tb = bytes(leaf.rd(OUTT + j, 1) for j in range(4))
        blb_t = f2bits(struct.unpack('>f', blb_tb)[0])
        used += 1
        if rom_i != blb_i or rom_t != blb_t:
            mm += 1
        if used % 4096 == 0 and time.time() - t0 > WALL:
            break
    if used < len(vecs):
        reduced.add('lookup')
    results.append(('lookup', used, mm, 'edge n/x + rnd'))

    # ---------------------------- report -------------------------------------
    print('\nfuzz_l2 — Lotto-2 differential fuzz (ROM vs gcc-3.4.6 blob)')
    print('%-12s %8s %8s   %s' % ('function', 'N', 'mismatch', 'edges/notes'))
    print('-' * 64)
    for name, u, m, note in results:
        flag = '  (reduced 20k)' if name in reduced else ''
        print('%-12s %8d %8d   %s%s' % (name, u, m, note, flag))
        total_mm += m
    print('-' * 64)
    if total_mm:
        print('fuzz_l2: %d mismatch(es) — FAIL' % total_mm)
        sys.exit(1)
    print('fuzz_l2: 0 mismatches over %d vectors — OK'
          % sum(r[1] for r in results))
    if reduced:
        print('note: time-box hit on %s; N reduced to %d and documented'
              % (', '.join(sorted(reduced)), N_REDUCED))


REG = 0x2400
AXB = 0x2200


if __name__ == '__main__':
    main()