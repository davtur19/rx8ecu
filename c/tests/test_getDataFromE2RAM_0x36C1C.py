#!/usr/bin/env python3
"""test_getDataFromE2RAM_0x36C1C.py

Differential test for ROM 0x36C1C (60E1D400.bin) — lift c/getDataFromE2RAM.c.

The function populates the working-copy variables from the EEPROM shadow by
calling getFromE2_E2ADDR_RAMADDR_LEN (0x39170) once per EEPROM region
(19 calls, fixed (index, ramaddr, len) — verified from the disassembly and the
literal pool).

Like test_eeprom_commit_dispatcher_37000.py, the callee 0x39170 is executed in
a SECOND emulator instance (cpu2) so its full RAM effect comes from the real
ROM bytes — the same bytes the main emulator executes — keeping the comparison
exact without transcribing 0x39170 by hand (it is covered independently by
test_getFromE2.py).

Callee stubs (same set as test_getFromE2.py): getSR/setSR (0x3920/0x3934) ->
rts;nop; SPI retry 0xC0A8 -> return 0; flash reader 0xBFCA -> return 0.

Run: python3 c/tests/test_getDataFromE2RAM_0x36C1C.py [N]
"""
import os, random, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ADDR = 0x36C1C
GETFROME2 = 0x39170
E2_PRI = 0xFFFFC2FE
E2_COM = 0xFFFFC3FE

# (eeprom_index, dest_addr, len) — from the lift, verified vs disasm literal pool
PAIRS = [
    (0x00, 0xFFFFC2D8, 1), (0x02, 0xFFFFC2DC, 4), (0x06, 0xFFFFC2E0, 4),
    (0x0A, 0xFFFFC2E4, 1), (0x0C, 0xFFFFC2E5, 1), (0x0D, 0xFFFFC2E6, 1),
    (0x0E, 0xFFFFC243, 1), (0x0F, 0xFFFFC2E7, 1), (0x10, 0xFFFFC242, 1),
    (0x16, 0xFFFFC2EA, 2), (0x18, 0xFFFFC2EC, 2), (0x12, 0xFFFFC244, 1),
    (0x13, 0xFFFFC2E8, 1), (0x14, 0xFFFFC2E9, 1), (0x1A, 0xFFFFC2EE, 1),
    (0x1B, 0xFFFFC2EF, 1), (0x1C, 0xFFFFC2F0, 1), (0x1D, 0xFFFFC2F1, 1),
    (0x1E, 0xFFFFC2F2, 1),
]


def stub():
    s = {}
    for a in (0x3920, 0x3934):
        s[a] = 0x00; s[a + 1] = 0x0B; s[a + 2] = 0x00; s[a + 3] = 0x09  # rts;nop
    for a in (0xC0A8, 0xBFCA):                     # return 0
        s[a] = 0xE0; s[a + 1] = 0x00
        s[a + 2] = 0x00; s[a + 3] = 0x0B
        s[a + 4] = 0x00; s[a + 5] = 0x09
    return s


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    cpu2 = SH2(rom)
    rng = random.Random(0x36C1C)
    fails = 0

    for it in range(N):
        # random EEPROM shadow (data + complement); mostly valid, some corrupt
        ram = {**stub()}
        for off in range(0x00, 0x40):
            if rng.random() < 0.7:
                d = rng.randint(0, 255)
                ram[E2_PRI + off] = d
                ram[E2_COM + off] = (~d) & 0xFF
            else:
                ram[E2_PRI + off] = rng.randint(0, 255)
                ram[E2_COM + off] = rng.randint(0, 255)

        # model: replay the 19 getFromE2 calls on cpu2 (real ROM bytes)
        m = dict(ram)
        for (idx, dst, ln) in PAIRS:
            cpu2.call(GETFROME2, r4=idx, r5=dst, r6=ln, ram=dict(m))
            m = dict(cpu2.ram)

        input_keys = set(ram.keys())
        cpu.call(ADDR, ram=dict(ram))
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
            def fmt(tup):
                k, g, e = tup
                if isinstance(e, str):
                    return (hex(k), hex(g), e)
                return (hex(k), hex(g), hex(e))
            print('MISMATCH iter=%d: %s' % (it, {fmt(b)[0]: (fmt(b)[1], fmt(b)[2]) for b in bad[:10]}))
            fails += 1
            if fails >= 3:
                break

    if fails:
        print('%d FAILURE(S) getDataFromE2RAM' % fails)
        sys.exit(1)
    print('OK  0x36C1C getDataFromE2RAM  (%d inputs)' % N)
    sys.exit(0)


if __name__ == '__main__':
    main()