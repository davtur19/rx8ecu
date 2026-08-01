#!/usr/bin/env python3
"""
harness_memcpy_bytewise.py — equivalence of rx8_memcpy_bytewise @0x42B0.

Reconstructed source: samples/src/rx8_memcpy_bytewise.c
Verified lift   : c/memcpy_bytewise_unroll4.c

The ROM function is a byte-by-byte memcpy with a 4x unrolled loop, invoked
with a NON-standard register protocol (r0 = count, r1 = dst, r2 = src), so
the emulator is driven with a custom caller (same as
c/tests/test_memcpy_bytewise_unroll4.py) instead of cpu.call()'s r4-r7 ABI.

Because the function acts on RAM, equivalence compares RAM side-effects:

  - emulator side: seed the sparse ram overlay at the SRC/DST addresses
    (src bytes first, then a 0xA5 prefill over the dst window), call the ROM
    entry with r0=count / r1=dst / r2=src, read the dst window back;
  - host side: the oracle mmap()s the very same pages (MAP_FIXED), seeds the
    same memory image, runs the reconstructed C, prints the dst window back.

The dst window is count + 16 bytes: the copied range plus a tail that must
still hold the 0xA5 prefill afterwards (the function must not overrun).

Usage:  python3 harness_memcpy_bytewise.py [N]     (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report  # noqa: E402

ADDR = 0x42B0
N_DEFAULT = 20000

# Buffer geometry.  Page-aligned bases above mmap_min_addr (0x10000 here) so
# the host oracle can MAP_FIXED them; the emulator overlay uses the same
# numeric addresses.
SRC_BASE = 0x00020000
DST_BASE = 0x00030000
OVL_BASE = 0x00040000      # overlap vectors (src and dst share this page)
MAX_LEN = 256
TAIL = 16
PATTERN = 0xA5
BUILD = '/tmp/rx8-recon-memcpy_bytewise'

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(os.path.dirname(SAMPLES))


def build_oracle(cc='cc'):
    """Compile ONLY this sample's oracle (host C under test)."""
    os.makedirs(BUILD, exist_ok=True)
    oracle = os.path.join(BUILD, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_memcpy_bytewise.c'),
           os.path.join(SAMPLES, 'src', 'rx8_memcpy_bytewise.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def run_oracle(oracle, lines):
    proc = subprocess.run([oracle], input='\n'.join(lines) + '\n',
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError('host oracle failed:\n' + proc.stderr)
    out = proc.stdout.splitlines()
    if len(out) != len(lines):
        raise RuntimeError('oracle produced %d outputs for %d vectors'
                           % (len(out), len(lines)))
    return out


def call_custom(cpu, entry, r0=0, r1=0, r2=0, r15=0xFFFFDF00, ram=None):
    """Drive a ROM function whose arguments live in r0/r1/r2 (memcpy
    protocol), bypassing cpu.call()'s r4-r7 ABI.  Same run loop as
    c/tests/test_memcpy_bytewise_unroll4.py."""
    cpu.ram = dict(ram or {})
    cpu.r = [0] * 16
    cpu.r[0] = r0 & 0xFFFFFFFF
    cpu.r[1] = r1 & 0xFFFFFFFF
    cpu.r[2] = r2 & 0xFFFFFFFF
    cpu.r[15] = r15 & 0xFFFFFFFF
    cpu.fr = [0.0] * 16
    cpu.pr = cpu.SENT
    cpu.T = 0
    cpu.macl = 0
    cpu.mach = 0
    cpu.gbr = 0
    cpu.fpul = 0
    cpu.fpscr = 0
    cpu.pc = entry & 0xFFFFFFFF
    steps = 0
    while True:
        if cpu.pc == cpu.SENT:
            return cpu.r[0] & 0xFFFFFFFF
        steps += 1
        if steps > 500000:
            raise RuntimeError("runaway at 0x%X" % cpu.pc)
        op = cpu.rd(cpu.pc, 2)
        br = cpu._delayed(op)
        if br is None:
            cpu._exec(op, cpu.pc)
            cpu.pc = (cpu.pc + 2) & 0xFFFFFFFF
        else:
            target, take = br
            cpu._exec(cpu.rd(cpu.pc + 2, 2), cpu.pc + 2)
            cpu.pc = target if take else (cpu.pc + 4) & 0xFFFFFFFF


def seed_ram(src, data, dst):
    """Memory image shared by both sides: src bytes first, then dst prefill."""
    ram = {}
    for i, b in enumerate(data):
        ram[src + i] = b
    for i in range(len(data) + TAIL):
        ram[dst + i] = PATTERN
    return ram


def build_vectors(n):
    """Edge vectors (small lengths x misalignment, unroll boundaries, a few
    overlapping src/dst) plus `n` random vectors with random misalignment."""
    rng = make_rng(0x42B0)
    vecs = []

    # Small lengths x src/dst misalignment (incl. count 0).
    for count in (0, 1, 2, 3, 4, 5, 8, 16):
        for so in (0, 1, 3, 7):
            for do in (0, 2, 5, 11):
                data = bytes(((i * 131 + count * 17 + so * 3 + do) & 0xFF)
                             for i in range(count))
                vecs.append((SRC_BASE + so, DST_BASE + do, count, data))

    # Longer lengths, incl. full 4-byte unroll boundaries and beyond.
    for count in (6, 7, 9, 15, 17, 31, 33, 63, 64, 65, 100, MAX_LEN):
        data = bytes(rng.getrandbits(8) for _ in range(count))
        vecs.append((SRC_BASE + rng.randint(0, 15),
                     DST_BASE + rng.randint(0, 15), count, data))

    # Overlapping src/dst in one page (memcpy, not memmove, semantics).
    for count, d in ((8, 4), (16, 4), (32, 8), (64, 16), (16, 0), (32, 31)):
        data = bytes(rng.getrandbits(8) for _ in range(count))
        vecs.append((OVL_BASE, OVL_BASE + d, count, data))

    # Random: misaligned src/dst, occasionally overlapping.
    for _ in range(n):
        count = rng.randint(0, MAX_LEN)
        data = bytes(rng.getrandbits(8) for _ in range(count))
        if rng.random() < 0.05:
            src = OVL_BASE + rng.randint(0, 8)
            vecs.append((src, src + rng.randint(0, 20), count, data))
        else:
            vecs.append((SRC_BASE + rng.randint(0, 15),
                         DST_BASE + rng.randint(0, 15), count, data))
    return vecs


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    vecs = build_vectors(n)
    n_edges = len(vecs) - n

    # (a) ROM behaviour via the emulator (RAM side-effects).
    emu = []
    for src, dst, count, data in vecs:
        call_custom(cpu, ADDR, r0=count, r1=dst, r2=src,
                    ram=seed_ram(src, data, dst))
        emu.append(''.join('%02X' % cpu.ram.get(dst + i, 0)
                           for i in range(count + TAIL)))

    # (b) host-C on the same vectors.
    lines = ['cpy %d %08X %08X %s'
             % (count, src, dst,
                ''.join('%02X' % b for b in data) if data else '-')
             for src, dst, count, data in vecs]
    host = run_oracle(oracle, lines)

    # (c) compare.
    mismatches = []
    for i, ((src, dst, count, data), e, h) in enumerate(zip(vecs, emu, host)):
        if e != h:
            mismatches.append('vec#%d count=%d src=%08X dst=%08X '
                              'ROM=[%s...] C=[%s...]'
                              % (i, count, src, dst, e[:32], h[:32]))
            if len(mismatches) >= 5:
                break

    report('memcpy_bytewise', ADDR, n, mismatches, edges=n_edges)


if __name__ == '__main__':
    main()
