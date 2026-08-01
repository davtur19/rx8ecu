#!/usr/bin/env python3
"""
Verify the idx_table helper family (0x68780/0x6879C/0x687C8/0x687F4) against
the ACTUAL ROM bytes, run in the SH-2E emulator.

All four share:  p = 0xFFFFD998 + (r4 & 0xFF) * 0x46C   (32-bit arithmetic)

  0x68780  clear(r4): word@p = word@p+2 = word@p+4 = 0
  0x6879C  step(r4):  word@p = (word@p+4 >= 0x0464) ? 0 : word@p+4 + 1
  0x687C8  step2(r4): same logic as 0x6879C (separate ROM copy)
  0x687F4  dec(r4):   word@p+4 = (word@p == 0) ? 0x0464 : word@p - 1

Indices 0..8 stay in the 0xFFFFxxxx RAM region; 9+ wrap to low 32-bit
addresses (pinned below with seeded low-RAM values).

C:
  void idx_table_clear_68780(uint32_t r4)
  void idx_table_step_6879C(uint32_t r4)
  void idx_table_step2_687C8(uint32_t r4)
  void idx_table_dec_687F4(uint32_t r4)

Run from repo root:  python3 c/tests/test_idx_table_helpers_68780.py [N]
"""
import os, sys, random

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ENTRIES = {'clear': 0x0068780, 'step': 0x006879C, 'step2': 0x00687C8, 'dec': 0x00687F4}

BASE = 0xFFFFD998
STRIDE = 0x46C
THRESH = 0x0464


def paddr(r4):
    return (BASE + (r4 & 0xFF) * STRIDE) & 0xFFFFFFFF


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 4000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)

    def seed_entry(idx, w0=0, w2=0, w4=0):
        a = paddr(idx)
        return {a: (w0 >> 8) & 0xFF, a + 1: w0 & 0xFF,
                a + 2: (w2 >> 8) & 0xFF, a + 3: w2 & 0xFF,
                a + 4: (w4 >> 8) & 0xFF, a + 5: w4 & 0xFF}

    def run(entry, idx, ram):
        cpu.call(ENTRIES[entry], r4=idx, ram=ram)
        a = paddr(idx)
        return ((cpu.ram.get(a, 0) << 8) | cpu.ram.get(a + 1, 0),
                (cpu.ram.get(a + 2, 0) << 8) | cpu.ram.get(a + 3, 0),
                (cpu.ram.get(a + 4, 0) << 8) | cpu.ram.get(a + 5, 0))

    # ---- targeted edges for step/dec ----
    for w4 in (0x0000, 0x0001, 0x0463, 0x0464, 0x0465, 0x0466, 0x7FFF, 0x8000, 0xFFFE, 0xFFFF):
        exp0 = 0 if w4 >= THRESH else (w4 + 1) & 0xFFFF
        for idx in (0, 1, 8):
            got = run('step', idx, seed_entry(idx, w4=w4))
            if got[0] != exp0:
                print("FAIL step: idx=%d w4=%04X got %04X expected %04X" % (idx, w4, got[0], exp0)); sys.exit(1)
        got = run('step2', 3, seed_entry(3, w4=w4))
        if got[0] != exp0:
            print("FAIL step2: w4=%04X got %04X expected %04X" % (w4, got[0], exp0)); sys.exit(1)
    for w0 in (0x0000, 0x0001, 0x0002, 0x0464, 0x7FFF, 0x8000, 0xFFFE, 0xFFFF):
        exp4 = THRESH if w0 == 0 else (w0 - 1) & 0xFFFF
        for idx in (0, 1, 8):
            got = run('dec', idx, seed_entry(idx, w0=w0))
            if got[2] != exp4:
                print("FAIL dec: idx=%d w0=%04X got %04X expected %04X" % (idx, w0, got[2], exp4)); sys.exit(1)

    # clear: zeroes all three words
    for idx in (0, 1, 8):
        got = run('clear', idx, seed_entry(idx, w0=0xAAAA, w2=0x5555, w4=0x1234))
        if got != (0, 0, 0):
            print("FAIL clear: idx=%d got %s" % (idx, got)); sys.exit(1)

    # ---- random over indices 0..8 ----
    for _ in range(N):
        idx = random.randint(0, 8)
        w0, w2, w4 = (random.randint(0, 0xFFFF) for _ in range(3))
        ram = seed_entry(idx, w0, w2, w4)
        exp = {'clear': (0, 0, 0),
               'step': (0 if w4 >= THRESH else (w4 + 1) & 0xFFFF, w2, w4),
               'step2': (0 if w4 >= THRESH else (w4 + 1) & 0xFFFF, w2, w4),
               'dec': (w0, w2, THRESH if w0 == 0 else (w0 - 1) & 0xFFFF)}
        for name in exp:
            got = run(name, idx, dict(ram))
            if got != exp[name]:
                print("FAIL %s: idx=%d (w0,w2,w4)=(%04X,%04X,%04X) got %s exp %s"
                      % (name, idx, w0, w2, w4, got, exp[name])); sys.exit(1)

    # ---- wrap pins: indices 9+ wrap p via 32-bit arithmetic ----
    for idx in (9, 0x7F, 0xFF):
        a = paddr(idx)
        assert a != (BASE + idx * STRIDE)  # sanity: really wrapped
        ram = {a: 0xAB, a + 1: 0xCD, a + 2: 0x12, a + 3: 0x34, a + 4: 0x56, a + 5: 0x78}
        got = run('clear', idx, dict(ram))
        if got != (0, 0, 0):
            print("FAIL clear wrap: idx=%d addr=%08X got %s" % (idx, a, got)); sys.exit(1)
        ram = {a: 0x00, a + 1: 0x07, a + 4: (THRESH - 1) >> 8, a + 5: (THRESH - 1) & 0xFF}
        got = run('step', idx, dict(ram))
        if got[0] != THRESH:
            print("FAIL step wrap: idx=%d addr=%08X got %04X" % (idx, a, got[0])); sys.exit(1)

    print("OK  idx_table family @0x68780 (clear/step/step2/dec)  (targeted + %d random + wrap)" % N)
    sys.exit(0)


if __name__ == '__main__':
    main()
