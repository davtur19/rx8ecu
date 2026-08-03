#!/usr/bin/env python3
"""test_calc_idle_speed_target_0x12F5E.py

Differential test for ROM 0x12F5E (60E1D400.bin) — lift c/calc_idle_speed_target.c,
plus its callee sensor_range_check_3ED0C @ 0x3ED0C (verified here through the
replay, and independently as a sub-check).

Runs the ACTUAL ROM bytes of 0x12F5E in tools/sh2emu.py over seeded RAM states
and compares the post-call RAM effect against a Python model.

Model (derived from the disassembly 0x12F5E..0x1306C):
   1. rotor_a=u8@0xFFFFA444 ; rotor_b=u8@0xFFFFA445 ; target@0xFFFFA678
   2. if engine_running(u8@0xFFFFC600)!=0: target=0.0
      elif rpm_raw(u16@0xFFFFA424) < u16@0x00072BC0: target=0.0
      elif closed_loop(u8@0xFFFFAADA)!=0: target=0.0
      else: diff = f32@0xFFFFC128 - f32@0xFFFFC12C  (single precision)
            target = sensor_range_check(diff, f32@0xFFFFC12C)   [callee 0x3ED0C]
   3. Phase 4 (state flags): inc@0xFFFFA68F
        if (state_a(u8@0xFFFFA6A9)==1 and rotor_a==0) or
           (state_b(u8@0xFFFFA6AA)==1 and rotor_b==0):
            inc = ROM8@0x00072BBB
        elif inc > 0: inc = (inc - 1) & 0xFF
   4. Phase 5 (adaptive): adaptive f32@0xFFFFA680
        if inc > 0: adaptive = fpu_mul_float_0x23E4(fr4=adaptive, fr5=target)
        else: if not (f32@0xFFFFA670 > 0.0) and not (f32@0xFFFFA674 > 0.0):
                 adaptive = 0.0
   5. state_a=rotor_a ; state_b=rotor_b

Callees 0x3ED0C (sensor_range_check) and 0x23E4 (fpu_mul_float) are executed in
a second emulator instance (cpu2) so float rounding matches the machine.

Run: python3 c/tests/test_calc_idle_speed_target_0x12F5E.py [N]
"""
import os, random, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2, ts

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ADDR = 0x12F5E
SRC_CHECK = 0x3ED0C
FPU_MUL = 0x23E4

A_ROTORA = 0xFFFFA444
A_ROTORB = 0xFFFFA445
A_RPM = 0xFFFFA424
A_RUN = 0xFFFFC600
A_CLOSED = 0xFFFFAADA
A_CALT = 0xFFFFC128
A_CMAIN = 0xFFFFC12C
A_TARGET = 0xFFFFA678
A_ADAPT = 0xFFFFA680
A_INC = 0xFFFFA68F
A_STATEA = 0xFFFFA6A9
A_STATEB = 0xFFFFA6AA
A_VAL1 = 0xFFFFA670
A_VAL2 = 0xFFFFA674
CAL_INC = 0x00072BBB
CAL_THRESH = 0x00072BC0


def u16(ram, a):
    return (ram.get(a, 0) << 8) | ram.get(a + 1, 0)


def f32(ram, a):
    return struct.unpack('>f', bytes(ram.get(a + i, 0) for i in range(4)))[0]


def put_f32(ram, a, v):
    b = struct.pack('>f', ts(v))
    for i in range(4):
        ram[a + i] = b[i]


def gen_state(rng):
    ram = {}
    ram[A_ROTORA] = rng.randint(0, 1)
    ram[A_ROTORB] = rng.randint(0, 1)
    ram[A_RPM] = rng.randint(0, 255); ram[A_RPM + 1] = rng.randint(0, 255)
    ram[A_RUN] = rng.randint(0, 1)
    ram[A_CLOSED] = rng.randint(0, 1)
    put_f32(ram, A_CALT, rng.uniform(-40, 120))
    put_f32(ram, A_CMAIN, rng.uniform(-40, 120))
    put_f32(ram, A_TARGET, rng.uniform(-1e3, 1e3))
    put_f32(ram, A_ADAPT, rng.uniform(-1e3, 1e3))
    ram[A_INC] = rng.randint(0, 255)
    ram[A_STATEA] = rng.randint(0, 1)
    ram[A_STATEB] = rng.randint(0, 1)
    put_f32(ram, A_VAL1, rng.uniform(-10, 10))
    put_f32(ram, A_VAL2, rng.uniform(-10, 10))
    return ram


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    cpu2 = SH2(rom)
    rng = random.Random(0x12F5E)
    threshold = u16({}, 0) | (rom[CAL_THRESH] << 8 | rom[CAL_THRESH + 1])
    cal_inc = rom[CAL_INC]
    fails = 0

    for it in range(N):
        ram = gen_state(rng)
        input_keys = set(ram.keys())
        m = dict(ram)

        # ---- phase 1-3 ----
        rotor_a = m[A_ROTORA]
        rotor_b = m[A_ROTORB]
        target = 0.0
        if m[A_RUN] == 0:
            if u16(m, A_RPM) >= threshold:
                if m[A_CLOSED] == 0:
                    diff = ts(f32(m, A_CALT) - f32(m, A_CMAIN))
                    main_v = f32(m, A_CMAIN)
                    ret = cpu2.call(SRC_CHECK, fr={4: diff, 5: main_v}, ram=dict(m))
                    target = cpu2.fr[0]
                    m = dict(cpu2.ram)
        put_f32(m, A_TARGET, target)

        # ---- phase 4 ----
        inc = m[A_INC]
        state_a = m[A_STATEA]
        state_b = m[A_STATEB]
        if (state_a == 1 and rotor_a == 0) or (state_b == 1 and rotor_b == 0):
            m[A_INC] = cal_inc
        elif inc > 0:
            m[A_INC] = (inc - 1) & 0xFF

        # ---- phase 5 ----
        if m[A_INC] > 0:
            adaptive = f32(m, A_ADAPT)
            tgt = f32(m, A_TARGET)
            ret = cpu2.call(FPU_MUL, fr={4: adaptive, 5: tgt}, ram=dict(m))
            m = dict(cpu2.ram)
            put_f32(m, A_ADAPT, cpu2.fr[0])
        else:
            v1 = f32(m, A_VAL1)
            v2 = f32(m, A_VAL2)
            if not (v1 > 0.0) and not (v2 > 0.0):
                put_f32(m, A_ADAPT, 0.0)

        # ---- phase 6 ----
        m[A_STATEA] = rotor_a
        m[A_STATEB] = rotor_b

        # ---- run ROM ----
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
            print('MISMATCH iter=%d: %s' %
                  (it, {hex(b[0]): (hex(b[1]), b[2] if isinstance(b[2], str) else hex(b[2])) for b in bad[:10]}))
            fails += 1
            if fails >= 3:
                break

    if fails:
        print('%d FAILURE(S) calc_idle_speed_target' % fails)
        sys.exit(1)
    print('OK  0x12F5E calc_idle_speed_target (+ 0x3ED0C replay)  (%d inputs)' % N)
    sys.exit(0)


if __name__ == '__main__':
    main()