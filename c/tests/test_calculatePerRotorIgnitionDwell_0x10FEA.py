#!/usr/bin/env python3
"""test_calculatePerRotorIgnitionDwell_0x10FEA.py

Differential test for ROM 0x10FEA (60E0FC00.bin) — lift
c/calculatePerRotorIgnitionDwell_0x10FEA.c.

Runs the ACTUAL ROM bytes of 0x10FEA in tools/sh2emu.py over seeded RAM states
oracle) and compares the full post-call RAM overlay (byte-exact) plus the
return register r0 against a Python reference model that mirrors the C lift
line-for-line.

Real-routine note: 0x10FEA is the genuine implementation behind the 0x10386
trampoline (`mov.l @0x104BC,r3 ; jmp @r3`, literal @0x104BC == 0x00010FEA).
The trampoline CSV row 0x010386..0x01038C is intentionally NOT lifted/touched.

Semantics (see lift header): per-rotor ignition dwell. For each rotor entry in
0xFFFFA578..0xFFFFA5D0 (stride 0x2C) it walks byte slots at +0x0C and +0x1C
(start +0x0C, +=0x10, while < +0x2C), uses each byte as a table index into the
dwell output at 0xFFFFA0C4 and writes `outputPerRotorIgnitionDwell(byte)` as a
u32 there.  outputPerRotorIgnitionDwell = (uint)trunc( x / 0.25f ) where x is
float32@0xFFFFBC50 for bytes 0/1, float32@0xFFFFBC54 for bytes 2/3, else 0.0.

Run: python3 c/tests/test_calculatePerRotorIgnitionDwell_0x10FEA.py [N]
     (N = random inputs per seed; default 100000 -> 500000 across 5 seeds)
"""
import os, random, sys, struct, math

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E0FC00.bin')
ADDR = 0x10FEA

BASE = 0xFFFFA578
END  = 0xFFFFA5D0
STR  = 0x2C
OUT  = 0xFFFFA0C4

F0 = 0xFFFFBC50   # float32 dwell input for codes 0/1
F2 = 0xFFFFBC54   # float32 dwell input for codes 2/3

STACK_LO = 0xFFFFDE00
STACK_HI = 0xFFFFDF00

# finite single-precision float byte patterns to seed the dwell inputs
FLOATS = [b'\x00\x00\x00\x00', b'\x3f\x80\x00\x00', b'\x40\x00\x00\x00',
          b'\x40\x20\x00\x00', b'\x41\xf0\x00\x00', b'\x42\xc8\x00\x00',
          b'\xc1\xf0\x00\x00', b'\x3c\x00\x00\x00']


def f32b(b0, b1, b2, b3):
    return struct.unpack('>f', bytes([b0, b1, b2, b3]))[0]


def calc_dwell(b, ram):
    """Mirror of outputPerRotorIgnitionDwell@0x10F84."""
    if b in (0, 1):
        x = f32b(ram.get(F0, 0), ram.get(F0 + 1, 0), ram.get(F0 + 2, 0), ram.get(F0 + 3, 0))
    elif b in (2, 3):
        x = f32b(ram.get(F2, 0), ram.get(F2 + 1, 0), ram.get(F2 + 2, 0), ram.get(F2 + 3, 0))
    else:
        x = 0.0
    # fdiv by 0.25f (exact power of two) then ftrc (trunc). Use single-precision
    # division to match the emulator exactly (bt.tl result == x * 4.0).
    q = x / 0.25
    v = int(math.trunc(q)) & 0xFFFFFFFF
    return v


def ref(m):
    """Mirror of calculatePerRotorIgnitionDwell_0x10FEA(). Returns (RAM-effect
    dict, expected r0)."""
    m = dict(m)
    last = 0
    rot = BASE
    while rot < END:
        off = 0x0C
        while off < STR:
            b = m.get(rot + off, 0) & 0xFF
            dw = calc_dwell(b, m)
            for i in range(4):
                m[OUT + b * 4 + i] = (dw >> (8 * (3 - i))) & 0xFF
            last = dw
            off += 0x10
        rot += STR
    return m, last


def wf(m, a, bits):
    for i in range(4):
        m[a + i] = (bits >> (8 * (3 - i))) & 0xFF


def gen_state(rng):
    ram = {}
    # dwell input floats (x / 0.25 handles) at BC50 and BC54
    fA = rng.choice(FLOATS)
    fB = rng.choice(FLOATS)
    # rotor byte slots +0x0C/+0x1C for both rotors
    for rot in (BASE, BASE + STR):
        for off in (0x00, 0x02, 0x04, 0x06, 0x08, 0x0A, 0x0C, 0x0E,
                    0x10, 0x12, 0x14, 0x16, 0x18, 0x1A, 0x1C, 0x1E, 0x20, 0x22):
            ram[rot + off] = rng.randrange(0, 256)
    # both dwell input addresses
    for a, fbytes in ((F0, fA), (F2, fB)):
        for i, by in enumerate(fbytes):
            ram[a + i] = by
    return ram


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    rom = open(ROM, 'rb').read()

    cpu = SH2(rom)
    seeds = (0x10FEA, 0x10F84, 0x10386, 0xA0C4, 0xA578)
    total_fails = 0

    for seed in seeds:
        rng = random.Random(seed)
        fails = 0
        for it in range(N):
            ram = gen_state(rng)
            want, want_r0 = ref(ram)
            try:
                cpu.call(ADDR, ram=ram)
            except Exception as e:
                print('EMULATOR EXC seed=0x%X iter=%d: %s' % (seed, it, e))
                fails += 1
                break
            bad = []
            allk = set(want.keys()) | set(cpu.ram.keys())
            for k in allk:
                if STACK_LO <= k <= STACK_HI:
                    continue
                if cpu.ram.get(k, 0) != want.get(k, 0):
                    bad.append((k, cpu.ram.get(k, 0), want.get(k, 0)))
            if bad or cpu.r[0] != want_r0:
                print('MISMATCH seed=0x%X iter=%d: r0=%d want_r0=%d %s' %
                      (seed, it, cpu.r[0], want_r0,
                       {hex(k): (hex(g), hex(e)) for k, g, e in bad[:8]}))
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
    print('OK  0x10FEA calculatePerRotorIgnitionDwell '
          '(%d random inputs across %d seeds)' % (N * len(seeds), len(seeds)))
    print('\nAll calculatePerRotorIgnitionDwell tests passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()