#!/usr/bin/env python3
"""test_ImmoUpdateRelated_37120.py

Differential test for ROM 0x37120 (60E1D400.bin) — lift c/ImmoUpdateRelated.c.

EEPROM write-queue driver for the immobilizer pairing data.

  - E2_WQ_INIT_DONE (0xFFFFC2D5) != 0            -> return
  - E2_WQ_ARMED (0xFFFFC2D6) == 0:
      E2_WORK_INDEX0 (0xFFFFC2D8) != 0x5A:
          C2D8 = 0x5A; E2_WQ_PENDING_CODE (0xFFFFC2D1) = 0x0C;
          updateE2RAMBasedOnInput(0x0C)  [0x36D0C -> writeToE2RAMArea 0x39124]
          E2_WQ_BUSY (0xFFFFC2D7) = 1; E2_WQ_ARMED = 1
      else: E2_WQ_INIT_DONE = 1
  - armed:
      was_busy = E2_WQ_BUSY
      eeprom_commit_dispatcher_37000(E2_WQ_PENDING_CODE)
          [0x37000 -> eeprom_write_sched 0x38B5C, the SPI queue scheduler]
      if E2_WRITE_COMPLETE (0xFFFFC2F8) == 1:
          E2_WQ_FLAG_D2 (0xFFFFC2D2) = 0
          was_busy:  E2_WQ_BUSY = 0; E2_WQ_PENDING_CODE = 3;
                     updateE2RAMBasedOnInput(3)
          else:      E2_WQ_PENDING_CODE = 0; E2_WQ_INIT_DONE = 1;
                     E2_WQ_ARMED = 0

The full call tree (updateE2RAMBasedOnInput + writeToE2RAMArea, the commit
dispatcher + eeprom_write_sched) executes in the main emulator for real.  The
Python model mirrors the control flow exactly and runs each callee through a
SECOND emulator instance (cpu2) so its RAM effect comes from the real ROM
bytes — the same strategy as test_eeprom_commit_dispatcher_37000.py.  Only
seeded random pre-state overlays are varied; the RAM overlay is compared
(the final r0 is a callee artifact and is not compared).

Run: python3 c/tests/test_ImmoUpdateRelated_37120.py [N]
     (N = random overlays per seed; default 5000 -> 25000 across 5 seeds)
"""
import os, random, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ADDR = 0x37120
UPD  = 0x36D0C    # updateE2RAMBasedOnInput
DISP = 0x37000    # eeprom_commit_dispatcher

C2D5 = 0xFFFFC2D5   # E2_WQ_INIT_DONE
C2D6 = 0xFFFFC2D6   # E2_WQ_ARMED
C2D7 = 0xFFFFC2D7   # E2_WQ_BUSY
C2D1 = 0xFFFFC2D1   # E2_WQ_PENDING_CODE
C2D2 = 0xFFFFC2D2   # E2_WQ_FLAG_D2
C2D8 = 0xFFFFC2D8   # E2_WORK_INDEX0
C2F8 = 0xFFFFC2F8   # E2_WRITE_COMPLETE
C2FB = 0xFFFFC2FB
C511 = 0xFFFFC511   # scheduler busy byte

# working copies read by updateE2RAMBasedOnInput(0x0C/0x03)
WORK = [0xFFFFC2E5, 0xFFFFC2E6, 0xFFFFC243, 0xFFFFC2E7, 0xFFFFC242,
        0xFFFFC2E9, 0xFFFFC244, 0xFFFFC2E8, 0xFFFFC2EE, 0xFFFFC2EF,
        0xFFFFC2F0, 0xFFFFC2F1, 0xFFFFC2F2]


def model(cpu2, ram):
    """Mirror of c/ImmoUpdateRelated.c with callees run on cpu2 (real bytes)."""
    m = dict(ram)
    if m.get(C2D5, 0) != 0:
        return m
    if m.get(C2D6, 0) == 0:
        if m.get(C2D8, 0) != 0x5A:
            m[C2D8] = 0x5A
            m[C2D1] = 0x0C
            cpu2.call(UPD, r4=0x0C, ram=dict(m))
            m = dict(cpu2.ram)
            m[C2D7] = 1
            m[C2D6] = 1
        else:
            m[C2D5] = 1
        return m
    was_busy = m.get(C2D7, 0)
    cpu2.call(DISP, r4=m.get(C2D1, 0), ram=dict(m))
    m = dict(cpu2.ram)
    if m.get(C2F8, 0) == 1:
        m[C2D2] = 0
        if was_busy:
            m[C2D7] = 0
            m[C2D1] = 3
            cpu2.call(UPD, r4=3, ram=dict(m))
            m = dict(cpu2.ram)
        else:
            m[C2D1] = 0
            m[C2D5] = 1
            m[C2D6] = 0
    return m


def seed_ram(rng):
    m = {}
    for a in (C2D5, C2D6, C2D7, C2D2, C2D1, C2D8, C2F8, C2FB, C511):
        m[a] = rng.randint(0, 255)
    for a in WORK:
        m[a] = rng.randint(0, 255)
    for a in range(0xFFFFC2FE, 0xFFFFC2FE + 0x40):   # E2 shadow primary
        m[a] = rng.randint(0, 255)
    for a in range(0xFFFFC3FE, 0xFFFFC3FE + 0x40):   # E2 shadow complement
        m[a] = rng.randint(0, 255)
    for a in (0xFFFFC4FE, 0xFFFFC4FF, 0xFFFFC500, 0xFFFFC501, 0xFFFFC506,
              0xFFFFC507, 0xFFFFC50C, 0xFFFFC50F, 0xFFFFC510, 0xFFFFC514,
              0xFFFFC515, 0xFFFFC516):
        m[a] = rng.randint(0, 255)
    return m


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    cpu2 = SH2(rom)          # second instance: real callee bytes
    seeds = (0x37120, 0xC2D5, 0xC2D1, 0x5EED, 0x13579)
    total = fails = 0

    for seed in seeds:
        rng = random.Random(seed)
        for _ in range(N):
            kind = _ % 8
            ram = seed_ram(rng)
            if kind == 0:                 # init done -> early return
                ram[C2D5] = 1
            elif kind == 1:               # not armed, dirty -> init path
                ram[C2D5], ram[C2D6] = 0, 0
                ram[C2D8] = rng.choice([0x00, 0x5A, 0x7F, 0xFF])
            elif kind == 2:               # not armed, clean -> init done
                ram[C2D5], ram[C2D6], ram[C2D8] = 0, 0, 0x5A
            elif kind == 3:               # armed, busy, write complete
                ram[C2D5], ram[C2D6], ram[C2D7] = 0, 1, 1
                ram[C2F8], ram[C2D2], ram[C511] = 1, 0, 1
                ram[C2D1] = 0x0C
            elif kind == 4:               # armed, not busy, write complete
                ram[C2D5], ram[C2D6], ram[C2D7] = 0, 1, 0
                ram[C2F8], ram[C2D2], ram[C511] = 1, 0, 1
                ram[C2D1] = 0x0C
            elif kind == 5:               # armed, queue flag set, complete
                ram[C2D5], ram[C2D6] = 0, 1
                ram[C2F8], ram[C2D2], ram[C511] = 1, 1, rng.randint(0, 1)
                ram[C2D7] = rng.randint(0, 1)
                ram[C2D1] = rng.choice([0x0C, 3, 0x2A])
            elif kind == 6:               # armed, write not complete
                ram[C2D5], ram[C2D6] = 0, 1
                ram[C2F8] = 0
                ram[C511] = rng.randint(0, 1)
                ram[C2D7] = rng.randint(0, 1)
                ram[C2D1] = rng.choice([0x0C, 3, 0x2A])
            else:                         # armed, fully random
                ram[C2D5], ram[C2D6] = 0, 1
                ram[C2F8] = rng.randint(0, 1)
                ram[C511] = rng.randint(0, 1)
                ram[C2D7] = rng.randint(0, 1)
                ram[C2D1] = rng.randint(0, 255)

            want = model(cpu2, ram)
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
                    print('MISMATCH seed=0x%X kind=%d: %s' %
                          (seed, kind, {k: (hex(g), hex(e))
                                        for k, g, e in bad[:12]}))
            total += 1
        if fails >= 5:
            break

    if fails:
        print('\nFAIL ImmoUpdateRelated @0x37120  (%d mismatches / %d inputs)'
              % (fails, total))
        sys.exit(1)
    print('OK  ImmoUpdateRelated @0x37120  (%d inputs, 0 mismatches)' % total)
    sys.exit(0)


if __name__ == '__main__':
    main()
