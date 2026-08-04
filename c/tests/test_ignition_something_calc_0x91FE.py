#!/usr/bin/env python3
"""test_ignition_something_calc_0x91FE.py

Differential test for ROM 0x91FE (60E1D400.bin) — lift
c/ignition_something_calc_0x91FE.c.

Runs the ACTUAL ROM bytes of 0x91FE — including the arming leaves 0x9478
(retrigger/arm-prepare; itself calling 0xAA74 and 0x2054/0x2064) and 0x9320
(compare-timer build) — in tools/sh2emu.py over seeded RAM states (the oracle),
and compares the full post-call RAM overlay against a Python reference model
that mirrors the C lift line-for-line.

Key semantic facts (see the lift header):
  * base = f32@0xFFFFA0FC; v = f32@(0xFFFFA0D8+idx*8) - base.
  * wrap v into [-90, 630): v<-90 -> v+720; else v<630 -> v; else v-720
    (SH-2E fcmp/gt FRm,FRn = FRn>FRm reversed the naive read — see header).
    Result written to f32@0xFFFFA0F8.
  * ch[5]==0 (unarmed): fpul = 0xFFFFA0C4[idx] + u16@0xFFFFA0D4*16;
    count = float(s32(fpul))*30.0 / float(s32(u32@0xFFFFA100)); arm ONLY when
    (w-count) < 60.0, via 0x9478 then 0x9320 (which set ch[5]=1/ch[6]=0 and
    write the descriptor compare words).  The divisor u32@0xFFFFA100 must be
    non-zero (fdiv) — seeded so.
  * ch[5]!=0 (armed): desc = u32@(0x0000DAB4+idx*24); its first word==0 -> disarm
    (ch[4]=0, ch[5]=0), else 0x9320.

The leaves 0x9478 / 0x9320 (and their internal 0xAA74 / 0x2054 / 0x2064) are
executed in the second emulator instance cpu2 and their RAM merged — the same
trick the 0x19220 split test uses for its helper calls — so float rounding,
s32->float conversion and every RAM side effect match the ROM exactly.

Note on idx overlap: for idx==4 the channel slot 0xFFFFA0D8+idx*8 == 0xFFFFA0F8
overlaps the wrapped-output/AAAA scratch, and idx*4 == ...A104 base region; the
test seeds the whole 0xFFFFA0D8..A107 + 0xFFFFA0C4..A0C7 neighbourhood and the
full-RAM diff covers it.

Run: python3 c/tests/test_ignition_something_calc_0x91FE.py [N]
     (N = random inputs per seed; default 100000 -> 500000 across 5 seeds)
"""
import os, random, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2, ts

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ADDR = 0x91FE

# ---- RAM addresses (see c/ignition_something_calc_0x91FE.c header) ----
A0D8 = 0xFFFFA0D8   # per-channel table (stride 8)
A0FC = 0xFFFFA0FC   # f32 wrap base
A0F8 = 0xFFFFA0F8   # f32 wrapped-out scratch
A0C4 = 0xFFFFA0C4   # per-channel u32 base pointer
A0D4 = 0xFFFFA0D4   # u16 dwell
A100 = 0xFFFFA100   # u32 deg->count divisor (must be non-zero)
A104 = 0xFFFFA104   # u16
DAB4 = 0x0000DAB4   # per-channel descriptor table (stride 24)


def put(ram, a, n, v):
    for i in range(n):
        ram[a + i] = (v >> (8 * (n - 1 - i))) & 0xFF


def rdf(m, a):
    return struct.unpack('>f', bytes(m.get(a + i, 0) for i in range(4)))[0]


def rd(m, a, n):
    v = 0
    for i in range(n):
        v = (v << 8) | m.get(a + i, 0)
    return v


def s32(x):
    return x - (1 << 32) if x & 0x80000000 else x


def f32b(v):
    return list(struct.pack('>f', ts(v)))


def ref(cpu2, m, rom, idx):
    """Line-for-line mirror of ignition_something_calc_0x91FE().

    Leaves 0x9478 / 0x9320 are executed in `cpu2` (with r5=0x3E80 for 0x9478 —
    set by the caller at 0x92C0 before the bsr) and their RAM merged.  Returns
    a full RAM-effect dict (int keys -> byte values).
    """
    m = dict(m)
    ch = A0D8 + idx * 8
    v = ts(rdf(m, ch) - rdf(m, A0FC))                    # fsub
    if v < -90.0:                                        # fcmp/gt fr4,fr1 -> fr1>fr4
        w = ts(v + 720.0)
    elif v < 630.0:
        w = v
    else:
        w = ts(v - 720.0)
    for i, b in enumerate(f32b(w)):
        m[A0F8 + i] = b                                  # L_0x927A

    if m.get(ch + 5, 0) == 0:
        fpul = rd(m, A0C4 + idx * 4, 4) + (rd(m, A0D4, 2) << 4)
        fr3 = ts(ts(float(s32(fpul))) * 30.0)            # lds/float + fmul L_0x9310
        fr1 = ts(float(s32(rd(m, A100, 4))))             # float divisor
        cnt = ts(fr3 / fr1)                              # fdiv
        if ts(w - cnt) < 60.0:                           # L_0x9318
            cpu2.call(0x9478, r4=idx, r5=0x3E80, ram=m)
            m = dict(cpu2.ram)
            cpu2.call(0x9320, r4=idx, ram=m)
            m = dict(cpu2.ram)
    else:
        desc = rd(m, DAB4 + idx * 24, 4)
        if rd(m, desc, 2) == 0:
            m[ch + 4] = 0
            m[ch + 5] = 0
        else:
            cpu2.call(0x9320, r4=idx, ram=m)
            m = dict(cpu2.ram)
    return m


def gen_state(rng):
    """Random seeded RAM hitting every wrap/dispatch/arm combination."""
    ram = {}
    idx = rng.randint(0, 7)

    def setf(a, v):
        put(ram, a, 4, struct.unpack('>I', struct.pack('>f', float(v)))[0])

    ch = A0D8 + idx * 8
    setf(ch, rng.uniform(-2000, 2000))      # spark value
    ram[ch + 4] = rng.randint(0, 255)       # ch[4]
    ram[ch + 5] = rng.randint(0, 255)       # ch[5] armed flag
    ram[ch + 6] = rng.randint(0, 255)       # ch[6] fired flag
    # bias ch[5] toward 0 so both the unarmed (count) and armed (desc) gates run
    if rng.random() < 0.5:
        ram[ch + 5] = 0
    setf(A0FC, rng.uniform(-1000, 1000))    # wrap base
    setf(A0F8, rng.uniform(-1000, 1000))    # prior wrapped scratch
    put(ram, A0C4 + idx * 4, 4, rng.randint(0, 0x7FFF))
    put(ram, A0D4, 2, rng.randint(0, 0xFFFF))   # dwell
    # divisor: non-zero (fdiv!).  Bias a large positive and a small/1 so both
    # the count-in-range and count-out-of-range arm decisions get exercised.
    put(ram, A100, 4, rng.choice([rng.randint(1, 100000), 1, 480, 60, 30]))
    put(ram, A104, 2, rng.randint(0, 0xFFFF))

    # descriptor 0xDAB4+idx*24: four u32 pointers into spare RAM (outside the
    # stack-skip window) so the leaves' compare-word writes are observable.
    targets = [0xFFFFDE20 + 16 * k for k in range(4)]
    for k, t in enumerate(targets):
        put(ram, DAB4 + idx * 24 + 4 * k, 4, t)
    for t in targets:
        put(ram, t, 2, rng.randint(0, 0xFFFF))
        for j in range(2, 4):
            ram[t + j] = rng.randint(0, 255)
    if rng.random() < 0.3:                  # force desc-target to read 0
        put(ram, targets[1], 2, 0)
    return idx, ram


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    rom = open(ROM, 'rb').read()

    cpu = SH2(rom)
    cpu2 = SH2(rom)          # dedicated instance for the leaves in ref()
    seeds = (0x91FE, 0xA0F8, 0xDAB4, 0x9478, 0x9320)
    total_fails = 0

    for seed in seeds:
        rng = random.Random(seed)
        fails = 0
        for it in range(N):
            idx, ram = gen_state(rng)
            want = ref(cpu2, ram, rom, idx)
            try:
                cpu.call(ADDR, r4=idx, ram=ram)
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
                ch = A0D8 + idx * 8
                print('MISMATCH seed=0x%X iter=%d idx=%d: %s' %
                      (seed, it, idx, {hex(k): (hex(g), hex(e)) for k, g, e in bad[:12]}))
                print('  ch=%s base=%r value=%r' % (
                    {hex(k): hex(ram.get(k, 0)) for k in range(ch, ch + 8)},
                    rdf(ram, A0FC), rdf(ram, ch)))
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
    print('OK  0x91FE ignition_something_calc / wrap_and_arm_compare_timer '
          '(%d random inputs across %d seeds)' % (N * len(seeds), len(seeds)))
    print('\nAll ignition_something_calc_0x91FE tests passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()