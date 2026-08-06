#!/usr/bin/env python3
"""test_calculateDriverConditions_0x42296.py

Differential test for ROM 0x42296 (60E0FC00.bin) — lift
c/calculateDriverConditions_0x42296.c.

Runs the ACTUAL ROM bytes of 0x42296 in tools/sh2emu.py over seeded RAM
states (the oracle) and compares the full post-call RAM overlay (byte-exact,
task-stack window 0xFFFFDE00..DF00 skipped) plus the return register r0
against a Python reference model that mirrors the C lift line-for-line.

Entry/range: 0x42296 IS the real entry (dispatcher slot @0x14454 of the
engineControlCalculateTiming table; preceding fn calculateThrottlePercent-
DuringLift 0x042230 ends rts @0x42292; next fn starts exactly at CSV end
0x42330). CSV range 0x42296..0x42330 CORRECT — no phantom rows.

Semantics (see lift header): out u8@FFFFC947 =
  (u8@B580==1 && u8@B586==0)
  || (f32@0x7A1D8(15.0) > f32@BFBC && u8@C940!=0 && u8@AD7C==0)
  || (u8@B580==0 && u8@C94C==1 && u8@ROM0x7A17C==1).
r0 on return is path-dependent (see ref), carried byte-exact.

Run: python3 c/tests/test_calculateDriverConditions_0x42296.py [N]
     (N = random inputs per seed; default 100000 -> 500000 across 5 seeds)
"""
import os, random, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E0FC00.bin')
ADDR = 0x42296

# ---- RAM addresses (see c/calculateDriverConditions_0x42296.c) ----
B580  = 0xFFFFB580   # u8 condition gate in
B586  = 0xFFFFB586   # u8 paired gate (==0)
BFBC  = 0xFFFFBFBC   # f32 sampled float
C940  = 0xFFFFC940   # u8 gate (!=0)
AD7C  = 0xFFFFAD7C   # u8 sys status bit latch
C94C  = 0xFFFFC94C   # u8 gate (==1)
C947  = 0xFFFFC947   # u8 driver-condition flag out

ROMF = 0x0007A1D8    # f32 15.0 threshold
ROMB = 0x0007A17C    # u8 1 enable byte

STACK_LO = 0xFFFFDE00
STACK_HI = 0xFFFFDF00


def r32(m, a):
    return struct.unpack('>f', bytes(m.get(a + i, 0) for i in range(4)))[0]


def ref(m, rom):
    """Line-for-line mirror of calculateDriverConditions_0x42296() with
    exact r0 tracking. Returns (full RAM-effect dict, expected r0)."""
    m = dict(m)
    b580 = m.get(B580, 0) & 0xFF
    b586 = m.get(B586, 0) & 0xFF
    c940 = m.get(C940, 0) & 0xFF
    ad7c = m.get(AD7C, 0) & 0xFF
    c94c = m.get(C94C, 0) & 0xFF
    fbfc = r32(m, BFBC)
    rombyte = rom[ROMB] & 0xFF          # u8@0x7A17C == 1 (const, read-only)

    r4 = b580
    r0 = b580                            # entry extu.b r4,r0
    if r4 == 1:
        if b586 == 0:                    # bt @0x422AA -> path 1
            m[C947] = 1
            return m, r0                 # r0 = b580 & 0xFF == 1
        # else fall through to 0x422AE
    else:
        pass                              # bf @0x422A0 (delay mov r4=r0 already)
    # ---- 0x422AE merge ----
    f15 = struct.unpack('>f', rom[ROMF:ROMF + 4])[0]   # 15.0
    if fbfc > f15:                     # fcmp/gt: T=(FR2>FR3)=(BFBC>15.0)
        r0 = 0xFFFFBFBC                 # mov.w 0x42310,r0 @0x422B0
        if c940 != 0:                   # tst C940 (bt @0x422C2 if 0)
            r0 = 0xFFFFAD7C            # mov.w 0x42314,r0 @0x422C6
            if ad7c == 0:              # tst AD7C (bt @0x422CC -> path 2)
                m[C947] = 1
                return m, r0          # r0 = 0xFFFFAD7C
            d0_r0 = 0xFFFFAD7C         # AD7C!=0 -> fall to D0
        else:
            d0_r0 = 0xFFFFBFBC         # C940==0 -> D0, r0 unchanged
    else:
        r0 = 0xFFFFBFBC                # fcmp false -> D0 (r0 set @0x422B0)
        d0_r0 = 0xFFFFBFBC
    # ---- 0x422D0 gate ----
    if r4 != 0:                        # tst r4 ; bf @0x422F4 (out=0)
        m[C947] = 0
        return m, d0_r0
    # ---- 0x422D6: u8@C94C == 1 ----
    r0 = c94c & 0xFF                   # mov.b @r3,r0 + extu
    if c94c != 1:                      # bf @0x422F4 (out=0)
        m[C947] = 0
        return m, r0
    # ---- 0x422E2: u8@ROM7A17C == 1 ----
    r0 = rombyte & 0xFF                # mov.b @r2,r0 + extu
    if r0 != 1:                        # bf @0x422F4 (out=0)
        m[C947] = 0
    else:
        m[C947] = 1                    # fall @0x422EE (path 3)
    return m, r0


def gen_state(rng):
    """Random seeded RAM. Each byte independently 0/1/other so all gates and
    every r0 leaf are exercised; f32@BFBC samples a wide range incl NaN and
    the exact threshold 15.0 so the fcmp/gt NaN behavior is hit."""
    def bbyte():
        r = rng.random()
        if r < 0.6:
            return rng.choice([0, 1])
        elif r < 0.85:
            return int(rng.randint(2, 255))
        else:
            return rng.choice([0x7F, 0x80, 0xFF])
    ram = dict((a, bbyte()) for a in (B580, B586, C940, AD7C, C94C, C947))
    r = rng.random()
    if r < 0.7:
        v = float(rng.uniform(-200, 200))
    elif r < 0.85:
        v = float(rng.choice([15.0, 0.0, 15.5, 14.5, -1.0, 1e9]))
    elif r < 0.94:
        v = float('nan')
    else:
        v = float(rng.uniform(-10, 40))
    raw = struct.pack('>f', v)
    for i, b in enumerate(raw):
        ram[BFBC + i] = b
    return ram


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    rom = open(ROM, 'rb').read()
    # sanity checks on the ROM constants the model depends on
    assert struct.unpack('>f', rom[0x7A1D8:0x7A1DC])[0] == 15.0
    assert rom[0x7A17C] == 1
    cpu = SH2(rom)
    seeds = (0x42296, 0x422B0, 0x7A1D8, 0xFFFFC947, 0xFFFFB580)
    total_fails = 0
    for seed in seeds:
        rng = random.Random(seed)
        fails = 0
        for it in range(N):
            ram = gen_state(rng)
            want, want_r0 = ref(ram, rom)
            cpu.call(ADDR, ram=ram)
            bad = []
            for k in set(k for k in want if isinstance(k, int)) | set(cpu.ram.keys()):
                if STACK_LO <= k <= STACK_HI:
                    continue
                if cpu.ram.get(k, 0) != want.get(k, 0):
                    bad.append((k, cpu.ram.get(k, 0), want.get(k, 0)))
            if bad or cpu.r[0] != want_r0:
                print('MISMATCH seed=0x%X iter=%d r0=%d want_r0=%d %s' %
                      (seed, it, cpu.r[0], want_r0,
                       {hex(k): (hex(g), hex(e)) for k, g, e in bad[:10]}))
                print('  B580=%d B586=%d BFBC=%r C940=%d AD7C=%d C94C=%d' %
                      (ram.get(B580, 0), ram.get(B586, 0), r32(ram, BFBC),
                       ram.get(C940, 0), ram.get(AD7C, 0), ram.get(C94C, 0)))
                fails += 1
                if fails >= 3:
                    break
        print('  seed 0x%X: %d inputs, fails=%d' % (seed, N, fails))
        total_fails += fails
        if total_fails:
            break
    print()
    if total_fails:
        print('%d FAILURE(S)' % total_fails)
        sys.exit(1)
    print('OK  0x42296 calculateDriverConditions '
          '(%d random inputs across %d seeds)' % (N * len(seeds), len(seeds)))
    print('\nAll calculateDriverConditions_0x42296 tests passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()