#!/usr/bin/env python3
"""test_getKnockControlActive_0x13A86.py

Differential test for ROM 0x13A86 (60E1D400.bin) — lift
c/getKnockControlActive_0x13A86.c.

Runs the ACTUAL ROM bytes of 0x13A86 in tools/sh2emu.py over seeded RAM states
(the oracle) and compares the full post-call RAM overlay (byte-exact) plus the
return register r0 against a Python reference model that mirrors the C lift
line-for-line.

Entry-point note: 0x13A86 IS the real entry point — the function-pointer slot
@0x1479C in the dispatcher engineControlCalculateTiming (0x14584) dispatch
table, phase 1, right after calc_rotor_sync_base_A (0x14798) and before
updateKnockMaxRAM (0x147A0).  Valid entry (no branches into the body;
preceding function ends with rts @0x13A82).  The merged symbols CSV row is
getKnockControlActive (kept; ida-ai row calc_rotor_sync_base_B is renamed).

Key semantic facts (see the lift header): void flag writer.
  u8@0xFFFFA740 = 1 iff (u8@0xFFFFA748 & 0xFF) == 1 && (u8@0xFFFFA749 & 0xFF) == 1
  else 0.  A748 is the ignition-advance-modifier flag (0x13A0E), A749 the rotor
  sync flag (0x13A5E); A740 is the knock-control-active output.
  r0 after return = last masked gate byte read (A748&0xFF, else A749&0xFF).

Run: python3 c/tests/test_getKnockControlActive_0x13A86.py [N]
     (N = random inputs per seed; default 100000 -> 500000 across 5 seeds)
"""
import os, random, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ADDR = 0x13A86

GATE_A748 = 0xFFFFA748   # u8 gate input (0x13A0E flag)
GATE_A749 = 0xFFFFA749   # u8 gate input (rotor sync)
OUT_A740  = 0xFFFFA740   # u8 knock-control-active output


def rbu(m, a):
    return m.get(a, 0) & 0xFF


def ref(m):
    """Line-for-line mirror of getKnockControlActive_0x13A86().
    Returns (RAM-effect dict, expected r0)."""
    m = dict(m)

    m748 = rbu(m, GATE_A748)          # extu.b after mov.b sign-extend
    if m748 == 1:
        m749 = rbu(m, GATE_A749)      # second gate (extu.b)
        if m749 == 1:
            m[OUT_A740] = 1
            return m, m749            # r0 = 1
        m[OUT_A740] = 0
        return m, m749
    m[OUT_A740] = 0
    return m, m748


def gen_state(rng):
    """Random seeded RAM: gate bytes cover 0/1/other/high-bit values; output
    is junk so a missed write is caught."""
    ram = {}
    ram[GATE_A748] = rng.choice([0, 0, 1, 1, 1, 2, 0x7F, 0x80, 0xFF])
    ram[GATE_A749] = rng.choice([0, 0, 1, 1, 1, 3, 0x7F, 0x80, 0xFE])
    ram[OUT_A740] = rng.choice([0, 1, 0x55, 0xFF])
    return ram


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    rom = open(ROM, 'rb').read()

    cpu = SH2(rom)
    seeds = (0x13A86, 0x13A0E, 0x13A5E, 0x13B90, 0xA740)
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
                if 0xFFFFDE00 <= k <= 0xFFFFDF00:   # task stack area
                    continue
                if cpu.ram.get(k, 0) != want.get(k, 0):
                    bad.append((k, cpu.ram.get(k, 0), want.get(k, 0)))
            if bad or cpu.r[0] != want_r0:
                print('MISMATCH seed=0x%X iter=%d: r0=%d want_r0=%d %s' %
                      (seed, it, cpu.r[0], want_r0,
                       {hex(k): (hex(g), hex(e)) for k, g, e in bad[:10]}))
                print('  A748=%d A749=%d' % (ram.get(GATE_A748, 0),
                                              ram.get(GATE_A749, 0)))
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
    print('OK  0x13A86 getKnockControlActive '
          '(%d random inputs across %d seeds)' % (N * len(seeds), len(seeds)))
    print('\nAll getKnockControlActive_0x13A86 tests passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()