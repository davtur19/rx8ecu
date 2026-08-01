#!/usr/bin/env python3
"""
harness_idx_table.py — equivalence of the rx8_index_table family
@0x68780 (clear) / 0x6879C (step) / 0x687C8 (step2) / 0x687F4 (dec).

Restored source: samples/src/rx8_index_table.c
Verified lift   : c/idx_table_helpers_68780.c

These leaves act on RAM (RX8_IDX_TABLE_BASE = 0xFFFFD998, stride 0x46C), so
the equivalence check compares RAM side-effects, not the return value:

  - emulator side: seed the slot's three 16-bit words as big-endian bytes in
    the sparse `ram` overlay, call the ROM entry, read the words back;
  - host side: the oracle mmap()s the same pages, seeds the same numeric
    words, runs the restored C, reads them back.

Slots 0..8 (realistic firmware range) are compared host-vs-ROM.  The 32-bit
pointer-wrap behaviour for indices 9..255 is pinned emulator-only, because
the wrapped addresses land below mmap_min_addr on this host.

Usage:  python3 harness_idx_table.py [N]     (default N = 20000)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import build_oracle, load_cpu, make_rng, run_oracle  # noqa: E402

BASE = 0xFFFFD998
STRIDE = 0x46C
THRESH = 0x0464
N_DEFAULT = 20000

ENTRIES = {'clr': 0x0068780, 'step': 0x006879C,
           'step2': 0x00687C8, 'dec': 0x00687F4}


def paddr(idx):
    return (BASE + (idx & 0xFF) * STRIDE) & 0xFFFFFFFF


def seed_slot(idx, w0, w2, w4):
    a = paddr(idx)
    return {a: (w0 >> 8) & 0xFF, a + 1: w0 & 0xFF,
            a + 2: (w2 >> 8) & 0xFF, a + 3: w2 & 0xFF,
            a + 4: (w4 >> 8) & 0xFF, a + 5: w4 & 0xFF}


def read_slot(cpu, idx):
    a = paddr(idx)
    return tuple((cpu.ram.get(a + k, 0) << 8) | cpu.ram.get(a + k + 1, 0)
                 for k in (0, 2, 4))


def build_vectors(n):
    """Edge vectors (mirroring the existing emulator test) + random ones."""
    rng = make_rng(0x68780)
    vecs = []
    for w4 in (0x0000, 0x0001, 0x0463, 0x0464, 0x0465, 0x0466,
               0x7FFF, 0x8000, 0xFFFE, 0xFFFF):
        for idx in (0, 1, 8):
            vecs.append(('step', idx, 0x5555, 0xAAAA, w4))
            vecs.append(('step2', idx, 0x5555, 0xAAAA, w4))
    for w0 in (0x0000, 0x0001, 0x0002, 0x0464, 0x7FFF, 0x8000, 0xFFFE, 0xFFFF):
        for idx in (0, 1, 8):
            vecs.append(('dec', idx, w0, 0xAAAA, 0x5555))
    for idx in (0, 1, 8):
        vecs.append(('clr', idx, 0xAAAA, 0x5555, 0x1234))
    for _ in range(n):
        vecs.append((rng.choice(['clr', 'step', 'step2', 'dec']),
                     rng.randint(0, 8),
                     rng.getrandbits(16), rng.getrandbits(16),
                     rng.getrandbits(16)))
    return vecs


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    vecs = build_vectors(n)
    n_edges = len(vecs) - n

    # (a) ROM behaviour via the emulator (seeded RAM, side-effect compare).
    emu = []
    for op, idx, w0, w2, w4 in vecs:
        cpu.call(ENTRIES[op], r4=idx, ram=seed_slot(idx, w0, w2, w4))
        emu.append(read_slot(cpu, idx))

    # (b) host-C on the same vectors.
    lines = ['tbl %s %02X %04X %04X %04X' % (op, idx, w0, w2, w4)
             for op, idx, w0, w2, w4 in vecs]
    host = [tuple(int(x, 16) for x in out.split())
            for out in run_oracle(oracle, lines)]

    # (c) compare.
    mismatches = []
    for i, (v, e, h) in enumerate(zip(vecs, emu, host)):
        if e != h:
            op, idx, w0, w2, w4 = v
            mismatches.append('vec#%d op=%s idx=%d (%04X,%04X,%04X) '
                              'ROM=(%04X,%04X,%04X) C=(%04X,%04X,%04X)'
                              % (i, op, idx, w0, w2, w4, e[0], e[1], e[2],
                                 h[0], h[1], h[2]))
            if len(mismatches) >= 5:
                break

    if mismatches:
        print('FAIL idx_table @0x68780 family  %d mismatch(es)' % len(mismatches))
        for m in mismatches:
            print('    ' + m)
        sys.exit(1)

    # Emulator-only wrap pins (indices 9..255 wrap the pointer below the
    # host mmap_min_addr; the ROM semantics still hold).
    for idx in (9, 0x7F, 0xFF):
        a = paddr(idx)
        assert a != (BASE + idx * STRIDE), 'sanity: must wrap'
        cpu.call(ENTRIES['clr'], r4=idx,
                 ram={a: 0xAB, a + 1: 0xCD, a + 2: 0x12,
                      a + 3: 0x34, a + 4: 0x56, a + 5: 0x78})
        if read_slot(cpu, idx) != (0, 0, 0):
            print('FAIL clear wrap idx=%d addr=%08X' % (idx, a))
            sys.exit(1)
        cpu.call(ENTRIES['step'], r4=idx,
                 ram={a: 0x00, a + 1: 0x07,
                      a + 4: (THRESH - 1) >> 8, a + 5: (THRESH - 1) & 0xFF})
        if read_slot(cpu, idx)[0] != THRESH:
            print('FAIL step wrap idx=%d addr=%08X' % (idx, a))
            sys.exit(1)

    print('OK  idx_table family @0x68780 (clear/step/step2/dec)  '
          '(%d random + %d edge vectors, host-C == emulated ROM; '
          'wrap pins emulator-only)' % (n, n_edges))


if __name__ == '__main__':
    main()
