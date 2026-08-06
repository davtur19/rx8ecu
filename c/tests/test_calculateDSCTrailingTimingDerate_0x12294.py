#!/usr/bin/env python3
"""test_calculateDSCTrailingTimingDerate_0x12294.py

Differential test for ROM 0x12294 (60E0FC00.bin) — lift
c/calculateDSCTrailingTimingDerate_0x12294.c.

Runs the ACTUAL ROM bytes of 0x12294 — including the real sub-calls
complement_shift_u32 @0x2440 (x2) and saturate @0x2404 — in tools/sh2emu.py
over seeded RAM states (the oracle) and compares the full post-call RAM
overlay (byte-exact, task-stack window 0xFFFFDE00..DF00 skipped) plus the
return register r0 against a Python reference model that mirrors the C lift
line-for-line.

Entry-point / range note: 0x12294 IS the real entry point (function-pointer
slot @0x144DC of the engineControlCalculateTiming dispatcher 0x141FC table;
valid prologue; preceding function = the DSC-leading twin 0x121A4 ends rts
@0x1224E).  The symbols CSV row is calculateDSCTrailingTimingDerate? with end
0x012326 — the real function runs to rts @0x1233E (delay pop @0x12340), so the
CSV is widened to 0x012294..0x012342 and the "?" dropped (the literal pool
@0x12384..0x123B8 is a shared tail block; next function @0x12342).  The phantom
"modifyTrailingTiming" row @0x012326 (inside this function) is removed.

Key semantic facts (see the lift header): void trailing-timing DSC derate writer.
  s = complement_shift_u32(f32@A784, 0.0, 1e-5)     (low byte -> stack)
  r = complement_shift_u32(f32@BCA8, 0.0, 1e-5)
  derate = 10.0   if u8@AAC6==1 && s==0 && 2000.0 > f32@B594 && u8@CCE4==1
  derate = f32@A990 if (above false) && u8@BC02==0 && f32@A9A4>0.0
                   && (u8@ROM 0x6E095==0 || r==0)     [enable byte is 0 -> always]
  derate = f32@A638 otherwise
  f32@A634 = saturate(derate, f32@A658, 65.0)
r0 at return is the last integer the branch chain left in it: 0 on the @A990
path, masked CCE4 on the 10.0 path, else masked AAC6 / 0x123A4 / masked CCE4
per the failing gate (the reference model mirrors the register exactly).

Run: python3 c/tests/test_calculateDSCTrailingTimingDerate_0x12294.py [N]
     (N = random inputs per seed; default 100000 -> 500000 across 5 seeds)
"""
import os, random, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2, ts

ROM = os.path.join(ROOT, 'roms', 'stock', '60E0FC00.bin')
ADDR = 0x12294

# ---- RAM addresses used by the ROM function ----
A784 = 0xFFFFA784   # f32 deadband input 1
BCA8 = 0xFFFFBCA8   # f32 deadband input 2
AAC6 = 0xFFFFAAC6   # u8 gate byte 1 (==1)
B594 = 0xFFFFB594   # f32 RPM gate (< 2000.0)
CCE4 = 0xFFFFCCE4   # u8 gate byte 2 (==1)
BC02 = 0xFFFFBC02   # u8 middle-branch gate (==0)
A9A4 = 0xFFFFA9A4   # f32 middle-branch gate (> 0.0)
A990 = 0xFFFFA990   # f32 middle derate reference
A638 = 0xFFFFA638   # f32 default derate reference
A658 = 0xFFFFA658   # f32 clamp low
A634 = 0xFFFFA634   # f32 output (trailing-timing derate)

# ---- ROM calibration constants ----
C_DEADBAND = 0x0001239C   # 1e-5f
C_RPM_GATE = 0x000123A4   # 2000.0f
C_ENABLE   = 0x0006E095   # u8, ==0x00 in this ROM
C_DSC_CUT  = 0x0006E0CC   # 10.0f
C_CLAMP_HI = 0x0006E0E4   # 65.0f
MAXA      = 0x123A4        # mova addr left in r0 on the RPM-gate-fail path

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
    """Line-for-line mirror of calculateDSC_TrailingTimingDerate_0x12294().
    Returns (RAM-effect dict, expected r0)."""
    m = dict(m)

    # call 1: complement_shift_u32(fr4=f32@A784, fr5=0.0, fr6=1e-5) -> r0
    r0 = is_not_zero(gf(m, A784))
    saved = r0 & 0xFF                      # mov.b r0,@r15 (low byte)

    # call 2: complement_shift_u32(fr4=f32@BCA8, fr5=0.0, fr6=1e-5) -> r4
    r4 = is_not_zero(gf(m, BCA8))

    # mov.b @AAC6 (sign-ext) ; extu.b -> r0 = byte & 0xFF
    r0 = gb(m, AAC6) & 0xFF
    dsc = False
    if r0 == 1 and saved == 0:
        r0 = MAXA                              # mova 0x123A4 (r0 kept if gate fails)
        if 2000.0 > gf(m, B594):              # fcmp/gt fr15,fr3 -> 2000 > @B594
            r0 = gb(m, CCE4) & 0xFF
            if r0 == 1:
                dsc = True

    if dsc:
        derate = 10.0                          # f32@ROM 0x6E0CC
    elif gb(m, BC02) != 0:
        derate = gf(m, A638)
    elif not (gf(m, A9A4) > 0.0):
        derate = gf(m, A638)
    else:
        r0 = 0                                 # mov.b @ROM 0x6E095 (==0x00)
        derate = gf(m, A990)

    out = saturate(derate, gf(m, A658), 65.0)
    setf(m, A634, out)
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
    for a in (A784, BCA8, B594, A9A4, A990, A638, A658, A634):
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
    assert f32_at(rom, C_DSC_CUT) == 10.0
    assert f32_at(rom, C_CLAMP_HI) == 65.0

    cpu = SH2(rom)
    seeds = (0x12294, 0x12352, 0x12326, 0xA634, 0x121A4)
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
                print('EMULATOR AVERR seed=0x%X iter=%d: %s' % (seed, it, e))
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
                print('  A784=%r BCA8=%r AAC6=%d B594=%r CCE4=%d BC02=%d '
                      'A9A4=%r A990=%r A638=%r A658=%r' %
                      (gf(ram, A784), gf(ram, BCA8), ram.get(AAC6, 0),
                       gf(ram, B594), ram.get(CCE4, 0), ram.get(BC02, 0),
                       gf(ram, A9A4), gf(ram, A990), gf(ram, A638),
                       gf(ram, A658)))
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
    print('OK  0x12294 calculateDSCTrailingTimingDerate '
          '(%d random inputs across %d seeds)' % (N * len(seeds), len(seeds)))
    print('\nAll calculateDSCTrailingTimingDerate_0x12294 tests passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()