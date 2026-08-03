#!/usr/bin/env python3
"""test_ImmoBadStateSet_365B8.py

Differential test for ROM 0x365B8 (60E1D400.bin) — lift c/ImmoBadStateSet.c.

Marks the immobilizer as "bad": setImmoLight(0) (0x263C8) clears the lamp
bits on 0xFFFFF754, CAN_TX_DATA (0xFFFFC240) = 0, IMMO_TIMEOUT_CTR
(0xFFFFC284, u16) = 0x01F4, IMMO_STATE_CODE (0xFFFFC28D) = 4.

The whole call tree (incl. setImmoLight and its 0x2054/0x4BBC/0x2064 helpers)
executes in the emulator; the model mirrors the lift.  No inputs: verifies the
effect over seeded random starting RAM overlays (pre-state gets overwritten).

Run: python3 c/tests/test_ImmoBadStateSet_365B8.py [N]
     (N = random RAM overlays per seed; default 5000 -> 25000 across 5 seeds)
"""
import os, random, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ADDR = 0x365B8

LAMP       = 0xFFFFF754   # 16-bit lamp GPIO (setImmoLight side effect)
CAN_TX     = 0xFFFFC240   # CAN_TX_DATA
TIMEOUT    = 0xFFFFC284   # IMMO_TIMEOUT_CTR (u16)
STATE_CODE = 0xFFFFC28D   # IMMO_STATE_CODE


def rd16(m, a):
    return ((m.get(a, 0) & 0xFF) << 8) | (m.get(a + 1, 0) & 0xFF)


def model(ram):
    m = dict(ram)
    v = rd16(m, LAMP) & ~0x60
    m[LAMP] = (v >> 8) & 0xFF
    m[LAMP + 1] = v & 0xFF
    m[CAN_TX] = 0
    m[TIMEOUT] = 0x01
    m[TIMEOUT + 1] = 0xF4
    m[STATE_CODE] = 4
    return m


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    seeds = (0x365B8, 0xF754, 0xC284, 0xC240, 0x5EED)
    total = fails = 0

    for seed in seeds:
        rng = random.Random(seed)
        for _ in range(N):
            ram = {}
            for a in (CAN_TX, STATE_CODE):
                ram[a] = rng.randint(0, 255)
            for a in (TIMEOUT, LAMP):
                ram[a] = rng.randint(0, 255)
                ram[a + 1] = rng.randint(0, 255)
            want = model(ram)
            cpu.call(ADDR, ram=dict(ram))
            bad = []
            allk = set(want) | set(cpu.ram.keys())
            for k in allk:
                if 0xFFFFDE00 <= k <= 0xFFFFDF00:
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
        print('\nFAIL ImmoBadStateSet @0x365B8  (%d mismatches / %d inputs)'
              % (fails, total))
        sys.exit(1)
    print('OK  ImmoBadStateSet @0x365B8  (%d inputs, 0 mismatches)' % total)
    sys.exit(0)


if __name__ == '__main__':
    main()