#!/usr/bin/env python3
"""test_ignitionDwellOutputInit.py

Differential test for ROM 0x8F62 (60E1D400.bin) — lift
c/ignitionDwellOutputInit.c.

Runs the ACTUAL ROM bytes of 0x8F62 in tools/sh2emu.py over seeded RAM states
(the oracle) and compares the full post-call RAM overlay against a Python
reference model that mirrors the C lift line-for-line.

Key semantic facts (see the lift header):
  * bsr 0x8FCC primes the coil-output peripheral block (RAM 0xFFFFF600..680):
    setSR_PARAM @0x2054 + @0x2064 SR save/restore, then read-modify-writes on
    0xFFFFF627 / 0xFFFFF630 / 0xFFFFF66C / 0xFFFFF626.
  * Loop 4 times over cfg table @0xDAB4 (stride 0x18); per channel:
      - call @0xAA74(cfg, 0)  (setSR_PARAM + zeroes u16@cfg twice)
      - u8 @(0xFFFFA0D8 + i*8 + 4) = 0   (coil on/off byte)
      - u8 @(0xFFFFA0D8 + i*8 + 5) = 0   (fault byte)
      - u32@(0xFFFFA0C4 + i*4)   = 0     (dwell output word)
  * Tail-call 0x94C8 get_ignition_dwell_time: reads RPM (f32@0xFFFF9F80),
    battV (f32@0xFFFF9F68) and offset (u16@0xFFFFA0D6), writes saturated
    u16@0xFFFFA0D4.

The callees (0x8FCC, 0xAA74, 0x94C8) are NOT modeled in Python: the reference
model executes each in a dedicated second emulator instance (`cpu2`) and copies
its non-stack RAM writes back — the same emulator-in-model trick used by
test_calc_spark_lead_trail_split_19220.py — so SR handling and every RAM side
effect match the ROM exactly.

Run: python3 c/tests/test_ignitionDwellOutputInit.py [N]
     (N = random inputs per seed; default 100000 -> 500000 across 5 seeds)
"""
import os, random, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2, ts

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ADDR = 0x8F62

# ---- RAM addresses (see c/ignitionDwellOutputInit.c header) ----
F9F80 = 0xFFFF9F80   # RPM      (f32 in, 0x94C8)
F9F68 = 0xFFFF9F68   # battV    (f32 in, 0x94C8)
FA0D6 = 0xFFFFA0D6   # u16 dwell offset (in, 0x94C8)
FA0D4 = 0xFFFFA0D4   # u16 dwell result (out, 0x94C8)
FA0C4 = 0xFFFFA0C4   # 4x u32 dwell output words (out, = 0)
FA0D8 = 0xFFFFA0D8   # 4x u8[8] channel control block; bytes +4/+5 cleared
BYTE_CLEAR = [FA0D8 + i * 8 + 4 for i in range(4)] + \
             [FA0D8 + i * 8 + 5 for i in range(4)]
# peripheral block read-modify-written by 0x8FCC / 0xAA74
F6LO, F6HI = 0xFFFFF600, 0xFFFFF680
CFG_TBL = 0xDAB4          # 4 x u32 cfg words, stride 0x18


def r32(d, a):
    return struct.unpack('>f', bytes(d.get(a + i, 0) for i in range(4)))[0]


def u32b(v):
    return [v >> 24, (v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF]


def merge(cpu2, m):
    """Copy every non-stack RAM write of the helper instance back into `m`."""
    for k, v in cpu2.ram.items():
        if 0xFFFFDE00 <= k <= 0xFFFFDF00:   # task stack area
            continue
        m[k] = v


def ref(cpu2, ram, rom):
    """Line-for-line mirror of ignitionDwellOutputInit().

    The callees (0x8FCC, 0xAA74, 0x94C8) run in the dedicated emulator
    instance `cpu2` so SR handling and all RAM side effects match the ROM
    exactly.  Returns a full RAM-effect dict (int keys -> byte values).
    """
    m = dict(ram)

    # ---- step 1: bsr 0x8FCC ----
    cpu2.call(0x8FCC, ram=m)
    merge(cpu2, m)

    # ---- step 2: 4-channel loop ----
    for i in range(4):
        cfg = (rom[CFG_TBL + i * 0x18] << 24) | (rom[CFG_TBL + i * 0x18 + 1] << 16) | \
              (rom[CFG_TBL + i * 0x18 + 2] << 8) | rom[CFG_TBL + i * 0x18 + 3]
        cpu2.call(0xAA74, r4=cfg, r5=0, ram=m)
        merge(cpu2, m)
        m[FA0D8 + i * 8 + 4] = 0            # coil on/off byte
        m[FA0D8 + i * 8 + 5] = 0            # fault byte
        for k, b in enumerate(u32b(0)):
            m[FA0C4 + i * 4 + k] = b        # dwell output word

    # ---- step 3: tail-call 0x94C8 ----
    cpu2.call(0x94C8, ram=m)
    merge(cpu2, m)
    return m


def gen_state(rng):
    """Random seeded RAM hitting every RAM read / write target."""
    ram = {}

    def setf(a, v):
        for i, b in enumerate(struct.pack('>f', ts(v))):
            ram[a + i] = b

    # inputs to the 0x94C8 tail call (incl. out-of-map values)
    setf(F9F80, rng.uniform(0, 9000))               # RPM
    setf(F9F68, rng.uniform(4, 20))                 # battV
    ram[FA0D6] = rng.randint(0, 255)
    ram[FA0D6 + 1] = rng.randint(0, 255)            # u16 dwell offset

    # write targets (must be overwritten by the lift)
    for a in [FA0C4, FA0C4 + 4, FA0C4 + 8, FA0C4 + 12, FA0D4]:
        for i in range(4):
            ram[a + i] = rng.randint(0, 255)
    for a in BYTE_CLEAR:
        ram[a] = rng.randint(0, 255)

    # peripheral block exercised by the 0x8FCC / 0xAA74 callee chain
    for a in range(F6LO, F6HI):
        ram[a] = rng.randint(0, 255)
    return ram


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    rom = open(ROM, 'rb').read()

    cpu = SH2(rom)
    cpu2 = SH2(rom)         # dedicated instance for the callee calls in ref()
    seeds = (0x8F62, 0xAA74, 0xDAB4, 0x8FCC, 0x94C8)
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
                      (seed, it, {hex(k): (hex(g), hex(e)) for k, g, e in bad[:12]}))
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
    print('OK  0x8F62 ignitionDwellOutputInit  (%d random inputs across %d seeds)'
          % (N * len(seeds), len(seeds)))
    print('\nAll ignitionDwellOutputInit tests passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()
