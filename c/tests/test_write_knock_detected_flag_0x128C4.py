#!/usr/bin/env python3
"""test_write_knock_detected_flag_0x128C4.py

Differential test for ROM 0x128C4 (60E1D400.bin) — lift
c/write_knock_detected_flag_0x128C4.c.

Runs the ACTUAL ROM bytes of 0x128C4 in tools/sh2emu.py over seeded RAM states
(the oracle) and compares the full post-call RAM overlay against a Python
reference model that mirrors the C lift line-for-line.

Entry-point note: 0x128C4 IS the real entry point — the only ROM reference is
the function-pointer slot @0x14844 in the dispatcher engineControlCalculateTiming
(0x14584) dispatch table (c/engineControlCalculateTiming.c line 264).  Valid
prologue / rts+delay at 0x128FA/0x128FC; the body is a straight line.

Key semantic facts (see the lift header):
  * void function — RAM side effect:
      f32@0xFFFFA654 = (f32@A734 - f32@A6AC)
                       - max_0x23E4(f32@A760, f32@CA10)
                       + f32@A5E4 + f32@B2F8 - f32@A670
  * The max leaf 0x23E4 is executed in the second emulator instance cpu2
    (oracle) with RAM merged — the same trick the knock / 0x162E4 tests use.
  * Every fsub/fadd is single-precision rounded (`ts`), left-associative.

Run: python3 c/tests/test_write_knock_detected_flag_0x128C4.py [N]
     (N = random inputs per seed; default 100000 -> 500000 across 5 seeds)
"""
import os, random, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2, ts

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ADDR = 0x128C4

# ---- RAM addresses (see c/write_knock_detected_flag_0x128C4.c header) ----
A6AC = 0xFFFFA6AC   # f32 input A
A734 = 0xFFFFA734   # f32 input B
CA10 = 0xFFFFCA10   # f32 knock-control output
A760 = 0xFFFFA760   # f32 knock delta
A5E4 = 0xFFFFA5E4   # f32 additive term
B2F8 = 0xFFFFB2F8   # f32 additive term
A670 = 0xFFFFA670   # f32 subtractive term
A654 = 0xFFFFA654   # f32 output (knock-detect)


def setf(ram, a, v):
    for i, b in enumerate(struct.pack('>f', ts(v))):
        ram[a + i] = b


def rdf(m, a):
    return struct.unpack('>f', bytes(m.get(a + i, 0) for i in range(4)))[0]


def wrf(m, a, v):
    for i, b in enumerate(struct.pack('>f', ts(v))):
        m[a + i] = b


def ref(cpu2, m, rom):
    """Line-for-line mirror of write_knock_detected_flag_0x128C4().

    The max leaf 0x23E4 is executed in `cpu2` (oracle); the inline fsub/fadd
    chain is modelled with the same single-precision rounding (`ts`) the
    emulator applies, in the exact instruction order.
    """
    m = dict(m)

    fr12 = ts(rdf(m, A734) - rdf(m, A6AC))          # fsub fr3,fr2 @0x128D2
    cpu2.call(0x23E4, fr={4: rdf(m, A760), 5: rdf(m, CA10)}, ram=m)
    m = dict(cpu2.ram)
    fr12 = ts(fr12 - cpu2.fr[0])                    # fsub fr0,fr12 @0x128E2
    fr12 = ts(fr12 + rdf(m, A5E4))                  # fadd fr3,fr12 @0x128EA
    fr12 = ts(fr12 + rdf(m, B2F8))                  # fadd fr2,fr12 @0x128EE
    fr12 = ts(fr12 - rdf(m, A670))                  # fsub fr1,fr12 @0x128F4

    wrf(m, A654, fr12)                              # fmov.s fr12,@r3 @0x128F6
    return m


def gen_state(rng):
    """Random seeded floats over all seven inputs.

    Each input independently samples: normal values across a wide range,
    exact zero, +/-inf, and NaN (NaN propagates through the leaf and the
    accumulate chain, so the reference must round the same NaN bit pattern).
    """
    ram = {}
    for a in (A6AC, A734, CA10, A760, A5E4, B2F8, A670):
        r = rng.random()
        if r < 0.02:
            setf(ram, a, float('nan'))
        elif r < 0.04:
            setf(ram, a, float('inf'))
        elif r < 0.06:
            setf(ram, a, float('-inf'))
        elif r < 0.08:
            setf(ram, a, 0.0)
        else:
            setf(ram, a, rng.uniform(-200.0, 200.0))
    setf(ram, A654, rng.uniform(-1000.0, 1000.0))   # output junk
    return ram


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    rom = open(ROM, 'rb').read()

    cpu = SH2(rom)
    cpu2 = SH2(rom)          # dedicated instance for the 0x23E4 leaf in ref()
    seeds = (0x12A48, 0x128C4, 0x128FE, 0xA654, 0x23E4)
    total_fails = 0

    for seed in seeds:
        rng = random.Random(seed)
        fails = 0
        for it in range(N):
            ram = gen_state(rng)
            want = ref(cpu2, ram, rom)
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
            if bad:
                print('MISMATCH seed=0x%X iter=%d: %s' %
                      (seed, it, {hex(k): (hex(g), hex(e))
                                  for k, g, e in bad[:12]}))
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
    print('OK  0x128C4 write_knock_detected_flag '
          '(%d random inputs across %d seeds)' % (N * len(seeds), len(seeds)))
    print('\nAll write_knock_detected_flag_0x128C4 tests passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()
