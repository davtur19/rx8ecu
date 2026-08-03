#!/usr/bin/env python3
"""test_checkImmoStatus_371E4.py

Differential test for ROM 0x371E4 (60E1D400.bin) — lift c/checkImmoStatus.c.

Periodic sanity/reset of the EEPROM working copies and CAN shadow bytes.

Prologue: E2_WORK_INDEX0 (0xFFFFC2D8) != 0x5A -> zeroed; then re-read:
  armed  (0xFFFFC2D8 == 0x5A):
    - E2_WORK_INDEX12 (0xFFFFC2E5): (v & 0xFC) != 0 -> v = 0
    - CAN_SHADOW_C243 (0xFFFFC243): (v & 0x0F) != 0 -> v = 0,
                                    then E2_WORK_INDEX10 (0xFFFFC2E4)==1 -> v |= 0x40
    - E2_WORK_INDEX13 (0xFFFFC2E6): v > 5 -> v = 0
    - MOVT idiom (0x37250): if bit1 of (post-zeroing) 0xFFFFC2E5 is CLEAR
        and (u8)0xFFFFC242 == 0x55: 0xFFFFC242 = 0x33, u16 0xFFFFC2A4 = 0
    - E2_WORK_INDEX30 (0xFFFFC2F2): v > 2 -> v = 2
  reset (not armed):
    - 0xFFFFC2E5=0, 0xFFFFC2E6=0, 0xFFFFC243=0
    - E2_WORK_INDEX10==1 -> 0xFFFFC243 |= 0x40
    - 0xFFFFC242=0x33, 0xFFFFC244=8, 0xFFFFC2E9=0, 0xFFFFC2E8=0,
      0xFFFFC2EE..0xFFFFC2F1=0, 0xFFFFC2F2=2
  common:
    - 0xFFFFC244: clamp to 8 if outside [8, 0x3F]
    - 0xFFFFC2E9 > 0 -> 0xFFFFC2A9=1, 0xFFFFC2E9=0xC8

All mov.w PC-relative literals (0xC242..0xC244) are SIGN-EXTENDED by the
`mov.w <lit>,Rn` load -> effective addresses 0xFFFFC242..0xFFFFC244.

Run: python3 c/tests/test_checkImmoStatus_371E4.py [N]
     (N = random pre-state overlays per seed; default 5000 -> 25000 across 5)
"""
import os, random, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ADDR = 0x371E4

C2D8 = 0xFFFFC2D8   # E2_WORK_INDEX0
C2E5 = 0xFFFFC2E5   # E2_WORK_INDEX12
C2E6 = 0xFFFFC2E6   # E2_WORK_INDEX13
C2E4 = 0xFFFFC2E4   # E2_WORK_INDEX10
C2E9 = 0xFFFFC2E9   # E2_WORK_INDEX20
C2E8 = 0xFFFFC2E8   # E2_WORK_INDEX19
C2EE = 0xFFFFC2EE
C2EF = 0xFFFFC2EF
C2F0 = 0xFFFFC2F0
C2F1 = 0xFFFFC2F1
C2F2 = 0xFFFFC2F2   # E2_WORK_INDEX30
C242 = 0xFFFFC242   # CAN shadow (mov.w sign-extended literal 0xC242)
C243 = 0xFFFFC243
C244 = 0xFFFFC244
C2A4 = 0xFFFFC2A4   # u16
C2A9 = 0xFFFFC2A9


def wr16(m, a, v):
    m[a] = (v >> 8) & 0xFF
    m[a + 1] = v & 0xFF


def model(ram):
    m = dict(ram)
    if m.get(C2D8, 0) != 0x5A:
        m[C2D8] = 0
    armed = (m.get(C2D8, 0) == 0x5A)
    if armed:
        e5 = m.get(C2E5, 0)
        if e5 & 0xFC:
            e5 = 0
            m[C2E5] = 0
        if m.get(C243, 0) & 0x0F:
            m[C243] = 0
            if m.get(C2E4, 0) == 1:
                m[C243] |= 0x40
        if m.get(C2E6, 0) > 5:
            m[C2E6] = 0
        # MOVT idiom (0x37250): r2 = T of tst #0x02 on post-zeroing C2E5;
        # bf 0x37272 taken iff bit1 SET -> handshake runs iff bit1 CLEAR
        c242 = m.get(C242, 0)
        if (e5 & 0x02) == 0:
            if c242 == 0x55:
                m[C242] = 0x33
                wr16(m, C2A4, 0)
        if m.get(C2F2, 0) > 2:
            m[C2F2] = 2
        # r0 at epilogue: 0x3724C r0 = (int8)@C2E5; handshake overwrites
        # with extu.b @C242 (pre-store value) when bit1 clear
        if e5 & 0x02:
            r0 = e5 & 0xFF          # e5 in {2,3} here
        else:
            r0 = 0x55 if c242 == 0x55 else (c242 & 0xFF)
    else:
        m[C2E5] = 0
        m[C2E6] = 0
        m[C243] = 0
        if m.get(C2E4, 0) == 1:
            m[C243] |= 0x40
        m[C242] = 0x33
        m[C244] = 8
        m[C2E9] = 0
        m[C2E8] = 0
        m[C2EE] = 0
        m[C2EF] = 0
        m[C2F0] = 0
        m[C2F1] = 0
        m[C2F2] = 2
        r0 = 0x40 if m.get(C2E4, 0) == 1 else (m.get(C2E4, 0) & 0xFF)
    # common epilogue
    c244 = m.get(C244, 0)
    if c244 < 8 or c244 > 0x3F:
        m[C244] = 8
    if m.get(C2E9, 0) > 0:
        m[C2A9] = 1
        m[C2E9] = 0xC8
    return m, r0 & 0xFFFFFFFF


def seed_ram(rng):
    m = {}
    for a in (C2D8, C2E5, C2E6, C2E4, C2E9, C2E8, C2EE, C2EF, C2F0, C2F1,
              C2F2, C242, C243, C244, C2A9):
        m[a] = rng.randint(0, 255)
    m[C2A4] = rng.randint(0, 255)
    m[C2A4 + 1] = rng.randint(0, 255)
    return m


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    seeds = (0x371E4, 0xC2D8, 0xC244, 0x5A5A, 0x5EED)
    total = fails = 0

    for seed in seeds:
        rng = random.Random(seed)
        for _ in range(N):
            ram = seed_ram(rng)
            # force armed / reset coverage on every seed
            if _ % 2 == 0:
                ram[C2D8] = 0x5A
            want, want_r0 = model(ram)
            got_r0 = cpu.call(ADDR, ram=dict(ram))
            bad = []
            allk = set(want) | set(cpu.ram.keys())
            for k in allk:
                if 0xFFFFDE00 <= k <= 0xFFFFDF00:
                    continue
                if cpu.ram.get(k, 0) != want.get(k, 0):
                    bad.append((k, cpu.ram.get(k, 0), want.get(k, 0)))
            if got_r0 != want_r0:
                bad.append(('r0', got_r0, want_r0))
            if bad:
                fails += 1
                if fails <= 5:
                    print('MISMATCH seed=0x%X: %s' %
                          (seed, {k: (hex(g), hex(e))
                                  for k, g, e in bad[:10]}))
            total += 1
        if fails >= 5:
            break

    if fails:
        print('\nFAIL checkImmoStatus @0x371E4  (%d mismatches / %d inputs)'
              % (fails, total))
        sys.exit(1)
    print('OK  checkImmoStatus @0x371E4  (%d inputs, 0 mismatches)' % total)
    sys.exit(0)


if __name__ == '__main__':
    main()
