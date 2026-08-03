#!/usr/bin/env python3
"""test_ImmoStateMachine_360E8.py

Differential test for ROM 0x360E8 (60E1D400.bin) — lift c/ImmoStateMachine.c.

The immobilizer state machine dispatches on IMMO_STATE (0xFFFFC28E):

  state == 1:  substate (0xFFFFC291) dispatch
      sub == 1: ImmoBadStateSet()            (lamp off, CAN_TX=0, TIMEOUT=0x01F4,
                                              STATE_CODE=4)
                0xFFFFC294 = 0
                setImmoCANTXData(0x01)       (RESP=C294=0 -> buf[1]=0)
                0xFFFFC29A = 1
      sub == 3: 0xFFFFC28D = 0
      sub == 2: v = E2_WORK_INDEX30 (0xFFFFC2F2)
                if 0 < v <= 2:  C2F2 = v-1; 0xFFFFC29F=1; setImmoLight(1);
                                CAN_TX(0xFFFFC240)=1; 0xFFFFC298=0
                else:           setImmoLight(0); CAN_TX=0
                IMMO_SEED_TIMER (0xFFFFC286, u16) = 0x02EE
                ImmoGetSeed_3664E()           (C270 = calculateImmoSeed(...))
                setImmoCANTXData(0x07)        (KEYGEN -> buf)
                0xFFFFC28D = 2
      other sub: nothing
  state == 3:  tail-jump into ImmoWaitForKey_35F92 (state still 3):
      E2_WORK_INDEX10 (0xFFFFC2E4)==1: 0xFFFFC290=0xFF; setImmoCANTXData(0x09);
                                       0xFFFFC28D=0
      else: ImmoKeyExpander_365D6(); 0xFFFFC290=1; setImmoCANTXData(0x09);
            0xFFFFC27E (u16)=0x01F4
  other state: 0xFFFFC28E = 5

The whole call tree (BadStateSet, setImmoLight, GetSeed, KeyExpander,
seed_mixer, setImmoCANTXData — incl. the 0x35F92 tail jump) executes in the
emulator; the Python model composes the line-for-line sub-models verified in
the sibling tests.  Only seeded random pre-state overlays are varied.

Run: python3 c/tests/test_ImmoStateMachine_360E8.py [N]
     (N = random overlays per seed; default 5000 -> 25000 across 5 seeds)
"""
import os, random, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ADDR = 0x360E8

# --- RAM map ---
STATE    = 0xFFFFC28E   # IMMO_STATE
SUB      = 0xFFFFC291   # substate
STATE_CODE = 0xFFFFC28D # IMMO_STATE_CODE
GOOD     = 0xFFFFC29A   # IMMO_GOODSTATE_FLAG
C294     = 0xFFFFC294
C298     = 0xFFFFC298
C29F     = 0xFFFFC29F   # IMMO_SEED_ACTIVE
E2W30    = 0xFFFFC2F2   # E2_WORK_INDEX30
E2W10    = 0xFFFFC2E4   # E2_WORK_INDEX10 (paired key flag)
WAIT_STATE = 0xFFFFC290 # IMMO_WAIT_STATE / key-match slot selector
SEED_TIMER = 0xFFFFC286 # u16
C27E     = 0xFFFFC27E   # u16
LAMP     = 0xFFFFF754   # 16-bit lamp GPIO
CAN_TX   = 0xFFFFC240   # CAN_TX_DATA
KEY      = 0xFFFFC278   # rolling key out
W2E0     = 0xFFFFC2E0   # EEPROM key word
W2DC     = 0xFFFFC2DC   # EEPROM key word
SEED     = 0xFFFFC270   # calculated seed out
BUF      = 0xFFFFC238   # 8-byte TX frame
RESP     = 0xFFFFC294
SLOT0    = 0xFFFFC24C   # expected-key slots (32-bit)
SLOT1    = 0xFFFFC250
SLOT2    = 0xFFFFC254
SLOT3    = 0xFFFFC258
EXP      = [0xFFFFC260, 0xFFFFC264, 0xFFFFC268, 0xFFFFC26C]
PREF     = [0x01000000, 0x02000000, 0x03000000, 0x04000000]
SLOTS    = {1: SLOT0, 2: SLOT1, 3: SLOT2, 4: SLOT3}
TX_REQ     = 0xFFFFC241
TX_STATUS  = 0xFFFFC296
TX_STATE   = 0xFFFFC28F
TX_PENDING = 0xFFFFC299


def rd16(m, a):
    return ((m.get(a, 0) & 0xFF) << 8) | (m.get(a + 1, 0) & 0xFF)


def rd32(m, a):
    return ((m.get(a, 0) << 24) | (m.get(a + 1, 0) << 16) |
            (m.get(a + 2, 0) << 8) | m.get(a + 3, 0))


def wr32(m, a, v):
    m[a] = (v >> 24) & 0xFF
    m[a + 1] = (v >> 16) & 0xFF
    m[a + 2] = (v >> 8) & 0xFF
    m[a + 3] = v & 0xFF


def wr16(m, a, v):
    m[a] = (v >> 8) & 0xFF
    m[a + 1] = v & 0xFF


def seed_mixer(r4, r5):
    """Mirror of c/seed_mixer.c (ROM 0x366B8)."""
    x = ((r4 >> 8) & 0xFF) << 16 | ((r5 & 0xFF) << 8) | (r4 & 0xFF)
    x = (x & 0xFFE0301F) | ((x & 0x0FE0) << 9) | ((x & 0x001FC000) >> 9)
    y = (((0 - (x >> 16)) & 0xFF) << 16) | (((0 - (x >> 8)) & 0xFF) << 8) \
        | ((0 - x) & 0xFF)
    z = ((y << 21) & 0xFFFFFFFF) | (y >> 3)
    return ((z & 0xFF) << 16) | (((z >> 8) & 0xFF) << 8) | ((z >> 16) & 0xFF)


def fold4(v):
    return ((v << 4) & 0xFFFFFFFF) + (v >> 4)


def calc(r4, r5, r6):
    """Mirror of c/calculateImmoSeed.c (ROM 0x3675C)."""
    sum16 = (r4 >> 16) + (r6 >> 16)
    sum32 = (r4 + r6) & 0xFFFFFFFF
    m1 = 0x0D * ((sum16 & 0xFFFF) >> 8)
    m2 = 0x0D * (sum16 & 0xFFFF)
    m3 = 0x0D * ((sum32 & 0xFFFF) >> 8)
    m4 = 0x0D * (sum32 & 0xFFFF)
    b0 = m2 & 0xFF
    b1 = m4 & 0xFF
    sc1 = ((((m1 & 0xFF) << 7) & 0xFFFF) >> 8) + ((m1 & 0xFF) << 7)
    sc2 = ((((b0 << 7) & 0xFFFF) >> 8) + (b0 << 7))
    sc3 = ((((m3 & 0xFF) << 7) & 0xFFFF) >> 8) + ((m3 & 0xFF) << 7)
    sc4 = ((((b1 << 7) & 0xFFFF) >> 8) + ((b1 << 7) & 0xFFFF)) & 0xFFFFFFFF
    r14 = ((r5 >> 16) ^ sc2) & 0xFFFFFFFF
    r7 = (sc3 ^ (r5 >> 8)) & 0xFFFFFFFF
    r5n = (r5 ^ sc4) & 0xFFFFFFFF
    r6n = (sc1 ^ (r5 >> 24)) & 0xFFFFFFFF
    if r5n & 1:
        bo0 = r6n & 0xFF
        bo1 = r14 & 0xFF
        bo2 = fold4(r5n & 0xFF) & 0xFF
        bo3 = fold4(r7 & 0xFF) & 0xFF
    else:
        bo0 = fold4(r14 & 0xFF) & 0xFF
        bo1 = fold4(r6n & 0xFF) & 0xFF
        bo2 = r7 & 0xFF
        bo3 = r5n & 0xFF
    return (bo0 << 24) | (bo1 << 16) | (bo2 << 8) | bo3


# --- sub-model: setImmoLight_263C8 ---
def set_light(m, on):
    if on == 1:
        v = rd16(m, LAMP) | 0x60
    else:
        v = rd16(m, LAMP) & ~0x60
    m[LAMP] = (v >> 8) & 0xFF
    m[LAMP + 1] = v & 0xFF


# --- sub-model: ImmoBadStateSet_365B8 ---
def bad_state_set(m):
    set_light(m, 0)
    m[CAN_TX] = 0
    m[0xFFFFC284] = 0x01      # IMMO_TIMEOUT_CTR u16 = 0x01F4
    m[0xFFFFC285] = 0xF4
    m[STATE_CODE] = 4


# --- sub-model: ImmoGetSeed_3664E ---
def get_seed(m):
    wr32(m, SEED, calc(rd32(m, W2DC), rd32(m, W2E0), rd32(m, KEY)))


# --- sub-model: ImmoKeyExpander_365D6 ---
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


# --- sub-model: setImmoCANTXData_369B8 ---
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
        m[BUF + 1] = m.get(RESP, 0)
        m[BUF + 2] = m[BUF + 3] = m[BUF + 4] = 0
    elif cmd in (0xC6, 0xC8):
        m[BUF + 1] = m[BUF + 2] = m[BUF + 3] = m[BUF + 4] = 0
    m[BUF + 5] = m[BUF + 6] = m[BUF + 7] = 0
    m[TX_REQ] = 1
    m[TX_STATUS] = 0
    m[TX_STATE] = 0
    m[TX_PENDING] = 1


# --- sub-model: ImmoWaitForKey_35F92 (state==3 branch only) ---
def wait_for_key_state3(m):
    if m.get(E2W10, 0) == 1:
        m[WAIT_STATE] = 0xFF
        set_can_tx(m, 0x09)
        m[STATE_CODE] = 0
    else:
        key_expander(m)
        m[WAIT_STATE] = 1
        set_can_tx(m, 0x09)
        wr16(m, C27E, 0x01F4)


# --- main model: ImmoStateMachine_360E8 ---
def model(ram):
    m = dict(ram)
    state = m.get(STATE, 0)
    if state == 1:
        sub = m.get(SUB, 0)
        if sub == 1:
            bad_state_set(m)
            m[C294] = 0
            set_can_tx(m, 0x01)
            m[GOOD] = 1
        elif sub == 3:
            m[STATE_CODE] = 0
        elif sub == 2:
            v = m.get(E2W30, 0)
            if 0 < v <= 2:
                m[E2W30] = (v - 1) & 0xFF
                m[C29F] = 1
                set_light(m, 1)
                m[CAN_TX] = 1
                m[C298] = 0
            else:
                set_light(m, 0)
                m[CAN_TX] = 0
            wr16(m, SEED_TIMER, 0x02EE)
            get_seed(m)
            set_can_tx(m, 0x07)
            m[STATE_CODE] = 2
        # other sub: nothing
    elif state == 3:
        wait_for_key_state3(m)
    else:
        m[STATE] = 5
    return m


def seed_ram(rng):
    m = {}
    for a in (STATE, SUB, STATE_CODE, GOOD, C294, C298, C29F, E2W30, E2W10,
              WAIT_STATE, CAN_TX, SEED, RESP):
        m[a] = rng.randint(0, 255)
    for a in (SEED_TIMER, C27E):
        m[a] = rng.randint(0, 255)
        m[a + 1] = rng.randint(0, 255)
    for a in (LAMP, 0xFFFFC284):
        m[a] = rng.randint(0, 255)
        m[a + 1] = rng.randint(0, 255)
    for a in (KEY, W2E0, W2DC, SEED):
        for i in range(4):
            m[a + i] = rng.randint(0, 255)
    return m


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    seeds = (0x360E8, 0xC28E, 0xC291, 0x35F92, 0x5EED)
    total = fails = 0

    for seed in seeds:
        rng = random.Random(seed)
        for _ in range(N):
            # force one of the interesting dispatch points per iteration
            s = rng.randint(0, 4)
            if s == 0:
                state, sub = 1, 1
            elif s == 1:
                state, sub = 1, 2
            elif s == 2:
                state, sub = 1, 3
            elif s == 3:
                state, sub = 3, 0
            else:
                state, sub = rng.choice([0, 2, 4, 5, 7]), 0
            ram = seed_ram(rng)
            ram[STATE] = state
            ram[SUB] = sub
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
                    print('MISMATCH seed=0x%X state=%d sub=%d: %s' %
                          (seed, state, sub,
                           {hex(k): (hex(g), hex(e))
                            for k, g, e in bad[:10]}))
            total += 1
        if fails >= 5:
            break

    if fails:
        print('\nFAIL ImmoStateMachine @0x360E8  (%d mismatches / %d inputs)'
              % (fails, total))
        sys.exit(1)
    print('OK  ImmoStateMachine @0x360E8  (%d inputs, 0 mismatches)' % total)
    sys.exit(0)


if __name__ == '__main__':
    main()