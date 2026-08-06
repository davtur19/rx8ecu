#!/usr/bin/env python3
"""test_sub_13E6C_0x13E6C.py

Differential test for ROM 0x13E6C (60E1D400.bin) — lift
c/sub_13E6C_0x13E6C.c.

Runs the ACTUAL ROM bytes of 0x13E6C in tools/sh2emu.py over seeded RAM/RAM
states (the oracle) and compares the full post-call RAM overlay (byte-exact)
plus the return FPU register fr0 against a Python reference model that mirrors
the C lift line-for-line.

Entry-point note: 0x13E6C IS the real entry point — a plain subroutine
referenced by `bsr 0x13E6C` from updateKnockMaxRAM (0x13B90 @0x13BBA) and from
the ignition helper calc_ignition_all_rotors (0x13C2C context).  Valid
prologue (sts.l pr,/add #0xFC) and rts+delay @0x13ECE/0x13ED0; no branches
into the body.  The symbols CSV row was calc_fuel_pump_control_output but the
real semantics is a saturating clamp whose lower bound comes from a 1D table
lookup — renamed to sub_13E6C (see the lift header).

Key semantic facts (see the lift header):
  * fr4@entry = v (signal to clamp).  fr4 is saved to the stack then the axis
    f32@0xFFFFB5B8 (RPM) is loaded into fr4 for the lookup.
  * Table selection from status bytes B5A4/BB55/BCA9 + threshold u8@0x79838:
        if B5A4==1  &&  (u32)(s8)BCA9 >= (u32)(s8)(5)  -> desc 0x6B678
        else if B5A4 != 0                              -> desc 0x6B664
        else if BB55 > 5 || BB55 == 0                  -> desc 0x6B664
        else                                           -> desc 0x6B678
    (the BCA9 compare is cmp/hs on sign-extended mov.b values, done unsigned).
  * lower = table1D_lookup(desc, f32@B5B8)   ; jsr 0x2068
  * out   = clamp(v, lower, f32@0x79878=0.0) ; jsr 0x2404
  * The two sub-calls run natively in a second emulator instance cpu2 (the
    updateKnockMaxRAM trick) with their RAM merged, mirroring the C lift's
    extern table1D_lookup / inline clamp.

Run: python3 c/tests/test_sub_13E6C_0x13E6C.py [N]
     (N = random inputs per seed; default 100000 -> 500000 across 5 seeds)
"""
import os, random, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2, ts

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ADDR = 0x13E6C

# ---- RAM addresses (see c/sub_13E6C_0x13E6C.c header) ----
B5A4 = 0xFFFFB5A4   # u8  table-select status
BB55 = 0xFFFFBB55   # u8  table-select status
BCA9 = 0xFFFFBCA9   # u8  table-select status
B5B8 = 0xFFFFB5B8   # f32 lookup axis (RPM)

ROM_79838 = 0x00079838   # u8  5 table-select threshold
DESC_A = 0x0006B678      # 1D descriptor A (4-pt u8)
DESC_B = 0x0006B664      # 1D descriptor B (5-pt u8)

SENT16 = 0xA5A5


def put(ram, a, n, v):
    for i in range(n):
        ram[a + i] = (v >> (8 * (n - 1 - i))) & 0xFF


def setf(ram, a, v):
    for i, b in enumerate(struct.pack('>f', ts(v))):
        ram[a + i] = b


def rdf(m, a):
    return struct.unpack('>f', bytes(m.get(a + i, 0) for i in range(4)))[0]


def rbu(rom, m, a):
    v = m.get(a)
    if v is not None:
        return v & 0xFF
    return rom[a] if a < len(rom) else 0


def ref(cpu2, rom, m, v):
    """Line-for-line mirror of sub_13E6C(v).  The two sub-calls run in cpu2
    (oracle) with their RAM merged.  Returns (RAM-effect dict, expected fr0)."""
    m = dict(m)

    thr = rbu(rom, m, ROM_79838)          # 0x05
    status = rbu(rom, m, B5A4)
    bb55 = rbu(rom, m, BB55)
    bca9 = rbu(rom, m, BCA9)

    # cmp/eq #1 on r0 = status&0xff  (mov.b sign-extend + extu.b)
    # then cmp/hs on sign-extended s8 values, unsigned u32 compare.
    desc = None
    if (status & 0xFF) == 1:
        # r0 = mov.b BCA9 (s8) ; r2 = mov.b @0x79838 (s8) ; cmp/hs r2,r0
        s_bca9 = bca9 - 256 if bca9 >= 128 else bca9
        s_thr = thr - 256 if thr >= 128 else thr
        if (s_bca9 & 0xFFFFFFFF) >= (s_thr & 0xFFFFFFFF):
            desc = DESC_A
    if desc is None:
        r6 = status & 0xFF
        if r6 != 0:                        # bf/s -> table B
            desc = DESC_B
        else:
            r2 = bb55 & 0xFF               # extu.b
            r3 = thr & 0xFF
            if r2 > r3:                    # cmp/gt (equiv unsigned 0..255)
                desc = DESC_B
            elif r2 == 0:                  # tst r2,r2 -> table B
                desc = DESC_B
            else:
                desc = DESC_A

    rpm = rdf(m, B5B8)
    # 0x2068 table1D_lookup(desc, rpm)
    cpu2.call(0x2068, r4=desc, fr={4: rpm}, ram=m)
    m = dict(cpu2.ram); lower = cpu2.fr[0]

    # 0x2404 clamp(v, lower, upper=0.0)
    cpu2.call(0x2404, fr={4: v, 5: lower, 6: 0.0}, ram=m)
    m = dict(cpu2.ram); out = cpu2.fr[0]
    return m, out


def gen_state(rng):
    """Random seeded RAM: status bytes cover every table-selection branch and
    the sign-extension edge; axis and input v cover finite/NaN/edge; lookup
    scratch cells are seeded with junk so reads are consistent oracle-vs-ref."""
    ram = {}
    ram[B5A4] = rng.randint(0, 255)
    ram[BB55] = rng.randint(0, 255)
    ram[BCA9] = rng.randint(0, 255)
    r = rng.random()
    if r < 0.8:
        setf(ram, B5B8, rng.uniform(0.0, 8000.0))
    else:
        setf(ram, B5B8, rng.choice([0.0, 459.0, 8000.0, 12000.0]))
    # lookup scratch cells (writes only; seed junk so both sides agree)
    if rng.random() < 0.5:
        put(ram, 0xFFFFA2A4, 4, rng.randint(0, 0xFFFFFFFF))
    if rng.random() < 0.3:
        put(ram, 0xFFFFA755, 1, rng.randint(0, 0xFF))
        put(ram, 0xFFFFA7A9, 1, rng.randint(0, 0xFF))
    if rng.random() < 0.3:
        for k in range(12):
            ram[0xFFFFB534 + k] = rng.randint(0, 0xFF)
    if rng.random() < 0.3:
        ramp = {0: SENT16, 3: SENT16}
        for a, n in ((0xFFFFA2A4, 4), (0xFFFFB534, 4)):
            put(ram, a, n, 0x11223344)
    return ram


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    rom = open(ROM, 'rb').read()

    cpu = SH2(rom)
    cpu2 = SH2(rom)          # dedicated instance for the sub-calls in ref()
    seeds = (0x13E6C, 0x13B90, 0x2068, 0x2404, 0xB5B8)
    total_fails = 0

    for seed in seeds:
        rng = random.Random(seed)
        fails = 0
        for it in range(N):
            ram = gen_state(rng)
            v = rng.uniform(-50.0, 50.0)
            if rng.random() < 0.1:
                v = rng.choice([0.0, -2.5, 1.0, float('nan'), float('inf'),
                                float('-inf'), 5.0, -5.0])
            want, want_fr0 = ref(cpu2, rom, ram, v)
            try:
                cpu.call(ADDR, fr={4: v}, ram=ram)
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
            if bad or cpu.fr[0] != want_fr0:
                print('MISMATCH seed=0x%X iter=%d: fr0=%r want_fr0=%r %s' %
                      (seed, it, cpu.fr[0], want_fr0,
                       {hex(k): (hex(g), hex(e)) for k, g, e in bad[:10]}))
                print('  B5A4=%d BB55=%d BCA9=%d v=%r rpm=%r' % (
                    ram.get(B5A4, 0), ram.get(BB55, 0), ram.get(BCA9, 0),
                    v, rdf(ram, B5B8)))
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
    print('OK  0x13E6C sub_13E6C '
          '(%d random inputs across %d seeds)' % (N * len(seeds), len(seeds)))
    print('\nAll sub_13E6C_0x13E6C tests passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()