#!/usr/bin/env python3
"""test_output_spark_0x8DAE.py

Differential test for ROM 0x8DAE (60E0FC00.bin) — lift c/output_spark_0x8DAE.c.
CSV/xmap name: "outputSpark1".

Runs the ACTUAL ROM bytes of 0x8DAE in tools/sh2emu.py over seeded RAM states
(the oracle) and compares the full post-call RAM overlay against a Python
reference model that mirrors the C lift line-for-line.  The complex callee
0x91C6 ("ignitonSomethingCalc", which wraps the spark angle and arms the
compare timer, and its 0x9440/A8A4 sub-chain) is NOT hand-transcribed: it is
executed in a dedicated second emulator instance (cpu2) and its RAM effects are
merged — the cpu2.call "emulator-in-the-model" pattern.  getSR(16)/setSR only
touch the Status Register (no RAM), so they are omitted from the RAM model.

Semantics (see c/output_spark_0x8DAE.c header):
  1. saved_sr = getSR(16)                      # raise IPL / save old SR mask
  2. ch = (u8*)(0xFFFFA0D8 + index*8)
     ch[0..3] = fr4 (float32 spark event value)
     ch[5]    = 0                              # clear "armed/fired" flag
     ch[4]    = 2                              # lead-spark output-enable
  3. ignitonSomethingCalc(index)  @0x8xC   # wrap angle + arm the compare timer
  4. setSR(saved_sr)                          # restore SR

gen() restricts index to 0..7 (the per-rotor/per-coil channel index): larger
indices index past the 0xD81C descriptor table used by the 0x9440 retrigger
path and would decode a garbage pointer, so the whole 0..255 byte space is not
a valid channel space (also crashes the ROM emulator on invalid descs).

Run: python3 c/tests/test_output_spark_0x8DAE.py [N]
     (N random inputs per seed; default 100000 -> 500000 across 5 seeds)
"""
import os, random, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2, ts

ROM = os.path.join(ROOT, 'roms', 'stock', '60E0FC00.bin')
ADDR = 0x8DAE
CALC = 0x91C6                 # un-lifted callee (ignitonSomethingCalc)

# ---- RAM addresses (see c/output_spark_0x8DAE.c header) ----
A0D8 = 0xFFFFA0D8   # per-channel spark-event table (stride 8)
A0FC = 0xFFFFA0FC   # f32 base/offset for the angle wrap
A0F8 = 0xFFFFA0F8   # f32 wrapped angle scratch (written by 0x91C6)
A0C4 = 0xFFFFA0C4   # u32 per-channel pointer table (read by 0x91C6 / 0x9440)
A0D4 = 0xFFFFA0D4   # u16 (dead-swap / hardware word read by 0x91C6)
A100 = 0xFFFFA100   # u32 divisor (30*ptr/divisor deg->counts); must be nonzero


def f32b(v):
    return list(struct.pack('>f', ts(v)))


def r32(d, a):
    return struct.unpack('>f', bytes(d.get(a + i, 0) for i in range(4)))[0]


def ref(cpu2, index, value, ram):
    """Line-for-line mirror of output_spark_0x8DAE().

    Un-lifted callees are executed in the dedicated emulator instance `cpu2`
    (the cpu2.call pattern) so the single-precision rounding / NaN / RAM
    side-effects match the ROM exactly.  getSR(16)/setSR touch only SR (no RAM).
    Returns a full RAM-effect dict.
    """
    m = dict(ram)
    off = (index & 0xFF) * 8
    # ---- steps 2: table slot ----
    for i, b in enumerate(f32b(value)):
        m[A0D8 + off + i] = b
    m[A0D8 + off + 5] = 0      # ch[5] (disasm: mov #0,@(5,r4))
    m[A0D8 + off + 4] = 2      # ch[4] (disasm: mov #2,@(4,r4))
    # ---- step 3: callee 0x91C6 (emulator-in-the-model) ----
    cpu2.call(CALC, r4=index & 0xFF, ram=m)
    m.update(cpu2.ram)
    return m


def gen_state(rng):
    """Random seeded RAM + a device-channel index and spark value."""
    ram = {}

    def put(a, bs):
        for j, b in enumerate(bs):
            ram[a + j] = b

    for i in range(8):                      # existing table slots (pre-values)
        put(A0D8 + i * 8, struct.pack('>f', rng.uniform(-720, 720)))
        ram[A0D8 + i * 8 + 4] = rng.randint(0, 255)   # previous mode byte
        ram[A0D8 + i * 8 + 5] = rng.randint(0, 255)   # previous flag byte
        ram[A0D8 + i * 8 + 6] = rng.randint(0, 255)   # previous scratch byte
    put(A0FC, struct.pack('>f', rng.uniform(-720, 720)))  # wrap base
    put(A0F8, struct.pack('>f', rng.uniform(-720, 720)))  # previous scratch
    for i in range(8):                      # per-channel pointer table
        v = rng.randint(0, 0xFFFFFFFF) if rng.random() < 0.5 else 0
        put(A0C4 + i * 8, struct.pack('>I', v))
    ram[A0D4] = rng.randint(0, 255); ram[A0D4 + 1] = rng.randint(0, 255)
    put(A100, struct.pack('>I', rng.randint(1, 0x7FFFFFFF)))  # divisor != 0
    index = rng.randint(0, 7)
    value = rng.uniform(-720, 720)
    return index, value, ram


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    rom = open(ROM, 'rb').read()

    cpu = SH2(rom)
    cpu2 = SH2(rom)             # dedicated instance for the callee in ref()
    seeds = (0x8DAE, 0x91C6, 0xA0D8, 0x9440, 0x8DE8)
    total_fails = 0

    for seed in seeds:
        rng = random.Random(seed)
        fails = 0
        for it in range(N):
            index, value, ram = gen_state(rng)
            want = ref(cpu2, index, value, ram)
            try:
                cpu.call(ADDR, r4=index, fr={4: value}, ram=ram)
            except Exception as e:
                print('EMULATOR EXC seed=0x%X iter=%d index=%d value=%r: %s' %
                      (seed, it, index, value, e))
                fails += 1
                break
            bad = []
            for k in (set(want) | set(cpu.ram)):
                if 0xFFFFDE00 <= k <= 0xFFFFDF00:   # task stack area
                    continue
                if cpu.ram.get(k, 0) != want.get(k, 0):
                    bad.append(k)
            if bad:
                print('MISMATCH seed=0x%X iter=%d index=%d value=%r: %s' %
                      (seed, it, index, value,
                       {hex(k): (hex(cpu.ram.get(k)), hex(want.get(k)))
                        for k in bad[:12]}))
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
    print('OK  0x8DAE outputSpark1/output_spark (%d random inputs across %d seeds)'
          % (N * len(seeds), len(seeds)))
    print('\nAll output_spark_0x8DAE tests passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()