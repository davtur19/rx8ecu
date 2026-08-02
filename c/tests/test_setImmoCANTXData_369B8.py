#!/usr/bin/env python3
"""test_setImmoCANTXData_369B8.py

Differential test for ROM 0x369B8 (60E1D400.bin) — lift
c/setImmoCANTXData_369B8.c (old name: message_queue_state_dispatcher_369B8).

Builds the 8-byte immobilizer CAN TX frame at 0xFFFFC238 and raises the TX
request flags.  Leaf function (no callees): only the ROM bytes of 0x369B8
are executed by the emulator (the oracle), and the full post-call RAM
overlay is compared against a Python reference model that mirrors the C lift
line-for-line.

Run: python3 c/tests/test_setImmoCANTXData_369B8.py [N]
     (N = random inputs per seed; default 100000 -> 500000 across 5 seeds)
"""
import os, random, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ADDR = 0x369B8

BUF        = 0xFFFFC238   # 8-byte TX frame
WAIT_STATE = 0xFFFFC290   # key-match slot selector (1..4 / 0xFF)
KEYGEN     = 0xFFFFC278   # 32-bit rolling key out
SLOT0      = 0xFFFFC24C   # expected-key slots (32-bit)
SLOT1      = 0xFFFFC250
SLOT2      = 0xFFFFC254
SLOT3      = 0xFFFFC258
RESP       = 0xFFFFC294   # challenge response byte
# ROM reaches TX_REQ via mov.w 0x36AD6,r3 (literal 0xC241), which sign-extends
# to 0xFFFFC241 — the same physical byte as 0x0000C241 on the SH-2, but a
# distinct key in the emulator's sparse RAM.  The C lift's CAN_TX_REQ macro
# (0x0000C241) aliases it on hardware.
TX_REQ     = 0xFFFFC241   # CAN TX request flag (mov.w sign-extended)
TX_STATUS  = 0xFFFFC296   # TX status
TX_STATE   = 0xFFFFC28F   # TX state counter
TX_PENDING = 0xFFFFC299   # TX pending flag

SLOTS = {1: SLOT0, 2: SLOT1, 3: SLOT2, 4: SLOT3}


def rd32(m, a):
    return (m.get(a, 0) << 24) | (m.get(a + 1, 0) << 16) | \
           (m.get(a + 2, 0) << 8) | m.get(a + 3, 0)


def model(ram, cmd):
    """Line-for-line mirror of setImmoCANTXData_369B8()."""
    m = dict(ram)
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
        # else: buf[1..4] untouched
    elif cmd == 0x07:
        v = rd32(m, KEYGEN)
        m[BUF + 1] = (v >> 24) & 0xFF
        m[BUF + 2] = (v >> 16) & 0xFF
        m[BUF + 3] = (v >> 8) & 0xFF
        m[BUF + 4] = v & 0xFF
    elif cmd in (0x01, 0x81):
        m[BUF + 1] = m.get(RESP, 0)
        m[BUF + 2] = m[BUF + 3] = m[BUF + 4] = 0
    elif cmd in (0xC6, 0xC8):
        m[BUF + 1] = m[BUF + 2] = m[BUF + 3] = m[BUF + 4] = 0
    # default: buf[1..4] untouched
    m[BUF + 5] = m[BUF + 6] = m[BUF + 7] = 0
    m[TX_REQ] = 1
    m[TX_STATUS] = 0
    m[TX_STATE] = 0
    m[TX_PENDING] = 1
    return m


def seed_word(m, addr, rng):
    for i in range(4):
        m[addr + i] = rng.randint(0, 255)


def gen_state(rng):
    """Random seeded RAM: every address the function reads or writes."""
    m = {}
    for a in (SLOT0, SLOT1, SLOT2, SLOT3, KEYGEN):
        seed_word(m, a, rng)
    # bias sel toward the interesting values so every branch is hammered
    m[WAIT_STATE] = rng.choice([1, 2, 3, 4, 0xFF, rng.randint(0, 255)])
    m[RESP] = rng.randint(0, 255)
    for a in (BUF, BUF + 1, BUF + 2, BUF + 3, BUF + 4, BUF + 5, BUF + 6, BUF + 7):
        m[a] = rng.randint(0, 255)          # junk -> must be overwritten
    m[TX_REQ] = rng.randint(0, 1)
    m[TX_STATUS] = rng.randint(0, 1)
    m[TX_STATE] = rng.randint(0, 1)
    m[TX_PENDING] = rng.randint(0, 1)
    return m


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    seeds = (0x369B8, 0xC238, 0xC290, 0xC24C, 0xC278)
    total_fails = 0

    # Deterministic sweep: every interesting cmd with every interesting sel.
    for cmd in (0x00, 0x01, 0x07, 0x09, 0x0A, 0x80, 0x81, 0xC6, 0xC8, 0xFF):
        for sel in (0x00, 0x01, 0x02, 0x03, 0x04, 0xFF):
            m = {}
            for a in (SLOT0, SLOT1, SLOT2, SLOT3, KEYGEN):
                seed_word(m, a, random.Random((cmd << 16) | (sel << 8) | a))
            m[WAIT_STATE] = sel
            m[RESP] = 0x5A
            for a in range(BUF, BUF + 8):
                m[a] = 0xAA
            m[TX_REQ] = m[TX_STATUS] = m[TX_STATE] = m[TX_PENDING] = 0
            want = model(m, cmd)
            cpu.call(ADDR, r4=cmd, ram=dict(m))
            bad = []
            allk = set(want) | set(cpu.ram.keys())
            for k in allk:
                if 0xFFFFDE00 <= k <= 0xFFFFDF00:
                    continue
                if cpu.ram.get(k, 0) != want.get(k, 0):
                    bad.append((k, cpu.ram.get(k, 0), want.get(k, 0)))
            if bad:
                print('SWEEP FAIL cmd=0x%02X sel=0x%02X: %s' %
                      (cmd, sel, {hex(k): (hex(g), hex(e)) for k, g, e in bad[:12]}))
                total_fails += 1
                if total_fails >= 5:
                    sys.exit(1)

    for seed in seeds:
        rng = random.Random(seed)
        fails = 0
        for it in range(N):
            cmd = rng.randint(0, 255)
            ram = gen_state(rng)
            want = model(ram, cmd)
            try:
                cpu.call(ADDR, r4=cmd, ram=dict(ram))
            except Exception as e:
                print('EMULATOR EXC seed=0x%X iter=%d: %s' % (seed, it, e))
                fails += 1
                break
            bad = []
            allk = set(want) | set(cpu.ram.keys())
            for k in allk:
                if 0xFFFFDE00 <= k <= 0xFFFFDF00:   # task stack area
                    continue
                if cpu.ram.get(k, 0) != want.get(k, 0):
                    bad.append((k, cpu.ram.get(k, 0), want.get(k, 0)))
            if bad:
                print('MISMATCH seed=0x%X iter=%d: %s' %
                      (seed, it, {hex(k): (hex(g), hex(e)) for k, g, e in bad[:12]}))
                print('  cmd=0x%02X sel=%d resp=%d buf=%s' %
                      (cmd, ram.get(WAIT_STATE, 0), ram.get(RESP, 0),
                       [ram.get(BUF + i) for i in range(8)]))
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
    print('OK  0x369B8 setImmoCANTXData  (%d random + %d sweep inputs)'
          % (N * len(seeds), 10 * 6))
    print('\nAll setImmoCANTXData_369B8 tests passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()
