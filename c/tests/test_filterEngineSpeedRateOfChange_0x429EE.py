#!/usr/bin/env python3
"""test_filterEngineSpeedRateOfChange_0x429EE.py

Differential test for ROM 0x429EE (60E0FC00.bin) - lift
c/filterEngineSpeedRateOfChange_0x429EE.c.

Runs the ACTUAL ROM bytes of 0x429EE in tools/sh2emu.py over seeded RAM
states (the oracle) and compares the full post-call RAM overlay (byte-exact,
task-stack window 0xFFFFDE00..DF00 skipped) plus the return register r0
against a Python reference model that mirrors the C lift line-for-line.

Entry/range: 0x429EE IS the real entry (dispatcher slot @0x1448C of the
engineControlCalculateTiming 0x141FC table; preceding fn getEngineSpeedRateOf
Change 0x429BC ends rts+delay @0x429EA; next fn starts exactly at CSV end
0x42B52). CSV range 0x429EE..0x42B52 (356 B) CORRECT - no phantom rows.

Semantics (see lift header): magnitude-gated lag filter.  Input in=f32@C908,
current raw rate cur=f32@C8F4, 10-slot history H[0..9] @ f32 C96C..C98C + H[10]
@ C990.  out (f32@C8F0) = a band-selected lagged sample; then H[10]<-H[9]<-...
<-H[0]<-cur.  All comparisons are SH-2 fcmp/gt (FRn>FRm), so NaN input falls
through to the oldest sample.  r0 on return = the mova literal address of the
last threshold examined (see ref).  Carried byte-exact.

Run: python3 c/tests/test_filterEngineSpeedRateOfChange_0x429EE.py [N]
     (N = random inputs per seed; default 100000 -> 500000 across 5 seeds)
"""
import os, random, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2, ts

ROM = os.path.join(ROOT, 'roms', 'stock', '60E0FC00.bin')
ADDR = 0x429EE

# ---- RAM addresses (see c/filterEngineSpeedRateOfChange_0x429EE.c) ----
C908 = 0xFFFFC908   # f32 input rate this call
C8F4 = 0xFFFFC8F4   # f32 current raw rate (from getEngineSpeedRateOfChange)
C8F0 = 0xFFFFC8F0   # f32 filtered output
H = [0xFFFFC96C + i * 4 for i in range(10)]   # H[0..9]
H10 = 0xFFFFC990    # oldest history slot
ALLH = H + [H10, C8F0]

# r0 leaf for each band: mova address of the threshold that expires the cascade
R0_LEAF = {0: 0x42AA0, 1: 0x42AA4, 2: 0x42AA8, 3: 0x42B5C, 4: 0x42B60,
           5: 0x42B64, 6: 0x42B68, 7: 0x42B6C, 8: 0x42B70, 9: 0x42B74,
           10: 0x42B74}

STACK_LO = 0xFFFFDE00
STACK_HI = 0xFFFFDF00


def r32(m, a):
    return struct.unpack('>f', bytes(m.get(a + i, 0) for i in range(4)))[0]


def put32(m, a, v):
    for i, b in enumerate(struct.pack('>f', ts(v))):
        m[a + i] = b


def ref(m):
    """Line-for-line mirror of filterEngineSpeedRateOfChange_0x429EE().  Returns
    (full RAM-effect dict, expected r0)."""
    m = dict(m)
    cur = r32(m, C8F4)
    iv = r32(m, C908)

    if 2.5 > iv:          out = cur;  lv = 0
    elif 3.5 > iv:        out = r32(m, H[0]); lv = 1
    elif 4.5 > iv:        out = r32(m, H[1]); lv = 2
    elif 5.5 > iv:        out = r32(m, H[2]); lv = 3
    elif 6.5 > iv:        out = r32(m, H[3]); lv = 4
    elif 7.5 > iv:        out = r32(m, H[4]); lv = 5
    elif 8.5 > iv:        out = r32(m, H[5]); lv = 6
    elif 9.5 > iv:        out = r32(m, H[6]); lv = 7
    elif 10.5 > iv:       out = r32(m, H[7]); lv = 8
    elif 11.5 > iv:       out = r32(m, H[8]); lv = 9
    else:                 out = r32(m, H10);  lv = 10

    put32(m, C8F0, out)
    # shift register, oldest first
    put32(m, H10, r32(m, H[9]))
    put32(m, H[9], r32(m, H[8]))
    put32(m, H[8], r32(m, H[7]))
    put32(m, H[7], r32(m, H[6]))
    put32(m, H[6], r32(m, H[5]))
    put32(m, H[5], r32(m, H[4]))
    put32(m, H[4], r32(m, H[3]))
    put32(m, H[3], r32(m, H[2]))
    put32(m, H[2], r32(m, H[1]))
    put32(m, H[1], r32(m, H[0]))
    put32(m, H[0], cur)
    return m, R0_LEAF[lv]


def gen_in(rng):
    """Random seeded RAM.  Input covers every band boundary, wide range and
    NaN; cur and history slots sample fixed extremes so NaN/boundary fcmp/gt
    behaviour and the shift come out byte-exact."""
    r = rng.random()
    if r < 0.5:
        iv = float(rng.uniform(-20, 30))
    elif r < 0.75:
        iv = float(rng.choice([0.0, 2.49, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5,
                               9.5, 10.5, 11.5, 12.0, -1.0, 1e9]))
    elif r < 0.9:
        iv = float('nan')
    else:
        iv = float(rng.uniform(-1e8, 1e8))
    m = {}
    put32(m, C908, iv)
    put32(m, C8F4, rng.choice([0.0, 1.0, -1.0, 100.0, 1e6, 3.14159, float('nan')]))
    for a in ALLH:
        rr = rng.random()
        if rr < 0.5:
            v = float(rng.uniform(-100, 100))
        elif rr < 0.85:
            v = float(rng.choice([0.0, 1.0, 2.5, 12.0, 1e9, -1e9]))
        elif rr < 0.94:
            v = float('nan')
        else:
            v = float(rng.uniform(-1e20, 1e20))
        put32(m, a, v)
    return m


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    seeds = (0x429EE, 0x42AA0, 0xFFFFC908, 0xFFFFC990, 0x1448C)
    total_fails = 0
    for seed in seeds:
        rng = random.Random(seed)
        fails = 0
        for it in range(N):
            ram = gen_in(rng)
            want, want_r0 = ref(ram)
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
    print('OK  0x429EE filterEngineSpeedRateOfChange '
          '(%d random inputs across %d seeds)' % (N * len(seeds), len(seeds)))
    print('\nAll filterEngineSpeedRateOfChange_0x429EE tests passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()