#!/usr/bin/env python3
"""test_finalTrailingTimingStuff_0x132CA.py

Differential test for ROM 0x132CA (60E0FC00.bin) — lift
c/finalTrailingTimingStuff_0x132CA.c.

Runs the ACTUAL ROM bytes of 0x132CA (no sub-calls) in tools/sh2emu.py over
seeded RAM states (the oracle) and compares the full post-call RAM overlay
(byte-exact, task-stack window 0xFFFFDE00..DF00 skipped) plus the return
register r0 against a Python reference model that mirrors the C lift
line-for-line.

Entry-point / range note: 0x132CA IS the real entry point (function-pointer
slot @0x144E4 of the engineControlCalculateTiming dispatcher 0x141FC table,
right after the leading twin 0x1326E @0x144E0; valid entry — no fall-through,
no incoming branches).  The symbols CSV row finalTrailingTimingStuff is kept
(no "?" to drop after verify) and the source set to c-lift.

Key semantic facts (see the lift header): gated by u8@ROM 0x6E0F1:
  flag==0: f32@A6E8 = f32@A634
  flag==1: f32@A6DC = (A6E8 + A6F4) + A6FC ; f32@A6E0 = (A6E8 + A6F8) + A700
  flag==2: f32@A6DC = f32@ROM 0x6E100   ; f32@A6E0 = f32@ROM 0x6E104
r0 at return == (flag & 0xFF) on every path.  Single-precision rounding is
applied at each fadd (ts), matching the emulator.

Run: python3 c/tests/test_finalTrailingTimingStuff_0x132CA.py [N]
     (N = random inputs per seed; default 100000 -> 500000 across 5 seeds;
      phase 2/3 use N/5 per seed on the patched ROM0x)
"""
import os, random, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2, ts

ROM = os.path.join(ROOT, 'roms', 'stock', '60E0FC00.bin')
ADDR = 0x132CA

FLAG_ROM = 0x0006E0F1   # u8 mode flag byte in ROM
C_R1     = 0x0006E100   # f32 rotor1 const (0.0 in this ROM)
C_R2     = 0x0006E104   # f32 rotor2 const (0.0 in this ROM)

A634 = 0xFFFFA634   # f32 trailing derate base (input)
A6E8 = 0xFFFFA6E8   # f32 per-rotor base/output
A6DC = 0xFFFFA6DC   # f32 rotor1 final trailing
A6E0 = 0xFFFFA6E0   # f32 rotor2 final trailing
A6F4 = 0xFFFFA6F4   # f32 rotor1 addend 1
A6F8 = 0xFFFFA6F8   # f32 rotor2 addend 1
A6FC = 0xFFFFA6FC   # f32 shared addend 1
A700 = 0xFFFFA700   # f32 shared addend 2

STACK_LO = 0xFFFFDE00
STACK_HI = 0xFFFFDF00


def f32_at(rom, a):
    return struct.unpack('>f', rom[a:a + 4])[0]


def setf(m, a, v):
    for i, b in enumerate(struct.pack('>f', ts(v))):
        m[a + i] = b


def gf(m, a):
    return struct.unpack('>f', bytes(m.get(a + i, 0) for i in range(4)))[0]


def ref(m, rom, flag):
    """Mirror of finalTrailingTimingStuff_0x132CA(). Returns (RAM dict, r0)."""
    m = dict(m)
    if flag == 0:
        setf(m, A6E8, gf(m, A634))
    if flag == 1:
        setf(m, A6DC, ts(ts(gf(m, A6E8) + gf(m, A6F4)) + gf(m, A6FC)))
        setf(m, A6E0, ts(ts(gf(m, A6E8) + gf(m, A6F8)) + gf(m, A700)))
    elif flag == 2:
        setf(m, A6DC, f32_at(rom, C_R1))
        setf(m, A6E0, f32_at(rom, C_R2))
    return m, flag & 0xFF


def pick_f(rng):
    return rng.choice([
        rng.uniform(-40, 40),
        rng.uniform(-1e-3, 1e-3),
        rng.uniform(-1e-30, 1e-30),
        -0.0, 0.0, 1.0, -1.0, 1e-30, -1e-30, 3.4e38, -3.4e38, 1e-40, -1e-40,
    ])


def gen_state(rng):
    """Random RAM: every f32 the function can read/write is varied so a missed
    or mis-sourced read/write is caught."""
    ram = {}
    for a in (A634, A6E8, A6DC, A6E0, A6F4, A6F8, A6FC, A700):
        setf(ram, a, pick_f(rng))
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
                if STACK_LO <= k <= STACK_HI:
                    continue
                if cpu.ram.get(k, 0) != want.get(k, 0):
                    bad.append((k, cpu.ram.get(k, 0), want.get(k, 0)))
            if bad or cpu.r[0] != want_r0:
                print('MISMATCH %s seed=0x%X iter=%d: r0=%d want_r0=%d %s' %
                      (label, seed, it, cpu.r[0], want_r0,
                       {hex(k): (hex(g), hex(e)) for k, g, e in bad[:10]}))
                print('  A634=%r A6E8=%r A6F4=%r A6F8=%r A6FC=%r A700=%r' %
                      (gf(ram, A634), gf(ram, A6E8), gf(ram, A6F4),
                       gf(ram, A6F8), gf(ram, A6FC), gf(ram, A700)))
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
    assert rom[FLAG_ROM] == 0x00, 'stock ROM flag byte @0x6E0F1 != 0'
    assert f32_at(rom, C_R1) == 0.0
    assert f32_at(rom, C_R2) == 0.0

    seeds = (0x132CA, 0x1326E, 0x13368, 0xA6DC, 0xA6E8)
    total = 0

    print('== phase 1: stock ROM (flag==0, copy path) ==')
    total += run_phase(rom, 0, 'stock ', seeds, N)

    print('== phase 2: patched ROM (flag==1, compute path) ==')
    r = bytearray(rom)
    r[FLAG_ROM] = 0x01
    rom1 = bytes(r)
    total += run_phase(rom1, 1, 'patch1', seeds, max(1, N // 5))

    print('== phase 3: patched ROM (flag==2, const path) ==')
    r = bytearray(rom)
    r[FLAG_ROM] = 0x02
    rom2 = bytes(r)
    total += run_phase(rom2, 2, 'patch2', seeds, max(1, N // 5))

    if total:
        print('\n%d FAILURE(S)' % total)
        sys.exit(1)
    print('OK  0x132CA finalTrailingTimingStuff '
          '(%d random inputs across %d seeds x3 paths)' %
          (N * len(seeds), len(seeds)))
    print('\nAll finalTrailingTimingStuff_0x132CA tests passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()