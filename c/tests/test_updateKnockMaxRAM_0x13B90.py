#!/usr/bin/env python3
"""test_updateKnockMaxRAM_0x13B90.py

Differential test for ROM 0x13B90 (60E1D400.bin) — lift
c/updateKnockMaxRAM_0x13B90.c.

Runs the ACTUAL ROM bytes of 0x13B90 in tools/sh2emu.py over seeded RAM states
(the oracle) and compares the full post-call RAM overlay (byte-exact) plus the
return register r0 against a Python reference model that mirrors the C lift
line-for-line.

Entry-point note: 0x13B90 IS the real entry point — the only ROM reference is
the function-pointer slot @0x147A0 in the dispatcher engineControlCalculateTiming
(0x14584) dispatch table (c/engineControlCalculateTiming.c line 211).  Valid
prologue / rts+delay at 0x13BCA/0x13BCC; no branches into the body.

Key semantic facts (see the lift header):
  * Gate: u8@0xFFFFA74A must be 1, else the function returns with no side
    effects (r0 = the gate byte value).
  * 0x3EE0A read of the checksummed struct @0xFFFF8038:
        valid checksum (u16@+4 or u16@+6 == (u16)~(u16@+0 + u16@+2))
        -> prev = f32@0xFFFF8038
        invalid -> prev = 0.0 and fault flag u8@0xFFFFC6AC = 1 (via 0x3F050)
  * firstOrderFilter(sig=f32@A734, sigprev=prev, ff=0.0039, min=1e-5)
    — snap to sig when |sig-filtered| <= 1e-5; bootstrap (return sig) when
    sigprev is inf/NaN.
  * 0x13E6C = saturate(v, table_select(f32@B5B8), 0.0) using status bytes
    B5A4/BB55/BCA9, threshold u8@0x00079838 (5), tables @0x6B678/@0x6B664.
  * 0x3EEB8 write-back: f32@0xFFFF8038 = out, u16@+4 = u16@+6 =
    (u16)~(se16(hi)+se16(lo)) of the f32 bits; skipped entirely when out is
    NaN (r0 = 1), else r0 = 0.
  * The four sub-calls (0x3EE0A / 0x23B0 / 0x13E6C / 0x3EEB8) are executed in
    the second emulator instance cpu2 (oracle) with their RAM merged — the
    same trick the 0x44824 / 0x12A48 tests use for helper calls.

Run: python3 c/tests/test_updateKnockMaxRAM_0x13B90.py [N]
     (N = random inputs per seed; default 100000 -> 500000 across 5 seeds)
"""
import os, random, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2, ts

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ADDR = 0x13B90

# ---- RAM addresses (see c/updateKnockMaxRAM_0x13B90.c header) ----
A74A = 0xFFFFA74A   # u8  enable gate (must == 1)
A734 = 0xFFFFA734   # f32 first-order-filter target
S8038 = 0xFFFF8038  # checksummed f32 struct base (f32@+0, u16 w0..w3 @+0/+2/+4/+6)
C6AC = 0xFFFFC6AC   # u8  fault flag (set to 1 by 0x3EE0A on bad checksum)
B5A4 = 0xFFFFB5A4   # u8  0x13E6C table-select status
BB55 = 0xFFFFBB55   # u8  0x13E6C table-select status
BCA9 = 0xFFFFBCA9   # u8  0x13E6C table-select status
B5B8 = 0xFFFFB5B8   # f32 0x13E6C lookup input (RPM)

ROM_79870 = 0x00079870   # f32 0.0    (0x3EE0A fallback)
ROM_79874 = 0x00079874   # f32 0.0039 (firstOrderFilter factor)
ROM_13C20 = 0x00013C20   # f32 1e-5   (firstOrderFilter deadband)
ROM_79838 = 0x00079838   # u8  5      (0x13E6C table-select threshold)

SENT16 = 0xA5A5
SENT32 = 0x11223344


def put(ram, a, n, v):
    for i in range(n):
        ram[a + i] = (v >> (8 * (n - 1 - i))) & 0xFF


def setf(ram, a, v):
    for i, b in enumerate(struct.pack('>f', ts(v))):
        ram[a + i] = b


def rdf(m, a):
    return struct.unpack('>f', bytes(m.get(a + i, 0) for i in range(4)))[0]


def rdfb(buf, a):
    return struct.unpack('>f', bytes(buf[a + i] for i in range(4)))[0]


def s16(x):
    x &= 0xFFFF
    return x - 0x10000 if x & 0x8000 else x


def ref(cpu2, m, rom):
    """Line-for-line mirror of updateKnockMaxRAM_0x13B90().

    The four sub-calls are executed in `cpu2` (oracle) with their RAM merged.
    Returns (RAM-effect dict, expected r0).
    """
    m = dict(m)

    gate = m.get(A74A, 0)
    if gate != 1:                  # bf/s 0x13BC8 — early return, no writes
        return m, gate & 0xFF

    # 0x3EE0A(0xFFFF8038, fr4=f32@0x79870)
    cpu2.call(0x3EE0A, r4=S8038, fr={4: rdfb(rom, ROM_79870)}, ram=m)
    m = dict(cpu2.ram); prev = cpu2.fr[0]

    # 0x23B0 firstOrderFilter(fr4=f32@A734, fr5=prev, fr6=0.0039, fr7=1e-5)
    cpu2.call(0x23B0, fr={4: rdf(m, A734), 5: prev,
                          6: rdfb(rom, ROM_79874), 7: rdfb(rom, ROM_13C20)}, ram=m)
    m = dict(cpu2.ram); v = cpu2.fr[0]

    # 0x13E6C(fr4=v)
    cpu2.call(0x13E6C, fr={4: v}, ram=m)
    m = dict(cpu2.ram); out = cpu2.fr[0]

    # 0x3EEB8(0xFFFF8038, fr4=out) — tail call
    cpu2.call(0x3EEB8, r4=S8038, fr={4: out}, ram=m)
    m = dict(cpu2.ram)
    return m, cpu2.r[0]


def gen_state(rng):
    """Random seeded RAM hitting every gate/checksum/filter/table branch.

    A74A covers the pass gate plus early-return values; the struct @0xFFFF8038
    is seeded with valid/invalid checksums and a stored float that is close to
    (snap) or far from (filter) the target, plus inf/NaN (bootstrap) and NaN
    outputs (0x3EEB8 skip); 0x13E6C status bytes and B5B8 cover all four table
    selections and the lookup axis; C6AC is junk so a missed fault write is
    caught.
    """
    ram = {}

    # enable gate
    ram[A74A] = rng.choice([0, 1, 1, 1, 2, 255])

    # checksummed struct: w0, w1 (+ w2/w3 sometimes = check)
    w0 = rng.randint(0, 0xFFFF); w1 = rng.randint(0, 0xFFFF)
    chk = (~((w0 + w1) & 0xFFFF)) & 0xFFFF
    r = rng.random()
    if r < 0.35:
        w2, w3 = chk, rng.randint(0, 0xFFFF)       # valid via w2
    elif r < 0.55:
        w2, w3 = rng.randint(0, 0xFFFF), chk       # valid via w3
    elif r < 0.75:
        w2, w3 = rng.randint(0, 0xFFFF), rng.randint(0, 0xFFFF)   # invalid
    else:
        w2, w3 = chk, chk
    put(ram, S8038, 2, w0); put(ram, S8038 + 2, 2, w1)
    put(ram, S8038 + 4, 2, w2); put(ram, S8038 + 6, 2, w3)

    # stored float (sigprev) — close to A734 for the snap path, far for the
    # filter path, inf/NaN for the bootstrap path; sentinel-free junk check
    setf(ram, S8038, rng.uniform(-200.0, 200.0))
    if rng.random() < 0.25:
        setf(ram, S8038, rng.choice([0.0, float('nan'), float('inf'),
                                     float('-inf')]))

    # filter target (sig)
    setf(ram, A734, rng.uniform(-200.0, 200.0))
    if rng.random() < 0.15:
        setf(ram, A734, rng.choice([0.0, float('nan'), float('inf'),
                                    float('-inf')]))
    if rng.random() < 0.2:
        setf(ram, A734, rdf(ram, S8038) + rng.choice([0.0, 1e-6, -1e-6,
                                                      0.01, -0.01]))

    # fault flag junk (a missed 0x3EE0A fault write is caught)
    ram[C6AC] = rng.choice([0, 1, 0x55, 0xFF])

    # 0x13E6C inputs: status bytes + lookup axis
    ram[B5A4] = rng.randint(0, 3)
    ram[BB55] = rng.randint(0, 255)
    ram[BCA9] = rng.randint(0, 255)
    setf(ram, B5B8, rng.uniform(0.0, 8000.0))

    # struct words get sentinels so a missed write is caught by comparison
    if rng.random() < 0.5:
        ram[S8038 + 4] = (SENT16 >> 8) & 0xFF; ram[S8038 + 5] = SENT16 & 0xFF
        ram[S8038 + 6] = (SENT16 >> 8) & 0xFF; ram[S8038 + 7] = SENT16 & 0xFF
    return ram


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    rom = open(ROM, 'rb').read()

    cpu = SH2(rom)
    cpu2 = SH2(rom)          # dedicated instance for the sub-calls in ref()
    seeds = (0x13B90, 0xA74A, 0x8038, 0xA734, 0x6E3E4)
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
                if 0xFFFFDE00 <= k <= 0xFFFFDF00:   # task stack area
                    continue
                if cpu.ram.get(k, 0) != want.get(k, 0):
                    bad.append((k, cpu.ram.get(k, 0), want.get(k, 0)))
            if bad or cpu.r[0] != want_r0:
                print('MISMATCH seed=0x%X iter=%d: r0=%d want_r0=%d %s' %
                      (seed, it, cpu.r[0], want_r0,
                       {hex(k): (hex(g), hex(e)) for k, g, e in bad[:10]}))
                print('  A74A=%d stored=%r A734=%r B5A4=%d BB55=%d BCA9=%d' % (
                    ram.get(A74A, 0), rdf(ram, S8038), rdf(ram, A734),
                    ram.get(B5A4, 0), ram.get(BB55, 0), ram.get(BCA9, 0)))
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
    print('OK  0x13B90 updateKnockMaxRAM '
          '(%d random inputs across %d seeds)' % (N * len(seeds), len(seeds)))
    print('\nAll updateKnockMaxRAM_0x13B90 tests passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()
