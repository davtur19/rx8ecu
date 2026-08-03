#!/usr/bin/env python3
"""test_coil_correction_write_0x50A54.py

Differential test for ROM 0x50A54 (60E1D400.bin) — lift
c/coil_correction_write_0x50A54.c.

Runs the ACTUAL ROM bytes of 0x50A54 in tools/sh2emu.py over seeded RAM states
and compares the full post-call RAM overlay plus r0 against a Python reference
model.

The three side-effecting callees are NOT inlined: they are reproduced by
executing the real ROM bytes in a second emulator instance (cpu2.call), so
their float rounding, checksum validation and task-check/dispatch side effects
match the machine exactly:
   - 0x3EE0A timing_correction_3EE0A(r4=0xFFFF86A4, fr4=0.0) -> fr0
   - 0x20C4  fpu_curve_index_0x20C4(r4=0x6BAE8, fr4=timing)  -> r0 (u16 idx)
   - 0x3EEB8 cold_start_enrichment_3EEB8(r4=0xFFFF86AC, fr4=delta)

Model flow (from the disassembly, verified):
   1. cfe = u16 @0xFFFFCFE6
   2. timing = 0x3EE0A();  D0B4 = idx = 0x20C4(timing)   (always written)
   3. if u8 @0xFFFFD201 == 1:  0x3EEB8(0.0); return
   4. elif u8 @0xFFFFD07C == 1 and cfe <= D0B4:  delta = f32@D01C - f32@D024;
        0x3EEB8(delta); return
   5. elif (u8)u16@CFC1 > ROM8@0x7D959 and cfe > u16@CFE4 and (u8)@D034 == 0:
        delta = f32@D01C - f32@D024;  0x3EEB8(delta); return
   6. else: no write

Run: python3 c/tests/test_coil_correction_write_0x50A54.py [N]
"""
import os, random, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2, ts, f2bits

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ADDR = 0x50A54
T_CORR = 0x3EE0A
CURVE = 0x20C4
COLD = 0x3EEB8
ROM_7D959 = 0x7D959

A_CFE6 = 0xFFFFCFE6
A_D201 = 0xFFFFD201
A_D07C = 0xFFFFD07C
A_D0B4 = 0xFFFFD0B4
A_CFC1 = 0xFFFFCFC1
A_CFE4 = 0xFFFFCFE4
A_D034 = 0xFFFFD034
A_D01C = 0xFFFFD01C
A_D024 = 0xFFFFD024
A_T86A4 = 0xFFFF86A4
A_86AC = 0xFFFF86AC
A_C6AC = 0xFFFFC6AC


def u16(ram, a):
    return (ram.get(a, 0) << 8) | ram.get(a + 1, 0)


def f32(ram, a):
    return struct.unpack('>f', bytes(ram.get(a + i, 0) for i in range(4)))[0]


def gen_state(rng):
    ram = {}
    # shared counter + enable flags
    ram[A_CFE6] = rng.randint(0, 255); ram[A_CFE6 + 1] = rng.randint(0, 255)
    ram[A_D201] = rng.randint(0, 1)
    ram[A_D07C] = rng.randint(0, 1)
    ram[A_D034] = rng.randint(0, 255)
    ram[A_CFC1] = rng.randint(0, 255)
    ram[A_CFE4] = rng.randint(0, 255); ram[A_CFE4 + 1] = rng.randint(0, 255)
    # timing struct @0xFFFF86A4: 4 x u16 checksum words + f32 value
    val = ts(rng.uniform(-1e3, 1e3))
    hi = (f2bits(val) >> 16) & 0xFFFF; lo = f2bits(val) & 0xFFFF
    ck = (~((hi + lo) & 0xFFFF)) & 0xFFFF
    mode = rng.random()
    if mode < 0.5:
        c1 = ck; c2 = rng.randint(0, 0xFFFF)
    elif mode < 0.75:
        c1 = rng.randint(0, 0xFFFF); c2 = ck
    else:
        c1 = rng.randint(0, 0xFFFF); c2 = rng.randint(0, 0xFFFF)
        if c1 == ck: c1 = (c1 + 1) & 0xFFFF
        if c2 == ck: c2 = (c2 + 1) & 0xFFFF
    for i in range(4):
        ram[A_T86A4 + i] = (val_bits(hi, lo) >> (8 * (3 - i))) & 0xFF
    ram[A_T86A4 + 0] = (hi >> 8) & 0xFF; ram[A_T86A4 + 1] = hi & 0xFF
    ram[A_T86A4 + 2] = (lo >> 8) & 0xFF; ram[A_T86A4 + 3] = lo & 0xFF
    ram[A_T86A4 + 4] = (c1 >> 8) & 0xFF; ram[A_T86A4 + 5] = c1 & 0xFF
    ram[A_T86A4 + 6] = (c2 >> 8) & 0xFF; ram[A_T86A4 + 7] = c2 & 0xFF
    # correction floats D01C / D024
    for a in (A_D01C, A_D024):
        fb = struct.pack('>f', ts(rng.uniform(-1e3, 1e3)))
        for i in range(4):
            ram[a + i] = fb[i]
    return ram


def val_bits(hi, lo):
    return (hi << 16) | lo


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    cpu2 = SH2(rom)
    rng = random.Random(0x50A54)
    fails = 0
    gate = rom[ROM_7D959]

    for it in range(N):
        ram = gen_state(rng)
        input_keys = set(ram.keys())

        # ---- model: replay the callees on cpu2 ----
        m = dict(ram)
        timing = cpu2.call(T_CORR, r4=A_T86A4, fr={4: 0.0}, ram=dict(m))
        timing = cpu2.fr[0]
        m = dict(cpu2.ram)
        idx = cpu2.call(CURVE, r4=0x6BAE8, fr={4: timing}, ram=dict(m))
        m = dict(cpu2.ram)
        idx = idx & 0xFFFF
        m[A_D0B4] = (idx >> 8) & 0xFF
        m[A_D0B4 + 1] = idx & 0xFF

        cfe = u16(m, A_CFE6)
        written = False
        if m.get(A_D201, 0) == 1:
            cpu2.call(COLD, r4=A_86AC, fr={4: 0.0}, ram=dict(m))
            m = dict(cpu2.ram); written = True
        elif m.get(A_D07C, 0) == 1 and not (cfe > idx):
            delta = ts(f32(m, A_D01C) - f32(m, A_D024))
            cpu2.call(COLD, r4=A_86AC, fr={4: delta}, ram=dict(m))
            m = dict(cpu2.ram); written = True
        else:
            # gate: (u8)u16@CFC1 (single byte) > ROM8@0x7D959 ...
            if m.get(A_CFC1, 0) > gate and \
               cfe > u16(m, A_CFE4) and (m.get(A_D034, 0) & 0xFF) == 0:
                delta = ts(f32(m, A_D01C) - f32(m, A_D024))
                cpu2.call(COLD, r4=A_86AC, fr={4: delta}, ram=dict(m))
                m = dict(cpu2.ram); written = True

        # ---- run the ROM function ----
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
            print('MISMATCH iter=%d cfe=%d D201=%d D07C=%d written=%d: %s' %
                  (it, cfe, m.get(A_D201, 0), m.get(A_D07C, 0), written,
                   {hex(b[0]): (hex(b[1]), b[2] if isinstance(b[2], str) else hex(b[2])) for b in bad[:10]}))
            fails += 1
            if fails >= 3:
                break

    if fails:
        print('%d FAILURE(S) coil_correction_write_0x50A54' % fails)
        sys.exit(1)
    print('OK  0x50A54 coil_correction_write_0x50A54  (%d inputs)' % N)
    sys.exit(0)


if __name__ == '__main__':
    main()