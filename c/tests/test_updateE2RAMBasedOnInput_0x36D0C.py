#!/usr/bin/env python3
"""test_updateE2RAMBasedOnInput_0x36D0C.py

Differential test for ROM 0x36D0C (60E1D400.bin) — lift c/updateE2RAMBasedOnInput.c.

Dispatches EEPROM shadow updates based on an 8-bit input code (r4).  Each code
maps to one or more writeToE2RAMArea(index, src, len) calls (0x39124) that
persist the current working-copy values into the E2 shadow (value + complement).

Model: for every code, the writeToE2RAMArea calls are replayed in a SECOND
emulator instance (cpu2, real ROM bytes at 0x39124), so the exact shadow bytes
come from the machine.  The dispatch table below is taken from the verified
lift (branch targets + literal pool).  Codes with no case do nothing.

Callee stubs: getSR/setSR (0x3920/0x3934) -> rts;nop.

Run: python3 c/tests/test_updateE2RAMBasedOnInput_0x36D0C.py [N]
"""
import os, random, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ADDR = 0x36D0C
WRITE = 0x39124

W0   = 0xFFFFC2D8   # work_00
W2   = 0xFFFFC2DC   # work_02 (8-byte pairing area)
W6   = 0xFFFFC2E0   # work_06
W10  = 0xFFFFC2E4   # work_0A
W12  = 0xFFFFC2E5   # work_0C
W13  = 0xFFFFC2E6   # work_0D
W15  = 0xFFFFC2E7   # work_0F
W19  = 0xFFFFC2E8   # work_13
W20  = 0xFFFFC2E9   # work_14
W22  = 0xFFFFC2EA   # work_16 (2B)
W24  = 0xFFFFC2EC   # work_18 (2B)
W26  = 0xFFFFC2EE   # work_1A
W27  = 0xFFFFC2EF   # work_1B
W28  = 0xFFFFC2F0   # work_1C
W29  = 0xFFFFC2F1   # work_1D
W30  = 0xFFFFC2F2   # work_1E
CB1  = 0xFFFFC243   # CAN shadow 0x0E
CB0  = 0xFFFFC242   # CAN shadow 0x10
CB2  = 0xFFFFC244   # CAN shadow 0x12

# code -> list of (index, src_addr, len)
TABLE = {
    0x01: [(0x0A, W10, 1)],
    0x02: [(0x02, W2, 8)],
    0x03: [(0x00, W0, 1)],
    0x04: [(0x0C, W12, 1), (0x0E, CB1, 1), (0x10, CB0, 1)],
    0x05: [(0x12, CB2, 1), (0x13, W19, 1)],
    0x06: [(0x0E, CB1, 1)],
    0x07: [(0x16, W22, 2), (0x18, W24, 2)],
    0x08: [(0x14, W20, 1)],
    0x09: [(0x0C, W12, 1), (0x0E, CB1, 1), (0x10, CB0, 1),
           (0x12, CB2, 1), (0x13, W19, 1)],
    0x0A: [(0x1A, W26, 1), (0x1B, W27, 1), (0x1C, W28, 1), (0x1D, W29, 1)],
    0x0B: [(0x02, W2, 8), (0x0A, W10, 1)],   # verified: 0x36ED4 jsr then falls
                                            # through to 0x36ED8 (second write)
    0x0C: [(0x0C, W12, 1), (0x0D, W13, 1), (0x0E, CB1, 1), (0x0F, W15, 1),
           (0x10, CB0, 1), (0x14, W20, 1), (0x12, CB2, 1), (0x13, W19, 1),
           (0x1A, W26, 1), (0x1B, W27, 1), (0x1C, W28, 1), (0x1D, W29, 1),
           (0x1E, W30, 1)],
    0x0D: [(0x1E, W30, 1)],
    0x0E: [(0x0D, W13, 1)],
    0x0F: [(0x0F, W15, 1)],
    0xFF: [(0x00, W0, 1), (0x02, W2, 8), (0x0A, W10, 1), (0x0C, W12, 1),
           (0x0D, W13, 1), (0x0E, CB1, 1), (0x0F, W15, 1), (0x10, CB0, 1),
           (0x12, CB2, 1), (0x13, W19, 1), (0x16, W22, 2), (0x18, W24, 2),
           (0x14, W20, 1), (0x1A, W26, 1), (0x1B, W27, 1), (0x1C, W28, 1),
           (0x1D, W29, 1), (0x1E, W30, 1)],
}

# addresses the function may READ as write sources (work copies + CAN shadow)
SRC_ADDRS = [W0, W2, W6, W10, W12, W13, W15, W19, W20, W22, W24,
             W26, W27, W28, W29, W30, CB0, CB1, CB2]
E2_PRI = 0xFFFFC2FE
E2_COM = 0xFFFFC3FE


def stub():
    s = {}
    for a in (0x3920, 0x3934):
        s[a] = 0x00; s[a + 1] = 0x0B; s[a + 2] = 0x00; s[a + 3] = 0x09
    return s


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    cpu2 = SH2(rom)
    rng = random.Random(0x36D0C)
    fails = 0

    for it in range(N):
        code = rng.randint(0, 255)
        ram = {**stub()}
        # randomize the source work copies (all bytes in the write-source window)
        for a in range(W0, W30 + 2):
            ram[a] = rng.randint(0, 255)
        for a in (CB0, CB1, CB2):
            ram[a] = rng.randint(0, 255)
        # random pre-existing shadow
        for off in range(0, 0x40):
            ram[E2_PRI + off] = rng.randint(0, 255)
            ram[E2_COM + off] = rng.randint(0, 255)

        # model: replay the dispatch table's writeToE2RAMArea calls on cpu2
        m = dict(ram)
        for (idx, src, ln) in TABLE.get(code, []):
            cpu2.call(WRITE, r4=idx, r5=src, r6=ln, ram=dict(m))
            m = dict(cpu2.ram)

        input_keys = set(ram.keys())
        cpu.call(ADDR, r4=code, ram=dict(ram))
        bad = []

        def stack(k):
            return 0xFFFFDE00 <= k <= 0xFFFFDF00

        for k, e in m.items():
            if stack(k):
                continue
            if cpu.ram.get(k, 0) != e:
                bad.append((k, cpu.ram.get(k, 0), e))
        for k in cpu.ram:
            if k in m or k in input_keys or stack(k):
                continue
            bad.append((k, cpu.ram.get(k, 0), '<none>'))
        if bad:
            print('MISMATCH iter=%d code=0x%02X: %s' %
                  (it, code, {hex(b[0]): (hex(b[1]), b[2] if isinstance(b[2], str) else hex(b[2])) for b in bad[:10]}))
            fails += 1
            if fails >= 3:
                break

    if fails:
        print('%d FAILURE(S) updateE2RAMBasedOnInput' % fails)
        sys.exit(1)
    print('OK  0x36D0C updateE2RAMBasedOnInput  (%d inputs)' % N)
    sys.exit(0)


if __name__ == '__main__':
    main()