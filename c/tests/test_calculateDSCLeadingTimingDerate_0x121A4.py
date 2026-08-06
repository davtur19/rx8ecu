#!/usr/bin/env python3
"""test_calculateDSCLeadingTimingDerate_0x121A4.py

Differential test for ROM 0x121A4 (60E0FC00.bin) — lift
c/calculateDSCLeadingTimingDerate_0x121A4.c.

Runs the ACTUAL ROM bytes of 0x121A4 — including the real sub-calls
complement_shift_u32 @0x2440 (x2) and saturate @0x2404 — in tools/sh2emu.py
over seeded RAM states (the oracle) and compares the full post-call RAM
overlay (byte-exact, task-stack window 0xFFFFDE00..DF00 skipped) plus the
return register r0 against a Python reference model that mirrors the C lift
line-for-line.

Entry-point / range note: 0x121A4 IS the real entry point (function-pointer
slot @0x144C8 of the engineControlCalculateTiming dispatcher 0x141FC table;
valid prologue; preceding function ends rts @0x121A0).  The symbols CSV row
is calculateDSCLeadingTimingDerate? with end 0x012236 — the real function runs
to rts @0x1224E (literal pool to 0x12292, next function @0x12294), so the CSV
is widened to 0x0121A4..0x012294 and the "?" dropped (see the lift header).
The phantom "modifyTiming" row @0x12236 (inside this function) is removed.

Key semantic facts (see the lift header): void leading-timing DSC derate writer.
  s = complement_shift_u32(f32@A780, 0.0, 1e-5)     (low byte -> stack)
  r = complement_shift_u32(f32@BCA8, 0.0, 1e-5)
  derate = -5.0   if u8@AAC6==1 && s==0 && 2000.0 > f32@B594 && u8@CCE4==1
  derate = f32@A994 if (above false) && u8@BC02==0 && f32@A9A4>0.0
                   && (u8@ROM 0x6E094==0 || r==0)     [enable byte is 0 -> always]
  derate = f32@A630 otherwise
  f32@A62C = saturate(derate, f32@A648, 65.0)
r0 at return is the last integer the branch chain left in it: 0 on the @A994
path, masked CCE4 on the -5.0 path, else masked AAC6 / 0x12280 / masked CCE4
per the failing gate (the reference model mirrors the register exactly).

Run: python3 c/tests/test_calculateDSCLeadingTimingDerate_0x121A4.py [N]
     (N = random inputs per seed; default 100000 -> 500000 across 5 seeds)
"""
import os, random, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2, ts

ROM = os.path.join(ROOT, 'roms', 'stock', '60E0FC00.bin')
ADDR = 0x121A4

# ---- RAM addresses used by the ROM function ----
A780 = 0xFFFFA780   # f32 deadband input 1
BCA8 = 0xFFFFBCA8   # f32 deadband input 2
AAC6 = 0xFFFFAAC6   # u8 gate byte 1 (==1)
B594 = 0xFFFFB594   # f32 RPM gate (< 2000.0)
CCE4 = 0xFFFFCCE4   # u8 gate byte 2 (==1)
BC02 = 0xFFFFBC02   # u8 middle-branch gate (==0)
A9A4 = 0xFFFFA9A4   # f32 middle-branch gate (> 0.0)
A994 = 0xFFFFA994   # f32 middle derate reference
A630 = 0xFFFFA630   # f32 default derate reference
A648 = 0xFFFFA648   # f32 clamp low
A62C = 0xFFFFA62C   # f32 output (leading-timing derate)

# ---- ROM calibration constants ----
C_DEADBAND = 0x00012278   # 1e-5f
C_RPM_GATE = 0x00012280   # 2000.0f
C_ENABLE   = 0x0006E094   # u8, ==0x00 in this ROM
C_DSC_CUT  = 0x0006E098   # -5.0f
C_CLAMP_HI = 0x0006E0B0   # 65.0f

STACK_LO = 0xFFFFDE00      # task stack window (skipped in the compare)
STACK_HI = 0xFFFFDF00


def f32_at(rom, a):
    return struct.unpack('>f', rom[a:a + 4])[0]


def setf(m, a, v):
    for i, b in enumerate(struct.pack('>f', ts(v))):
        m[a + i] = b


def gf(m, a):
    return struct.unpack('>f', bytes(m.get(a + i, 0) for i in range(4)))[0]


def gb(m, a):
    return m.get(a, 0)


def is_not_zero(x):
    """Mirror of ROM 0x2440 (complement_shift_u32) with center=0, tol=1e-5:
    returns 1 iff |x| > 1e-5 (single-precision fsub/fadd first)."""
    t = ts(1e-5)
    return 1 if (ts(-t) > x or x > t) else 0


def saturate(v, lo, hi):
    """Mirror of ROM 0x2404: v <= lo -> lo ; v >= hi -> hi ; else v."""
    if v <= lo:
        return lo
    if v >= hi:
        return hi
    return v


def ref(m, rom):
    """Line-for-line mirror of calculateDSCLeadingTimingDerate_0x121A4().
    Returns (RAM-effect dict, expected r0)."""
    m = dict(m)

    # call 1: complement_shift_u32(fr4=f32@A780, fr5=0.0, fr6=1e-5) -> r0
    r0 = is_not_zero(gf(m, A780))
    saved = r0 & 0xFF                      # mov.b r0,@r15 (low byte)

    # call 2: complement_shift_u32(fr4=f32@BCA8, fr5=0.0, fr6=1e-5) -> r4
    r4 = is_not_zero(gf(m, BCA8))

    # mov.b @AAC6 (sign-ext) ; extu.b -> r0 = byte & 0xFF
    r0 = gb(m, AAC6) & 0xFF
    dsc = False
    if r0 == 1 and saved == 0:
        r0 = 0x12280                       # mova 0x12280 (r0 kept if gate fails)
        if 2000.0 > gf(m, B594):           # fcmp/gt fr15,fr3 -> fr3(2000)>fr15(@B594)
            r0 = gb(m, CCE4) & 0xFF
            if r0 == 1:
                dsc = True

    if dsc:
        derate = -5.0                      # f32@ROM 0x6E098
    elif gb(m, BC02) != 0:
        derate = gf(m, A630)
    elif not (gf(m, A9A4) > 0.0):
        derate = gf(m, A630)
    else:
        r0 = 0                             # mov.b @ROM 0x6E094 (==0x00)
        derate = gf(m, A994)

    out = saturate(derate, gf(m, A648), 65.0)
    setf(m, A62C, out)
    return m, r0


def pick_f(rng):
    """Float pool: uniform spans plus threshold/edge values."""
    return rng.choice([
        rng.uniform(-40, 40),
        rng.uniform(1800, 2200),           # around the 2000.0 RPM gate
        rng.uniform(-1e-4, 1e-4),          # around the 1e-5 deadband
        rng.uniform(-1, 1),
        -0.0, 0.0, 1e-5, -1e-5, 1e-6, -1e-6, 1e-30, -1e-30,
        3.4e38, -3.4e38, 1e-40, -1e-40,
    ])


def gen_state(rng):
    """Random seeded RAM hitting every branch combination; the output word is
    junk so a missed write is caught."""
    ram = {}
    for a in (A780, BCA8, B594, A9A4, A994, A630, A648, A62C):
        setf(ram, a, pick_f(rng))
    ram[AAC6] = rng.choice([0, 1, 1, 1, 2])
    ram[CCE4] = rng.choice([0, 1, 1, 1, 2])
    ram[BC02] = rng.choice([0, 0, 0, 1])
    return ram


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    rom = open(ROM, 'rb').read()
    assert f32_at(rom, C_DEADBAND) == ts(1e-5)   # single-precision 1e-5
    assert f32_at(rom, C_RPM_GATE) == 2000.0
    assert rom[C_ENABLE] == 0x00
    assert f32_at(rom, C_DSC_CUT) == -5.0
    assert f32_at(rom, C_CLAMP_HI) == 65.0

    cpu = SH2(rom)
    seeds = (0x121A4, 0x12342, 0x12236, 0xA62C, 0x12192)
    total_fails = 0

    for seed in seeds:
        rng = random.Random(seed)
        fails = 0
        for it in range(N):
            ram = gen_state(rng)
            want, want_r0 = ref(ram, rom)
            try:
                cpu.call(ADDR, ram=ram)
            except Exception as e:
                print('EMULATOR EXC seed=0x%X iter=%d: %s' % (seed, it, e))
                fails += 1
                break
            bad = []
            allk = set(k for k in want if isinstance(k, int)) | set(cpu.ram.keys())
            for k in allk:
                if STACK_LO <= k <= STACK_HI:    # task stack area
                    continue
                if cpu.ram.get(k, 0) != want.get(k, 0):
                    bad.append((k, cpu.ram.get(k, 0), want.get(k, 0)))
            if bad or cpu.r[0] != want_r0:
                print('MISMATCH seed=0x%X iter=%d: r0=%d want_r0=%d %s' %
                      (seed, it, cpu.r[0], want_r0,
                       {hex(k): (hex(g), hex(e)) for k, g, e in bad[:10]}))
                print('  A780=%r BCA8=%r AAC6=%d B594=%r CCE4=%d BC02=%d '
                      'A9A4=%r A994=%r A630=%r A648=%r' %
                      (gf(ram, A780), gf(ram, BCA8), ram.get(AAC6, 0),
                       gf(ram, B594), ram.get(CCE4, 0), ram.get(BC02, 0),
                       gf(ram, A9A4), gf(ram, A994), gf(ram, A630),
                       gf(ram, A648)))
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
    print('OK  0x121A4 calculateDSCLeadingTimingDerate '
          '(%d random inputs across %d seeds)' % (N * len(seeds), len(seeds)))
    print('\nAll calculateDSCLeadingTimingDerate_0x121A4 tests passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()
