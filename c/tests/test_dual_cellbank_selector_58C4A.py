#!/usr/bin/env python3
"""test_dual_cellbank_selector_58C4A.py

Differential test for ROM 0x58C4A (60E1D400.bin) — lift
c/dual_cellbank_selector_58C4A.c.

Runs the ACTUAL ROM bytes of 0x58C4A in tools/sh2emu.py over seeded RAM states
and compares the full post-call RAM overlay against a Python model.

All five side-effecting callees are executed in a second emulator instance
(cpu2.call, real ROM bytes), so the 0x3ED3C validation, the fault flag side
effect and the 0x3EE68 cell-bank encoding match the machine exactly:
   - 0x58C38 refresh_redundant_byte (leaf, no args)
   - 0x58C98 cellbankA_reset (leaf, no args)
   - 0x58D1C cellbankB_reset (leaf, no args)
   - 0x58C9E cellbankA_recalc (leaf, no args)
   - 0x58D58 cellbankB_recalc (leaf, no args)

Model flow (verified from the disassembly):
   1. prev = RAM8@0xFFFFD26C
   2. refresh_redundant_byte_0x58C38()      (writes D26C, maybe fault C6AC)
   3. sel = RAM8@0xFFFFD201
      if sel == 1: cellbankA_reset(); cellbankB_reset(); return
   4. elif prev == 0 and RAM8@0xFFFFD26C == 1:
        cellbankA_recalc(); cellbankB_recalc(); return
   5. else: nothing

Run: python3 c/tests/test_dual_cellbank_selector_58C4A.py [N]
"""
import os, random, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ADDR = 0x58C4A
A_D26C = 0xFFFFD26C
A_D201 = 0xFFFFD201
A_8FF2 = 0xFFFF8FF2
A_8FF3 = 0xFFFF8FF3


def gen_state(rng):
    ram = {}
    ram[A_D26C] = rng.randint(0, 255)
    ram[A_D201] = rng.randint(0, 255)
    # redundant pair read by 0x58C38 via 0x3ED3C (mostly valid)
    v = rng.randint(0, 255)
    if rng.random() < 0.8:
        ram[A_8FF2] = v
        ram[A_8FF3] = (~v) & 0xFF
    else:
        ram[A_8FF2] = rng.randint(0, 255)
        ram[A_8FF3] = rng.randint(0, 255)
    # float calibrations used on the recalc path
    for a in (0xFFFFC760, 0xFFFFC764, 0xFFFFC768, 0xFFFFC76C):
        fb = __import__('struct').pack('>f', rng.uniform(-1e3, 1e3))
        for i in range(4):
            ram[a + i] = fb[i]
    return ram


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    cpu2 = SH2(rom)
    rng = random.Random(0x58C4A)
    fails = 0

    for it in range(N):
        ram = gen_state(rng)
        input_keys = set(ram.keys())

        # ---- model ----
        m = dict(ram)
        prev = m.get(A_D26C, 0)
        cpu2.call(0x58C38, ram=dict(m)); m = dict(cpu2.ram)
        sel = m.get(A_D201, 0)
        if sel == 1:
            cpu2.call(0x58C98, ram=dict(m)); m = dict(cpu2.ram)
            cpu2.call(0x58D1C, ram=dict(m)); m = dict(cpu2.ram)
        elif prev == 0 and m.get(A_D26C, 0) == 1:
            cpu2.call(0x58C9E, ram=dict(m)); m = dict(cpu2.ram)
            cpu2.call(0x58D58, ram=dict(m)); m = dict(cpu2.ram)

        # ---- run ROM ----
        cpu.call(ADDR, ram=dict(ram))
        bad = []

        def stack(k):
            return 0xFFFFDE00 <= k <= 0xFFFFDF00

        for k, e in m.items():
            if stack(k):
                continue
            if cpu.ram.get(k, 0) != e:
                bad.append((k, cpu.ram.get(k, 0), e))
        for k in cpu.ram:
            if k in m or k in input_keys or stack(k):
                continue
            bad.append((k, cpu.ram.get(k, 0), '<none>'))
        if bad:
            print('MISMATCH iter=%d prev=%d sel=%d D26C_after=%d: %s' %
                  (it, prev, sel, m.get(A_D26C, 0),
                   {hex(b[0]): (hex(b[1]), b[2] if isinstance(b[2], str) else hex(b[2])) for b in bad[:10]}))
            fails += 1
            if fails >= 3:
                break

    if fails:
        print('%d FAILURE(S) dual_cellbank_selector_58C4A' % fails)
        sys.exit(1)
    print('OK  0x58C4A dual_cellbank_selector_58C4A  (%d inputs)' % N)
    sys.exit(0)


if __name__ == '__main__':
    main()