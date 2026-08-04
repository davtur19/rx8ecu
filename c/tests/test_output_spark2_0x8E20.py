#!/usr/bin/env python3
"""test_output_spark2_0x8E20.py

Differential test for ROM 0x8E20 (60E1D400.bin) — lift
c/output_spark2_0x8E20.c.  CSV/xmap name: "outputSpark2".

Runs the ACTUAL ROM bytes of 0x8E20 in tools/sh2emu.py over seeded RAM states
(the oracle) and compares the full post-call RAM overlay against a Python
reference model that mirrors the C lift line-for-line.  The complex callee
0x91FE ("ignitonSomethingCalc", which wraps the spark angle and arms the
compare timer, and its 0x9478 retrigger / 0xAA74 write_to_memory_with_fpu_sync
/ 0x2054 setSR_PARAM / 0x2064 loadStatusRegister_ADDR sub-chain) is NOT
hand-transcribed: it is executed in a dedicated second emulator instance
(cpu2) and its RAM effects are merged — the cpu2.call "emulator-in-the-model"
pattern.  getSR(16)/setSR only touch the Status Register (no RAM), so they are
omitted from the RAM model.

Semantics (see c/output_spark2_0x8E20.c header):
  1. saved_sr = getSR(16)
  2. ch = (u8*)(0xFFFFA0D8 + index*8)
  3. ONLY IF ch[4] == 2:                 # trail event fires on armed channels only
       ch[0..3] = fr4 (float32 spark event value)
       ch[6]    = 0                      # clear "fired" flag
       ignitonSomethingCalc(index)  @0x91FE
     (when ch[4] != 2 the channel is left untouched — no write, no 0x91FE call)
  4. setSR(saved_sr)

gen() restricts index to 0..7 (per-rotor/per-coil channel space): larger
indices index past the 0xDAB4 descriptor table used by 0x91FE/0x9478 and would
decode garbage pointers.  ch[4] is biased (70% == 2) so both the armed and the
not-armed paths get coverage; ch[5] (0x91FE's armed/fired discriminator, NOT
cleared by outputSpark2) is seeded 0 or nonzero so both 0x91FE sub-paths
(fresh-arm vs already-armed) are exercised.

Run: python3 c/tests/test_output_spark2_0x8E20.py [N]
     (N random inputs per seed; default 100000 -> 500000 across 5 seeds)
"""
import os, random, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2, ts

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ADDR = 0x8E20
CALC = 0x91FE                 # un-lifted callee (ignitonSomethingCalc)

# ---- RAM addresses (see c/output_spark2_0x8E20.c header) ----
A0D8 = 0xFFFFA0D8   # per-channel spark-event table (stride 8)
A0FC = 0xFFFFA0FC   # f32 base/offset for the angle wrap
A0F8 = 0xFFFFA0F8   # f32 wrapped angle scratch (written by 0x91FE)
A0C4 = 0xFFFFA0C4   # u32 per-channel pointer table (read by 0x91FE)
A0D4 = 0xFFFFA0D4   # u16 (dead-swap / hardware word read by 0x91FE)
A100 = 0xFFFFA100   # u32 divisor (30*ptr/divisor deg->counts); must be nonzero
A104 = 0xFFFFA104   # u16 (hardware word read by 0x91FE)


def f32b(v):
    return list(struct.pack('>f', ts(v)))


def ref(cpu2, index, value, ram):
    """Line-for-line mirror of output_spark2_0x8E20().

    Un-lifted callees are executed in the dedicated emulator instance `cpu2`
    (the cpu2.call pattern) so the single-precision rounding / NaN / RAM
    side-effects match the ROM exactly.  getSR(16)/setSR touch only SR (no RAM).
    Returns a full RAM-effect dict.
    """
    m = dict(ram)
    off = (index & 0xFF) * 8
    # ---- step 3: only when the channel is already armed (ch[4] == 2) ----
    if m.get(A0D8 + off + 4, 0) == 2:
        for i, b in enumerate(f32b(value)):
            m[A0D8 + off + i] = b
        m[A0D8 + off + 6] = 0      # ch[6] (disasm: mov #0,@(6,r1))
        # ---- step 3b: callee 0x91FE (emulator-in-the-model) ----
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
        ram[A0D8 + i * 8 + 4] = 2 if rng.random() < 0.7 else rng.randint(0, 255)
        ram[A0D8 + i * 8 + 5] = rng.randint(0, 255)   # armed/fired discriminator
        ram[A0D8 + i * 8 + 6] = rng.randint(0, 255)   # previous scratch byte
    put(A0FC, struct.pack('>f', rng.uniform(-720, 720)))  # wrap base
    put(A0F8, struct.pack('>f', rng.uniform(-720, 720)))  # previous scratch
    for i in range(16):                     # pointer table + surrounding bytes
        ram[A0C4 + i] = rng.randint(0, 255)
    ram[A0D4] = rng.randint(0, 255); ram[A0D4 + 1] = rng.randint(0, 255)
    put(A100, struct.pack('>I', rng.randint(1, 0x7FFFFFFF)))  # divisor != 0
    ram[A104] = rng.randint(0, 255); ram[A104 + 1] = rng.randint(0, 255)
    index = rng.randint(0, 7)
    value = rng.uniform(-720, 720)
    return index, value, ram


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    rom = open(ROM, 'rb').read()

    cpu = SH2(rom)
    cpu2 = SH2(rom)             # dedicated instance for the callee in ref()
    seeds = (0x8E20, 0xA0D8, 0x91FE, 0x9478, 0x8DE6)
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
    print('OK  0x8E20 outputSpark2/output_spark2 (%d random inputs across %d seeds)'
          % (N * len(seeds), len(seeds)))
    print('\nAll output_spark2_0x8E20 tests passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()
