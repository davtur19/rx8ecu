#!/usr/bin/env python3
"""test_getEngineCrankingStatus_0x10EE6.py

Differential test for ROM 0x10EE6 (60E0FC00.bin) — lift
c/getEngineCrankingStatus_0x10EE6.c.

Runs the ACTUAL ROM bytes of 0x10EE6 in tools/sh2emu.py over seeded RAM states
(the oracle) and compares the full post-call RAM overlay (byte-exact) plus the
return register r0 against a Python reference model that mirrors the C lift
line-for-line.

Entry-point note: 0x10EE6 IS the real entry point — the function-pointer slot
@0x144F4 in the dispatcher engineControlCalculateTiming (0x141FC) dispatch
table, immediately after the calculatePerRotorIgnitionDwell stub slot @0x144F0.
Valid entry (no branches into the body; preceding getEngineCrankingStatusEnum
ends rts @0x10EE2).  The CSV range 0x10EE6..0x10F04 is CORRECT.

Key semantic facts (see the lift header): round-status flag writer over the
rotor timing array anchored at 0xFFFFA578 (stride 0x2C, end 0xFFFFA578+0x58):
  for p = 0xFFFFA578; p < 0xFFFFA5D0; p += 0x2C:  *(u8)(p+2) = 1
=> writes u8 1 to 0xFFFFA57A and 0xFFFFA5A6.  r0 after return = 1.
No stack frame, no sub-calls.

Run: python3 c/tests/test_getEngineCrankingStatus_0x10EE6.py [N]
     (N = random inputs per seed; default 100000 -> 500000 across 5 seeds)
"""
import os, random, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E0FC00.bin')
ADDR = 0x10EE6

BASE = 0xFFFFA578
END = 0xFFFFA5D0
STRIDE = 0x2C

STACK_LO = 0xFFFFDE00    # task stack window (skipped in the compare)
STACK_HI = 0xFFFFDF00


def rbu(m, a):
    return m.get(a, 0) & 0xFF


def ref(m):
    """Mirror of getEngineCrankingStatus_0x10EE6().  Returns (RAM-effect
    dict, expected r0)."""
    m = dict(m)
    flags = []
    for p in range(BASE, END, STRIDE):
        flags.append(p + 2)
    for f in flags:
        m[f] = 0x01
    return m, 1


def gen_state(rng):
    """Random seeded RAM: junk the two +2 flag bytes so a missed write is
    caught.  The function has no other RAM input (all anchors are constants),
    so any junk elsewhere must be untouched."""
    ram = {}
    ram[0xFFFFA57A] = rng.choice([0, 0x11, 0x55, 0x7F, 0x80, 0xFF])
    ram[0xFFFFA5A6] = rng.choice([0, 0x22, 0x33, 0xA9, 0x00, 0xFE])
    # a couple of sentinel neighbours must remain untouched
    ram[0xFFFFA578] = 0x5A
    ram[0xFFFFA5A4] = 0x5A
    ram[0xFFFFA57B] = 0x6B
    ram[0xFFFFA5A7] = 0x6B
    return ram


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    rom = open(ROM, 'rb').read()

    cpu = SH2(rom)
    seeds = (0x10EE6, 0x10ED2, 0x144F4, 0xA57A, 0xA5A6)
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
            allk = set(k for k in want if isinstance(k, int)) | set(cpu.ram.keys())
            for k in allk:
                if STACK_LO <= k <= STACK_HI:    # task stack area
                    continue
                if cpu.ram.get(k, 0) != want.get(k, 0):
                    bad.append((k, cpu.ram.get(k, 0), want.get(k, 0)))
            if bad or cpu.r[0] != want_r0:
                print('MISMATCH seed=0x%X iter=%d: r0=%d want_r0=%d %s' %
                      (seed, it, cpu.r[0], want_r0,
                       {hex(k): (hex(g), hex(e)) for k, g, e in bad[:10]}))
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
    print('OK  0x10EE6 getEngineCrankingStatus '
          '(%d random inputs across %d seeds)' % (N * len(seeds), len(seeds)))
    print('\nAll getEngineCrankingStatus_0x10EE6 tests passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()