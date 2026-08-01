#!/usr/bin/env python3
"""
Test calc_fan1_control (0x303A6) via SH-2E emulator.

Function under test (60E1D400.bin):
  calc_fan1_control @0x303A6 (288 bytes) - cooling fan thermostat with
  hysteresis (on >= 97, off < 94) driving RAM[0xFFFFBE16]/[0xFFFFBE17],
  plus a fan-enable latch RAM[0xFFFFBE0D] computed from a branch tree
  over 14 status bytes.

Reference model mirrors the firmware CFG at 0x30416..0x304C0 exactly.
"""
import os, sys, struct, random
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'tools'))
from sh2emu import SH2

ROM = os.path.join(os.path.dirname(__file__), '..', '..', 'roms', 'stock', '60E1D400.bin')
ADDR = 0x303A6

ADDR_TEMP = 0xFFFFAA10   # f32 temperature input
BE16 = 0xFFFFBE16        # fan 1 relay command
BE17 = 0xFFFFBE17        # fan 2 relay command
BE0D = 0xFFFFBE0D        # fan enable latch

STATUS_CELLS = [0xFFFFB13D, 0xFFFFAAE0, 0xFFFFBE0C, 0xFFFFCD06, 0xFFFFA96A,
                0xFFFFBFF5, 0xFFFFBDD4, 0xFFFFBDD6, 0xFFFFD07C, 0xFFFFD0E4,
                0xFFFFD2A0, 0xFFFFD2A5, 0xFFFFD29F]

def ref(t, ram):
    """Reference model: returns (be16, be17, be0d)."""
    def g(a):
        return ram.get(a, 0)
    be16 = g(BE16); be17 = g(BE17); be0d = g(BE0D)
    # hysteresis (both fans, same band: on >= 97.0, off < 94.0)
    if t >= 97.0: be16 = 1
    elif t < 94.0: be16 = 0
    if t >= 97.0: be17 = 1
    elif t < 94.0: be17 = 0
    # fan-enable latch: mirror of CFG 0x30416..0x304C0
    loc = 'start'
    while True:
        if loc == 'start':
            if be16 == 1 or (be17 == 1 and g(0xFFFFB13D) == 1) or \
               (g(0xFFFFAAE0) == 0 and g(0xFFFFBE0C) == 1 and g(0xFFFFCD06) == 0 and
                g(0xFFFFA96A) == 0 and g(0xFFFFBFF5) == 0):
                loc = 'B86'
            else:
                loc = 'B6E'
        elif loc == 'B6E':
            if g(0xFFFFBDD4) == 1: loc = 'B86'
            elif g(0xFFFFBDD6) != 1: loc = 'B9A'
            else: loc = 'B86'
        elif loc == 'B86':
            if g(0xFFFFD07C) != 0: loc = 'B9A'
            elif g(0xFFFFD0E4) == 0: loc = 'BB2'
            else: loc = 'B9A'
        elif loc == 'B9A':
            if g(0xFFFFD2A0) == 1 or g(0xFFFFD2A5) == 1: loc = 'BB2'
            else: loc = 'BC0'
        elif loc == 'BB2':
            if g(0xFFFFD29F) != 0: loc = 'BC0'
            else: loc = 'BC2'
        elif loc == 'BC0':
            be0d = 0
            break
        elif loc == 'BC2':
            be0d = 1
            break
    return be16, be17, be0d

def run_one(cpu, t, init):
    ram = dict(init)
    b = struct.pack('>f', t)
    for i, v in enumerate(b):
        ram[ADDR_TEMP + i] = v
    cpu.call(ADDR, ram=ram)
    # NOTE: call() copies the dict; read results from cpu.ram
    return (cpu.ram[BE16], cpu.ram[BE17], cpu.ram[BE0D])

def main():
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    random.seed(20260731)
    temps = ([0.0, -40.0, 20.0, 93.999, 94.0, 96.999, 97.0, 97.001, 120.0, 100.0] +
             [random.uniform(-50, 150) for _ in range(300)])
    fails = tests = 0
    for t in temps:
        for _ in range(40):
            init = {}
            for c in STATUS_CELLS:
                init[c] = random.randrange(0, 2)
            init[BE16] = random.randrange(0, 2)
            init[BE17] = random.randrange(0, 2)
            init[BE0D] = random.randrange(0, 2)
            out = run_one(cpu, t, init)
            exp = ref(t, init)
            tests += 1
            if out != exp:
                fails += 1
                print(f"  calc_fan1_control FAIL t={t} emu={out} ref={exp} init={init}")
                if fails >= 5:
                    break
        if fails >= 5:
            break
    print(f"calc_fan1_control: {tests} tests, {fails} failures")
    print("CALC_FAN1_CONTROL:", "PASS" if fails == 0 else "FAIL")
    return 0 if fails == 0 else 1

if __name__ == '__main__':
    sys.exit(main())
