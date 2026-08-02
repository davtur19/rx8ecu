#!/usr/bin/env python3
"""
verify_datalookup.py — rx8_data_lookup @0x2624, era-ROM toolchain validation.

Closes the "ROM -> abstract C -> era-ROM toolchain (gcc 3.4.6)" loop on the
*behavioural* plane for the 1-D axis-search leaf dataLookup.

  ROM leaf  : roms/stock/60E1D400.bin @0x2624
  Source    : reconstructed/samples/src/rx8_data_lookup.c
  Lift      : c/2DLookup.c  (dataLookup @ 0x2624)

CALLING CONVENTION (leaf-level, NOT the r4-r7/fr4-fr6 C ABI — deduced from the
disassembly window 0x2624):

    in:  r0  = count n (number of f32 breakpoints)
         r1  = axis pointer (ascending f32 breakpoints)
         fr0 = x  (input value searched)
    out: r0  = breakpoint index i
         fr0 = interpolation fraction t = (x-axis[i])/(axis[i+1]-axis[i])

The gcc-3.4.6 blob of the same C uses the standard ABI instead:

    in:  r4 = n, r5 = axis, fr4 = x, r6 = &out_index, r7 = &out_t
    out: *r6 = i, *r7 = t   (results written through the out pointers)

so the two sides are driven differently and compared on (r0, fr0-bits) vs
(*r6, *r7-bits) — the gcc-ABI <-> ROM mapping:

    r0/n  <-> r4      r1/axis <-> r5      fr0/x <-> fr4

Method (mirrors verify_gcc346.py):

  (a) compiles the reconstructed source with the era-ROM recipe
      `-m2e -O1 -fomit-frame-pointer` via /home/davide/gcc346-build/gcc/xgcc,
  (b) links at a fixed base 0x4000 (libgcc 3.4.6 is pulled in but unused —
      the interpolation is pure FPU: fsub/fsub/fdiv, no div/shift helpers),
  (c) objcopy --only-section=.text extracts a self-contained code blob,
  (d) loads the blob into the same SH-2E emulator (tools/sh2emu.py) through
      the sparse `ram` overlay, staging the f32 axis array at 0x2000,
  (e) generates seeded vectors: axis lengths 1..8 (loop guard: a backward
      linear search of ≤ n cells, so every call is ≤ a few hundred steps),
      x values on/around every breakpoint, interval midpoints, out of range
      on both sides, +/-inf and NaN (fcmp/gt compares false -> clamp high),
  (f) runs BOTH the real ROM bytes @0x2624 and the blob @0x4000 on the very
      same vectors (ROM via the r0/r1/fr0 call_leaf driver, blob via
      cpu.call(r4/r5/fr4/r6/r7)) and compares (index, t-bits), plus a host
      oracle (system cc) as a third reference.

The harness is read-only w.r.t. the repo: everything it writes goes to /tmp,
and the exit code is non-zero iff any check reports mismatch(es).

Usage:  python3 tests/verify_datalookup.py [N]
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

from sh2emu import SH2, MASK, ts, f2bits  # noqa: E402
from common import ROM_PATH, make_rng  # noqa: E402

# ---- era-ROM toolchain ------------------------------------------------------
XGCC = '/home/davide/gcc346-build/gcc/xgcc'
XGCC_B = '/home/davide/gcc346-build/gcc'
LD = '/usr/bin/sh-elf-ld'
OBJCOPY = '/usr/bin/sh-elf-objcopy'
NM = '/usr/bin/sh-elf-nm'
CC_HOST = os.environ.get('CC', 'cc')
LIBGCC = os.path.join(XGCC_B, 'libgcc.a')   # linked but unused (pure-FPU leaf)

STUB_INC = '/tmp/verify_gcc346/inc'          # stub headers (created by
                                             # verify_gcc346.py, reused here)
WORK = '/tmp/verify_datalookup/work'
LINK_BASE = 0x4000                           # fixed link base (blob load addr)

SRC_DIR = os.path.join(SAMPLES, 'src')
INC_DIR = os.path.join(SAMPLES, 'include')

# ---- ROM leaf geometry ------------------------------------------------------
ADDR_ROM = 0x2624
AXIS_BASE = 0x2000            # sparse-RAM address backing the axis array
OUT_INDEX = 0x3000            # blob out_index pointer target (sparse RAM)
OUT_T = 0x3004                # blob out_t pointer target (sparse RAM)

_LINKER = (
    'OUTPUT_FORMAT(elf32-sh)\n'
    'MEMORY { RAM (rx) : ORIGIN = 0x%X, LENGTH = 0x1000 }\n'
    'SECTIONS {\n'
    '  .text : { *(.text) *(.text.*) *(.rodata) *(.rodata.*) *(.rdata) } > RAM\n'
    '  /DISCARD/ : { *(.comment) *(.note*) *(.symtab) *(.strtab) '
    '*(.shstrtab) *(.debug*) }\n}\n' % LINK_BASE)


class SH2E(SH2):
    """SH2 + call_leaf(): inject arbitrary initial registers (r0-r15, fr0-fr15),
    needed for dataLookup's r0/r1/fr0 -> r0/fr0 leaf-level convention (it is not
    entered via r4-r7).  Line-for-line copy of SH2.call()'s body, as in
    harness_data_lookup.py / c/tests/test_dataLookup.py."""

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
        self.gbr = 0; self.fpul = 0; self.fpscr = 0
        self.pc = entry & MASK
        steps = 0
        while True:
            if self.pc == self.SENT:
                return self.r[0] & MASK
            steps += 1
            if steps > 500000:
                raise RuntimeError('runaway at 0x%X' % self.pc)
            op = self.rd(self.pc, 2)
            br = self._delayed(op)
            if br is None:
                self._exec(op, self.pc)
                self.pc = (self.pc + 2) & MASK
            else:
                target, take = br
                self._exec(self.rd(self.pc + 2, 2), self.pc + 2)
                self.pc = target if take else (self.pc + 4) & MASK


# ============================================================================
# Toolchain build
# ============================================================================
_blob_cache = {}


def build_blob():
    """Compile rx8_data_lookup.c with gcc 3.4.6, link at 0x4000, extract .text.

    Returns (blob_bytes, {'rx8_data_lookup': linked_absolute_addr})."""
    os.makedirs(WORK, exist_ok=True)
    obj = os.path.join(WORK, 'datalookup.o')
    elf = os.path.join(WORK, 'datalookup.elf')
    blb = os.path.join(WORK, 'datalookup.bin')

    subprocess.run(
        [XGCC, '-B', XGCC_B, '-m2e', '-O1', '-fomit-frame-pointer',
         '-c', os.path.join(SRC_DIR, 'rx8_data_lookup.c'), '-o', obj,
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


def ram_overlay(blob):
    return {LINK_BASE + i: blob[i] for i in range(len(blob))}


def build_oracle():
    """Compile oracle_data_lookup.c + rx8_data_lookup.c into a host binary."""
    os.makedirs(WORK, exist_ok=True)
    binp = os.path.join(WORK, 'oracle_datalookup')
    subprocess.run(
        [CC_HOST, '-O2', '-Wall', '-Wextra',
         '-I', INC_DIR, '-I', SRC_DIR,
         os.path.join(TESTS, 'oracle_data_lookup.c'),
         os.path.join(SRC_DIR, 'rx8_data_lookup.c'), '-lm', '-o', binp],
        check=True, capture_output=True)
    return binp


# ============================================================================
# Vector generation  (seeded, reproducible)
# ============================================================================
def gen_edges(axis):
    """Edge x values: every breakpoint, +/-0.001 either side, interval
    midpoints, far out-of-range both sides, +/-inf, NaN (clamps high because
    fcmp/gt compares false), and plain 0.0."""
    n = len(axis)
    v = []
    for i, a in enumerate(axis):
        v.append(a)                              # exact breakpoint
        v.append(ts(a - 0.001))
        v.append(ts(a + 0.001))
        if i + 1 < n:
            v.append(ts((a + axis[i + 1]) * 0.5))    # interval midpoint
    v.append(ts(axis[0] - 100.0))                # far below axis[0]
    v.append(ts(axis[-1] + 100.0))               # far above axis[-1]
    v.append(float('-inf'))                      # clamps low
    v.append(float('inf'))                       # clamps high
    v.append(float('nan'))                       # clamps high (fcmp/gt false)
    v.append(0.0)
    return v


def rand_axis(rng, n):
    """Strictly-ascending f32 axis of length n (cumulative random gaps, so no
    duplicate breakpoints).  n in 1..8 keeps the linear search ≤ 8 cells."""
    a = ts(rng.uniform(-500.0, 500.0))
    axis = [a]
    for _ in range(1, n):
        a = ts(a + rng.uniform(1.0, 500.0))
        axis.append(a)
    return axis


def gen_vectors(n_edge_axes=2, n_rand_axes=18, n_rand_x=40, seed=0x2624):
    """Deterministic vector list: [(axis, x), ...].  Axis lengths cover the
    guard-relevant 1..8 range (n==1 fast path, n==2 clamp-low boundary)."""
    rng = make_rng(seed)
    axes = [[37.5], [-5.0, 100.0]]               # synthetic extremes
    for _ in range(n_rand_axes):
        axes.append(rand_axis(rng, rng.randint(2, 8)))

    vecs = []
    for axis in axes:
        for x in gen_edges(axis):
            vecs.append((axis, x))
        lo = min(axis[0], 0.0) - 100.0
        hi = axis[-1] + 100.0
        for _ in range(n_rand_x):
            vecs.append((axis, ts(rng.uniform(lo, hi))))
    return vecs


# ============================================================================
# Evaluation
# ============================================================================
def seed_axis(axis):
    """Sparse-RAM overlay of the f32 axis array at AXIS_BASE (big-endian)."""
    ram = {}
    for i, a in enumerate(axis):
        b = struct.pack('>f', a)
        for j in range(4):
            ram[AXIS_BASE + 4 * i + j] = b[j]
    return ram


def rd32(cpu, a):
    return ((cpu.ram.get(a, 0) << 24) | (cpu.ram.get(a + 1, 0) << 16)
            | (cpu.ram.get(a + 2, 0) << 8) | cpu.ram.get(a + 3, 0)) & MASK


def main():
    n_override = int(sys.argv[1]) if len(sys.argv) > 1 else None
    blob, syms = build_blob()
    entry = syms.get('rx8_data_lookup', LINK_BASE)
    base = ram_overlay(blob)
    oracle = build_oracle()

    vecs = gen_vectors()
    if n_override:
        vecs = vecs[:n_override]

    with open(ROM_PATH, 'rb') as f:
        cpu = SH2E(f.read())

    rom_res, blb_res = [], []
    t0 = time.time()
    for axis, x in vecs:
        ram = seed_axis(axis)

        # ROM side: r0=n, r1=axis, fr0=x -> r0=index, fr0=t
        cpu.call_leaf(ADDR_ROM, regs={0: len(axis), 1: AXIS_BASE},
                      fr={0: x}, ram=dict(ram))
        rom_res.append((cpu.r[0] & MASK, f2bits(cpu.fr[0])))

        # blob side: r4=n, r5=axis, fr4=x, r6=&out_index, r7=&out_t
        m = dict(base); m.update(ram)
        cpu.call(entry, r4=len(axis), r5=AXIS_BASE, fr={4: x},
                 r6=OUT_INDEX, r7=OUT_T, ram=m)
        blb_res.append((rd32(cpu, OUT_INDEX), rd32(cpu, OUT_T)))

    # (a) ROM vs blob
    rb = 0
    samples = []
    for i, (e, h) in enumerate(zip(rom_res, blb_res)):
        if e != h:
            rb += 1
            if len(samples) < 5:
                samples.append('vec#%d n=%d x=%r axis=%s ROM=(%d,0x%08X) '
                               'blob=(%d,0x%08X)'
                               % (i, len(vecs[i][0]), vecs[i][1], vecs[i][0],
                                  e[0], e[1], h[0], h[1]))

    # (b) host oracle vs blob (third reference: system-cc C, same semantics)
    ob = 0
    lines = ['dl %X %08X %s'
             % (len(axis), f2bits(x),
                ' '.join('%08X' % f2bits(a) for a in axis))
             for axis, x in vecs]
    proc = subprocess.run([oracle], input='\n'.join(lines) + '\n',
                          capture_output=True, text=True)
    if proc.returncode != 0:
        print('    (host oracle failed: %s)' % proc.stderr.strip())
    else:
        outs = [tuple(int(t, 16) for t in ln.split())
                for ln in proc.stdout.splitlines()]
        if len(outs) == len(blb_res):
            for i, (h, o) in enumerate(zip(blb_res, outs)):
                if h != o:
                    ob += 1
                    if ob == 1:
                        samples.append('oracle-vs-blob: blob=(%d,0x%08X) '
                                       'host=(%d,0x%08X)' % (h[0], h[1], o[0], o[1]))
        else:
            print('    (host oracle output count mismatch: %d vs %d)'
                  % (len(outs), len(blb_res)))

    dt = time.time() - t0
    status = 'OK  ' if (rb == 0 and not ob) else 'FAIL'
    print('%s dataLookup     @0x%-6X  n=%-5d  ROM-vs-blob=%-4d  '
          'oracle-vs-blob=%-4s  %.2fs'
          % (status, ADDR_ROM, len(vecs), rb,
             ob if ob is not None else '-', dt))
    for s in samples:
        print('        ' + s)

    if rb or ob:
        print('\nverify_datalookup: %d mismatch(es) total — FAIL' % (rb + ob))
        sys.exit(1)
    print('\nverify_datalookup: rx8_data_lookup @0x2624 OK (0 mismatch)')


if __name__ == '__main__':
    main()
