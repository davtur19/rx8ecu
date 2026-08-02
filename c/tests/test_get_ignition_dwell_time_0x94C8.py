#!/usr/bin/env python3
"""test_get_ignition_dwell_time_0x94C8.py

Differential test for ROM 0x94C8 (60E1D400.bin) — lift
c/get_ignition_dwell_time_0x94C8.c.

Runs the ACTUAL ROM bytes of 0x94C8 in tools/sh2emu.py over seeded RAM states
(the oracle) and compares the full post-call RAM overlay against a Python
reference model that mirrors the C lift line-for-line.

Key semantic facts (see the lift header):
  * x = RPM (f32@0xFFFF9F80), y = battery voltage (f32@0xFFFF9F68).
  * cell = ThreeDLookup_FP_16bit(desc 0x6C1C0, x, y) — u16-cell bilinear lookup,
    9x9 (RPM 1000..9000 x batt 6.5..16.5), type/scale/offset ignored, result
    truncated to u16 in r0.
  * sum = u16(cell) + u16@0xFFFFA0D6 (32-bit); result saturates at 0xFFFF:
      sum > 0xFFFF -> u16@0xFFFFA0D4 = 0xFFFF, else u16@0xFFFFA0D4 = u16(sum).

The 0x213C lookup is NOT modeled in Python: the reference model executes it in a
second emulator instance (`cpu2`), the same emulator-in-model trick used by
test_calc_spark_lead_trail_split_19220.py for its 0x20DC/0x2440/0x2500 helpers,
so single-precision rounding and the u16 truncation match the ROM exactly.

Run: python3 c/tests/test_get_ignition_dwell_time_0x94C8.py [N]
     (N = random inputs per seed; default 100000 -> 500000 across 5 seeds)
"""
import os, random, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2, ts

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ADDR = 0x94C8

# ---- RAM addresses (see c/get_ignition_dwell_time_0x94C8.c header) ----
F9F80 = 0xFFFF9F80   # RPM    (f32 in)
F9F68 = 0xFFFF9F68   # battV  (f32 in)
FA0D6 = 0xFFFFA0D6   # u16 dwell offset (in)
FA0D4 = 0xFFFFA0D4   # u16 dwell time result (out)

FLOAT_IN = [F9F80, F9F68]


def r32(d, a):
    return struct.unpack('>f', bytes(d.get(a + i, 0) for i in range(4)))[0]


def r16(d, a):
    return (d.get(a, 0) << 8) | d.get(a + 1, 0)


def f32b(v):
    return list(struct.pack('>f', ts(v)))


def u16b(v):
    return [v >> 8, v & 0xFF]


def ref(cpu2, ram, rom):
    """Line-for-line mirror of get_ignition_dwell_time_0x94C8().

    The 0x213C lookup runs in the dedicated emulator instance `cpu2` so the
    u16-cell bilinear interp (fmac single rounding, ftrc truncation) matches the
    ROM exactly.  Returns a full RAM-effect dict (int keys -> byte values).
    """
    m = dict(ram)
    rpm = r32(m, F9F80)
    batt = r32(m, F9F68)

    # 0x213C ThreeDLookup_FP_16bit(desc 0x6C1C0, x=rpm, y=batt) -> u16 in r0
    cpu2.call(0x213C, r4=0x6C1C0, fr={4: rpm, 5: batt})
    cell = cpu2.r[0] & 0xFFFF

    # sum = cell + u16@FFFFA0D6 ; saturate at 0xFFFF
    s = cell + r16(m, FA0D6)
    out = 0xFFFF if s > 0xFFFF else (s & 0xFFFF)
    for i, b in enumerate(u16b(out)):
        m[FA0D4 + i] = b
    return m


def gen_state(rng):
    """Random seeded RAM.  RPM/batt cover the full map range plus out-of-range
    (below 1000, above 9000, below 6.5, above 16.5); offset covers 0..0xFFFF so
    both the saturated and the plain-sum branch of the clamp are hit."""
    ram = {}
    for a, lo, hi in [(F9F80, -2000, 12000), (F9F68, 0.0, 20.0)]:
        v = struct.pack('>f', rng.uniform(lo, hi))
        for i, b in enumerate(v):
            ram[a + i] = b
    for i, b in enumerate(u16b(rng.randint(0, 0xFFFF))):   # dwell offset
        ram[FA0D6 + i] = b
    for i in range(2):                      # previous output (must be overwritten)
        ram[FA0D4 + i] = rng.randint(0, 255)
    return ram


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    rom = open(ROM, 'rb').read()

    cpu = SH2(rom)
    cpu2 = SH2(rom)         # dedicated instance for the 0x213C helper in ref()
    seeds = (0x94C8, 0x9F80, 0x9F68, 0xA0D6, 0xA0D4)
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
                print('  rpm=%r batt=%r off=%d cell=%d want_A0D4=%d got_A0D4=%d' % (
                    r32(ram, F9F80), r32(ram, F9F68), r16(ram, FA0D6), 0,
                    want.get(FA0D4, 0) << 8 | want.get(FA0D4 + 1, 0),
                    r16(cpu.ram, FA0D4)))
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
    print('OK  0x94C8 get_ignition_dwell_time  (%d random inputs across %d seeds)'
          % (N * len(seeds), len(seeds)))
    print('\nAll get_ignition_dwell_time_0x94C8 tests passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()
