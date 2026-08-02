#!/usr/bin/env python3
"""test_split_selector_decoder_48C12.py

Differential test for ROM 0x48C12 (60E1D400.bin) — lift
c/split_selector_decoder_48C12.c.

Runs the ACTUAL ROM bytes of 0x48C12 in tools/sh2emu.py over seeded RAM states
(the oracle) and compares the full post-call RAM overlay against a Python
reference model that mirrors the C lift line-for-line.

Semantics (see the lift header): pure 2-bit decoder of the split-state
selector u8@0xFFFFCCD2 (from split_selector_state_ctrl_487DC) into the
output pair (u8@0xFFFFCCE2, u8@0xFFFFCCE3):
    0 -> (0,0), 1 -> (0,1), >=2 -> (1,0).
The function writes nothing else (no stack use, no other RAM).

Run: python3 c/tests/test_split_selector_decoder_48C12.py [N]
     (N = random inputs per seed; default 100000 -> 500000 across 5 seeds)
"""
import os, random, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ADDR = 0x48C12

# ---- RAM addresses (see c/split_selector_decoder_48C12.c header) ----
CCD2 = 0xFFFFCCD2   # u8 state selector byte (input)
CCE2 = 0xFFFFCCE2   # u8 output mode A ("leading")
CCE3 = 0xFFFFCCE3   # u8 output mode B ("trailing")

# a few unrelated RAM bytes that must NOT be touched (diff coverage)
SCRATCH = [0xFFFFCCE0, 0xFFFFCCE1, 0xFFFFCCE4, 0xFFFFCCD6, 0xFFFFB560,
           0xFFFFA734, 0xFFFFA738, 0xFFFFCC8C, 0xFFFFCC8D]


def model(ram, rom):
    """Line-for-line mirror of split_selector_decoder_48C12()."""
    m = dict(ram)
    s = m.get(CCD2, 0)
    if s == 0:
        m[CCE2] = 0
        m[CCE3] = 0
    elif s == 1:
        m[CCE2] = 0
        m[CCE3] = 1
    else:
        m[CCE2] = 1
        m[CCE3] = 0
    return m


def gen_state(rng):
    """Random seeded RAM: any selector byte + previous outputs + scratch."""
    ram = {}
    ram[CCD2] = rng.randint(0, 255)          # input selector (must be decoded)
    ram[CCE2] = rng.randint(0, 255)          # previous outputs (must be overwritten)
    ram[CCE3] = rng.randint(0, 255)
    for a in SCRATCH:
        ram[a] = rng.randint(0, 255)         # unrelated bytes must survive
    return ram


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    rom = open(ROM, 'rb').read()

    cpu = SH2(rom)
    seeds = (0x48C12, 0xCCD2, 0xCCE2, 0xCCE3, 0xB560)
    total_fails = 0

    for seed in seeds:
        rng = random.Random(seed)
        fails = 0
        for it in range(N):
            ram = gen_state(rng)
            want = model(ram, rom)
            try:
                cpu.call(ADDR, ram=ram)
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
                print('  CCD2=%d  CCE2=%d CCE3=%d want=(%d,%d)' %
                      (ram.get(CCD2, 0), cpu.ram.get(CCE2, 0), cpu.ram.get(CCE3, 0),
                       want.get(CCE2, 0), want.get(CCE3, 0)))
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
    print('OK  0x48C12 split_selector_decoder  (%d random inputs across %d seeds)'
          % (N * len(seeds), len(seeds)))
    print('\nAll split_selector_decoder_48C12 tests passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()
