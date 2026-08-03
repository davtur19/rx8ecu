#!/usr/bin/env python3
"""test_Immo_Keygen_related_ADC_36AFC.py

Differential test for ROM 0x36AFC (60E1D400.bin) — lift c/Immo_Keygen_related_ADC.c.

Rolling-code / key generator.  Mixes three ADC samples with the previous mixer
state and a CRC-ish value from adc_read() to produce the next 32-bit code at
0xFFFFC278.

Inputs:
  adc_a = u16 @0xFFFF9F1C, adc_b = u16 @0xFFFF9F1E, adc_c = u16 @0xFFFF9F00
  ret   = adc_read(0xFFFF869C, 0)   (valid iff u16@0xFFFF86A0 or u16@0xFFFF86A2
          == ~(u16@0xFFFF869C + u16@0xFFFF869E) & 0xFFFF; else 0xFFFFC6AC = 1
          and ret = 0)
  state: w288 u16@0xFFFFC288, w28A u16@0xFFFFC28A, cnt u8@0xFFFFC293,
         fallback u32@0xFFFFC2DC | u32@0xFFFFC2E0

Semantics (verified against disasm 0x36B00..0x36BBA and the address
sign-extension of all mov.w literals):
  cnt  = (cnt + adc_a + (ret&0xFFFF)) & 0xFF
  guard1 (cmp/ge 0x36B3E, ALWAYS falls through): if w28A==0xFFFF cnt+=1;
         w28A = (w28A+1)&0xFFFF
  retval = ((ret>>16)&0xFFFF) + (int16)w288 + (int16)adc_b   -> r0
  w288   = retval & 0xFFFF
  guard2 (ALWAYS falls): cnt = (cnt+1)&0xFF
  w28A   = ((((ret&0x00FFFF00)>>8) + (int16)w28A + (int16)adc_c) & 0xFFFFFFFF)
  w288   = ((((adc_c&0xFF)<<8) + (adc_a&0xFF)) ^ w288) & 0xFFFF
  w28A   = (~((((adc_a&0xFF)<<8) + (adc_b&0xFF)) ^ w28A)) & 0xFFFF
  cnt    = (adc_b ^ cnt) & 0xFF
  combined = (w288<<16)|w28A; if 0 -> (u32@0xFFFFC2DC | u32@0xFFFFC2E0)
  publish u32@0xFFFFC278; store w288, w28A, cnt; return retval.

NOTE: the two "guards" are modeled as ALWAYS executing the increment blocks:
`cmp/ge Rm,Rn` on SH-2 compares 32-bit signed Rn >= Rm, and the ROM compares
the 32-bit complement of a 16-bit value (always negative) against a
0..0xFFFF value (always non-negative) -> false, so the guarded block always
runs.

Run: python3 c/tests/test_Immo_Keygen_related_ADC_36AFC.py [N]
     (N = random vectors per seed; default 5000 -> 25000 across 5 seeds)
"""
import os, random, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ADDR = 0x36AFC

A_ADC = 0xFFFF9F1C
B_ADC = 0xFFFF9F1E
C_ADC = 0xFFFF9F00
ADCREG = 0xFFFF8700   # functionally unused small constant, see below

W288 = 0xFFFFC288
W28A = 0xFFFFC28A
CNT  = 0xFFFFC293
OUT  = 0xFFFFC278
W2DC = 0xFFFFC2DC
W2E0 = 0xFFFFC2E0
C6AC = 0xFFFFC6AC


def rd16(m, a):
    return ((m.get(a, 0) & 0xFF) << 8) | (m.get(a + 1, 0) & 0xFF)


def rd32(m, a):
    return ((m.get(a, 0) << 24) | (m.get(a + 1, 0) << 16) |
            (m.get(a + 2, 0) << 8) | m.get(a + 3, 0))


def wr16(m, a, v):
    m[a] = (v >> 8) & 0xFF
    m[a + 1] = v & 0xFF


def wr32(m, a, v):
    m[a] = (v >> 24) & 0xFF
    m[a + 1] = (v >> 16) & 0xFF
    m[a + 2] = (v >> 8) & 0xFF
    m[a + 3] = v & 0xFF


def s16(v):
    v &= 0xFFFF
    return v - 0x10000 if v >= 0x8000 else v


def adc_read(m):
    """Mirror of adc_read(0x3EDBC) operating on 0xFFFF869C."""
    w0 = rd16(m, 0xFFFF869C) & 0xFFFF
    w2 = rd16(m, 0xFFFF869E) & 0xFFFF
    chk = (~((w0 + w2) & 0xFFFF)) & 0xFFFF
    c0 = rd16(m, 0xFFFF86A0) & 0xFFFF
    c1 = rd16(m, 0xFFFF86A2) & 0xFFFF
    if c0 == chk or c1 == chk:
        return rd32(m, 0xFFFF869C)
    m[C6AC] = 1
    return 0


def gen(m):
    """Mirror of c/Immo_Keygen_related_ADC.c."""
    m = dict(m)
    adc_a = rd16(m, A_ADC) & 0xFFFF
    adc_b = rd16(m, B_ADC) & 0xFFFF
    adc_c = rd16(m, C_ADC) & 0xFFFF
    ret = adc_read(m)
    w288 = rd16(m, W288) & 0xFFFF
    w28A = rd16(m, W28A) & 0xFFFF
    cnt = m.get(CNT, 0) & 0xFF

    cnt = ((ret & 0xFFFF) + adc_a + cnt) & 0xFF
    if w28A == 0xFFFF:
        cnt = (cnt + 1) & 0xFF
    w28A = (w28A + 1) & 0xFFFF

    retval = (((ret >> 16) & 0xFFFF) + s16(w288) + s16(adc_b)) & 0xFFFFFFFF
    w288 = retval & 0xFFFF

    cnt = (cnt + 1) & 0xFF
    r7 = (((ret & 0x00FFFF00) >> 8) + s16(w28A) + s16(adc_c)) & 0xFFFFFFFF
    w28A = r7 & 0xFFFF

    w288 = ((((adc_c & 0xFF) << 8) + (adc_a & 0xFF)) ^ w288) & 0xFFFF
    w28A = (~((((adc_a & 0xFF) << 8) + (adc_b & 0xFF)) ^ w28A)) & 0xFFFF
    cnt = (adc_b ^ cnt) & 0xFF

    m[CNT] = cnt
    wr16(m, W288, w288)
    wr16(m, W28A, w28A)

    combined = (w288 << 16) | w28A
    if combined == 0:
        combined = rd32(m, W2DC) | rd32(m, W2E0)
    wr32(m, OUT, combined)
    return m, retval & 0xFFFFFFFF


def seed_ram(rng):
    m = {}
    for a in (A_ADC, B_ADC, C_ADC):
        wr16(m, a, rng.randrange(0x10000))
    m[W2DC] = 0
    m[W2E0] = 0
    for i in range(4):
        m[W2DC + i] = rng.randint(0, 255)
        m[W2E0 + i] = rng.randint(0, 255)
    wr16(m, W288, rng.randrange(0x10000))
    wr16(m, W28A, rng.randrange(0x10000))
    m[CNT] = rng.randint(0, 255)
    # build the adc_read shadow region: w0, w2, value, checksum bytes
    w0 = rng.randrange(0x10000)
    w2 = rng.randrange(0x10000)
    val = rng.randrange(0x100000000)
    chk = (~((w0 + w2) & 0xFFFF)) & 0xFFFF
    valid = rng.randint(0, 1)
    if valid:
        c0, c1 = chk, rng.randrange(0x10000)
    else:
        c0, c1 = (chk + 1) & 0xFFFF, (chk + 2) & 0xFFFF
    wr16(m, 0xFFFF869C, w0)
    wr16(m, 0xFFFF869E, w2)
    wr32(m, 0xFFFF869C, val)
    wr16(m, 0xFFFF86A0, c0)
    wr16(m, 0xFFFF86A2, c1)
    return m, valid


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    seeds = (0x36AFC, 0xC288, 0x9F1C, 0x5EED, 0x13579)
    total = fails = 0

    for seed in seeds:
        rng = random.Random(seed)
        for _ in range(N):
            ram, valid = seed_ram(rng)
            want, want_r0 = gen(ram)
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
                    print('MISMATCH seed=0x%X valid=%d: %s' %
                          (seed, valid, {k: (hex(g), hex(e))
                                         for k, g, e in bad[:10]}))
            total += 1
        if fails >= 5:
            break

    if fails:
        print('\nFAIL Immo_Keygen_related_ADC @0x36AFC  (%d mismatches / %d)'
              % (fails, total))
        sys.exit(1)
    print('OK  Immo_Keygen_related_ADC @0x36AFC  (%d inputs, 0 mismatches)'
          % total)
    sys.exit(0)


if __name__ == '__main__':
    main()