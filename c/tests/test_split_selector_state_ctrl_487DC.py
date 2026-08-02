#!/usr/bin/env python3
"""test_split_selector_state_ctrl_487DC.py

Differential test for ROM 0x487DC (60E1D400.bin) — lift
c/split_selector_state_ctrl_487DC.c.

Runs the ACTUAL ROM bytes of 0x487DC — including the verified leaf 0x3ED3C
(readValue_8bit_ADDRESS_VAL, and its 0x3F050 fault-flag side effect) — in
tools/sh2emu.py over seeded RAM states (the oracle), and compares the full
post-call RAM overlay against a Python reference model that mirrors the C lift
line-for-line.

Key semantic facts (see the lift header):
  * Despite the IDA name, this function does NOT compute a split angle and does
    NOT touch A734/A738.  It computes one byte u8@0xFFFFCCD2 as a gated running
    max over 29 calibration thresholds cal8[0x7C27F..0x7C29B] (stock 0..3).
  * Gates are either plain RAM bytes == 1 (0xFFFFB5xx / 0xFFFFCCxx) or the
    verified leaf 0x3ED3C on 7 redundant (value, ~value) byte pairs at
    0xFFFF8750/8764/8768/876C/8770/8778/8780.  On a bad pair the leaf returns
    0 AND writes the fault flag RAM8@0xFFFFC6AC = 1 (via 0x3F050).
  * The next function split_selector_decoder_48C12 decodes CCD2 into the output
    pair (CCE2, CCE3): 0 -> (0,0), 1 -> (0,1), >=2 -> (1,0).

Run: python3 c/tests/test_split_selector_state_ctrl_487DC.py [N]
     (N = random inputs per seed; default 100000 -> 500000 across 5 seeds)
"""
import os, random, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ADDR = 0x487DC

# ---- RAM addresses (see c/split_selector_state_ctrl_487DC.c header) ----
CCD2 = 0xFFFFCCD2   # u8 output selector byte
C6AC = 0xFFFFC6AC   # u8 fault flag (set to 1 by 0x3ED3C on a bad pair)

# plain-byte gate addresses, in ROM block order
GATE_ADDRS = [
    0xFFFFB563, 0xFFFFB565, 0xFFFFB567, 0xFFFFB569, 0xFFFFB56D, 0xFFFFB56B,
    0xFFFFCCD6, 0xFFFFCCD7, 0xFFFFCCDE,
    0xFFFFB57C,
    0xFFFFB560, 0xFFFFB588, 0xFFFFCCD3, 0xFFFFCCD4, 0xFFFFCCD5,
    0xFFFFB584, 0xFFFFB586, 0xFFFFB57E, 0xFFFFB580, 0xFFFFB582,
    0xFFFFCC8C, 0xFFFFCC8D,
]

# (addr, ROM threshold) for the 7 readValue_8bit_ADDRESS_VAL(addr, 0) gates,
# in ROM block order
RV_GATES = [
    (0xFFFF8768, 0x7C27F),   # block 1: special cmp/pl (signed > 0) check
    (0xFFFF876C, 0x7C286),
    (0xFFFF8750, 0x7C28A),
    (0xFFFF8780, 0x7C28C),
    (0xFFFF8764, 0x7C28D),
    (0xFFFF8770, 0x7C28E),
    (0xFFFF8778, 0x7C28F),
]

# (gate_addr, ROM threshold) for the plain-byte gates, in ROM block order
DIRECT_GATES = [
    (0xFFFFB563, 0x7C280), (0xFFFFB565, 0x7C281), (0xFFFFB567, 0x7C282),
    (0xFFFFB569, 0x7C283), (0xFFFFB56D, 0x7C284), (0xFFFFB56B, 0x7C285),
    (0xFFFFCCD6, 0x7C287), (0xFFFFCCD7, 0x7C288), (0xFFFFCCDE, 0x7C289),
    (0xFFFFB57C, 0x7C28B),
    (0xFFFFB560, 0x7C290), (0xFFFFB588, 0x7C291), (0xFFFFCCD3, 0x7C292),
    (0xFFFFCCD4, 0x7C293), (0xFFFFCCD5, 0x7C294),
    (0xFFFFB584, 0x7C295), (0xFFFFB586, 0x7C296), (0xFFFFB57E, 0x7C297),
    (0xFFFFB580, 0x7C298), (0xFFFFB582, 0x7C299),
    (0xFFFFCC8C, 0x7C29A), (0xFFFFCC8D, 0x7C29B),
]


def gb(ram, a):
    return ram.get(a, 0)


def model(ram, rom):
    """Line-for-line mirror of split_selector_state_ctrl_487DC().

    Returns a full RAM-effect dict (int keys -> byte values) so the caller can
    diff it against the emulator's post-call RAM (like the other lift tests).
    """
    m = dict(ram)

    def rd(a):
        return m.get(a, 0)

    def rv(addr):
        """Leaf 0x3ED3C readValue_8bit_ADDRESS_VAL(addr, 0):
        RAM8[a] == ~RAM8[a+1] ? RAM8[a] : (fault flag C6AC = 1, 0)."""
        b0 = rd(addr)
        b1 = rd(addr + 1)
        if b0 == ((~b1) & 0xFF):
            return b0
        m[C6AC] = 1
        return 0

    def gate_max(cur, gate, thresh_addr):
        t = rom[thresh_addr]
        if gate == 1 and t > cur:
            return t
        return cur

    r14 = 0

    # Block 1 (0x487E8): cmp/pl (signed > 0) on cal[0x7C27F]
    if rv(0xFFFF8768) == 1 and _s8(rom[0x7C27F]) > 0:
        r14 = rom[0x7C27F]

    # Blocks 2..7
    for g, t in DIRECT_GATES[:6]:
        r14 = gate_max(r14, rd(g), t)

    # Block 8
    r14 = gate_max(r14, rv(0xFFFF876C), 0x7C286)

    # Blocks 9..11
    for g, t in DIRECT_GATES[6:9]:
        r14 = gate_max(r14, rd(g), t)

    # Block 12
    r14 = gate_max(r14, rv(0xFFFF8750), 0x7C28A)

    # Block 13
    r14 = gate_max(r14, rd(0xFFFFB57C), 0x7C28B)

    # Blocks 14..17
    for g, t in RV_GATES[3:]:
        r14 = gate_max(r14, rv(g), t)

    # Block 18
    r14 = gate_max(r14, rd(0xFFFFB560), 0x7C290)

    # Blocks 19..29
    for g, t in DIRECT_GATES[10:]:
        r14 = gate_max(r14, rd(g), t)

    m[CCD2] = r14
    return m


def _s8(x):
    x &= 0xFF
    return x - 0x100 if x & 0x80 else x


def seed_rv_pair(ram, addr, rng):
    """Seed a redundant (value, ~value) byte pair; 30% chance of a bad pair."""
    val = rng.randint(0, 255)
    if rng.random() < 0.3:
        ram[addr] = val
        ram[addr + 1] = rng.randint(0, 255)        # broken complement
    else:
        ram[addr] = val
        ram[addr + 1] = (~val) & 0xFF              # valid complement
    return val


def gen_state(rng):
    """Random seeded RAM hitting every gate combination."""
    ram = {}
    for a in GATE_ADDRS:
        ram[a] = rng.choice([0, 1, rng.randint(0, 255)])
    for a, _ in RV_GATES:
        seed_rv_pair(ram, a, rng)
    # 30% chance all direct gates are 0 -> r14 stays whatever the RV gates set
    if rng.random() < 0.3:
        for a in GATE_ADDRS:
            ram[a] = 0
    # 30% chance all RV pairs are valid with value 1 (max coverage of ==1 path)
    if rng.random() < 0.3:
        for a, _ in RV_GATES:
            ram[a] = 1
            ram[a + 1] = 0xFE
    ram[C6AC] = rng.choice([0, 1])
    ram[CCD2] = rng.randint(0, 255)               # previous output (must be overwritten)
    return ram


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    rom = open(ROM, 'rb').read()

    cpu = SH2(rom)
    seeds = (0x487DC, 0xCCD2, 0x8768, 0xB560, 0x7C28F)
    total_fails = 0

    for seed in seeds:
        rng = random.Random(seed)
        fails = 0
        for it in range(N):
            ram = gen_state(rng)
            want = model(ram, rom)
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
                print('  gates=%s' % {hex(a): gb(ram, a) for a in GATE_ADDRS})
                print('  rv=%s' % {hex(a): (gb(ram, a), gb(ram, a + 1)) for a, _ in RV_GATES})
                print('  C6AC=%d CCD2=%d want_CCD2=%d' %
                      (gb(ram, C6AC), gb(ram, CCD2), want.get(CCD2, 0)))
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
    print('OK  0x487DC split_selector_state_ctrl  (%d random inputs across %d seeds)'
          % (N * len(seeds), len(seeds)))
    print('\nAll split_selector_state_ctrl_487DC tests passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()
