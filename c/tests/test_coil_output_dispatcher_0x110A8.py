#!/usr/bin/env python3
"""test_coil_output_dispatcher_0x110A8.py

Differential test for ROM 0x110A8 (60E1D400.bin) — lift
c/coil_output_dispatcher_0x110A8.c.

Runs the ACTUAL ROM bytes of 0x110A8 in tools/sh2emu.py over seeded RAM states
(the oracle) and compares the returned r0 plus the full post-call RAM overlay
against a Python reference model that mirrors the C lift line-for-line.

NOTE on entry point: the task label "0x11010" is not a function start — bytes
at 0x11010 (`ff08 a036 ...`) are the mid-prologue of the sibling function A
that begins at 0x10FF0, and there are no code references to 0x11010 anywhere
in the ROM.  The actual coil-output dispatcher (dispatch site 0x110D8..0x110DC
-> 0x11218 / 0x1120A, plus the 0x2158 scale call) begins at 0x110A8 and is
referenced by the function-pointer table element @0x4ED58 (value 0x000110A8).
This test therefore drives the emulator at the real entry 0x110A8.

Key semantic facts (see the lift header):
  * r4 = base pointer, r5 = limit (u32; comparisons are SIGNED 32-bit).
  * Two 16-byte channel descriptors at base+0xC and base+0x1C.  For each:
      ch12 = u32 @ desc+0xC        (channel time / phase word)
      gate 1: require (s32)limit > (s32)ch12            else return 0
      ch0  = u8  @ desc            (channel index for 0x11218)
      dw   = 0x11218(ch0)          (per-rotor dwell count, leaf)
      dw16 = 0x1120A()             (u16@0xFFFFA0D4 * 16, leaf)
      f    = 0x2158(dw16+dw, u32@0xFFFF9F88)   (fixed-point scale, leaf)
      r4   = (f * 180 + ch12) mod 2^32
      gate 2: require (s32)limit >= (s32)r4              else return 0
    return 1 iff BOTH channels pass both gates.
  * The dispatcher writes nothing to RAM (only stack round-trips); the leaves
    are pure-read, so the full-RAM diff vs the model is trivially empty.

Run: python3 c/tests/test_coil_output_dispatcher_0x110A8.py [N]
     (N = random inputs per seed; default 100000 -> 500000 across 5 seeds)
"""
import os, random, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2, ts

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ADDR = 0x110A8

# ---- RAM addresses (see c/coil_output_dispatcher_0x110A8.c header) ----
BC84 = 0xFFFFBC84   # rotor-A dwell time (f32, input to 0x11218)
BC88 = 0xFFFFBC88   # rotor-B dwell time (f32, input to 0x11218)
A0D4 = 0xFFFFA0D4   # u16 dwell time (input to 0x1120A)
N9F88 = 0xFFFF9F88  # u32 fixed-point scale (input to 0x2158 via dispatcher)
BASE = 0xFFFFC000   # descriptor-table base handed in r4

FLOAT_IN = [BC84, BC88]


def put(ram, a, n, v):
    for i in range(n):
        ram[a + i] = (v >> (8 * (n - 1 - i))) & 0xFF


def setf(ram, a, v):
    for i, b in enumerate(struct.pack('>f', float(v))):
        ram[a + i] = b


def rd(m, a, n):
    v = 0
    for i in range(n):
        v = (v << 8) | m.get(a + i, 0)
    return v


def r32(d, a):
    return struct.unpack('>f', bytes(d.get(a + i, 0) for i in range(4)))[0]


def s32(x):
    return x - (1 << 32) if x & 0x80000000 else x


def ref(cpu2, ram, rom, base, limit):
    """Line-for-line mirror of coil_output_dispatcher_0x110A8().

    The three leaves (0x11218, 0x1120A, 0x2158) are executed in the second
    emulator instance `cpu2` (oracle) with their RAM merged — the same trick
    the 0x91FE / 0x19220 tests use for helper calls.  Returns (r0, ram-diff
    dict); the dispatcher writes nothing itself.
    """
    m = dict(ram)
    for k in (0, 1):
        d = base + 0xC + 0x10 * k
        ch12 = rd(m, d + 0xC, 4)
        if not (s32(limit) > s32(ch12)):          # cmp/gt r2,r9 ; bf/s
            return 0, m
        ch0 = m.get(d, 0)                         # mov.b @r14,r4
        dw = cpu2.call(0x11218, r4=ch0, ram=m)    # jsr @0x11218
        m = dict(cpu2.ram)
        dw16 = cpu2.call(0x1120A, ram=m)          # jsr @0x1120A
        m = dict(cpu2.ram)
        scale = rd(m, N9F88, 4)                   # mov.l @r2,r5 (0xFFFF9F88)
        f = cpu2.call(0x2158, r4=(dw16 + dw) & 0xFFFFFFFF, r5=scale, ram=m)
        m = dict(cpu2.ram)
        r4 = ((f * 180) + ch12) & 0xFFFFFFFF      # mul.l; sts macl; add
        if not (s32(limit) >= s32(r4)):           # cmp/ge r4,r9 ; bt/s
            return 0, m
    return 1, m


def gen_state(rng):
    """Random seeded RAM + base/limit hitting both gates and both directions.

    The descriptor table (BASE+0xC, BASE+0x1C, 16-byte stride) holds:
      +0   ch0 channel index (u8)  -> rotor index for 0x11218
      +0xC ch12 channel time (u32) -> gate 1 comparator
    """
    ram = {}
    # channel descriptors
    for k in (0, 1):
        d = BASE + 0xC + 0x10 * k
        # ch0: bias toward realistic rotor indices 0..3 (else 0.25 random)
        if rng.random() < 0.75:
            ram[d] = rng.randint(0, 3)
        else:
            ram[d] = rng.randint(0, 255)
        put(ram, d + 0xC, 4, rng.randint(0, 0xFFFFFFFF))   # ch12
        for j in range(4, 0xC):
            if j == 4:
                ram[d + j] = 0                              # pad byte
    # dwell float inputs for 0x11218 (same policy as its own test)
    for a in FLOAT_IN:
        if rng.random() < 0.85:
            setf(ram, a, rng.uniform(0.0, 20000.0))
        else:
            setf(ram, a, rng.uniform(-10000.0, 10000.0))
    if rng.random() < 0.2:                                   # degenerate
        for a in FLOAT_IN:
            setf(ram, a, 0.0)
    put(ram, A0D4, 2, rng.randint(0, 0xFFFF))                # u16 dwell
    put(ram, N9F88, 4, rng.choice([rng.randint(1, 0xFFFFFFFF), 0]))
    limit = rng.randint(0, 0xFFFFFFFF)                       # r5
    return ram, BASE, limit


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    rom = open(ROM, 'rb').read()

    cpu = SH2(rom)
    cpu2 = SH2(rom)          # dedicated instance for the leaves in ref()
    seeds = (0x110A8, 0x110D8, 0xBC84, 0xA0D4, 0x9F88)
    total_fails = 0

    for seed in seeds:
        rng = random.Random(seed)
        fails = 0
        for it in range(N):
            ram, base, limit = gen_state(rng)
            want_r0, want = ref(cpu2, ram, rom, base, limit)
            try:
                got_r0 = cpu.call(ADDR, r4=base, r5=limit, ram=ram)
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
            if got_r0 != want_r0:
                bad.append(('r0', got_r0, want_r0))
            if bad:
                print('MISMATCH seed=0x%X iter=%d: %s' %
                      (seed, it, {hex(k) if isinstance(k, int) else k:
                                  (hex(g), hex(e)) for k, g, e in bad[:12]}))
                print('  limit=0x%08X base=0x%X desc0: ch0=%d ch12=0x%X '
                      'desc1: ch0=%d ch12=0x%X A0D4=0x%X 9F88=0x%X got_r0=0x%08X want=0x%08X' % (
                          limit, base,
                          ram.get(BASE + 0xC, 0), rd(ram, BASE + 0x18, 4),
                          ram.get(BASE + 0x1C, 0), rd(ram, BASE + 0x28, 4),
                          rd(ram, A0D4, 2), rd(ram, N9F88, 4), got_r0, want_r0))
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
    print('OK  0x110A8 coil_output_dispatcher  (%d random inputs across %d seeds)'
          % (N * len(seeds), len(seeds)))
    print('\nAll coil_output_dispatcher_0x110A8 tests passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()
