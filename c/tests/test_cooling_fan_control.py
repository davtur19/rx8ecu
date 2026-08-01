#!/usr/bin/env python3
"""
Test cooling_fan_control (0x17DCC) via SH-2E emulator.

Function under test (60E1D400.bin):
  cooling_fan_control @0x17DCC (84 bytes) - "coolant sensor valid" check
  via complement_shift_u32 (0x2440); on the rising edge of the fan-enable
  state (RAM[0xFFFFA95C] == 0 and sensor valid) it increments the fan
  speed counter RAM[0xFFFFA93B] and the redundant 8-bit cell
  RAM[0xFFFF8076] (value + ~value, read/written through the verified
  0x3ED3C / 0x3EE58 accessors).  RAM[0xFFFFA95C] is then latched to the
  validity flag.

The whole call chain (0x2440, 0x2478 addSaturate8Bit, 0x3ED3C readValue_8bit
-> getSR 0x3920 / setSR 0x3934 / 0x3F050 error-flag setter, 0x3EE58
updateMemoryAtAddress_8bit) executes natively in the emulator.
"""
import os, sys, struct, random
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'tools'))
from sh2emu import SH2

ROM = os.path.join(os.path.dirname(__file__), '..', '..', 'roms', 'stock', '60E1D400.bin')
ADDR = 0x17DCC

A_COOLANT = 0xFFFFA73C   # f32 coolant temperature
A_ENABLE  = 0xFFFFA95C   # fan-enable latch (u8)
A_CNT     = 0xFFFFA93B   # fan speed counter (u8)
A_CELL    = 0xFFFF8076   # redundant 8-bit cell (value, ~value)
A_ERRFLAG = 0xFFFFC6AC   # corruption flag set by 0x3F050 on invalid read

def read_eps():
    """Exact eps float used by the ROM: mova @0x17DD4 (op C73A, lo=0x3A)
    resolves to 0x17EC0; fr6 of the 0x2440 call = ROM[0x17EC0] = 1e-5."""
    return struct.unpack('>f', open(ROM, 'rb').read()[0x17EC0:0x17EC4])[0]

def ref(t, ram):
    """Reference model. Returns (enabled, cnt, b0, b1, errflag)."""
    def g(a): return ram.get(a, 0)
    eps = read_eps()
    # complement_shift_u32(t, 0.0, eps): 1 iff NOT(-eps < t < eps)
    valid = 0 if (-eps < t < eps) else 1
    en  = g(A_ENABLE)
    cnt = g(A_CNT)
    b0, b1 = g(A_CELL), g(A_CELL + 1)
    err = g(A_ERRFLAG)
    if en == 0 and valid == 1:
        cnt = min(cnt + 1, 255)          # addSaturate8Bit(cnt, 1)
        if b0 == ((~b1) & 0xFF):         # readValue_8bit valid
            v = b0
        else:                            # invalid -> default 0 + error flag
            v = 0
            err = 1
        v = min(v + 1, 255)              # addSaturate8Bit(v, 1)
        b0, b1 = v, (~v) & 0xFF          # updateMemoryAtAddress_8bit
    en = valid                           # RAM[0xFFFFA95C] = r14 (valid flag)
    return en, cnt, b0, b1, err

def run_one(cpu, t, init):
    ram = dict(init)
    for i, b in enumerate(struct.pack('>f', t)):
        ram[A_COOLANT + i] = b
    cpu.call(ADDR, ram=ram)
    return (cpu.ram[A_ENABLE], cpu.ram[A_CNT], cpu.ram[A_CELL],
            cpu.ram[A_CELL + 1], cpu.ram.get(A_ERRFLAG, 0))

def main():
    cpu = SH2(open(ROM, 'rb').read())
    random.seed(20260801)
    temps = [0.0, -0.0, 95.0, 20.0, -40.0, 120.0, 1e-30, 1e-45] + \
            [random.uniform(-50, 150) for _ in range(300)]
    fails = tests = 0
    for t in temps:
        for _ in range(50):
            init = {A_ENABLE: random.randrange(0, 2),
                    A_CNT: random.randrange(0, 256),
                    A_ERRFLAG: random.randrange(0, 2)}
            # random cell: value byte + complement (valid) or random byte (invalid)
            b0 = random.randrange(0, 256)
            if random.random() < 0.5:
                b1 = (~b0) & 0xFF
            else:
                b1 = random.randrange(0, 256)
                if b1 == (~b0) & 0xFF:
                    b1 = (b1 + 1) & 0xFF
            init[A_CELL] = b0
            init[A_CELL + 1] = b1
            out = run_one(cpu, t, init)
            exp = ref(t, init)
            tests += 1
            if out != exp:
                fails += 1
                print(f"  cooling_fan_control FAIL t={t} emu={out} ref={exp} init={init}")
                if fails >= 5:
                    break
        if fails >= 5:
            break
    print(f"cooling_fan_control: {tests} tests, {fails} failures")
    print("COOLING_FAN_CONTROL:", "PASS" if fails == 0 else "FAIL")
    return 0 if fails == 0 else 1

if __name__ == '__main__':
    sys.exit(main())
