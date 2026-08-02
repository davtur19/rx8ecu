#!/usr/bin/env python3
"""test_spark_output_enable_fault_mask_0x10DC8.py

Differential test for ROM 0x10DC8 (60E1D400.bin) — lift
c/spark_output_enable_fault_mask_0x10DC8.c.

Runs the ACTUAL ROM bytes of 0x10DC8 (a pure leaf, no callee calls) in
tools/sh2emu.py over seeded RAM states (the oracle), and compares the full
post-call RAM overlay against a Python reference model that mirrors the C lift
line-for-line.

Key semantic facts (see the lift header):
  * r4 = u8 status code; only 0, 6, 12, 18 are special.
  * r5 starts 0; if A9D9 == 1 the re-arm latch A5DE is cleared first.
  * r5 = 15 iff any fault flag (C63C/A798/BC94/BC95) == 1 or CAN TX C240 == 0.
  * A9DA == 1 (enable path): clear A9D9/A5DE, OR A9D8->4, A9D6->8,
    A9D7->1, A9D5->2.
  * A9DA != 1: re-arm block runs iff A5DE == 1 or (A9D9 == 0 and r4 in 6/18):
    OR A9D8->4, A9D6->8, set A5DE = 1.  Clear-latch block runs iff
    A9D9 == 0 or r4 == 0 or r4 == 12: OR A9D7->1, A9D5->2, clear A9D9 = 0.
  * Outputs: RAM16 A5D8 = r5; BC96 == 1 -> A5DA = 1, A5DC = 4 (r0 = 1),
    else A5DA = A5DC = 0 (r0 = BC96 byte).

Run: python3 c/tests/test_spark_output_enable_fault_mask_0x10DC8.py [N]
     (N = random inputs per seed; default 100000 -> 500000 across 5 seeds)
"""
import os, random, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ADDR = 0x10DC8

# ---- RAM byte addresses (all u8; mov.w 16-bit literals sign-extended) ----
A9D9 = 0xFFFFA9D9   # fault latch / state flag
A9DA = 0xFFFFA9DA   # enable-path selector
A5DE = 0xFFFFA5DE   # re-arm latch
A9D8 = 0xFFFFA9D8   # channel flag -> bit2
A9D6 = 0xFFFFA9D6   # channel flag -> bit3
A9D7 = 0xFFFFA9D7   # channel flag -> bit0
A9D5 = 0xFFFFA9D5   # channel flag -> bit1
C63C = 0xFFFFC63C   # fault flag
A798 = 0xFFFFA798   # enable flag
BC94 = 0xFFFFBC94   # fault flag
BC95 = 0xFFFFBC95   # fault flag
C240 = 0xFFFFC240   # CAN TX flag
BC96 = 0xFFFFBC96   # output-enable flag

# ---- RAM u16 output words ----
A5D8 = 0xFFFFA5D8   # output bitmask
A5DA = 0xFFFFA5DA   # output word
A5DC = 0xFFFFA5DC   # output word

FLAG_IN = [A9D9, A9DA, A5DE, A9D8, A9D6, A9D7, A9D5,
           C63C, A798, BC94, BC95, C240, BC96]


def gb(m, a):
    return m.get(a, 0)


def put16(m, a, v):
    m[a] = (v >> 8) & 0xFF
    m[a + 1] = v & 0xFF


def model(ram, r4):
    """Line-for-line mirror of spark_output_enable_fault_mask_0x10DC8().

    Returns a full RAM-effect dict (int keys -> byte values) so the caller can
    diff it against the emulator's post-call RAM.
    """
    m = dict(ram)
    r4 &= 0xFF
    r5 = 0

    if gb(m, A9D9) == 1:
        m[A5DE] = 0

    if (gb(m, C63C) == 1 or gb(m, A798) == 1 or gb(m, BC94) == 1 or
            gb(m, BC95) == 1 or gb(m, C240) == 0):
        r5 = 15

    if gb(m, A9DA) == 1:
        m[A9D9] = 0
        m[A5DE] = 0
        if gb(m, A9D8) == 1: r5 |= 4
        if gb(m, A9D6) == 1: r5 |= 8
        if gb(m, A9D7) == 1: r5 |= 1
        if gb(m, A9D5) == 1: r5 |= 2
    else:
        a9d9 = gb(m, A9D9)
        if gb(m, A5DE) == 1 or (a9d9 == 0 and (r4 == 6 or r4 == 18)):
            if gb(m, A9D8) == 1: r5 |= 4
            if gb(m, A9D6) == 1: r5 |= 8
            m[A5DE] = 1
        if gb(m, A9D9) == 0 or r4 == 0 or r4 == 12:
            if gb(m, A9D7) == 1: r5 |= 1
            if gb(m, A9D5) == 1: r5 |= 2
            m[A9D9] = 0

    put16(m, A5D8, r5)
    if gb(m, BC96) == 1:
        put16(m, A5DA, 1)
        put16(m, A5DC, 4)
    else:
        put16(m, A5DA, 0)
        put16(m, A5DC, 0)
    return m


def gen_state(rng):
    """Random seeded RAM hitting every flag / status-code combination."""
    ram = {}
    for a in FLAG_IN:
        ram[a] = rng.choice([0, 1, 1, 2, rng.randint(0, 255)])
    # push the status code toward the special values 0/6/12/18
    pick = rng.random()
    if pick < 0.15:
        r4 = 0
    elif pick < 0.3:
        r4 = 6
    elif pick < 0.45:
        r4 = 12
    elif pick < 0.6:
        r4 = 18
    else:
        r4 = rng.randint(0, 255)
    # previous outputs (must be overwritten)
    for a in (A5D8, A5DA, A5DC):
        put16(ram, a, rng.randint(0, 0xFFFF))
    return ram, r4


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    rom = open(ROM, 'rb').read()

    cpu = SH2(rom)
    seeds = (0x10DC8, 0xA9D9, 0xA5DE, 0xBC96, 0x10F0A)
    total_fails = 0

    for seed in seeds:
        rng = random.Random(seed)
        fails = 0
        for it in range(N):
            ram, r4 = gen_state(rng)
            want = model(ram, r4)
            try:
                cpu.call(ADDR, r4=r4, ram=ram)
            except Exception as e:
                print('EMULATOR EXC seed=0x%X iter=%d: %s' % (seed, it, e))
                fails += 1
                break
            bad = []
            allk = set(k for k in want if isinstance(k, int)) | set(cpu.ram.keys())
            for k in allk:
                if 0xFFFFDE00 <= k <= 0xFFFFDF00:   # task stack area
                    continue
                if cpu.ram.get(k, 0) != want.get(k, 0):
                    bad.append((k, cpu.ram.get(k, 0), want.get(k, 0)))
            if bad:
                print('MISMATCH seed=0x%X iter=%d: %s' %
                      (seed, it, {hex(k): (hex(g), hex(e)) for k, g, e in bad[:12]}))
                print('  r4=%d flags=%s' % (r4, {hex(a): gb(ram, a) for a in FLAG_IN}))
                print('  A5D8=%04X A5DA=%04X A5DC=%04X' % (
                    (gb(cpu.ram, A5D8) << 8) | gb(cpu.ram, A5D8 + 1),
                    (gb(cpu.ram, A5DA) << 8) | gb(cpu.ram, A5DA + 1),
                    (gb(cpu.ram, A5DC) << 8) | gb(cpu.ram, A5DC + 1)))
                fails += 1
                if fails >= 3:
                    break
        print('  seed 0x%X: %d inputs, fails=%d' % (seed, N, fails))
        total_fails += fails
        if total_fails:
            break

    if total_fails:
        print('\n%d FAILURE(S)' % total_fails)
        sys.exit(1)
    print('OK  0x10DC8 spark_output_enable_fault_mask  (%d random inputs across %d seeds)'
          % (N * len(seeds), len(seeds)))
    print('\nAll spark_output_enable_fault_mask_0x10DC8 tests passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()
