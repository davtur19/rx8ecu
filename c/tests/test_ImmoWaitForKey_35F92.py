#!/usr/bin/env python3
"""test_ImmoWaitForKey_35F92.py

Differential test for ROM 0x35F92 (60E1D400.bin) — lift c/ImmoWaitForKey.c.

"Waiting for key" state handler.  Already exercised as a real tail-jump target
of ImmoStateMachine_360E8 (test_ImmoStateMachine_360E8.py, state==3); this
dedicated test drives it directly at its entry point.

  state == 3 (0xFFFFC28E):
    E2_WORK_INDEX10 (0xFFFFC2E4) == 1 (paired):
        0xFFFFC290 = 0xFF; setImmoCANTXData(0x09); 0xFFFFC28D = 0
    else:
        ImmoKeyExpander_365D6() (recomputes the 4 expected slots);
        0xFFFFC290 = 1; setImmoCANTXData(0x09); 0xFFFFC27E (u16) = 0x01F4
  state == 4:
    sel = 0xFFFFC290; key = u32@0xFFFFC25C
    sel==1: key == u32@0xFFFFC260 -> 0xFFFFC290 = 2; setImmoCANTXData(0x09)
    sel==2: key == u32@0xFFFFC264 -> 0xFFFFC290 = 3; setImmoCANTXData(0x09)
    sel==3: key == u32@0xFFFFC268 -> 0xFFFFC290 = 4; setImmoCANTXData(0x09)
    sel==4: key == u32@0xFFFFC26C -> 0xFFFFC27C (u16) = 0x01F4;
            setImmoCANTXData(0xC6); 0xFFFFC28D = 0
            else setImmoCANTXData(0x09)
    other sel: nothing
  any other state: 0xFFFFC28E = 5; countdown 0xFFFFC27E (u16): if signed
    positive (1..0x7FFF) decrement by 1; when 0 -> ImmoBadStateSet();
    0xFFFFC294 = 0; setImmoCANTXData(0x01); 0xFFFFC29A = 1

All callees (KeyExpander + seed_mixer, setImmoCANTXData, BadStateSet,
setImmoLight) execute in the emulator; the Python model composes the same
line-for-line sub-models verified in the sibling tests.  Only seeded random
pre-state overlays are varied.  RAM overlay is compared; the final r0 is a
setImmoCANTXData callee artifact and is not compared (same as the sibling
state-machine test).

Run: python3 c/tests/test_ImmoWaitForKey_35F92.py [N]
     (N = random overlays per seed; default 5000 -> 25000 across 5 seeds)
"""
import os, random, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ADDR = 0x35F92

STATE     = 0xFFFFC28E
STATE_CODE = 0xFFFFC28D
E2W10     = 0xFFFFC2E4
WAIT_STATE = 0xFFFFC290
C27E      = 0xFFFFC27E   # u16 countdown
C27C      = 0xFFFFC27C   # u16
C294      = 0xFFFFC294
C29A      = 0xFFFFC29A
KEY       = 0xFFFFC278   # rolling key out (u32)
W2E0      = 0xFFFFC2E0   # EEPROM key word (u32)
W2DC      = 0xFFFFC2DC   # EEPROM key word (u32)
C25C      = 0xFFFFC25C   # received key (u32)
BUF       = 0xFFFFC238
SLOT0     = 0xFFFFC24C
SLOT1     = 0xFFFFC250
SLOT2     = 0xFFFFC254
SLOT3     = 0xFFFFC258
EXP       = [0xFFFFC260, 0xFFFFC264, 0xFFFFC268, 0xFFFFC26C]
PREF      = [0x01000000, 0x02000000, 0x03000000, 0x04000000]
SLOTS     = {1: SLOT0, 2: SLOT1, 3: SLOT2, 4: SLOT3}
TX_REQ    = 0xFFFFC241
TX_STATUS = 0xFFFFC296
TX_STATE  = 0xFFFFC28F
TX_PENDING = 0xFFFFC299
CAN_TX    = 0xFFFFC240
LAMP      = 0xFFFFF754


def rd16(m, a):
    return ((m.get(a, 0) & 0xFF) << 8) | (m.get(a + 1, 0) & 0xFF)


def rd32(m, a):
    return ((m.get(a, 0) << 24) | (m.get(a + 1, 0) << 16) |
            (m.get(a + 2, 0) << 8) | m.get(a + 3, 0))


def wr16(m, a, v):
    m[a] = (v >> 8) & 0xFF
    m[a + 1] = v & 0xFF


def wr32(m, a, v):
    m[a] = (v >> 24) & 0xFF
    m[a + 1] = (v >> 16) & 0xFF
    m[a + 2] = (v >> 8) & 0xFF
    m[a + 3] = v & 0xFF


def seed_mixer(r4, r5):
    x = ((r4 >> 8) & 0xFF) << 16 | ((r5 & 0xFF) << 8) | (r4 & 0xFF)
    x = (x & 0xFFE0301F) | ((x & 0x0FE0) << 9) | ((x & 0x001FC000) >> 9)
    y = (((0 - (x >> 16)) & 0xFF) << 16) | (((0 - (x >> 8)) & 0xFF) << 8) \
        | ((0 - x) & 0xFF)
    z = ((y << 21) & 0xFFFFFFFF) | (y >> 3)
    return ((z & 0xFF) << 16) | (((z >> 8) & 0xFF) << 8) | ((z >> 16) & 0xFF)


# --- sub-models (identical to test_ImmoStateMachine_360E8.py) ---
def set_light(m, on):
    if on == 1:
        v = rd16(m, LAMP) | 0x60
    else:
        v = rd16(m, LAMP) & ~0x60
    m[LAMP] = (v >> 8) & 0xFF
    m[LAMP + 1] = v & 0xFF


def bad_state_set(m):
    set_light(m, 0)
    m[CAN_TX] = 0
    m[0xFFFFC284] = 0x01
    m[0xFFFFC285] = 0xF4
    m[STATE_CODE] = 4


def key_expander(m):
    key = rd32(m, KEY)
    w2E0 = rd32(m, W2E0)
    w2DC = rd32(m, W2DC)
    slots = [
        seed_mixer(w2E0, key),
        seed_mixer(w2E0 >> 16, key >> 8),
        seed_mixer(w2DC, key >> 16),
        seed_mixer(w2DC >> 16, key >> 24),
    ]
    for i in range(4):
        wr32(m, SLOTS[i + 1], slots[i])
        wr32(m, EXP[i], slots[i] | PREF[i])


def set_can_tx(m, cmd):
    m[BUF] = cmd
    if cmd == 0x09:
        sel = m.get(WAIT_STATE, 0)
        if sel in SLOTS:
            v = rd32(m, SLOTS[sel])
            m[BUF + 1] = sel
            m[BUF + 2] = (v >> 16) & 0xFF
            m[BUF + 3] = (v >> 8) & 0xFF
            m[BUF + 4] = v & 0xFF
        elif sel == 0xFF:
            m[BUF + 1] = sel
            m[BUF + 2] = m[BUF + 3] = m[BUF + 4] = 0
    elif cmd == 0x07:
        v = rd32(m, KEY)
        m[BUF + 1] = (v >> 24) & 0xFF
        m[BUF + 2] = (v >> 16) & 0xFF
        m[BUF + 3] = (v >> 8) & 0xFF
        m[BUF + 4] = v & 0xFF
    elif cmd in (0x01, 0x81):
        m[BUF + 1] = m.get(C294, 0)
        m[BUF + 2] = m[BUF + 3] = m[BUF + 4] = 0
    elif cmd in (0xC6, 0xC8):
        m[BUF + 1] = m[BUF + 2] = m[BUF + 3] = m[BUF + 4] = 0
    m[BUF + 5] = m[BUF + 6] = m[BUF + 7] = 0
    m[TX_REQ] = 1
    m[TX_STATUS] = 0
    m[TX_STATE] = 0
    m[TX_PENDING] = 1


# --- main model: ImmoWaitForKey_35F92 ---
def model(ram):
    m = dict(ram)
    state = m.get(STATE, 0)
    if state == 3:
        if m.get(E2W10, 0) == 1:
            m[WAIT_STATE] = 0xFF
            set_can_tx(m, 0x09)
            m[STATE_CODE] = 0
        else:
            key_expander(m)
            m[WAIT_STATE] = 1
            set_can_tx(m, 0x09)
            wr16(m, C27E, 0x01F4)
    elif state == 4:
        sel = m.get(WAIT_STATE, 0)
        key = rd32(m, C25C)
        if sel == 1:
            if rd32(m, EXP[0]) == key:
                m[WAIT_STATE] = 2
            set_can_tx(m, 0x09)
        elif sel == 2:
            if rd32(m, EXP[1]) == key:
                m[WAIT_STATE] = 3
            set_can_tx(m, 0x09)
        elif sel == 3:
            if rd32(m, EXP[2]) == key:
                m[WAIT_STATE] = 4
            set_can_tx(m, 0x09)
        elif sel == 4:
            if rd32(m, EXP[3]) == key:
                wr16(m, C27C, 0x01F4)
                set_can_tx(m, 0xC6)
                m[STATE_CODE] = 0
            else:
                set_can_tx(m, 0x09)
        # other sel: nothing
    else:
        m[STATE] = 5
        cnt = rd16(m, C27E)
        if cnt != 0:                     # extu.w + cmp/pl: any nonzero
            wr16(m, C27E, (cnt - 1) & 0xFFFF)
        if rd16(m, C27E) == 0:
            bad_state_set(m)
            m[C294] = 0
            set_can_tx(m, 0x01)
            m[C29A] = 1
    return m


def seed_ram(rng):
    m = {}
    for a in (STATE, STATE_CODE, E2W10, WAIT_STATE, C294, C29A, CAN_TX,
              TX_REQ, TX_STATUS, TX_STATE, TX_PENDING):
        m[a] = rng.randint(0, 255)
    m[0xFFFFC284] = rng.randint(0, 255)
    m[0xFFFFC285] = rng.randint(0, 255)
    m[LAMP] = rng.randint(0, 255)
    m[LAMP + 1] = rng.randint(0, 255)
    for a in (C27E, C27C):
        m[a] = rng.randint(0, 255)
        m[a + 1] = rng.randint(0, 255)
    for a in (KEY, W2E0, W2DC, C25C, SLOT0, SLOT1, SLOT2, SLOT3):
        for i in range(4):
            m[a + i] = rng.randint(0, 255)
    for a in EXP:
        for i in range(4):
            m[a + i] = rng.randint(0, 255)
    return m


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    seeds = (0x35F92, 0xC28E, 0xC290, 0x5EED, 0x13579)
    total = fails = 0

    for seed in seeds:
        rng = random.Random(seed)
        for _ in range(N):
            kind = _ % 7
            ram = seed_ram(rng)
            if kind == 0:            # state 3, paired
                ram[STATE], ram[E2W10] = 3, 1
            elif kind == 1:          # state 3, unpaired
                ram[STATE], ram[E2W10] = 3, 0
            elif kind == 2:          # state 4, sel 1..4, match
                sel = rng.randint(1, 4)
                ram[STATE], ram[WAIT_STATE] = 4, sel
                wr32(ram, C25C, rd32(ram, EXP[sel - 1]))
            elif kind == 3:          # state 4, sel 1..4, no-match
                sel = rng.randint(1, 4)
                ram[STATE], ram[WAIT_STATE] = 4, sel
                # force a different key
                v = rd32(ram, EXP[sel - 1]) ^ 0x01020304
                for i in range(4):
                    ram[C25C + i] = (v >> (24 - 8 * i)) & 0xFF
            elif kind == 4:          # state 4, other sel (0, 5, 0xFF)
                ram[STATE] = 4
                ram[WAIT_STATE] = rng.choice([0, 5, 0xFF, 7])
            elif kind == 5:          # other state, countdown edges
                ram[STATE] = rng.choice([0, 1, 2, 5, 6, 7])
                wr16(ram, C27E, rng.choice([0x0000, 0x0001, 0x0002, 0x7FFF,
                                            0x8000, 0xFFFF]))
            else:                    # other state, random countdown
                ram[STATE] = rng.choice([0, 1, 2, 5, 6, 7])
                ram[C27E] = rng.randint(0, 255)
                ram[C27E + 1] = rng.randint(0, 255)

            want = model(ram)
            cpu.call(ADDR, ram=dict(ram))
            bad = []
            allk = set(want) | set(cpu.ram.keys())
            for k in allk:
                if 0xFFFFDE00 <= k <= 0xFFFFDF00:
                    continue
                if cpu.ram.get(k, 0) != want.get(k, 0):
                    bad.append((k, cpu.ram.get(k, 0), want.get(k, 0)))
            if bad:
                fails += 1
                if fails <= 5:
                    print('MISMATCH seed=0x%X kind=%d: %s' %
                          (seed, kind, {k: (hex(g), hex(e))
                                        for k, g, e in bad[:10]}))
            total += 1
        if fails >= 5:
            break

    if fails:
        print('\nFAIL ImmoWaitForKey @0x35F92  (%d mismatches / %d inputs)'
              % (fails, total))
        sys.exit(1)
    print('OK  ImmoWaitForKey @0x35F92  (%d inputs, 0 mismatches)' % total)
    sys.exit(0)


if __name__ == '__main__':
    main()
