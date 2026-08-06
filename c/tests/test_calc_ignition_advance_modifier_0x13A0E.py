#!/usr/bin/env python3
"""test_calc_ignition_advance_modifier_0x13A0E.py

Differential test for ROM 0x13A0E (60E1D400.bin) — lift
c/calc_ignition_advance_modifier_0x13A0E.c.

Runs the ACTUAL ROM bytes of 0x13A0E in tools/sh2emu.py over seeded RAM states
(the oracle) and compares the full post-call RAM overlay (byte-exact) plus the
return register r0 against a Python reference model that mirrors the C lift
line-for-line.

Entry-point note: 0x13A0E IS the real entry point — the function-pointer slot
@0x14794 in the dispatcher engineControlCalculateTiming (0x14584) dispatch
table, phase 1, right before calc_rotor_sync_base_A (0x14798),
getKnockControlActive (0x1479C) and updateKnockMaxRAM (0x147A0).  Valid entry
(no branches into the body; preceding function ends with rts @0x13A0A).
The symbols CSV row is calc_ignition_advance_modifier (kept).

Key semantic facts (see the lift header): void flag writer.
  u8@0xFFFFA748 = 1 iff
      (s8)u8@0x0007A172 == 0
   && (u32)(s16)u16@0xFFFFA424 >= (u32)(s16)u16@0x0007983C   (cmp/hs, unsigned)
   && !(f32@0x00079840 > f32@0xFFFFAA10)
   && !(f32@0x00079844 > f32@0xFFFFC12C)
   &&  (f32@0x00079848 > f32@0xFFFFB5B8)
  else 0.  The flag feeds getKnockControlActive (0x13A86).
  r0 after return = 0 if the ROM gate fired (branch to 0x13A56 before the
  r0=0xA424 mov.w), else 0xFFFFA424 (constant for all other paths).

Run: python3 c/tests/test_calc_ignition_advance_modifier_0x13A0E.py [N]
     (N = random inputs per seed; default 100000 -> 500000 across 5 seeds)
"""
import os, random, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2, ts

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ADDR = 0x13A0E

OUT_A748 = 0xFFFFA748   # u8 enable flag output
RAM_A424 = 0xFFFFA424   # u16 compare input
RAM_AA10 = 0xFFFFAA10   # f32 compare input
RAM_C12C = 0xFFFFC12C   # f32 compare input
RAM_B5B8 = 0xFFFFB5B8   # f32 compare input (fr4, delay-slot load)

ROM_GATE  = 0x0007A172   # u8 hard-disable gate (mov.b @r1,r2)
ROM_THR   = 0x0007983C   # u16 threshold (mov.w @r1,r3)
ROM_CA    = 0x00079840   # f32 const A (mov.l)
ROM_CB    = 0x00079844   # f32 const B (mov.l)
ROM_CC    = 0x00079848   # f32 const C (mov.l)

R0_LOADED = 0xFFFFA424   # r0 value once the mov.w @0x13AB2 path is reached


def setf(ram, a, v):
    for i, b in enumerate(struct.pack('>f', ts(v))):
        ram[a + i] = b


def rdf(rom, m, a):
    bb = []
    for i in range(4):
        v = m.get(a + i)
        if v is None:
            v = rom[a + i] if a + i < len(rom) else 0
        bb.append(v)
    return struct.unpack('>f', bytes(bb))[0]


def rbu(rom, m, a):
    v = m.get(a)
    if v is not None:
        return v & 0xFF
    return rom[a] if a < len(rom) else 0


def rbw(rom, m, a):
    return (rbu(rom, m, a) << 8) | rbu(rom, m, a + 1)


def s16(x):
    x &= 0xFFFF
    return x - 0x10000 if x & 0x8000 else x


def ref(rom, m):
    """Line-for-line mirror of calc_ignition_advance_modifier_0x13A0E().
    Returns (RAM-effect dict, expected r0)."""
    m = dict(m)

    # 0x13A14..0x13A1A: tst r2,r2 (r2 = s8 @0x7A172) ; bf/s 0x13A56.
    # r2 is a sign-extended mov.b; tst sets T on zero, bf/s fires when != 0.
    if rbu(rom, m, ROM_GATE) != 0:
        # nonzero (either sign) -> jump straight to store-0.
        m[OUT_A748] = 0
        return m, 0                 # r0 never loaded (stays 0 from call init)

    # 0x13A1C..0x13A28: cmp/hs r3,r2 on sign-extended mov.w, unsigned u32.
    r2 = s16(rbw(rom, m, RAM_A424)) & 0xFFFFFFFF
    r3 = s16(rbw(rom, m, ROM_THR)) & 0xFFFFFFFF
    ok = r2 >= r3
    if ok:
        # 0x13A2A..0x13A36: fcmp/gt fr2,fr3 -> T = (fr3 > fr2) ; bt/s
        if not (rdf(rom, m, ROM_CA) > rdf(rom, m, RAM_AA10)):
            # 0x13A38..0x13A44: fcmp/gt fr0,fr1 -> T = (fr1 > fr0) ; bt/s
            if not (rdf(rom, m, ROM_CB) > rdf(rom, m, RAM_C12C)):
                # 0x13A46..0x13A4E: fcmp/gt fr4,fr3 -> T = (fr3 > fr4) ; bf/s
                if rdf(rom, m, ROM_CC) > rdf(rom, m, RAM_B5B8):
                    m[OUT_A748] = 1
                    return m, R0_LOADED
    m[OUT_A748] = 0
    return m, R0_LOADED


def gen_state(rng):
    """Random seeded RAM hitting every branch of the modifier chain plus the
    ROM gate (seeded via the RAM overlay to exercise both gate paths)."""
    ram = {}
    # ROM gate byte (overlay) — 0 = enabled path (stock value), else disabled.
    ram[ROM_GATE] = rng.choice([0, 0, 0, 0, 1, 2, 0xFF])
    # A424 vs threshold 0x177
    ram[RAM_A424] = rng.randint(0, 0xFFFF)
    ram[RAM_A424] = (ram[RAM_A424] & 0xFF00) | rng.choice(
        [0x00, 0x76, 0x77, 0x78, 0x79, 0xFF])      # around 0x177
    # f32 compares
    for a in (RAM_AA10, RAM_C12C, RAM_B5B8):
        r = rng.random()
        if r < 0.7:
            setf(ram, a, rng.uniform(-50.0, 50.0))
        else:
            setf(ram, a, rng.choice([-10.0, -2.0, 0.0, 0.4, 0.5, 0.6,
                                     9.0, 10.0, 11.0, 6999.0, 7000.0,
                                     7001.0, float('nan'), float('inf'),
                                     float('-inf')]))
    # output junk so a missed write is caught
    ram[OUT_A748] = rng.choice([0, 1, 0x55, 0xFF])
    return ram


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    rom = open(ROM, 'rb').read()

    cpu = SH2(rom)
    seeds = (0x13A0E, 0x13A5E, 0x13A86, 0x13B90, 0xA748)
    total_fails = 0

    for seed in seeds:
        rng = random.Random(seed)
        fails = 0
        for it in range(N):
            ram = gen_state(rng)
            want, want_r0 = ref(rom, ram)
            try:
                cpu.call(ADDR, ram=ram)
            except Exception as e:
                print('EMULATOR EXC seed=0x%X iter=%d: %s' % (seed, it, e))
                fails += 1
                break
            bad = []
            allk = set(k for k in want if isinstance(k, int)) | set(cpu.ram.keys())
            for k in allk:
                if 0xFFFFDE00 <= k <= 0xFFFFDF00:   # task stack area
                    continue
                if cpu.ram.get(k, 0) != want.get(k, 0):
                    bad.append((k, cpu.ram.get(k, 0), want.get(k, 0)))
            if bad or cpu.r[0] != want_r0:
                print('MISMATCH seed=0x%X iter=%d: r0=%d want_r0=%d %s' %
                      (seed, it, cpu.r[0], want_r0,
                       {hex(k): (hex(g), hex(e)) for k, g, e in bad[:10]}))
                print('  gate=%d A424=%04x AA10=%r C12C=%r B5B8=%r' % (
                    ram.get(ROM_GATE, 0), ram.get(RAM_A424, 0),
                    rdf(rom, ram, RAM_AA10), rdf(rom, ram, RAM_C12C),
                    rdf(rom, ram, RAM_B5B8)))
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
    print('OK  0x13A0E calc_ignition_advance_modifier '
          '(%d random inputs across %d seeds)' % (N * len(seeds), len(seeds)))
    print('\nAll calc_ignition_advance_modifier_0x13A0E tests passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()