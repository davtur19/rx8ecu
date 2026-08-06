#!/usr/bin/env python3
"""test_getKnockSensorFaultedStatus_0x136D6.py

Differential test for ROM 0x136D6 (60E0FC00.bin) — lift
c/getKnockSensorFaultedStatus_0x136D6.c.

Runs the ACTUAL ROM bytes of 0x136D6 in tools/sh2emu.py over seeded RAM states
(the oracle) and compares the full post-call RAM overlay (byte-exact) plus the
return register r0 against a Python reference model that mirrors the C lift
line-for-line.

Entry-point / bank note: 0x136D6 in 60E1D400 is a jump-table region (inside
calc_evap_purge_duty), so the genuine knock-sensor-fault writer is lifted from
60E0FC00 (byte-identical in 60E0FB00).  There it is called via the function-
pointer slot @0x14410 of the dispatcher engineControlCalculateTiming (0x141FC),
phase 1, right after getKnockControlAllowed?? (0x13686) and before
getKnockControlActive (0x136FE).  Valid entry (no branches into the body;
preceding function ends with rts @0x136D2).  The symbols CSV row is
getKnockSensorFaultedStatus? (name kept, ? dropped after verification).

Key semantic facts (see the lift header): void flag writer.
  u8@0xFFFFA739 = 1 iff (u8@0xFFFFCC30 & 0xFF) == 1 && (u8@0xFFFFCC32 & 0xFF) == 1
  else 0.  A739 is the knock-sensor-faulted latch consumed by the knock control
  chain.  r0 after return = the masked byte of the last status read that decided
  the branch (1 on the both-match path, else the failing masked byte).

Run: python3 c/tests/test_getKnockSensorFaultedStatus_0x136D6.py [N]
     (N = random inputs per seed; default 100000 -> 500000 across 5 seeds)
"""
import os, random, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E0FC00.bin')
ADDR = 0x136D6

IN_A_CC30 = 0xFFFFCC30   # u8 knock sensor A status (mov.w literal 0xCC30)
IN_B_CC32 = 0xFFFFCC32   # u8 knock sensor B status (mov.w literal 0xCC32)
OUT_A739  = 0xFFFFA739   # u8 knock-sensor-fault flag output


def rbu(m, a):
    return m.get(a, 0) & 0xFF


def ref(m):
    """Line-for-line mirror of getKnockSensorFaultedStatus_0x136D6().
    Returns (RAM-effect dict, expected r0)."""
    m = dict(m)

    b4 = rbu(m, IN_A_CC30)            # extu.b after mov.b sign-extend
    if b4 == 1:
        b6 = rbu(m, IN_B_CC32)        # second gate (extu.b)
        if b6 == 1:
            m[OUT_A739] = 1
            return m, b6              # r0 = 1
        m[OUT_A739] = 0
        return m, b6
    m[OUT_A739] = 0
    return m, b4


def gen_state(rng):
    """Random seeded RAM: status bytes cover 0/1/other/high-bit values; the
    output flag is junk so a missed write is caught."""
    ram = {}
    ram[IN_A_CC30] = rng.choice([0, 0, 1, 1, 1, 2, 0x7F, 0x80, 0xFF])
    ram[IN_B_CC32] = rng.choice([0, 0, 1, 1, 1, 3, 0x7F, 0x80, 0xFE])
    ram[OUT_A739] = rng.choice([0, 1, 0x55, 0xFF])
    return ram


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    rom = open(ROM, 'rb').read()

    cpu = SH2(rom)
    seeds = (0x136D6, 0x13686, 0x136FE, 0x13760, 0xA739)
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
                print('  CC30=%d CC32=%d' % (ram.get(IN_A_CC30, 0),
                                              ram.get(IN_B_CC32, 0)))
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
    print('OK  0x136D6 getKnockSensorFaultedStatus '
          '(%d random inputs across %d seeds)' % (N * len(seeds), len(seeds)))
    print('\nAll getKnockSensorFaultedStatus_0x136D6 tests passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()