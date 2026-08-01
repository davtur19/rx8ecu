#!/usr/bin/env python3
"""
Test the EVAP purge subsystem (0xF534, 0xF5B4, 0xF5DC, 0xF544) via SH-2E emulator.

Functions under test (60E1D400.bin):
  purge_flow_counter_init    @0xF534  - zero the 3-byte purge cell
  purge_flow_decrement       @0xF5B4  - countdown + arm latch
  purge_state_query          @0xF5DC  - return RAM[0xFFFFA4B1]
  purge_control_state_update @0xF544  - select purge target from demand
"""
import os, sys, struct, random
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'tools'))
from sh2emu import SH2

ROM = os.path.join(os.path.dirname(__file__), '..', '..', 'roms', 'stock', '60E1D400.bin')

# RAM cell addresses (as used by the ROM instructions).
# NOTE: the firmware stores RAM addresses as 16-bit literals loaded with
# mov.w @(disp,pc), which SIGN-EXTENDS: literal 0xA4B0 -> 0xFFFFA4B0.
ADDR_FLOW      = 0xFFFFA4B0
ADDR_STATE     = 0xFFFFA4B1
ADDR_DEC_EN    = 0xFFFFA4B2
ADDR_DEMAND    = 0xFFFFA4B3
ADDR_FLOW_DEMAND = 0xFFFF9F94
ADDR_ALT_TRIG  = 0xFFFFCE6E
ADDR_TRIG      = 0xFFFFBED0      # read by the 0x104C8 leaf (0xBED0 sign-ext)

ROM_THR_LOW  = 4
ROM_THR_HIGH = 10
ROM_OUT_LOW  = 1
ROM_OUT_MID  = 0
ROM_OUT_HIGH = 0
ROM_OUT_ALT  = 0

def build_ram(t):
    ram = {}
    ram[ADDR_FLOW]      = t['flow'] & 0xFF
    ram[ADDR_STATE]     = t['state'] & 0xFF
    ram[ADDR_DEC_EN]    = t['dec_en'] & 0xFF
    ram[ADDR_DEMAND]    = t['demand'] & 0xFF
    ram[ADDR_FLOW_DEMAND] = t['flow_demand'] & 0xFF
    ram[ADDR_ALT_TRIG]  = t['alt_trig'] & 0xFF
    ram[ADDR_TRIG]      = t['trigger'] & 0xFF
    return ram

def test_counter_init(cpu):
    ram = {ADDR_FLOW: 0x77, ADDR_STATE: 0x55, ADDR_DEC_EN: 0xAA}
    cpu.call(0xF534, ram=dict(ram))
    ok = (cpu.rd(ADDR_FLOW, 1) == 0 and cpu.rd(ADDR_STATE, 1) == 0
          and cpu.rd(ADDR_DEC_EN, 1) == 0)
    print(f"  purge_flow_counter_init: {'OK' if ok else 'FAIL'}")
    return ok

def test_state_query(cpu):
    ok = True
    for v in range(256):
        ram = {ADDR_STATE: v}
        r = cpu.call(0xF5DC, ram=dict(ram)) & 0xFF
        if r != v:
            ok = False
            print(f"  purge_state_query FAIL v={v} got={r}")
            break
    print(f"  purge_state_query (exhaustive 0..255): {'OK' if ok else 'FAIL'}")
    return ok

def ref_decrement(t):
    flow, dec_en = t['flow'], t['dec_en']
    if dec_en == 1:
        if flow > 0:
            flow -= 1
    else:
        dec_en = 1
    return flow, dec_en

def test_decrement(cpu):
    random.seed(20260731)
    fails = tests = 0
    for _ in range(5000):
        t = dict(flow=random.randint(0, 255), dec_en=random.randint(0, 1),
                 state=0, demand=0, flow_demand=0, alt_trig=0, trigger=0)
        # reset cells
        cpu.call(0xF534, ram=build_ram(t))
        cpu.call(0xF5B4, ram=build_ram(t))
        got_flow = cpu.rd(ADDR_FLOW, 1)
        got_dec  = cpu.rd(ADDR_DEC_EN, 1)
        exp_flow, exp_dec = ref_decrement(t)
        tests += 1
        if got_flow != exp_flow or got_dec != exp_dec:
            print(f"  purge_flow_decrement FAIL t={t} got=({got_flow},{got_dec}) exp=({exp_flow},{exp_dec})")
            fails += 1
            if fails >= 5: break
    # edges
    for flow in (0, 1, 255):
        for dec_en in (0, 1):
            t = dict(flow=flow, dec_en=dec_en, state=0, demand=0,
                     flow_demand=0, alt_trig=0, trigger=0)
            cpu.call(0xF5B4, ram=build_ram(t))
            got_flow = cpu.rd(ADDR_FLOW, 1); got_dec = cpu.rd(ADDR_DEC_EN, 1)
            exp_flow, exp_dec = ref_decrement(t)
            tests += 1
            if (got_flow, got_dec) != (exp_flow, exp_dec):
                print(f"  purge_flow_decrement edge FAIL t={t} got=({got_flow},{got_dec}) exp=({exp_flow},{exp_dec})")
                fails += 1
    print(f"  purge_flow_decrement: {tests} tests, {fails} failures")
    return fails == 0

def ref_state_update(t):
    v = t['trigger'] & 0xFF
    # latch demand byte
    t = dict(t)
    demand = t['flow_demand'] & 0xFF
    if v == 1:
        if demand <= ROM_THR_LOW:
            out = ROM_OUT_LOW
        elif demand <= ROM_THR_HIGH:
            out = ROM_OUT_MID
        else:
            out = ROM_OUT_HIGH
    else:
        out = ROM_OUT_ALT if (t['alt_trig'] & 0xFF) == 1 else 0
    return out

def test_state_update(cpu):
    random.seed(99)
    fails = tests = 0
    for _ in range(10000):
        t = dict(flow=random.randint(0, 255), state=random.randint(0, 255),
                 dec_en=random.randint(0, 1), demand=random.randint(0, 255),
                 flow_demand=random.randint(0, 255),
                 alt_trig=random.randint(0, 1), trigger=random.randint(0, 2))
        cpu.call(0xF544, ram=build_ram(t))
        got_state = cpu.rd(ADDR_STATE, 1)
        got_flow  = cpu.rd(ADDR_FLOW, 1)
        exp = ref_state_update(t)
        tests += 1
        if got_state != exp or got_flow != exp:
            print(f"  purge_control_state_update FAIL t={t} got=({got_state},{got_flow}) exp={exp}")
            fails += 1
            if fails >= 5: break
    # exhaustive demand/trigger combos with fixed cells
    for trig in (0, 1, 2):
        for fd in range(16):
            t = dict(flow=0x55, state=0x55, dec_en=1, demand=0x11,
                     flow_demand=fd, alt_trig=0, trigger=trig)
            cpu.call(0xF544, ram=build_ram(t))
            got = cpu.rd(ADDR_STATE, 1)
            exp = ref_state_update(t)
            tests += 1
            if got != exp:
                print(f"  purge_control_state_update combo FAIL trig={trig} fd={fd} got={got} exp={exp}")
                fails += 1
    print(f"  purge_control_state_update: {tests} tests, {fails} failures")
    return fails == 0

def main():
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    ok = True
    ok &= test_counter_init(cpu)
    ok &= test_state_query(cpu)
    ok &= test_decrement(cpu)
    ok &= test_state_update(cpu)
    print("PURGE SUBSYSTEM:", "PASS" if ok else "FAIL")
    return 0 if ok else 1

if __name__ == '__main__':
    sys.exit(main())
