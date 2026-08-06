#!/usr/bin/env python3
"""test_idleTrailingTimingCorrection_0x13544.py

Differential test for ROM 0x13544 (60E0FC00.bin) — lift
c/idleTrailingTimingCorrection_0x13544.c.  Trailing twin of
test_idleLeadingTimingCorrection_0x13414.py (same skeleton, trailing RAM/ROM
block: A71C/A714/A70C/A721, descs 0x686D4/0x686E8, ROM const block 0x726E8..
0x726F8 + word 0x726D2 + pool 0x13660 — all values identical).

Runs the ACTUAL ROM bytes of 0x13544 — including the real sub-calls 2D lookup
@0x2068 and saturate @0x2404 — in tools/sh2emu.py over seeded RAM states (the
oracle) and compares the full post-call RAM overlay (byte-exact, task-stack
window 0xFFFFDE00..DF00 skipped) plus the return register r0 against a Python
reference model.  The sub-calls are executed in a dedicated emulator instance
`cpu2` seeded with the same RAM so single-precision rounding matches the ROM.

Entry-point / range note: 0x13544 IS the real entry point (function-pointer
slot @0x1442C of the engineControlCalculateTiming dispatcher 0x141FC table;
valid prologue; preceding twin 0x13414 ends rts @0x134F4).  CSV range
0x13544..0x13674 is CORRECT (code to rts @0x13624, pool to 0x13672, thunk
updateKnockRamTHUNK at the CSV end).

Key semantic facts (see the lift header): void idle trailing-timing writer.
  fr2  = ts(B594 - B5A0); A71C = fr2
  desc = (B580==0) ? (B588==0 ? 0x686D4 : 0x686E8)
                   : (B586==1 ? 0x686D4 : 0x686E8)
  res  = 2D(desc, fr2); A714 = res
  fr15 = res if (AAC6==1 && B594 > 1500.0 &&
                 (C030 > 0.009765625 || word A424 >= 375)) else 0.0
  load gate A721: 1 if C0D8 <= 0.6, 0 if C0D8 > 0.555, else unchanged
  fr15 = saturate(fr15, -2.8, 0.7) if A721 == 1
  A70C = fr15
r0 at return = u8@A721 & 0xFF (0x2404 never writes r0).

Run: python3 c/tests/test_idleTrailingTimingCorrection_0x13544.py [N]
      (N = random inputs per seed; default 100000 -> 500000 across 5 seeds)
"""
import os, random, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2, ts

ROM = os.path.join(ROOT, 'roms', 'stock', '60E0FC00.bin')
ADDR = 0x13544

# ---- RAM addresses (see c/idleTrailingTimingCorrection_0x13544.c) ----
B594 = 0xFFFFB594   # f32 RPM
C0D8 = 0xFFFFC0D8   # f32 load
B5A0 = 0xFFFFB5A0   # f32 idle RPM target
B580 = 0xFFFFB580   # u8 lookup-select gate
B588 = 0xFFFFB588   # u8 lookup-select gate
B586 = 0xFFFFB586   # u8 lookup-select gate
AAC6 = 0xFFFFAAC6   # u8 idle gate
C030 = 0xFFFFC030   # f32 idle gate
A424 = 0xFFFFA424   # u16 idle gate
A721 = 0xFFFFA721   # u8 load gate / out
A71C = 0xFFFFA71C   # f32 out (RPM error)
A714 = 0xFFFFA714   # f32 out (lookup result)
A70C = 0xFFFFA70C   # f32 out (correction)

FLOAT_RW = [B594, C0D8, B5A0, C030, A71C, A714, A70C]

STACK_LO = 0xFFFFDE00      # task stack window (skipped in the compare)
STACK_HI = 0xFFFFDF00


def romf(rom, a):
    return struct.unpack('>f', rom[a:a + 4])[0]


def gf(m, a):
    return struct.unpack('>f', bytes(m.get(a + i, 0) for i in range(4)))[0]


def setf(m, a, v):
    for i, b in enumerate(struct.pack('>f', ts(v))):
        m[a + i] = b


def gw(m, a):
    return (m.get(a, 0) << 8) | m.get(a + 1, 0)


def gb(m, a):
    return m.get(a, 0)


def merge(cpu2, m):
    return {k: v for k, v in cpu2.ram.items() if not (STACK_LO <= k <= STACK_HI)}


def ref(cpu2, m, rom):
    """Line-for-line mirror of idleTrailingTimingCorrection_0x13544().
    Returns (RAM-effect dict, expected r0)."""
    m = dict(m)
    rpm = gf(m, B594)
    load = gf(m, C0D8)
    fr2 = ts(rpm - gf(m, B5A0))
    setf(m, A71C, fr2)

    # ---- 2D lookup ----
    if gb(m, B580) == 0:
        desc = 0x686D4 if gb(m, B588) == 0 else 0x686E8
    else:
        desc = 0x686D4 if gb(m, B586) == 1 else 0x686E8
    cpu2.call(0x2068, r4=desc, fr={4: fr2}, ram=dict(m))
    m = merge(cpu2, m)
    res = cpu2.fr[0]
    setf(m, A714, res)

    # ---- idle gate -> fr15 (fcmp/gt Fm,Fn == Fn > Fm, i.e. inverted) ----
    gate = (gb(m, AAC6) == 1 and romf(rom, 0x726E8) > rpm and
            (romf(rom, 0x726EC) > gf(m, C030) or
             gw(m, A424) >= struct.unpack('>H', rom[0x726D2:0x726D4])[0]))
    fr15 = res if gate else 0.0

    # ---- load gate byte A721 (fr14 = load survives the lookup: fr0-fr5 only) ----
    fr5 = romf(rom, 0x726F0)
    if load < fr5:                            # 0.6 > load
        if load < ts(fr5 + romf(rom, 0x13660)):   # 0.555 > load
            m[A721] = 0
    else:
        m[A721] = 1
    a721 = gb(m, A721)

    # ---- saturate when the gate is set ----
    if a721 == 1:
        cpu2.call(0x2404, fr={4: fr15, 5: romf(rom, 0x726F4),
                              6: romf(rom, 0x726F8)}, ram=dict(m))
        m = merge(cpu2, m)
        fr15 = cpu2.fr[0]

    setf(m, A70C, fr15)
    return m, a721 & 0xFF


def pick_f(rng):
    """Float pool: wide spans plus the gate boundaries (1500.0 RPM, 0.6/0.555
    load, 1/1024, map range) and NaN/Inf."""
    return rng.choice([
        rng.uniform(0, 10000),
        rng.uniform(1490, 1510),
        rng.uniform(0, 2),
        rng.uniform(0.4, 0.7),
        rng.uniform(-1, 1),
        rng.uniform(-200, 200),
        0.0, -0.0, 1500.0, 0.6, 0.555, 0.009765625, 1.0 / 1024.0,
        float('nan'), float('inf'), float('-inf'),
    ])


def gen_state(rng):
    """Random seeded RAM hitting every branch combination; every output word
    is junk so a missed write is caught."""
    ram = {}
    for a in FLOAT_RW:
        setf(ram, a, pick_f(rng))
    ram[B580] = rng.choice([0, 0, 1, 1, 2])
    ram[B588] = rng.choice([0, 0, 1, 1, 2])
    ram[B586] = rng.choice([0, 0, 1, 1, 2])
    ram[AAC6] = rng.choice([0, 0, 1, 1, 1, 2])
    ram[A721] = rng.choice([0, 1, 0xEE, 0xFF])
    v = rng.choice([0, 375, 374, 376, 0xFFFF, rng.randint(0, 65535)])
    ram[A424] = v >> 8
    ram[A424 + 1] = v & 0xFF
    return ram


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    rom = open(ROM, 'rb').read()
    assert romf(rom, 0x726E8) == 1500.0
    assert romf(rom, 0x726EC) == ts(0.009765625)
    assert struct.unpack('>H', rom[0x726D2:0x726D4])[0] == 375
    assert romf(rom, 0x726F0) == ts(0.6)
    # pool literal is -0.045 one-ULP off (BD3851EB, not the nearest float32)
    assert abs(romf(rom, 0x13660) - (-0.045)) < 1e-6
    assert romf(rom, 0x726F4) == ts(-2.8)
    assert romf(rom, 0x726F8) == ts(0.7)

    cpu = SH2(rom)
    cpu2 = SH2(rom)             # dedicated instance for the leaves in ref()
    seeds = (0x13544, 0x13414, 0x686E8, 0xA721, 0x726F0)
    total_fails = 0

    for seed in seeds:
        rng = random.Random(seed)
        fails = 0
        for it in range(N):
            ram = gen_state(rng)
            want, want_r0 = ref(cpu2, ram, rom)
            try:
                cpu.call(ADDR, ram=ram)
            except Exception as e:
                print('EMULATOR EXC seed=0x%X iter=%d: %s' % (seed, it, e))
                fails += 1
                break
            bad = []
            allk = set(k for k in want if isinstance(k, int)) | set(cpu.ram.keys())
            for k in allk:
                if STACK_LO <= k <= STACK_HI:
                    continue
                if cpu.ram.get(k, 0) != want.get(k, 0):
                    bad.append((k, cpu.ram.get(k, 0), want.get(k, 0)))
            if bad or cpu.r[0] != want_r0:
                print('MISMATCH seed=0x%X iter=%d: r0=%d want_r0=%d %s' %
                      (seed, it, cpu.r[0], want_r0,
                       {hex(k): (hex(g), hex(e)) for k, g, e in bad[:10]}))
                print('  B594=%r C0D8=%r B5A0=%r C030=%r A424=%d '
                      'B580=%d B588=%d B586=%d AAC6=%d A721=%d' %
                      (gf(ram, B594), gf(ram, C0D8), gf(ram, B5A0),
                       gf(ram, C030), gw(ram, A424),
                       ram.get(B580, 0), ram.get(B588, 0), ram.get(B586, 0),
                       ram.get(AAC6, 0), ram.get(A721, 0)))
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
    print('OK  0x13544 idleTrailingTimingCorrection '
          '(%d random inputs across %d seeds)' % (N * len(seeds), len(seeds)))
    print('\nAll idleTrailingTimingCorrection_0x13544 tests passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()