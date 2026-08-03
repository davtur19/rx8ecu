#!/usr/bin/env python3
"""
test_battery_voltage_monitor_26766.py — differential test of
getBatteryVoltageStatus @0x26766 (lift: c/battery_voltage_monitor.c).

The REAL ROM bytes of 0x26766 run in the SH-2E emulator (the saturating
increment helper @0x2460 runs natively).  Result bytes/words at
0xFFFFB6B6 / 0xFFFFB67A / 0xFFFFB6AC / 0xFFFFB6AE are compared against a
pure-Python model from the disassembly.

Model (disasm 0x26766, helper 0x2460 = min(U+V,0xFFFF)):

  volt = f32[0xFFFFB600] ; ibyte = u8[0xFFFFA428]
  B6B6: volt<9 -> 0 ; 9<=volt<10 -> unchanged ; volt>=10 / NaN -> 1
  B67A: reach_312 = NOT(c4>16.9729) OR NOT(c8<10.938) OR ibyte==0
                    OR (ibyte==1 AND B6AC<63) OR B6B6==0
                    OR (B6B6==1 AND B6AE<63)
        reach_312 -> B67A = 312 else (old>0 ? old-1 : old)
  B6AC = (ibyte==0) ? 0 : min(B6AC+1, 0xFFFF)
  B6AE = (B6B6==0) ? 0 : min(B6AE+1, 0xFFFF)

Run from repo root:  python3 c/tests/test_battery_voltage_monitor_26766.py [N]
"""
import math, os, random, struct, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2, ts  # noqa: E402

rom = open(os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin'), 'rb').read()
cpu = SH2(rom)

ADDR = 0x26766
B600 = 0xFFFFB600   # f32 battery voltage
A428 = 0xFFFFA428   # u8 input byte
B6C4 = 0xFFFFB6C4   # f32
B6C8 = 0xFFFFB6C8   # f32
B6B6 = 0xFFFFB6B6   # u8 stage-1 flag (in/out)
B67A = 0xFFFFB67A   # u16 pulse (in/out)
B6AC = 0xFFFFB6AC   # u16 (in/out)
B6AE = 0xFFFFB6AE   # u16 (in/out)

C4T = struct.unpack('>f', rom[0x751C0:0x751C4])[0]   # 16.9729...
C8T = struct.unpack('>f', rom[0x751C4:0x751C8])[0]   # 10.938


def putf(ram, a, v):
    b = struct.pack('>f', ts(v))
    for i in range(4):
        ram[a + i] = b[i]


def u16at(ram, a):
    return (ram.get(a, 0) << 8) | ram.get(a + 1, 0)


def ref(volt, ibyte, c4, c8, old_b6, old_b67a, old_b6ac, old_b6ae):
    volt = ts(volt)
    # stage B6B6
    if volt < 10.0:
        b6 = 0 if volt < 9.0 else old_b6 & 0xFF
    else:
        b6 = 1
    c4 = ts(c4)
    c8 = ts(c8)
    reach = not (c4 > C4T) or not (c8 < C8T) or (ibyte == 0) \
        or (ibyte == 1 and old_b6ac < 63) or (b6 == 0) \
        or (b6 == 1 and old_b6ae < 63)
    if reach:
        b67a = 312
    else:
        b67a = (old_b67a - 1) & 0xFFFF if old_b67a > 0 else old_b67a
    # stage B6AC (helper 0x2460: saturating +1)
    b6ac = 0 if ibyte == 0 else min(old_b6ac + 1, 0xFFFF)
    # stage B6AE
    b6ae = 0 if b6 == 0 else min(old_b6ae + 1, 0xFFFF)
    return (b6, b67a, b6ac, b6ae)


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
    rng = random.Random(0x26766)
    tests = fails = 0
    fspec = [float('nan'), float('inf'), float('-inf'), 8.0, 8.5, 9.0,
             9.5, 10.0, 10.5, 11.0, 12.0, 13.0, 14.0, 16.96, 16.97,
             16.98, 9.4, 9.9, 10.94, 10.93, 10.95]

    def run(v, ib, c4, c8, old_b6, old_b67, old_ac, old_ae):
        ram = {}
        putf(ram, B600, v); putf(ram, B6C4, c4); putf(ram, B6C8, c8)
        ram[A428] = ib & 0xFF
        ram[B6B6] = old_b6 & 0xFF
        ram[B67A] = (old_b67 >> 8) & 0xFF; ram[B67A + 1] = old_b67 & 0xFF
        ram[B6AC] = (old_ac >> 8) & 0xFF; ram[B6AC + 1] = old_ac & 0xFF
        ram[B6AE] = (old_ae >> 8) & 0xFF; ram[B6AE + 1] = old_ae & 0xFF
        cpu.call(ADDR, ram=ram)
        return (cpu.ram.get(B6B6, old_b6 & 0xFF),
                u16at(cpu.ram, B67A), u16at(cpu.ram, B6AC),
                u16at(cpu.ram, B6AE))

    for _ in range(N):
        if rng.random() < 0.4:
            volt = rng.choice(fspec)
        else:
            volt = rng.uniform(0, 15)
        if rng.random() < 0.4:
            c4 = rng.choice(fspec)
        else:
            c4 = rng.uniform(0, 25)
        if rng.random() < 0.4:
            c8 = rng.choice(fspec)
        else:
            c8 = rng.uniform(0, 15)
        if rng.random() < 0.5:
            ib = rng.choice((0, 1, 2, 0xFF, 0x7F))
        else:
            ib = rng.getrandbits(8)
        if rng.random() < 0.5:
            old_b6 = rng.choice((0, 1, 2, 0xFF))
        else:
            old_b6 = rng.getrandbits(8)
        old_b67 = rng.getrandbits(16)
        old_ac = rng.getrandbits(16)
        old_ae = rng.getrandbits(16)
        got = run(volt, ib, c4, c8, old_b6, old_b67, old_ac, old_ae)
        want = ref(volt, ib, c4, c8, old_b6, old_b67, old_ac, old_ae)
        tests += 1
        if got != want:
            fails += 1
            if fails <= 10:
                print("FAIL volt=%r ib=%d c4=%r c8=%r old=%s\n  got=%s\n  want=%s"
                      % (volt, ib, c4, c8, (old_b6, old_b67, old_ac, old_ae),
                         got, want))
    print("battery_voltage_monitor @0x26766: %d tests, %d failures"
          % (tests, fails))
    if fails == 0:
        print("OK  battery_voltage_monitor @0x26766 (%d inputs, 0 mismatches)" % tests)
        return 0
    print("FAIL battery_voltage_monitor @0x26766 (%d mismatches)" % fails)
    return 1


if __name__ == '__main__':
    sys.exit(main())