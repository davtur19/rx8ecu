#!/usr/bin/env python3
"""test_output_per_rotor_ignition_dwell_0x11218.py

Differential test for ROM 0x11218 (60E1D400.bin) — lift
c/output_per_rotor_ignition_dwell_0x11218.c.

Runs the ACTUAL ROM bytes of 0x11218 in tools/sh2emu.py over seeded RAM states
(the oracle) and compares the full post-call RAM overlay plus the returned r0
against a Python reference model that mirrors the C lift line-for-line.

Key semantic facts (see the lift header):
  * r4 (rotor index) is masked to 8 bits FIRST (extu.b), then compared:
      b == 0/1 -> v = f32@0xFFFFBC84 (rotor-A dwell)
      b == 2/3 -> v = f32@0xFFFFBC88 (rotor-B dwell)
      else     -> v = 0.0f
  * return (uint32_t)(int32_t)(v / 0.25f)  (fdiv by f32 0.25 @0x112DC, then
    ftrc = truncate toward zero; 0.25 = count-to-time scale -> count = 4*dwell).
  * The leaf performs NO RAM/HW writes — the full-RAM diff is trivially empty;
    the caller @0x1127E stores the count into RAM32 LUT 0xFFFFA0C4[rotor].
  * Bytes 0x11236..0x1125E are dead code/data never reached by the flow.

Run: python3 c/tests/test_output_per_rotor_ignition_dwell_0x11218.py [N]
     (N = random inputs per seed; default 100000 -> 500000 across 5 seeds)
"""
import os, random, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2, ts

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ADDR = 0x11218

# ---- RAM addresses (see c/output_per_rotor_ignition_dwell_0x11218.c header) ----
BC84 = 0xFFFFBC84   # rotor-A dwell time (f32, input)
BC88 = 0xFFFFBC88   # rotor-B dwell time (f32, input)

FLOAT_IN = [BC84, BC88]


def r32(d, a):
    return struct.unpack('>f', bytes(d.get(a + i, 0) for i in range(4)))[0]


def setf(ram, a, v):
    for i, b in enumerate(struct.pack('>f', float(v))):
        ram[a + i] = b


def ref(ram, rom, rotor):
    """Line-for-line mirror of output_per_rotor_ignition_dwell_0x11218().

    No callee calls, so the model is direct Python.  Returns (r0, ram-diff
    dict); the leaf writes nothing, so the ram-diff dict == the input ram.
    """
    m = dict(ram)
    b = rotor & 0xFF                       # 0x11218 extu.b r4,r0
    if b == 0 or b == 1:                   # -> 0x11260
        v = r32(m, BC84)
    elif b == 2 or b == 3:                 # -> 0x11266
        v = r32(m, BC88)
    else:                                  # -> 0x1126C
        v = 0.0
    q = ts(v / 0.25)                       # 0x11272 fdiv fr3,fr4 (0.25)
    return int(q) & 0xFFFFFFFF, m          # 0x11276 ftrc (trunc toward zero)


def gen_state(rng):
    """Random seeded RAM + rotor index hitting every branch (incl. the extu.b
    masking: rotor values >= 0x100 fall back to the low-byte branch)."""
    ram = {}
    for a in FLOAT_IN:
        # dwell times: mostly positive (realistic ~1..10 ms); keep |v| small
        # enough that count = 4*v stays well inside int32 (no ftrc range edge)
        if rng.random() < 0.85:
            setf(ram, a, rng.uniform(0.0, 20000.0))
        else:
            setf(ram, a, rng.uniform(-10000.0, 10000.0))
    if rng.random() < 0.2:                 # degenerate RAM state (zeros)
        for a in FLOAT_IN:
            setf(ram, a, 0.0)
    rotor = rng.randint(0, 3)              # realistic channel index
    if rng.random() < 0.15:
        rotor = rng.choice([0x100, 0x101, 0x102, 0x103, 0x1FF, 0xFE, 0x12345600])
    return ram, rotor


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    rom = open(ROM, 'rb').read()

    cpu = SH2(rom)
    seeds = (0x11218, 0xBC84, 0xBC88, 0xA0C4, 0x1127E)
    total_fails = 0

    for seed in seeds:
        rng = random.Random(seed)
        fails = 0
        for it in range(N):
            ram, rotor = gen_state(rng)
            want_r0, want = ref(ram, rom, rotor)
            try:
                got_r0 = cpu.call(ADDR, r4=rotor, ram=ram)
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
                print('  rotor=0x%X b=0x%X BC84=%r BC88=%r got_r0=0x%08X want=0x%08X' % (
                    rotor, rotor & 0xFF, r32(ram, BC84), r32(ram, BC88),
                    got_r0, want_r0))
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
    print('OK  0x11218 output_per_rotor_ignition_dwell  (%d random inputs across %d seeds)'
          % (N * len(seeds), len(seeds)))
    print('\nAll output_per_rotor_ignition_dwell_0x11218 tests passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()
