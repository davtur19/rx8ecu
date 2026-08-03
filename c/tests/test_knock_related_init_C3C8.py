#!/usr/bin/env python3
"""test_knock_related_init_C3C8.py

Differential test for ROM 0xC3C8 (60E1D400.bin) — knockRelatedInit
(lift: c/knockRelatedInit.c).

ADDRESS NOTE: the audit (/tmp/untested_lifts.tsv) lists 0xC1F8, but in THIS
ROM 0xC1F8 is an unrelated SFR-init function with no inbound references.
The knock init is at 0xC3C8 (referenced from 0x6754) — matching the lift
header "knockRelatedInit @ 0xC1F8 (60E0FC00) / 0xC3C8 (60E1D400)".  The
test targets the address that matches this ROM.

Level: FULL.  The function is self-contained: it reads a handful of ROM
constants and writes a fixed RAM window; no registers/RAM influence the
result, so the model is the exact write list below and every input is a
freshly seeded RAM environment around the footprint.

Disassembly (60E1D400) writes, in order:
  0xFFFFA37E u16 = u16@0x7A178                 (0x005E)
  0xFFFFA37C u16 = u16@0x7A17A                 (0x00C1)
  0xFFFFA328 f32 = f32@0x7A1A4                 (3.6875)
  0xFFFFA360 f32 = f32@0x0C4B0                 (10.0)
  0xFFFFA364 f32 = f32@0x7A1D0                 (64.0)
  0xFFFFA384 u8  = 0xFF
  0xFFFFA385 u8  = 0
  0xFFFFA386 u8  = 0
  0xFFFFA32C f32 = 0.0
  0xFFFFA324 u8  = 0
  0xFFFFA348 f32 = 0.0
  loop r6=1..2 (2 rotors):
    0xFFFFA350/0xFFFFA354 f32 = 10.0     (fr5, filter gain)
    0xFFFFA368/0xFFFFA36C f32 = 64.0     (fr3 = [0x7A1D0])
    0xFFFFA389/0xFFFFA38A u8  = [0x7A164]/[0x7A165]
    0xFFFFA334/0xFFFFA338 f32 = 0.0      (fr4)
  + 4 prologue pushes r13..r10 (all 0) at 0xFFFFDEF0..0xFFFFDF00
  return: r0 = 8 (loop index), r1 = 2 (loop limit), r15 = 0xFFFFDF00

LIFT DISCREPANCIES (c/knockRelatedInit.c, logical lift):
  1. header says ADC copy 1 at 0xFFFFA37A; the ROM writes 0xFFFFA37E.
  2. KNOCK_FILTER_STATE (0xFFFFA32C) is cleared to 0.0, not set from
     0xFFFF9F80 RPM ref.
  3. per-rotor threshold A (0xFFFFA334/0xFFFFA338) = 0.0, but threshold B
     (0xFFFFA350/0xFFFFA354) = 10.0 (the filter gain), and filter B
     (0xFFFFA368/0xFFFFA36C) = 64.0, not 0.0.
  4. sensor IDs land at 0xFFFFA389/0xFFFFA38A (u8@0x7A164/0x7A165).
  This test pins the ROM behavior; the lift's approximations are noted,
  not silently relied upon.

Run: python3 c/tests/test_knock_related_init_C3C8.py [N]
     (N = fresh seeded environments per seed; default 600 -> 3000 across 5 seeds)
"""
import os, random, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2, ts  # noqa: E402

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ADDR = 0xC3C8
MASK = 0xFFFFFFFF

# ROM calibration reads
R_ADCB = 0x7A178      # u16 -> 0xFFFFA37E
R_ADCC = 0x7A17A      # u16 -> 0xFFFFA37C
R_F32A = 0x7A1A4      # f32 -> 0xFFFFA328
R_GAIN = 0x0C4B0      # f32 -> 0xFFFFA360 and rotor-B thresholds
R_F64  = 0x7A1D0      # f32 -> 0xFFFFA364 and rotor-B filters
R_SID  = 0x7A164      # u8[2] -> 0xFFFFA389/0xFFFFA38A

FOOT_START = 0xFFFFA320
FOOT_END = 0xFFFFA3A0


def rb(m, a):
    return m.get(a & MASK, 0)


def rd(m, a, n):
    v = 0
    for i in range(n):
        v = (v << 8) | rb(m, a + i)
    return v


def wr(m, a, n, v):
    for i in range(n):
        m[(a + i) & MASK] = (v >> (8 * (n - 1 - i))) & 0xFF


def putf(m, a, v):
    for i, b in enumerate(struct.pack('>f', ts(v))):
        m[(a + i) & MASK] = b


def ref(rom, ram):
    """Python model of 0xC3C8 — exact write list from the disassembly."""
    m = dict(ram)
    wr(m, 0xFFFFA37E, 2, struct.unpack('>H', rom[R_ADCB:R_ADCB + 2])[0])
    wr(m, 0xFFFFA37C, 2, struct.unpack('>H', rom[R_ADCC:R_ADCC + 2])[0])
    putf(m, 0xFFFFA328, struct.unpack('>f', rom[R_F32A:R_F32A + 4])[0])
    gain = struct.unpack('>f', rom[R_GAIN:R_GAIN + 4])[0]
    f64 = struct.unpack('>f', rom[R_F64:R_F64 + 4])[0]
    putf(m, 0xFFFFA360, gain)
    putf(m, 0xFFFFA364, f64)
    m[0xFFFFA384] = 0xFF
    m[0xFFFFA385] = 0
    m[0xFFFFA386] = 0
    putf(m, 0xFFFFA32C, 0.0)
    m[0xFFFFA324] = 0
    putf(m, 0xFFFFA348, 0.0)
    # rotor loop: r6 = 1,2 ; r0 = 0,4
    for i, r0 in enumerate((0, 4)):
        putf(m, 0xFFFFA350 + r0, gain)     # fmov.s fr5,@(r0,r12)
        putf(m, 0xFFFFA368 + r0, f64)      # fmov.s fr3,@(r0,r11)
        m[0xFFFFA389 + i] = rom[R_SID + i]  # mov.b @r13+,r3 / mov.b r3,@r5
        putf(m, 0xFFFFA334 + r0, 0.0)      # fmov.s fr4,@(r0,r10)
    # prologue: mov.l r13..r10,@-r15 (initial values all 0)
    for off in range(4):
        wr(m, 0xFFFFDF00 - 4 * (off + 1), 4, 0)
    return m


def gen_env(rng):
    """Fresh seeded RAM around the footprint and the stack window."""
    ram = {}
    for a in range(FOOT_START, FOOT_END):
        ram[a] = rng.getrandbits(8)
    for a in range(0xFFFFDEB0, 0xFFFFDF00):
        ram[a] = rng.getrandbits(8)
    return ram


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 600
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    seeds = (0xC3C8, 0x7A164, 0xFFFFA334, 0x5EED, 0xC0FF)
    total_fails = 0

    for seed in seeds:
        rng = random.Random(seed)
        fails = 0
        for it in range(N):
            ram = gen_env(rng)
            want = ref(rom, ram)
            try:
                got_r0 = cpu.call(ADDR, ram=ram)
            except Exception as e:
                print('EMULATOR EXC seed=0x%X iter=%d: %s' % (seed, it, e))
                fails += 1
                break
            got = cpu.ram
            bad = []
            if got_r0 != 8:
                bad.append(('r0', got_r0, 8))
            if cpu.r[1] != 2:
                bad.append(('r1', cpu.r[1], 2))
            if cpu.r[15] != 0xFFFFDF00:
                bad.append(('r15', cpu.r[15], 0xFFFFDF00))
            for k in set(got) | set(want):
                if got.get(k, 0) != want.get(k, 0):
                    bad.append((k, got.get(k, 0), want.get(k, 0)))
            if bad:
                print('MISMATCH seed=0x%X iter=%d' % (seed, it))
                shown = []
                for k, g, e in bad[:16]:
                    if isinstance(k, int):
                        shown.append((hex(k), hex(g), hex(e)))
                    else:
                        shown.append((k, hex(g), hex(e)))
                print('  %s' % shown)
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
    print('OK  0xC3C8 knockRelatedInit  (knock RAM init bit-exact vs ROM '
          'constants, %d environments across %d seeds)'
          % (N * len(seeds), len(seeds)))
    sys.exit(0)


if __name__ == '__main__':
    main()
