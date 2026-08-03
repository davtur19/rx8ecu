#!/usr/bin/env python3
"""test_ImmoGetCANData_36870.py

Differential test for ROM 0x36870 (60E1D400.bin) — lift c/ImmoGetCANData.c.

Consumes one CAN RX frame from mailboxes 0xFFFFC529..0xFFFFC52F (loaded via
`mov.w <lit>,Rn` which SIGN-EXTENDS: 0xC52x -> 0xFFFFC52x).  Entry flag
0xFFFFC52F gates processing; mode 0xFFFFC529 dispatches; 0xFFFFC52A..D carry
payload; 0xFFFFC52F cleared on every exit.

Dispatch (verified against disasm 0x36882..0x369AE):
  0xFFFFC52F != 1          -> state (0xFFFFC28E) = 5
  mode == 0x00             -> state = 0
  mode == 0x06             -> state = 1;  a==0&&b==0xFF -> C291=1
                                         a==1&&b==0xFF -> C291=3
                                         a==0x7F        -> C291=2
                                         else           -> state = 6
  mode == 0x08             -> state = 2; u32 0xFFFFC274 = a<<24|b<<16|c<<8|d
  mode == 0x90             -> a in {1,2,3,4}: state=4, u32 0xFFFFC25C = ...
                              else state = 6
  mode == 0xC9             -> state = 3
  else                     -> state = 6
  epilogue always          -> 0xFFFFC52F = 0

The emulator's final r0 is also modeled (it is an incidental artifact of the
disasm: e.g. r0 = the literal address 0xFFFFC274 for mode 0x08, 0xFFFFC25C
for mode 0x90).

Run: python3 c/tests/test_ImmoGetCANData_36870.py [N]
     (N = random frames per seed; default 5000 -> 25000 across 5 seeds)
"""
import os, random, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ADDR = 0x36870

C28E = 0xFFFFC28E   # IMMO_STATE
C291 = 0xFFFFC291   # IMMO_SUBSTATE
C274 = 0xFFFFC274   # IMMO_RX_CHALLENGE (u32)
C25C = 0xFFFFC25C   # IMMO_RX_KEY_VALUE (u32)
C52F = 0xFFFFC52F   # CAN_RX_STATUS
C529 = 0xFFFFC529   # CAN_RX_MODE
C52A = 0xFFFFC52A   # CAN_RX_B1
C52B = 0xFFFFC52B   # CAN_RX_B2
C52C = 0xFFFFC52C   # CAN_RX_B3
C52D = 0xFFFFC52D   # CAN_RX_B4


def wr32(m, a, v):
    m[a] = (v >> 24) & 0xFF
    m[a + 1] = (v >> 16) & 0xFF
    m[a + 2] = (v >> 8) & 0xFF
    m[a + 3] = v & 0xFF


def model(ram):
    m = dict(ram)
    status = m.get(C52F, 0)
    if status != 1:
        m[C28E] = 5
        r0 = status & 0xFF    # r0 retains extu.b(C52F) on the bypass path
    else:
        mode = m.get(C529, 0)
        a = m.get(C52A, 0)
        b = m.get(C52B, 0)
        c = m.get(C52C, 0)
        d = m.get(C52D, 0)
        if mode == 0x00:
            m[C28E] = 0
            r0 = 0
        elif mode == 0x06:
            m[C28E] = 1
            if a == 0x00 and b == 0xFF:
                m[C291] = 1
                r0 = 0xFF
            elif a == 0x01 and b == 0xFF:
                m[C291] = 3
                r0 = 1
            elif a == 0x7F:
                m[C291] = 2
                r0 = 0x7F
            else:
                m[C28E] = 6
                r0 = a & 0xFF
        elif mode == 0x08:
            m[C28E] = 2
            wr32(m, C274, (a << 24) | (b << 16) | (c << 8) | d)
            r0 = 0xFFFFC274
        elif mode == 0x90:
            if 1 <= a <= 4:
                m[C28E] = 4
                wr32(m, C25C, (a << 24) | (b << 16) | (c << 8) | d)
                r0 = 0xFFFFC25C
            else:
                m[C28E] = 6
                r0 = a & 0xFF
        elif mode == 0xC9:
            m[C28E] = 3
            r0 = 0xC9
        else:
            m[C28E] = 6
            r0 = mode & 0xFF
    m[C52F] = 0
    return m, r0 & 0xFFFFFFFF


def seed_ram(rng):
    m = {}
    m[C28E] = rng.randint(0, 255)
    m[C291] = rng.randint(0, 255)
    for a in (C52F, C529, C52A, C52B, C52C, C52D):
        m[a] = rng.randint(0, 255)
    return m


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    seeds = (0x36870, 0xC529, 0xC52F, 0x5EED, 0x13579)
    total = fails = 0

    # interesting modes per iteration to force full dispatch coverage
    interesting = [0x00, 0x06, 0x08, 0x90, 0xC9, 0x7F, 0x55, 0xAA]

    for seed in seeds:
        rng = random.Random(seed)
        for _ in range(N):
            ram = seed_ram(rng)
            mode = interesting[_ % len(interesting)]
            ram[C529] = mode
            if _ % 7 == 0:          # gate closed sometimes
                ram[C52F] = 0
            elif mode == 0x06:      # force the sub-dispatch corners
                subcase = _ % 5
                if subcase == 0:
                    ram[C52A], ram[C52B] = 0x00, 0xFF
                elif subcase == 1:
                    ram[C52A], ram[C52B] = 0x01, 0xFF
                elif subcase == 2:
                    ram[C52A], ram[C52B] = 0x7F, rng.randint(0, 255)
                else:
                    ram[C52A], ram[C52B] = rng.choice(
                        [0, 2, 0xFF]), rng.randint(0, 255)
            elif mode == 0x90:      # force the sel corners
                if _ % 3 == 0:
                    ram[C52A] = rng.choice([1, 2, 3, 4])
            want, want_r0 = model(ram)
            got_r0 = cpu.call(ADDR, ram=dict(ram))
            bad = []
            allk = set(want) | set(cpu.ram.keys())
            for k in allk:
                if 0xFFFFDE00 <= k <= 0xFFFFDF00:
                    continue
                if cpu.ram.get(k, 0) != want.get(k, 0):
                    bad.append((k, cpu.ram.get(k, 0), want.get(k, 0)))
            if got_r0 != want_r0:
                bad.append(('r0', got_r0, want_r0))
            if bad:
                fails += 1
                if fails <= 5:
                    print('MISMATCH seed=0x%X mode=%02X: %s' %
                          (seed, mode, {k: (hex(g), hex(e))
                                        for k, g, e in bad[:10]}))
            total += 1
        if fails >= 5:
            break

    if fails:
        print('\nFAIL ImmoGetCANData @0x36870  (%d mismatches / %d inputs)'
              % (fails, total))
        sys.exit(1)
    print('OK  ImmoGetCANData @0x36870  (%d inputs, 0 mismatches)' % total)
    sys.exit(0)


if __name__ == '__main__':
    main()
