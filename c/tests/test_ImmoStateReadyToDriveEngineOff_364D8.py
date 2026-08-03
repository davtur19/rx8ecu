#!/usr/bin/env python3
"""test_ImmoStateReadyToDriveEngineOff_364D8.py

Differential test for ROM 0x364D8 (60E1D400.bin) — lift
c/ImmoStateReadyToDriveEngineOff.c.

The idle-state handler dispatches on IMMO_STATE (0xFFFFC28E):

  state == 1:  snapshot = *(u32*)0xFFFFC278; do { Immo_Keygen_related_ADC();
                } while (*0xFFFFC278 == snapshot); then 0xFFFFC27C (u16) =
                0x01F4 and a tail-jump into ImmoStateMachine_360E8 (state
                still == 1, so the substate 0xFFFFC291 dispatch runs next).
  else:        state = 5; IMMO_TIMER (0xFFFFC282, u16) decrements only while
                positive as int16; when it reaches 0: ImmoBadStateSet(),
                IMMO_STATE_CODE = 5, setImmoCANTXData(0xC8), IMMO_TIMER=0x01F4.

The whole call tree executes in the emulator for real: the state==1 key
generator Immo_Keygen_related_ADC (0x36AFC, incl. in-ROM adc_read 0x3EDBC
and its SR/flag helpers 0x3920/0x3934/0x3F050), and the state==3 tail jump
through ImmoStateMachine_360E8 (all sub-models identical to
test_ImmoStateMachine_360E8.py).  The Python model mirrors the ROM bytes
verbatim — including adc_c read from 0xFFFF9F00 (base 0xFFFF9EE4 + 0x1C),
NOT the 0xFFFF9EF2 claimed in some lift comments.

Run: python3 c/tests/test_ImmoStateReadyToDriveEngineOff_364D8.py [N]
     (N = random overlays per seed; default 5000 -> 25000 across 5 seeds)
"""
import os, random, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ADDR = 0x364D8

# --- RAM map ---
STATE      = 0xFFFFC28E   # IMMO_STATE
SUB        = 0xFFFFC291   # substate (tail-jump into state machine)
ROLL       = 0xFFFFC278   # u32 rolling code / keygen out
C27C       = 0xFFFFC27C   # u16 500-tick timer
TIMER      = 0xFFFFC282   # u16 IMMO_TIMER
STATE_CODE = 0xFFFFC28D   # IMMO_STATE_CODE
BADTO      = 0xFFFFC284   # u16 IMMO_TIMEOUT_CTR (ImmoBadStateSet)
CAN_TX     = 0xFFFFC240
LAMP       = 0xFFFFF754   # 16-bit lamp GPIO
BUF        = 0xFFFFC238
RESP       = 0xFFFFC294
WAIT_STATE = 0xFFFFC290
TX_REQ     = 0xFFFFC241
TX_STATUS  = 0xFFFFC296
TX_STATE   = 0xFFFFC28F
TX_PENDING = 0xFFFFC299
W2E0       = 0xFFFFC2E0
W2DC       = 0xFFFFC2DC
SEED       = 0xFFFFC270
# keygen internals
WGEN_C     = 0xFFFFC293   # u8 cnt
WGEN_288   = 0xFFFFC288   # u16
WGEN_28A   = 0xFFFFC28A   # u16
ADC_A      = 0xFFFF9F1C   # u16 (base 0xFFFF9EE4 + 0x38)
ADC_B      = 0xFFFF9F1E   # u16 (base + 0x3A)
ADC_C      = 0xFFFF9F00   # u16 (base + 0x1C)  <- ROM really reads 0x9F00
ADCREG     = 0xFFFF869C   # adc_read channel base
C6AC       = 0xFFFFC6AC   # adc_read fail path flag (0x3F050)


def u16(m, a):
    return ((m.get(a, 0) & 0xFF) << 8) | (m.get(a + 1, 0) & 0xFF)


def u32(m, a):
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


def s16(x):
    x &= 0xFFFF
    return x - 0x10000 if x & 0x8000 else x


# ---------- sub-models (identical to the sibling tests) ----------

def set_light(m, on):
    v = (u16(m, LAMP) | 0x60) if on == 1 else (u16(m, LAMP) & ~0x60)
    wr16(m, LAMP, v & 0xFFFF)


def bad_state_set(m):
    set_light(m, 0)
    m[CAN_TX] = 0
    wr16(m, BADTO, 0x01F4)
    m[STATE_CODE] = 4


def set_can_tx(m, cmd):
    m[BUF] = cmd
    if cmd == 0x09:
        sel = m.get(WAIT_STATE, 0)
        if sel in (1, 2, 3, 4):
            v = u32(m, 0xFFFFC24C + (sel - 1) * 4)
            m[BUF + 1] = sel
            m[BUF + 2] = (v >> 16) & 0xFF
            m[BUF + 3] = (v >> 8) & 0xFF
            m[BUF + 4] = v & 0xFF
        elif sel == 0xFF:
            m[BUF + 1] = sel
            m[BUF + 2] = m[BUF + 3] = m[BUF + 4] = 0
    elif cmd == 0x07:
        v = u32(m, ROLL)
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


def fold4(v):
    return ((v << 4) & 0xFFFFFFFF) + (v >> 4)


def calc(r4, r5, r6):
    """Mirror of calculateImmoSeed (ROM 0x3675C)."""
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


# ---------- keygen (ROM 0x36AFC) ----------

def adc_read(m):
    """ROM 0x3EDBC (+0x3F050 on checksum fail)."""
    w0 = u16(m, ADCREG)
    w1 = u16(m, ADCREG + 2)
    w2 = u16(m, ADCREG + 4)
    w3 = u16(m, ADCREG + 6)
    comp = (~((w0 + w1) & 0xFFFF)) & 0xFFFF
    if w2 == comp or w3 == comp:
        return u32(m, ADCREG)
    m[C6AC] = 1
    return 0


def keygen(m):
    """ROM 0x36AFC line-for-line (reads adc_a/b/c + adc_read, mixes the
    three keygen words, publishes new rolling code to 0xFFFFC278)."""
    adc_a = u16(m, ADC_A)
    adc_b = u16(m, ADC_B)
    adc_c = u16(m, ADC_C)
    r7 = adc_read(m)

    # *cnt = (ret & 0xffff) + adc_a + *cnt   (byte)
    m[WGEN_C] = ((r7 & 0xFFFF) + adc_a + m.get(WGEN_C, 0)) & 0xFF

    rhi = (r7 >> 16) & 0xFFFF
    # guard: ~(w288) >= rhi? never true -> always run A-block
    # A-block: if w28A == 0xFFFF: cnt++; w28A++
    if u16(m, WGEN_28A) == 0xFFFF:
        m[WGEN_C] = (m.get(WGEN_C, 0) + 1) & 0xFF
    wr16(m, WGEN_28A, (u16(m, WGEN_28A) + 1) & 0xFFFF)

    # w288 = (ret>>16)&0xffff + w288 + adc_b
    wr16(m, WGEN_288, (rhi + u16(m, WGEN_288) + adc_b) & 0xFFFF)

    # guard: ~(w28A) >= (ret&0x00FFFF00)>>8? never true -> cnt++
    m[WGEN_C] = (m.get(WGEN_C, 0) + 1) & 0xFF

    # w28A = ((ret&0x00FFFF00)>>8) + w28A + adc_c
    wr16(m, WGEN_28A, (((r7 & 0x00FFFF00) >> 8) + u16(m, WGEN_28A) +
                       adc_c) & 0xFFFF)

    # w288 = ((adc_c<<8) + (adc_a&0xff)) ^ w288
    wr16(m, WGEN_288, ((((adc_c & 0xFF) << 8) | (adc_a & 0xFF)) ^
                       u16(m, WGEN_288)) & 0xFFFF)

    # w28A = ~(((adc_a<<8) + (adc_b&0xff)) ^ w28A)
    wr16(m, WGEN_28A, (~((((adc_a & 0xFF) << 8) | (adc_b & 0xFF)) ^
                         u16(m, WGEN_28A))) & 0xFFFF)

    # cnt = adc_b ^ cnt   (byte)
    m[WGEN_C] = (m.get(WGEN_C, 0) ^ (adc_b & 0xFF)) & 0xFF

    # combined = (w288<<16) | w28A; if 0 -> w2E0 | w2DC
    combined = (u16(m, WGEN_288) << 16) | u16(m, WGEN_28A)
    if combined == 0:
        combined = u32(m, W2E0) | u32(m, W2DC)
    wr32(m, ROLL, combined)


# ---------- main model ----------

def model(ram):
    m = dict(ram)
    state = m.get(STATE, 0)
    if state == 1:
        snapshot = u32(m, ROLL)
        while True:
            keygen(m)
            if u32(m, ROLL) != snapshot:
                break
        wr16(m, C27C, 0x01F4)
        # tail-jump ImmoStateMachine_360E8 with state still == 1
        sub = m.get(SUB, 0)
        if sub == 1:
            bad_state_set(m)
            m[RESP] = 0
            set_can_tx(m, 0x01)
            m[0xFFFFC29A] = 1
        elif sub == 3:
            m[STATE_CODE] = 0
        elif sub == 2:
            v = m.get(0xFFFFC2F2, 0)
            if 0 < v <= 2:
                m[0xFFFFC2F2] = (v - 1) & 0xFF
                m[0xFFFFC29F] = 1
                set_light(m, 1)
                m[CAN_TX] = 1
                m[0xFFFFC298] = 0
            else:
                set_light(m, 0)
                m[CAN_TX] = 0
            wr16(m, 0xFFFFC286, 0x02EE)
            wr32(m, SEED, calc(u32(m, W2DC), u32(m, W2E0), u32(m, ROLL)))
            set_can_tx(m, 0x07)
            m[STATE_CODE] = 2
        # sub == 0/other: nothing after the C27C write
    else:
        m[STATE] = 5
        c = u16(m, TIMER)
        if (c & 0xFFFF) != 0:   # cmp/pl after extu.w: true for any nonzero
            c = (c - 1) & 0xFFFF
            wr16(m, TIMER, c)
        if c == 0:
            bad_state_set(m)
            m[STATE_CODE] = 5
            set_can_tx(m, 0xC8)
            wr16(m, TIMER, 0x01F4)
    return m


def seed_ram(rng):
    m = {}
    for a in (STATE, SUB, STATE_CODE, CAN_TX, RESP, WAIT_STATE,
              0xFFFFC2F2, 0xFFFFC29F, 0xFFFFC298, 0xFFFFC29A,
              WGEN_C, C6AC):
        m[a] = rng.randint(0, 255)
    for a in (TIMER, C27C, BADTO, WGEN_288, WGEN_28A, LAMP,
              ADC_A, ADC_B, ADC_C):
        m[a] = rng.randint(0, 255)
        m[a + 1] = rng.randint(0, 255)
    for a in (ROLL, W2DC, W2E0):
        for i in range(4):
            m[a + i] = rng.randint(0, 255)
    for i in range(8):
        m[ADCREG + i] = rng.randint(0, 255)
    return m


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    seeds = (0x364D8, 0xC278, 0x36AFC, 0xC282, 0x5EED)
    total = fails = 0

    for seed in seeds:
        rng = random.Random(seed)
        for _ in range(N):
            m = seed_ram(rng)
            if rng.random() < 0.5:
                m[STATE] = 1
                m[SUB] = rng.choice([1, 2, 3, 0])
            else:
                m[STATE] = rng.choice([0, 2, 3, 4, 5, 7])
            want = model(m)
            cpu.call(ADDR, ram=dict(m))
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
                          (seed, m.get(STATE, 0), m.get(SUB, 0),
                           {hex(k): (hex(g), hex(e))
                            for k, g, e in bad[:10]}))
            total += 1
        if fails >= 5:
            break

    if fails:
        print('\nFAIL ImmoStateReadyToDriveEngineOff @0x364D8 '
              '(%d mismatches / %d inputs)' % (fails, total))
        sys.exit(1)
    print('OK  ImmoStateReadyToDriveEngineOff @0x364D8 '
          '(%d inputs, 0 mismatches)' % total)
    sys.exit(0)


if __name__ == '__main__':
    main()