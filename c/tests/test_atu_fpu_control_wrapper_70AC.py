#!/usr/bin/env python3
"""test_atu_fpu_control_wrapper_70AC.py

Differential test for ROM 0x70AC (60E1D400.bin) — lift c/atu_fpu_control_wrapper.c.

Runs the ACTUAL ROM bytes of 0x70AC in tools/sh2emu.py over seeded random RAM
+ SR states and compares the post-call RAM overlay, SR and r15 against a Python
reference model.

Confirmed net semantics from the disassembly (0x70AC..0x70CE, 60E1D400):
  * sub-call chain (real ROM, not stubbed):
      1. setSR_PARAM @0x2054 (r4 = &spad, r5 = 0xE0)  -> SR = max(SR&0xF0, 0xE0),
         saves (SR_in & 0xF0) to the stack pad.
      2. setRegister_REG_BIT_VAL @0x4BBC (r4 = 0xF74E, r5 = 0x0100, r6 = 1)
         -> OR: RAM16[0xFFFFF74E] |= 0x0100.
      3. loadStatusRegister_ADDR @0x2064 (r4 = saved) -> SR = SR_in & 0xF0.
  * r15 restored to entry value; pr restored.

Run: python3 c/tests/test_atu_fpu_control_wrapper_70AC.py [N]
     (N = random inputs per seed; default 5000 -> 25000 across 5 seeds)
"""
import os, random, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ADDR = 0x70AC
MASK = 0xFFFFFFFF

FPU_REG = 0xFFFFF74E        # u16 control register the wrapper ORs into
BIT = 0x0100


def rb(m, a):
    a &= MASK
    v = m.get(a)
    return v if v is not None else 0


def rd(m, a, n):
    v = 0
    for i in range(n):
        v = (v << 8) | rb(m, a + i)
    return v


def wr(m, a, n, v):
    for i in range(n):
        m[(a + i) & MASK] = (v >> (8 * (n - 1 - i))) & 0xFF


def ref(ram, sr_in):
    """Mirror of atu_fpu_control_wrapper: OR 0x0100 into the FPU reg, SR_out =
    SR_in & 0xF0.  The stack temp/pushes sit in the excluded stack region and
    leave no other RAM effect."""
    m = dict(ram)
    wr(m, FPU_REG, 2, rd(m, FPU_REG, 2) | BIT)
    return m, sr_in & 0xF0


def gen_state(rng):
    ram = {}
    ram[FPU_REG] = rng.getrandbits(8)
    ram[FPU_REG + 1] = rng.getrandbits(8)
    sr_in = rng.getrandbits(32)
    return ram, sr_in


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    seeds = (0x70AC, 0x2054, 0x4BBC, 0x2064, 0xF74E)
    total_fails = 0

    for seed in seeds:
        rng = random.Random(seed)
        fails = 0
        for it in range(N):
            ram, sr_in = gen_state(rng)
            want, want_sr = ref(ram, sr_in)
            try:
                cpu.call(ADDR, sr=sr_in, ram=ram)
            except Exception as e:
                print('EMULATOR EXC seed=0x%X iter=%d: %s' % (seed, it, e))
                fails += 1
                break
            got = cpu.ram
            bad = []
            for k in set(k for k in want if isinstance(k, int)) | set(got.keys()):
                if 0xFFFFDE00 <= k <= 0xFFFFDF00:      # task stack area
                    continue
                if got.get(k, 0) != want.get(k, 0):
                    bad.append((k, got.get(k, 0), want.get(k, 0)))
            if bad:
                print('MISMATCH seed=0x%X iter=%d sr_in=%08X: %s' %
                      (seed, it, sr_in,
                       {hex(k): (hex(g), hex(e)) for k, g, e in bad[:12]}))
                fails += 1
                if fails >= 3:
                    break
                continue
            if cpu.sr != want_sr:
                print('SR MISMATCH seed=0x%X iter=%d sr_in=%08X want=%08X got=%08X'
                      % (seed, it, sr_in, want_sr, cpu.sr))
                fails += 1
                if fails >= 3:
                    break
                continue
            if cpu.r[15] != 0xFFFFDF00:
                print('R15 MISMATCH seed=0x%X iter=%d got=%08X' % (seed, it, cpu.r[15]))
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
    print('OK  0x70AC atu_fpu_control_wrapper  (%d random inputs across %d seeds)'
          % (N * len(seeds), len(seeds)))
    sys.exit(0)


if __name__ == '__main__':
    main()