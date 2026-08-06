#!/usr/bin/env python3
"""test_getEngineCrankingState_0x1477C.py

Differential test for ROM 0x1477C (60E0FC00.bin) — candidate lift
c/getEngineCrankingState_0x1477C.c.

Runs the ACTUAL ROM bytes of 0x1477C in tools/sh2emu.py over seeded RAM states
oracle) and compares the full post-call RAM overlay (byte-exact) plus the
return register r0 against a Python reference model.

NOTE: candidate verification — the function has a deep sub-call chain
(0x1477C -> 0x20AC -> 0x2624 float-table index search + 0x26B0 byte lerp)
which the reference models line-for-line with single-precision rounding.
If this cannot be made byte-exact the function is EXCLUDED from the lift.

Semantics (see lift header):
  b = u8@0xFFFFA79D ; fr4 = f32@0xFFFFB594
  if b != 0: u8@FFFFA79D = (b - 1) & 0xFF      (countdown)
  v = u8@0xFFFFA79E ; r14 = v
  if fr4 > 500.0: r14 = 0 if fr4 > 300.0 else v
  else:
      r14 = 1
      if v == 0:
          u8@FFFFA79D = sub_0x20AC(f32@0xFFFFA9FC)   (byte via float tables)
  u8@0xFFFFA79E = r14
  if u8@FFFFA79D != 0: r14 = 0
  u8@0xFFFFA79C = r14
  r0 = subcall result if taken, else entry r0.

sub_0x20AC(x) = int(trunc( lerp_byte( idx(x), tblB ) )) & 0xFF where idx(x)
and fraction come from the descending float-table search sub_0x2624 over the
calibration table at 0x68C04 (w[0]=6, tblA@0x753F8, tblB@0x75410).

Run: python3 c/tests/test_getEngineCrankingState_0x1477C.py [N]
"""
import os, random, sys, struct, math

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2, ts

ROM = os.path.join(ROOT, 'roms', 'stock', '60E0FC00.bin')
ADDR = 0x1477C

A79D = 0xFFFFA79D
A79E = 0xFFFFA79E
A79C = 0xFFFFA79C
B594 = 0xFFFFB594
A9FC = 0xFFFFA9FC

STRUCT = 0x68C04
STACK_LO = 0xFFFFDE00
STACK_HI = 0xFFFFDF00

_ROM = open(ROM, 'rb').read()


def u16(a): return struct.unpack('>H', _ROM[a:a + 2])[0]
def u32(a): return struct.unpack('>I', _ROM[a:a + 4])[0]
def f32at(a): return struct.unpack('>f', _ROM[a:a + 4])[0]


def f32m(m, a):
    return struct.unpack('>f', bytes(m.get(a + i, 0) for i in range(4)))[0]


def sub_2624(P0, tblA, f0):
    """0x2624: descending float-table index search + fraction.

    fcmp/gt Fm,Fn compares FRn > FRm (opcode F105 -> fr1 > fr0), i.e. the
    search walks DOWN from index P0+255 while T[idx] > f0, then interpolates
    between T[idx] and T[idx+4].  Stops at idx==0 -> (0, 0.0)."""
    idx = ((P0 - 1) << 2) & 0xFFFFFFFF      # add #0xFF sign-extends: P0-1
    if f32at(tblA + idx) <= f0:                   # !(T[idx] > f0) -> bf/s 0x264C
        return ((idx >> 2) & 0xFFFFFFFF), 0.0     # rts delay fldi0 fr0
    while True:
        if idx == 0:                              # 0x2630 bt/s (r0==0)
            return 0, 0.0
        idx = (idx - 4) & 0xFFFFFFFF
        fr1 = f32at(tblA + idx)                   # already single-precision
        if fr1 <= f0:                             # !(T[idx] > f0) -> exit loop
            fr0 = ts(f0 - fr1)                    # 0x263C fsub
            fr2 = ts(f32at(tblA + (idx + 4) & 0xFFFFFFFF) - fr1)   # 0x2640/0x2644
            fr0 = ts(fr0 / fr2)                   # 0x2646 fdiv
            return ((idx >> 2) & 0xFFFFFFFF), fr0


def sub_26B0(offset, tblB, frac):
    """0x26B0: two-byte lerp at tblB+offset, fraction frac (single rounding)."""
    p = tblB + offset
    b0 = _ROM[p]
    fr2 = ts(float(b0))                           # float fpul,fr2 (always)
    if frac == 0.0:                               # fcmp/eq fr0,fr2 -> rts
        return fr2
    b1 = _ROM[p + 1]
    fr1 = ts(float(b1) - fr2)                     # fsub
    fr2 = ts(frac * fr1 + fr2)                    # fmac
    return fr2


def sub_20AC(x):
    """0x20AC: calibration-table float -> byte (r4 = 0x68C04)."""
    P0 = u16(STRUCT)
    tblA = u32(STRUCT + 4)
    tblB = u32(STRUCT + 8)
    idx, frac = sub_2624(P0, tblA, x)
    r = sub_26B0(idx, tblB, frac)
    return (int(math.trunc(r)) & 0xFFFFFFFF) & 0xFF   # ftrc ; r0 &= 0xFF


def ref(m, ini_r0):
    m = dict(m)
    r0 = ini_r0 & 0xFFFFFFFF
    b = m.get(A79D, 0) & 0xFF
    fr4 = f32m(m, B594)
    if b != 0:
        m[A79D] = (b - 1) & 0xFF
    v = m.get(A79E, 0) & 0xFF
    r14 = v
    if fr4 < 500.0:                       # fcmp/gt FR4,FR3 -> FR3>FR4 (500>fr4)
        if fr4 < 300.0:                   # fcmp/gt FR4,FR2 -> FR2>FR4 (300>fr4)
            r14 = 0
    else:
        r14 = 1
        if v == 0:
            x = f32m(m, A9FC)
            res = sub_20AC(x)
            m[A79D] = res & 0xFF
            r0 = res & 0xFF
    m[A79E] = r14 & 0xFF
    if (m.get(A79D, 0) & 0xFF) != 0:
        r14 = 0
    m[A79C] = r14 & 0xFF
    return m, r0 & 0xFFFFFFFF


FLOATS = [b'\x00\x00\x00\x00', b'\x3f\x80\x00\x00', b'\x41\x20\x00\x00',
          b'\x43\xfa\x00\x00', b'\x43\x96\x00\x00', b'\x42\xc8\x00\x00',
          b'\x3f\x00\x00\x00', b'\xc2\xc8\x00\x00', b'\x44\x7a\x00\x00']


def gen_state(rng):
    ram = {}
    for a in (A79D, A79E, A79C, 0xFFFFA7A0):
        ram[a] = rng.randrange(0, 256)
    for a, fb in ((B594, rng.choice(FLOATS)), (A9FC, rng.choice(FLOATS))):
        for i, by in enumerate(fb):
            ram[a + i] = by
    ini_r0 = rng.randrange(0, 256)
    return ram, ini_r0


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    rom = _ROM
    cpu = SH2(rom)
    seeds = (0x1477C, 0x20AC, 0x2624, 0x26B0, 0xA79E)
    total_fails = 0

    for seed in seeds:
        rng = random.Random(seed)
        fails = 0
        for it in range(N):
            ram, ini_r0 = gen_state(rng)
            want, want_r0 = ref(ram, ini_r0)
            try:
                cpu.call(ADDR, ram=ram, regs={'0': ini_r0})
            except Exception as e:
                print('EMULATOR EXC seed=0x%X iter=%d: %s' % (seed, it, e))
                fails += 1
                break
            bad = []
            allk = set(want.keys()) | set(cpu.ram.keys())
            for k in allk:
                if STACK_LO <= k <= STACK_HI:
                    continue
                if cpu.ram.get(k, 0) != want.get(k, 0):
                    bad.append((k, cpu.ram.get(k, 0), want.get(k, 0)))
            if bad or cpu.r[0] != want_r0:
                print('MISMATCH seed=0x%X iter=%d: r0=%d want_r0=%d %s' %
                      (seed, it, cpu.r[0], want_r0,
                       {hex(k): (hex(g), hex(e)) for k, g, e in bad[:8]}))
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
    print('OK  0x1477C getEngineCrankingState '
          '(%d random inputs across %d seeds)' % (N * len(seeds), len(seeds)))
    print('\nAll getEngineCrankingState tests passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()