#!/usr/bin/env python3
"""test_calculateKnockTimingDerateConditionEvents_0x178E8.py — differential test.

Runs the ACTUAL ROM bytes of 0x178E8 (including sub-calls isNotZero @0x2440,
addSaturate8Bit @0x2478, read_value_complement_check @0x3E0DC,
pack_complement @0x3E1F8) over seeded RAM states (oracle) in tools/sh2emu.py,
and compares a full post-call RAM overlay (byte-exact, task-stack window
0xFFFFDE00..DF00 skipped) against a Python reference mirroring the C lift
c/calculateKnockTimingDerateConditionEvents_0x178E8.c.  Sub-call leaves are
themselves run via a dedicated cpu2 instance (results + RAM side-effects from
the ROM), the same pattern as the isNotZero leaf in the 0x125B0 test.

0x178E8 is the real entry (slots @0x14420 and @0x14648 of the timing
dispatchers); code runs to rts delay @0x1793A; CSV end 0x1793C = start of
FUN_0001793c.  Range OK.

Semantics: condition-event counter for knock-timing derate (void RAM-writer):
  active = isNotZero(f32@A72C, 0, 1e-5)                 (0x2440)
  if (byte@A948 == 0 && active != 0):                    (fresh edge)
      byte@A927 = addSaturate8Bit(byte@A927, 1)          (0x2478)
      v = addSaturate8Bit( read_complement_check(0xFFFF8076, 0), 1)
      pack_complement(0xFFFF8076, v)                     (0x3E1F8)
  byte@A948 = active                                     (always)

Run: python3 c/tests/test_calculateKnockTimingDerateConditionEvents_0x178E8.py [N]
"""
import os, random, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2, ts

ROM = os.path.join(ROOT, 'roms', 'stock', '60E0FC00.bin')
ADDR = 0x178E8

A72C = 0xFFFFA72C   # f32 knock derate source value
A948 = 0xFFFFA948   # u8 active latch (r/w)
A927 = 0xFFFFA927   # u8 event counter
AD80 = 0xFFFF8076   # u16 packed complementary word

STACK_LO = 0xFFFFDE00; STACK_HI = 0xFFFFDF00
NAV = float('nan'); INF = float('inf')


def rdf(m, a):
    return struct.unpack('>f', bytes(m.get(a + i, 0) for i in range(4)))[0]


def rdb(m, a):
    return m.get(a, 0)


def setf(m, a, v):
    for i, b in enumerate(struct.pack('>f', ts(v))):
        m[a + i] = b


def wrb(m, a, v):
    m[a] = v & 0xFF


def wrw(m, a, v):
    m[a] = (v >> 8) & 0xFF
    m[a + 1] = v & 0xFF


def gen_state(rng):
    m = {}
    r = rng.random()
    if r < 0.55:
        setf(m, A72C, rng.uniform(-40.0, 40.0))
    elif r < 0.75:
        setf(m, A72C, rng.choice([0.0, -0.0, 1e-6, -1e-6, 1.0, -1.0]))
    elif r < 0.85:
        setf(m, A72C, NAV)
    else:
        setf(m, A72C, INF if rng.random() < 0.5 else -INF)
    wrb(m, A948, rng.randrange(2))
    wrb(m, A927, rng.randrange(256))
    wrw(m, AD80, rng.randrange(65536))
    return m


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    cpu2 = SH2(rom)

    def ref(m):
        m = dict(m)
        def go(addr, fr=None, r4=0, r5=0, r6=0):
            cp = dict(m)
            cpu2.call(addr, r4=r4, r5=r5, r6=r6, fr=fr, ram=cp)
            for k, v in cpu2.ram.items():
                if cp.get(k, 0) != v:
                    m[k] = v
            return cpu2.fr[0], cpu2.r[0]

        _, s = go(0x2440, fr={4: rdf(m, A72C), 5: 0.0, 6: ts(1e-5)})
        s &= 0xFF
        if rdb(m, A948) == 0 and s != 0:
            _, r1 = go(0x2478, r4=rdb(m, A927), r5=1)
            wrb(m, A927, r1 & 0xFF)
            _, rv = go(0x3E0DC, r4=AD80, r5=0)
            _, r2 = go(0x2478, r4=rv & 0xFF, r5=1)
            go(0x3E1F8, r4=AD80, r5=r2 & 0xFF)
        wrb(m, A948, s)
        return m

    seeds = (0x178E8, 0x2440, 0x2478, 0x3E0DC, 0x3E1F8)
    total_fails = 0
    for seed in seeds:
        rng = random.Random(seed)
        fails = 0
        for it in range(N):
            ram = gen_state(rng)
            want = ref(ram)
            try:
                cpu.call(ADDR, ram=dict(ram))
            except Exception as e:
                print('EMULATOR EXC seed=0x%X iter=%d: %s' % (seed, it, e))
                fails += 1
                break
            bad = {}
            for k in set(want) | set(cpu.ram.keys()):
                if STACK_LO <= k <= STACK_HI:
                    continue
                if cpu.ram.get(k, 0) != want.get(k, 0):
                    bad[k] = (cpu.ram.get(k, 0), want.get(k, 0))
            if bad:
                print('MISMATCH seed=0x%X iter=%d %s' %
                      (seed, it, {hex(k): (hex(a), hex(b)) for k, (a, b) in bad.items()}))
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
    print('OK  0x178E8 calculateKnockTimingDerateConditionEvents '
          '(%d random inputs across %d seeds)' % (N * len(seeds), len(seeds)))
    print('\nAll calculateKnockTimingDerateConditionEvents_0x178E8 tests passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()