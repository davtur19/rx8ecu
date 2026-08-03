#!/usr/bin/env python3
"""test_ImmoGoodStateSet_36544.py

Differential test for ROM 0x36544 (60E1D400.bin) — lift c/ImmoGoodStateSet.c.

Marks the immobilizer as "good": setImmoLight(1) (0x263C8), CAN_TX_DATA
(0xC240 -> sign-extended 0xFFFFC240) = 1, E2_WORK_INDEX30 (0xFFFFC2F2) = 2,
IMMO_SEED_ACTIVE (0xFFFFC29F) = 1, IMMO_TIMER (0xFFFFC282, u16) = 0x3A98,
IMMO_TIMEOUT_CTR (0xFFFFC284, u16) = 0x00FA, 0xFFFFC28C = 0,
IMMO_STATE_CODE (0xFFFFC28D) = 3, IMMO_GOODSTATE_FLAG (0xFFFFC29A) = 0,
plus the lamp effect of setImmoLight(1) on 0xFFFFF754 (|= 0x60).

The ROM bytes of the whole call tree (incl. setImmoLight and its helpers
0x2054/0x4BBC/0x2064) execute in the emulator; the model mirrors the lift
line-for-line.  There are no inputs, so the test verifies the effect against
seeded random starting RAM overlays (pre-state must be overwritten exactly).

Run: python3 c/tests/test_ImmoGoodStateSet_36544.py [N]
     (N = random RAM overlays; default 5000 -> 25000 across 5 seeds)
"""
import os, random, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ADDR = 0x36544

LAMP       = 0xFFFFF754   # 16-bit lamp GPIO (setImmoLight side effect)
CAN_TX     = 0xFFFFC240   # CAN_TX_DATA (mov.w 0xC240 sign-extended)
E2W30      = 0xFFFFC2F2   # E2_WORK_INDEX30
SEED_ACT   = 0xFFFFC29F   # IMMO_SEED_ACTIVE
TIMER      = 0xFFFFC282   # IMMO_TIMER (u16)
TIMEOUT    = 0xFFFFC284   # IMMO_TIMEOUT_CTR (u16)
C28C       = 0xFFFFC28C
STATE_CODE = 0xFFFFC28D   # IMMO_STATE_CODE
GOOD_FLAG  = 0xFFFFC29A   # IMMO_GOODSTATE_FLAG


def rd16(m, a):
    return ((m.get(a, 0) & 0xFF) << 8) | (m.get(a + 1, 0) & 0xFF)


def model(ram):
    m = dict(ram)
    v = rd16(m, LAMP) | 0x60
    m[LAMP] = (v >> 8) & 0xFF
    m[LAMP + 1] = v & 0xFF
    m[CAN_TX] = 1
    m[E2W30] = 2
    m[SEED_ACT] = 1
    m[TIMER] = 0x3A
    m[TIMER + 1] = 0x98
    m[TIMEOUT] = 0x00
    m[TIMEOUT + 1] = 0xFA
    m[C28C] = 0
    m[STATE_CODE] = 3
    m[GOOD_FLAG] = 0
    return m


def gen_state(rng):
    """Random seeded RAM overlay covering every address the function touches."""
    m = {}
    for a in (E2W30, SEED_ACT, C28C, STATE_CODE, GOOD_FLAG, CAN_TX):
        m[a] = rng.randint(0, 255)
    for a in (TIMER, TIMEOUT, LAMP):
        m[a] = rng.randint(0, 255)
        m[a + 1] = rng.randint(0, 255)
    return m


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    seeds = (0x36544, 0xC240, 0xC2F2, 0xF754, 0x5EED)
    total = fails = 0

    for seed in seeds:
        rng = random.Random(seed)
        for _ in range(N):
            ram = gen_state(rng)
            want = model(ram)
            cpu.call(ADDR, ram=dict(ram))
            bad = []
            allk = set(want) | set(cpu.ram.keys())
            for k in allk:
                if 0xFFFFDE00 <= k <= 0xFFFFDF00:   # task stack area
                    continue
                if cpu.ram.get(k, 0) != want.get(k, 0):
                    bad.append((k, cpu.ram.get(k, 0), want.get(k, 0)))
            if bad:
                fails += 1
                if fails <= 5:
                    print('MISMATCH seed=0x%X: %s' %
                          (seed, {hex(k): (hex(g), hex(e))
                                  for k, g, e in bad[:10]}))
            total += 1
        if fails >= 5:
            break

    if fails:
        print('\nFAIL ImmoGoodStateSet @0x36544  (%d mismatches / %d inputs)'
              % (fails, total))
        sys.exit(1)
    print('OK  ImmoGoodStateSet @0x36544  (%d inputs, 0 mismatches)' % total)
    sys.exit(0)


if __name__ == '__main__':
    main()
