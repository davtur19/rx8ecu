#!/usr/bin/env python3
"""test_air_charge_calc_0x19190.py

Differential test for ROM 0x19190 (60E1D400.bin) — lift
c/air_charge_calc_0x19190.c.

Runs the ACTUAL ROM bytes of 0x19190 in tools/sh2emu.py over seeded RAM states
(the oracle) and compares the full post-call RAM overlay against a Python
reference model that mirrors the C lift line-for-line.

Key semantic facts (see the lift header):
  * gate = u16@0xFFFFA9BC.  gate == 0 -> A9B8 = 0.0 and return (A9C4/A9C8
    untouched); else:
  * lookup = ThreeDLookup(0x69EDC, x=RPM f32@FFFFB5B8, y=temp f32@FFFFAA10)
    (12x8 u8 map, axis_x = RPM 0..3000, axis_y = temp -40..100).
  * A9C4 = lookup;  A9C8 = f32@FFFFBD0C - lookup;
  * A9B8 = min_0x23F4(A9C8, max_0x23E4(A9B0, A9B4)).

The ThreeDLookup / min / max helpers are executed in a second emulator instance
(`cpu2`) so single-precision rounding and NaN behavior match the ROM exactly —
the same trick test_calc_spark_lead_trail_split_19220.py uses for 0x20DC etc.

Run: python3 c/tests/test_air_charge_calc_0x19190.py [N]
     (N = random inputs per seed; default 100000 -> 500000 across 5 seeds)
"""
import os, random, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2, ts

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ADDR = 0x19190

# ---- RAM addresses (see c/air_charge_calc_0x19190.c header) ----
A9BC = 0xFFFFA9BC   # u16 gate (load-estimate counter, shared with 0x190A6)
B5B8 = 0xFFFFB5B8   # f32 RPM
AA10 = 0xFFFFAA10   # f32 charge temp
BD0C = 0xFFFFBD0C   # f32
A9B0 = 0xFFFFA9B0   # f32 (shared with 0x190A6)
A9B4 = 0xFFFFA9B4   # f32 (shared with 0x190A6)

A9B8 = 0xFFFFA9B8   # f32 out (air charge, always written)
A9C4 = 0xFFFFA9C4   # f32 out (raw lookup, gate != 0 only)
A9C8 = 0xFFFFA9C8   # f32 out (BD0C - lookup, gate != 0 only)

FLOAT_IN = [B5B8, AA10, BD0C, A9B0, A9B4]
FLOAT_OUT = [A9B8, A9C4, A9C8]


def r32(d, a):
    return struct.unpack('>f', bytes(d.get(a + i, 0) for i in range(4)))[0]


def f32b(v):
    return list(struct.pack('>f', ts(v)))


def ref(cpu2, ram, rom):
    """Line-for-line mirror of air_charge_calc_0x19190().

    Helper calls (0x20DC ThreeDLookup, 0x23E4 max, 0x23F4 min) are executed in
    the dedicated emulator instance `cpu2` so the single-precision rounding /
    NaN behavior matches the ROM exactly.  Returns a full RAM-effect dict.
    """
    m = dict(ram)

    gate = (m.get(A9BC, 0) | (m.get(A9BC + 1, 0) << 8)) & 0xFFFF
    if gate == 0:
        for i in range(4):
            m[A9B8 + i] = 0
        return m

    cpu2.call(0x20DC, r4=0x69EDC, fr={4: r32(m, B5B8), 5: r32(m, AA10)})
    lookup = cpu2.fr[0]
    for i, b in enumerate(f32b(lookup)):
        m[A9C4 + i] = b

    d = ts(r32(m, BD0C) - lookup)
    for i, b in enumerate(f32b(d)):
        m[A9C8 + i] = b

    cpu2.call(0x23E4, fr={4: r32(m, A9B0), 5: r32(m, A9B4)})
    mx = cpu2.fr[0]
    cpu2.call(0x23F4, fr={4: d, 5: mx})
    for i, b in enumerate(f32b(cpu2.fr[0])):
        m[A9B8 + i] = b
    return m


def setf(ram, a, v):
    for i, b in enumerate(struct.pack('>f', ts(v))):
        ram[a + i] = b


def gen_state(rng):
    """Random seeded RAM hitting both gate paths and the float helpers' edges."""
    ram = {}

    def maybe_nan(v):
        r = rng.random()
        if r < 0.08:
            return float('nan')
        if r < 0.12:
            return float('inf') if rng.random() < 0.5 else float('-inf')
        return v

    setf(ram, B5B8, maybe_nan(rng.uniform(-500, 5000)))     # RPM (incl. out-of-map)
    setf(ram, AA10, maybe_nan(rng.uniform(-100, 150)))      # charge temp (incl. out-of-map)
    setf(ram, BD0C, maybe_nan(rng.uniform(-100, 100)))
    setf(ram, A9B0, maybe_nan(rng.uniform(-100, 100)))
    setf(ram, A9B4, maybe_nan(rng.uniform(-100, 100)))
    gate = rng.getrandbits(16)                         # 0x0000 and 0x8000..0xFFFF paths
    ram[A9BC] = gate & 0xFF
    ram[A9BC + 1] = (gate >> 8) & 0xFF
    for a in FLOAT_OUT:                                # previous outputs (must be overwritten)
        setf(ram, a, rng.uniform(-999, 999))
    return ram


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    rom = open(ROM, 'rb').read()

    cpu = SH2(rom)
    cpu2 = SH2(rom)         # dedicated instance for the helper calls in ref()
    seeds = (0x19190, 0xA9BC, 0x69EDC, 0xAA10, 0x23F4)
    total_fails = 0

    for seed in seeds:
        rng = random.Random(seed)
        fails = 0
        for it in range(N):
            ram = gen_state(rng)
            want = ref(cpu2, ram, rom)
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
            if bad:
                print('MISMATCH seed=0x%X iter=%d: %s' %
                      (seed, it, {hex(k): (hex(g), hex(e)) for k, g, e in bad[:12]}))
                print('  gate=0x%04X rpm=%r temp=%r bd0c=%r A9B0=%r A9B4=%r' % (
                    gate, r32(ram, B5B8), r32(ram, AA10), r32(ram, BD0C),
                    r32(ram, A9B0), r32(ram, A9B4)))
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
    print('OK  0x19190 air_charge_calc  (%d random inputs across %d seeds)'
          % (N * len(seeds), len(seeds)))
    print('\nAll air_charge_calc_0x19190 tests passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()
