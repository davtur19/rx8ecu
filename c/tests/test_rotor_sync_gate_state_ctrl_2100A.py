#!/usr/bin/env python3
"""test_rotor_sync_gate_state_ctrl_2100A.py

Differential test for ROM 0x2100A (60E1D400.bin) — lift
c/rotor_sync_gate_state_ctrl_2100A.c.

Runs the ACTUAL ROM bytes of 0x2100A (including the shared max helper
@0x23E4) in tools/sh2emu.py over seeded RAM states (the oracle), and compares
the 3 output words — u8@0xFFFFB240 plus f32@0xFFFFB18C / f32@0xFFFFB188 —
against a Python reference model that mirrors the C lift line-for-line.

Key semantic facts (see the lift header):
  * fcmp/gt Fm,Fn sets T = (Fn > Fm) on this core, so "fcmp/gt fr4,fr5"
    means -40.0 > coolant and "fcmp/gt fr3,fr7" means fr7 > 1000.0.
  * The shared helper @0x23E4 (IDA: fpu_mul_float) is actually
    max(fr4, fr5) — verified against the emulator (fr={4:10,5:5} -> fr0=10,
    fr={4:3,5:8} -> fr0=8).  The decay therefore clamps the decremented
    state at 0.0 from below: B18C/B188 = max(state - 0.0667, 0.0).
  * The function does NOT write A734/A738 (the lead/trail timing words).  It
    manages a cold/validity flag B240 and two state floats B18C/B188 that are
    set to 1.0 together, decayed independently, or cleared to 0.0 together.
    The lead/trail split is therefore NOT here.
  * fr15 = 0.0 (fldi0 in the delay slot of 0x21090) on every path.

Run: python3 c/tests/test_rotor_sync_gate_state_ctrl_2100A.py [N]
     (N = random inputs per seed; default 100000 -> 500000 across 5 seeds)
"""
import os, random, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2, ts

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ADDR = 0x2100A

# ---- RAM map (see c/rotor_sync_gate_state_ctrl_2100A.c header) ----
AA10 = 0xFFFFAA10   # f32 coolant-temp word (fr4 input)
C6B4 = 0xFFFFC6B4   # f32 (fr7 input, compared against CAL_1000)
B1B2 = 0xFFFFB1B2   # u16 gate (r4, used unsigned)
B1C7 = 0xFFFFB1C7   # u8 gate (r7)
B1C9 = 0xFFFFB1C9   # u8 gate (r5)
B1C4 = 0xFFFFB1C4   # u8 gate (r6)
B1C2 = 0xFFFFB1C2   # u8 gate (r0)
C600 = 0xFFFFC600   # u8 engine-off flag (r2)
CCE1 = 0xFFFFCCE1   # u8 enable gate (r1)
CDA0 = 0xFFFFCDA0   # u8 gate (r2)
B19C = 0xFFFFB19C   # u8 allow-decrement gate (r3)
B240 = 0xFFFFB240   # u8 output cold/validity flag (r12)
B18C = 0xFFFFB18C   # f32 output state word (r13)
B188 = 0xFFFFB188   # f32 output state word (r14)

# ---- ROM constants ----
F_CAL1 = None   # f32@0x71C54 = -40.0
F_CAL2 = None   # f32@0x71C58 = 3.0
F_DEC  = None   # f32@0x71C74 / 0x71C78 = 0.0667
F_1000 = None   # f32@0x71C7C = 1000.0


def f32_at(rom, a):
    return struct.unpack('>f', rom[a:a + 4])[0]


def gf(ram, a):
    """Read big-endian f32 from the seeded RAM overlay (missing bytes = 0)."""
    return struct.unpack('>f', bytes(ram.get(a + i, 0) for i in range(4)))[0]


def gb(ram, a):
    return ram.get(a, 0)


def model(ram, rom):
    """Line-for-line mirror of rotor_sync_gate_state_ctrl_2100A().

    Returns a full RAM-effect dict (int keys -> byte values) so the caller can
    diff it against the emulator's post-call RAM (like test_omp_control_task_1825E).
    """
    m = dict(ram)
    fr4 = gf(m, AA10)                 # f32@AA10
    fr7 = gf(m, C6B4)                 # f32@C6B4
    r4 = (gb(m, B1B2) << 8) | gb(m, B1B2 + 1)   # u16@B1B2
    r7 = gb(m, B1C7)
    r5 = gb(m, B1C9)
    r6 = gb(m, B1C4)
    r0 = gb(m, B1C2)
    eng_off = gb(m, C600)
    cce1 = gb(m, CCE1)
    cda0 = gb(m, CDA0)
    fr15 = 0.0
    fr5 = F_CAL1                     # -40.0
    fr6 = ts(fr5 - F_CAL2)           # fsub @0x2102A -> -43.0

    def wrf(a, v):
        for i, x in enumerate(struct.pack('>f', ts(v))):
            m[a + i] = x

    def set0():
        wrf(B18C, 0.0)
        wrf(B188, 0.0)

    def set1():
        wrf(B18C, 1.0)
        wrf(B188, 1.0)

    def fc():
        """0x210FC + 0x21132 block (decay via shared max @0x23E4)."""
        if gb(m, B19C) != 1:
            set0()
            return
        if r4 == 0 or r7 == 0 or r5 == 0 or fr7 > F_1000:
            pass                        # fall through to decay
        elif r6 != 0:
            set0()
            return
        v = ts(gf(m, B18C) - F_DEC)     # fsub @0x2113A
        wrf(B18C, max(fr15, v))         # 0x23E4 = max(fr5=0, fr4)
        v = ts(gf(m, B188) - F_DEC)     # fsub @0x2114A
        wrf(B188, max(fr15, v))

    # ---- Block A: B240 flag (fcmp/gt Fm,Fn -> T = Fn > Fm) ----
    if fr5 > fr4:                       # -40.0 > coolant  (bt/s 0x2103A)
        if fr6 > fr4:                   # -43.0 > coolant  (bf/s 0x2107E)
            m[B240] = 0
        # else B240 unchanged
    else:
        m[B240] = 1

    # ---- Block B: gated state update ----
    if eng_off != 0 or cce1 != 0 or rom[0x71BD0] != 1:
        set0()                          # 0x2115A
    elif m[B240] != 1 or cda0 != 0 or fr7 > F_1000:
        fc()                            # 0x210FC
    else:
        # set-1.0 test (0x210C8..0x210F4)
        if (r0 == 1 and r4 > 0) or (r5 == 1 and r6 == 1) or r7 == 1:
            set1()                      # 0x210F4
        else:
            fc()
    return m


def seed_f32(ram, a, v):
    b = struct.pack('>f', ts(v))
    for i, x in enumerate(b):
        ram[a + i] = x


def gen_state(rng):
    """Random seeded RAM hitting every gate combination."""
    ram = {}
    seed_f32(ram, AA10, rng.uniform(-50.0, 60.0))
    seed_f32(ram, C6B4, rng.uniform(-10.0, 3000.0))
    seed_f32(ram, B18C, rng.uniform(-5.0, 2.0))
    seed_f32(ram, B188, rng.uniform(-5.0, 2.0))
    # edge-flavoured float picks
    if rng.random() < 0.3:
        seed_f32(ram, AA10, rng.choice([-45.0, -42.0, -40.0, -39.0, 0.0, 90.0]))
    if rng.random() < 0.3:
        seed_f32(ram, C6B4, rng.choice([500.0, 999.0, 1000.0, 1001.0, 1500.0]))
    if rng.random() < 0.3:
        seed_f32(ram, B18C, rng.choice([0.0, 1.0, 0.0667, 0.05, -1.0]))
    if rng.random() < 0.3:
        seed_f32(ram, B188, rng.choice([0.0, 1.0, 0.0667, 0.05, -1.0]))
    for a in (B1C7, B1C9, B1C4, B1C2, C600, CCE1, CDA0, B19C):
        ram[a] = rng.choice([0, 1, rng.randint(0, 255)])
    ram[B240] = rng.choice([0, 1, rng.randint(0, 255)])
    ram[B1B2] = rng.randint(0, 255)
    ram[B1B2 + 1] = rng.randint(0, 255)
    if rng.random() < 0.3:
        ram[B1B2] = 0; ram[B1B2 + 1] = 0
    return ram


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    rom = open(ROM, 'rb').read()
    global F_CAL1, F_CAL2, F_DEC, F_1000
    F_CAL1 = f32_at(rom, 0x71C54)
    F_CAL2 = f32_at(rom, 0x71C58)
    F_DEC = f32_at(rom, 0x71C74)
    F_1000 = f32_at(rom, 0x71C7C)
    assert F_CAL1 == -40.0 and F_CAL2 == 3.0 and F_1000 == 1000.0

    cpu = SH2(rom)
    seeds = (0x2100A, 0xB188, 0xCAFE, 0x1234, 0x5555)
    total_fails = 0

    for seed in seeds:
        rng = random.Random(seed)
        fails = 0
        for it in range(N):
            ram = gen_state(rng)
            want = model(ram, rom)
            try:
                cpu.call(ADDR, ram=ram, sr=0xF0)
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
                print('  AA10=%r C6B4=%r B1B2=%d r7=%d r5=%d r6=%d r0=%d '
                      'C600=%d CCE1=%d CDA0=%d B19C=%d B240=%d B18C=%r B188=%r' %
                      (gf(ram, AA10), gf(ram, C6B4), (ram[B1B2] << 8) | ram[B1B2 + 1],
                       ram[B1C7], ram[B1C9], ram[B1C4], ram[B1C2], ram[C600],
                       ram[CCE1], ram[CDA0], ram[B19C], ram[B240],
                       gf(ram, B18C), gf(ram, B188)))
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
    print('OK  0x2100A rotor_sync_gate_state_ctrl  (%d random inputs across %d seeds)'
          % (N * len(seeds), len(seeds)))
    print('\nAll rotor_sync_gate_state_ctrl_2100A tests passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()
