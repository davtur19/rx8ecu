#!/usr/bin/env python3
"""test_calc_rotor_sync_idle_gate_B_0x12840.py

Differential test for ROM 0x12840 (60E0FC00.bin) - lift
c/calc_rotor_sync_idle_gate_B_0x12840.c.

Runs the ACTUAL ROM bytes of 0x12840 in tools/sh2emu.py over seeded RAM
states (the oracle) and compares the full post-call RAM overlay (byte-exact,
task-stack window 0xFFFFDE00..DF00 skipped) plus the return register r0
against a Python reference model that mirrors the C lift line-for-line.

Entry/range: 0x12840 IS the real entry (dispatcher slot @0x14440 of the
engineControlCalculateTiming 0x141FC table; preceding fn 0x127E8 ends
rts+delay @0x1283C; next fn starts exactly at CSV end 0x12904). CSV range
0x12840..0x12904 (196 B) CORRECT - no phantom rows.

Semantics (see lift header): gate u8@FFFFA680 = 1 iff (B580==1 || C94C==1)
&& AAC6==1 && rotor-select && drop>=40.0 && rpm<=2000.0, where
drop = f32@FFFFA684 - f32@FFFFB594.  On every call A694 <= rpm and A695/A684
latch the per-rotor status bytes (A444/A445).  r0 on return is path-dependent
(the last compared byte on each fail leaf, or 0 / A694&0xFF on the pass and
threshold paths) - carried byte-exact.

Run: python3 c/tests/test_calc_rotor_sync_idle_gate_B_0x12840.py [N]
     (N = random inputs per seed; default 100000 -> 500000 across 5 seeds)
"""
import os, random, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2, ts

ROM = os.path.join(ROOT, 'roms', 'stock', '60E0FC00.bin')
ADDR = 0x12840

# ---- RAM addresses (see c/calc_rotor_sync_idle_gate_B_0x12840.c) ----
A444 = 0xFFFFA444   # u8 rotor A status
A445 = 0xFFFFA445   # u8 rotor B status
B594 = 0xFFFFB594   # f32 engine speed (rpm)
A684 = 0xFFFFA684   # f32 previous RPM sample
A680 = 0xFFFFA680   # u8 idle anti-stall gate out
B580 = 0xFFFFB580   # u8 enable source A
C94C = 0xFFFFC94C   # u8 enable source B
AAC6 = 0xFFFFAAC6   # u8 idle-gate-active
A693 = 0xFFFFA693   # u8 rotor-select / latch A
A694 = 0xFFFFA694   # u8 rotor-select / latch B

CAL_DROP = 0x00072638  # f32 40.0
CAL_RPM  = 0x0007263C  # f32 2000.0

BYTE_IN = [A444, A445, A680, B580, C94C, AAC6, A693, A694]
STACK_LO = 0xFFFFDE00
STACK_HI = 0xFFFFDF00


def r32(m, a):
    return struct.unpack('>f', bytes(m.get(a + i, 0) for i in range(4)))[0]


def put32(m, a, v):
    for i, b in enumerate(struct.pack('>f', ts(v))):
        m[a + i] = b


def ref(m, rom):
    """Line-for-line mirror of calc_rotor_sync_idle_gate_B_0x12840() with
    exact r0 tracking. Returns (full RAM-effect dict, expected r0)."""
    m = dict(m)
    a444 = m.get(A444, 0) & 0xFF
    a445 = m.get(A445, 0) & 0xFF
    rpm  = r32(m, B594)
    prev = r32(m, A684)
    drop = ts(prev - rpm)                 # fsub in delay slot, always runs
    b580 = m.get(B580, 0) & 0xFF
    c94c = m.get(C94C, 0) & 0xFF
    aac6 = m.get(AAC6, 0) & 0xFF
    a693 = m.get(A693, 0) & 0xFF
    a694 = m.get(A694, 0) & 0xFF
    cal_drop = struct.unpack('>f', rom[CAL_DROP:CAL_DROP + 4])[0]
    cal_rpm  = struct.unpack('>f', rom[CAL_RPM:CAL_RPM + 4])[0]
    out = 0

    r0 = b580
    if b580 != 1:                          # else check C94C
        r0 = c94c
        if c94c != 1:                      # fail leaf
            m[A680] = 0; put32(m, A684, rpm); m[A693] = a444; m[A694] = a445
            return m, r0
    r0 = aac6
    if aac6 != 1:                          # fail leaf
        m[A680] = 0; put32(m, A684, rpm); m[A693] = a444; m[A694] = a445
        return m, r0
    # rotor-select gate
    if a693 == 1 and a444 == 0:            # rotor A not running, armed
        r0 = 0
        ok = True
    else:
        r0 = a694
        ok = (a694 == 1 and a445 == 0)     # rotor B not running, armed
        if not ok:                         # fail leaf
            m[A680] = 0; put32(m, A684, rpm); m[A693] = a444; m[A694] = a445
            return m, r0
    # thresholds (fcmp/gt bt-fail): pass needs drop>=40 and rpm<=2000
    if not (cal_drop > drop) and not (rpm > cal_rpm):
        out = 1
    m[A680] = out
    put32(m, A684, rpm)                    # store current as prev for next call
    m[A693] = a444                          # latch per-rotor status bytes
    m[A694] = a445
    return m, r0


def gen_state(rng):
    """Random seeded RAM.  Byte inputs independently 0/1/other; f32 A rpm and
    prev cover the threshold band (40.0, 2000.0), wide ranges and NaN, so the
    fcmp /gt NaN behaviour and every r0 leaf are exercised."""
    def bbyte():
        r = rng.random()
        if r < 0.6:
            return rng.choice([0, 1])
        elif r < 0.85:
            return rng.randint(2, 255)
        else:
            return rng.choice([0x7F, 0x80, 0xFF])
    ram = dict((a, bbyte()) for a in BYTE_IN)
    r = rng.random()
    if r < 0.55:
        v = float(rng.uniform(-500, 5000))
    elif r < 0.8:
        v = float(rng.choice([0.0, 40.0, 39.99, 40.01, 1999.0, 2000.0,
                              2000.5, 1500.0, 2100.0, 3000.0]))
    elif r < 0.9:
        v = float('nan')
    else:
        v = float(rng.uniform(-1e6, 1e6))
    put32(ram, B594, v)
    put32(ram, A684, rng.choice([0.0, 1.0, 100.0, 500.0, 1000.0, 3000.0,
                                 7000.0, 1e6, -5.0, float('nan')]))
    return ram


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    rom = open(ROM, 'rb').read()
    assert struct.unpack('>f', rom[CAL_DROP:CAL_DROP + 4])[0] == 40.0
    assert struct.unpack('>f', rom[CAL_RPM:CAL_RPM + 4])[0] == 2000.0
    cpu = SH2(rom)
    seeds = (0x12840, 0x12840 | 0x2638, 0xFFFFA680, 0xFFFFB594, 0x14444)
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
    print('OK  0x12840 calc_rotor_sync_idle_gate_B '
          '(%d random inputs across %d seeds)' % (N * len(seeds), len(seeds)))
    print('\nAll calc_rotor_sync_idle_gate_B_0x12840 tests passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()