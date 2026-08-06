#!/usr/bin/env python3
"""test_setPerRotorTimingValuesTrailing_0x1470A.py

Differential test for ROM 0x1470A (60E0FC00.bin) — lift
c/setPerRotorTimingValuesTrailing_0x1470A.c.

Runs the ACTUAL ROM bytes of 0x1470A in tools/sh2emu.py over seeded RAM states
(the oracle) and compares the full post-call RAM overlay (byte-exact) plus the
return register r0 against a Python reference model that mirrors the C lift
line-for-line.

Entry-point / bank note: 0x1470A IS the real entry point — the function-pointer
slot @0x144EC of the engineControlCalculateTiming dispatcher (0x141FC) dispatch
table, immediately after the leading twin setPerRotorTimingValuesLeading
(0x146D4, slot @0x144E8).  Valid entry (preceding function ends rts @0x14706;
no branches into the body).  The symbols CSV row is setPerRotorTimingValues
Trailing (kept, no "?" to drop); source updated to c-lift after this verify.

Key semantic facts (see the lift header): void per-rotor trailing writer.
  if u8@ROM 0x6E0F1 == 0:   f32@A794 = f32@A634 + f32@ROM 0x753E4 (0.0)
                             f32@A798 = f32@A634 + f32@ROM 0x753E8 (0.0)
  else:                     f32@A794 = f32@A6DC ;  f32@A798 = f32@A6E0
r0 is never touched by the function -> expected r0 == 0 on both paths.
The stock ROM flag byte is 0, so phase 1 exercises the add-path; phase 2 runs
the SAME code bytes with an in-memory patched copy of the ROM (flag byte @0x6E0F1
forced to 1) so the fallback copy path is verified against the emulator too.

Run: python3 c/tests/test_setPerRotorTimingValuesTrailing_0x1470A.py [N]
     (N = random inputs per seed; default 100000 -> 500000 across 5 seeds;
      phase 2 uses N/5 per seed on the patched ROM)
"""
import os, random, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2, ts

ROM = os.path.join(ROOT, 'roms', 'stock', '60E0FC00.bin')
ADDR = 0x1470A

FLAG_ROM = 0x0006E0F1        # u8 enable flag in ROM (cal constant)
ADD1_ROM = 0x000753E4        # f32 add constant 1 (0.0 in this ROM)
ADD2_ROM = 0x000753E8        # f32 add constant 2 (0.0 in this ROM)

IN_BASE_A634 = 0xFFFFA634    # f32 per-rotor trailing base input
IN_FB_A6DC   = 0xFFFFA6DC    # f32 fallback copy source 1
IN_FB_A6E0   = 0xFFFFA6E0    # f32 fallback copy source 2
OUT_A794     = 0xFFFFA794    # f32 trailing output 1
OUT_A798     = 0xFFFFA798    # f32 trailing output 2

STACK_LO = 0xFFFFDE00        # task stack window (skipped in the compare)
STACK_HI = 0xFFFFDF00


def f32_at(rom, a):
    return struct.unpack('>f', rom[a:a + 4])[0]


def setf(m, a, v):
    for i, b in enumerate(struct.pack('>f', ts(v))):
        m[a + i] = b


def gf(m, a):
    return struct.unpack('>f', bytes(m.get(a + i, 0) for i in range(4)))[0]


def ref(m, rom, flag):
    """Line-for-line mirror of setPerRotorTimingValuesTrailing_0x1470A().
    Returns (RAM-effect dict, expected r0)."""
    m = dict(m)
    if flag == 0:
        setf(m, OUT_A794, ts(gf(m, IN_BASE_A634) + f32_at(rom, ADD1_ROM)))
        setf(m, OUT_A798, ts(gf(m, IN_BASE_A634) + f32_at(rom, ADD2_ROM)))
    else:
        setf(m, OUT_A794, gf(m, IN_FB_A6DC))
        setf(m, OUT_A798, gf(m, IN_FB_A6E0))
    return m, 0


def pick_f(rng):
    """Float pool: uniform spans around the interesting scales plus edge cases."""
    return rng.choice([
        rng.uniform(-40, 40),
        rng.uniform(-1e-3, 1e-3),
        rng.uniform(-1e-30, 1e-30),
        -0.0, 0.0, 1.0, -1.0, 1e-30, -1e-30, 3.4e38, -3.4e38, 1e-40, -1e-40,
    ])


def gen_state(rng):
    """Random seeded RAM: trailing base value varies; outputs and the fallback
    sources are junk so a missed write / wrong-source copy is caught."""
    ram = {}
    setf(ram, IN_BASE_A634, pick_f(rng))
    setf(ram, IN_FB_A6DC, pick_f(rng))
    setf(ram, IN_FB_A6E0, pick_f(rng))
    setf(ram, OUT_A794, pick_f(rng))
    setf(ram, OUT_A798, pick_f(rng))
    return ram


def run_phase(rom, flag, label, seeds, N):
    cpu = SH2(rom)
    total_fails = 0
    for seed in seeds:
        rng = random.Random(seed)
        fails = 0
        for it in range(N):
            ram = gen_state(rng)
            want, want_r0 = ref(ram, rom, flag)
            try:
                cpu.call(ADDR, ram=ram)
            except Exception as e:
                print('EMULATOR EXC %s seed=0x%X iter=%d: %s' % (label, seed, it, e))
                fails += 1
                break
            bad = []
            allk = set(k for k in want if isinstance(k, int)) | set(cpu.ram.keys())
            for k in allk:
                if STACK_LO <= k <= STACK_HI:      # task stack area
                    continue
                if cpu.ram.get(k, 0) != want.get(k, 0):
                    bad.append((k, cpu.ram.get(k, 0), want.get(k, 0)))
            if bad or cpu.r[0] != want_r0:
                print('MISMATCH %s seed=0x%X iter=%d: r0=%d want_r0=%d %s' %
                      (label, seed, it, cpu.r[0], want_r0,
                       {hex(k): (hex(g), hex(e)) for k, g, e in bad[:10]}))
                print('  A634=%r' % gf(ram, IN_BASE_A634))
                fails += 1
                if fails >= 3:
                    break
        print('  %s seed 0x%X: %d inputs, fails=%d' % (label, seed, N, fails))
        total_fails += fails
        if total_fails:
            break
    return total_fails


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    rom = open(ROM, 'rb').read()
    assert rom[FLAG_ROM] == 0x00, "stock ROM flag byte @0x6E0F1 != 0"

    seeds = (0x1470A, 0x146D4, 0x1476C, 0xA634, 0xA794)
    total = 0

    print('== phase 1: stock ROM (flag==0, add-path) ==')
    total += run_phase(rom, 0, 'stock ', seeds, N)

    print('== phase 2: patched ROM (flag==1, fallback copy path) ==')
    rom1 = bytearray(rom)
    rom1[FLAG_ROM] = 0x01
    rom1 = bytes(rom1)
    total += run_phase(rom1, 1, 'patch ', seeds, max(1, N // 5))

    if total:
        print('\n%d FAILURE(S)' % total)
        sys.exit(1)
    print('OK  0x1470A setPerRotorTimingValuesTrailing '
          '(%d random inputs across %d seeds x2 paths)' %
          (N * len(seeds), len(seeds)))
    print('\nAll setPerRotorTimingValuesTrailing_0x1470A tests passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()
