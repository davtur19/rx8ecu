#!/usr/bin/env python3
"""
Test leaf hardware-port helpers 0x3EE58 / 0x3EE68 / 0x3920 via SH-2E emulator.

0x3EE58 (write_port_u16_inv): stores ((r5 & 0xFF) << 8) | ((~r5) & 0xFF) as a
  big-endian u16 at [r4]; returns 0.  (active-high/low complementary encoding
  used for the 0xFFFF8078/807A/807C waveform output ports).

0x3EE68 (write_port_u32_inv): same idea, 32-bit:
  ((r5 & 0xFFFF) << 16) | ((~r5) & 0xFFFF) at [r4]; returns 0.

0x3920 (read_sr_interrupt_mask): r5 = 0x00F0 (literal @0x392E);
  r0 = sr & 0x00F0; T = (r4 > r0) unsigned; both paths return r0, so it
  always returns (sr & 0xF0) = 0xF0 in the emulator (sr = 0x000000F0).
  NOTE: the rts delay slot at 0x392C is 0x440E = MOV.W R0,@(0xE,R4) — an
  emulator gap (not implemented), so no memory write occurs in tests.
"""
import os, sys, struct, random
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'tools'))
from sh2emu import SH2

ROM = os.path.join(os.path.dirname(__file__), '..', '..', 'roms', 'stock', '60E1D400.bin')

def rb(ram, a):
    return ram.get(a & 0xFFFFFFFF, 0)

def ref_3EE58(ram_in, r4, r5):
    ram = dict(ram_in)
    v = (((r5 & 0xFF) << 8) | ((~r5) & 0xFF)) & 0xFFFF
    ram[r4 & 0xFFFFFFFF] = (v >> 8) & 0xFF
    ram[(r4 + 1) & 0xFFFFFFFF] = v & 0xFF
    return 0, ram

def ref_3EE68(ram_in, r4, r5):
    ram = dict(ram_in)
    v = (((r5 & 0xFFFF) << 16) | ((~r5) & 0xFFFF)) & 0xFFFFFFFF
    for i in range(4):
        ram[(r4 + i) & 0xFFFFFFFF] = (v >> (8 * (3 - i))) & 0xFF
    return 0, ram

def ref_3920(ram_in, r4, r5):
    return (0xF0, dict(ram_in))     # r0 = sr & 0xF0 = 0xF0 constant; no writes

def main():
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    random.seed(20260731)
    fails = tests = 0

    # --- 0x3EE58 ---
    for _ in range(3000):
        init = {}
        port = 0xFFFF8078
        r5 = random.randrange(0, 0x100)
        got = cpu.call(0x3EE58, r4=port, r5=r5, ram=dict(init))
        ref_ret, ref_ram = ref_3EE58(init, port, r5)
        bad = []
        if (got & 0xFF) != (ref_ret & 0xFF):
            bad.append('ret emu=%d ref=%d' % (got & 0xFF, ref_ret & 0xFF))
        for a in range(port, port + 2):
            if rb(cpu.ram, a) != rb(ref_ram, a):
                bad.append('%s emu=%02x ref=%02x' % (hex(a), rb(cpu.ram, a), rb(ref_ram, a)))
        if bad:
            fails += 1
            print('0x3EE58 FAIL r5=%d:' % r5, bad[:4])
            if fails >= 5: break
        tests += 1

    # --- 0x3EE68 ---
    for _ in range(3000):
        init = {}
        port = 0xFFFF8078
        r5 = random.randrange(0, 0x10000)
        got = cpu.call(0x3EE68, r4=port, r5=r5, ram=dict(init))
        ref_ret, ref_ram = ref_3EE68(init, port, r5)
        bad = []
        if (got & 0xFF) != (ref_ret & 0xFF):
            bad.append('ret emu=%d ref=%d' % (got & 0xFF, ref_ret & 0xFF))
        for a in range(port, port + 4):
            if rb(cpu.ram, a) != rb(ref_ram, a):
                bad.append('%s emu=%02x ref=%02x' % (hex(a), rb(cpu.ram, a), rb(ref_ram, a)))
        if bad:
            fails += 1
            print('0x3EE68 FAIL r5=%d:' % r5, bad[:4])
            if fails >= 5: break
        tests += 1

    # --- 0x3920 ---
    for _ in range(3000):
        init = {}
        r4 = random.choice([0, 1, 0xF0, 0xFF, 0x100, 0x1000, 0xF0000000])
        got = cpu.call(0x3920, r4=r4, ram=dict(init))
        ref_ret, _ = ref_3920(init, r4, 0)
        if (got & 0xFF) != ref_ret:
            fails += 1
            print('0x3920 FAIL r4=%d: emu=%d ref=%d' % (r4, got & 0xFF, ref_ret))
            if fails >= 5: break
        tests += 1

    print(f"port helpers 0x3EE58/0x3EE68/0x3920: {tests} tests, {fails} failures")
    print("PORT_HELPERS:", "PASS" if fails == 0 else "FAIL")
    return 0 if fails == 0 else 1

if __name__ == '__main__':
    sys.exit(main())
