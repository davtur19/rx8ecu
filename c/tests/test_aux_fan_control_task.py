#!/usr/bin/env python3
"""
Test aux_fan_control_task (0x1AED2) via SH-2E emulator.

Function under test (60E1D400.bin):
  aux_fan_control_task @0x1AED2 (48 bytes) - boost-pressure auxiliary fan
  task.  Wraps a chain of calculations in a getSR/setSR critical section:

    1. getSR(0x10)                       ; save SR, restore at the end
    2. 0x32F42  RAM[0xFFFFC008] = firstOrderFilter(RAM[0xFFFFC008],
                   RAM[0xFFFFBC1C], 0.7, 1e-5)          ; boost filter
    3. 0x2DD6E  boost_delta_control:
                   RAM[0xFFFFBD3C] = (RAM[0xFFFFC008] - RAM[0xFFFFBD40]) * 15.625
                   RAM[0xFFFFBD40] = RAM[0xFFFFC008]    ; update prev
    4. 0x2DD88  boost_error_abs_calc:
                   RAM[0xFFFFBD38] = firstOrderFilter(RAM[0xFFFFBD3C],
                                       RAM[0xFFFFBD38], 0.5, 1e-5)
    5. 0x344FE  fpu_multi_register_swap: 6 float copies
                   C0D8<-C104  C0DC<-C108  C0E0<-C10C  C108<-C12C  C104<-B5B8  C10C<-ADC0
    6. 0x3488C  boost-pressure hysteresis on RAM[0xFFFFB5B8] (f32):
                   >= 7000 -> flag 1 ; < 6500 -> flag 0 ; else hold
                   -> 0xC2E6(flag) on the two active paths
    7. 0xC2E6    on flag CHANGE: RAM[0xFFFFA384]=0xFF, RAM[0xFFFFA385]=0,
                   RAM[0xFFFFA324]=0, RAM[0xFFFFA38C]=flag
    8. setSR(saved_SR)

The reference model recomputes every step (calling the emulator's own
verified 0x23B0 firstOrderFilter for the filter outputs) and compares the
full RAM effect against the emulated ROM run.
"""
import os, sys, struct, random, math
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'tools'))
from sh2emu import SH2, ts

ROM = os.path.join(os.path.dirname(__file__), '..', '..', 'roms', 'stock', '60E1D400.bin')
ADDR = 0x1AED2

C008  = 0xFFFFC008   # boost input (f32)
BC1C  = 0xFFFFBC1C   # filter prev (f32)
BD40  = 0xFFFFBD40   # delta-control prev (f32)
BD3C  = 0xFFFFBD3C   # scaled delta (f32)
BD38  = 0xFFFFBD38   # error filter prev/out (f32)
B5B8  = 0xFFFFB5B8   # boost pressure (f32) -> hysteresis input
C104  = 0xFFFFC104; C108 = 0xFFFFC108; C10C = 0xFFFFC10C
C0D8  = 0xFFFFC0D8; C0DC = 0xFFFFC0DC; C0E0 = 0xFFFFC0E0
C12C  = 0xFFFFC12C; ADC0 = 0xFFFFADC0
A38C  = 0xFFFFA38C   # boost flag (u8)
A384  = 0xFFFFA384; A385 = 0xFFFFA385; A324 = 0xFFFFA324

FLOAT_CELLS = [C008, BC1C, BD40, BD3C, BD38, B5B8, C104, C108, C10C,
               C0D8, C0DC, C0E0, C12C, ADC0]
BYTE_CELLS  = [A38C, A384, A385, A324]

def r32(d, a):
    return struct.unpack('>f', bytes(d.get(a + i, 0) for i in range(4)))[0]

def f32b(v):
    return list(struct.pack('>f', ts(v)))

def ref(cpu2, init):
    ram = dict(init)
    # --- step 2: 0x32F42 ---
    out = cpu2.call(0x23B0, fr={4: r32(ram, C008), 5: r32(ram, BC1C), 6: 0.7, 7: 1e-5})
    for i, b in enumerate(f32b(cpu2.fr[0])):
        ram[C008 + i] = b
    # --- step 3: 0x2DD6E boost_delta_control ---
    c008 = r32(ram, C008); bd40 = r32(ram, BD40)
    delta = ts(ts(c008 - bd40) * 15.625)
    for i, b in enumerate(f32b(delta)):
        ram[BD3C + i] = b
    for i, b in enumerate(f32b(c008)):
        ram[BD40 + i] = b
    # --- step 4: 0x2DD88 boost_error_abs_calc ---
    out = cpu2.call(0x23B0, fr={4: r32(ram, BD3C), 5: r32(ram, BD38), 6: 0.5, 7: 1e-5})
    for i, b in enumerate(f32b(cpu2.fr[0])):
        ram[BD38 + i] = b
    # --- step 5: 0x344FE float register swap ---
    for src, dst in [(C104, C0D8), (C108, C0DC), (C10C, C0E0),
                     (C12C, C108), (B5B8, C104), (ADC0, C10C)]:
        for i, b in enumerate(f32b(r32(ram, src))):
            ram[dst + i] = b
    # --- steps 6+7: 0x3488C hysteresis -> 0xC2E6 flag transition ---
    p = r32(ram, B5B8)
    if p >= 7000.0:
        flag = 1
    elif p < 6500.0:
        flag = 0
    else:
        flag = None
    if flag is not None and ram.get(A38C, 0) != flag:
        ram[A384] = 0xFF
        ram[A385] = 0
        ram[A324] = 0
        ram[A38C] = flag
    return ram

def run_one(cpu, init):
    cpu.call(ADDR, ram=dict(init))
    return dict(cpu.ram)

def main():
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    cpu2 = SH2(rom)          # dedicated instance for 0x23B0 in the ref
    random.seed(20260802)
    fails = tests = 0
    for _ in range(6000):
        init = {}
        for c in FLOAT_CELLS:
            init.update({c + i: b for i, b in enumerate(
                struct.pack('>f', random.uniform(-1000, 1000)))})
        for c in BYTE_CELLS:
            init[c] = random.randrange(0, 256)
        got = run_one(cpu, init)
        exp = ref(cpu2, init)
        tests += 1
        bad = []
        for c in FLOAT_CELLS:
            if bytes(got.get(c + i, 0) for i in range(4)) != bytes(exp.get(c + i, 0) for i in range(4)):
                bad.append('%s emu=%s ref=%s' % (hex(c),
                    r32(got, c), r32(exp, c)))
        for c in BYTE_CELLS:
            if got.get(c, 0) != exp.get(c, 0):
                bad.append('%s emu=%d ref=%d' % (hex(c), got.get(c, 0), exp.get(c, 0)))
        if bad:
            fails += 1
            print("  aux_fan_control_task FAIL:", bad[:4])
            if fails >= 5:
                break
    print(f"aux_fan_control_task: {tests} tests, {fails} failures")
    print("AUX_FAN_CONTROL_TASK:", "PASS" if fails == 0 else "FAIL")
    return 0 if fails == 0 else 1

if __name__ == '__main__':
    sys.exit(main())
