#!/usr/bin/env python3
"""
Test calc_rotor_sync_idle_gate_B (0x12BC8) via SH-2E emulator.

Model (verified against disassembly):
  prev = RAM[0xFFFFA694]                (previous RPM sample, float)
  drop = prev - rpm                     (signed, computed unconditionally)
  if ((warmup==1 || cl_en==1) && cl_act==1)
     and ((cam_en_a==1 && rotor_a==0) || (cam_en_b==1 && rotor_b==0))
     and not (40.0 > drop)              i.e. drop >= 40.0
     and not (rpm > 2000.0)             i.e. rpm <= 2000.0
  -> RAM[0xFFFFA690] = 1  else 0
  RAM[0xFFFFA694] = rpm   (always)
  RAM[0xFFFFA6A3] = rotor_a, RAM[0xFFFFA6A4] = rotor_b  (always)
"""
import os, sys, struct, random
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'tools'))
from sh2emu import SH2

ROM = os.path.join(os.path.dirname(__file__), '..', '..', 'roms', 'stock', '60E1D400.bin')

A = 0xFFFF0000
ADDRS = dict(prev=0xA694, rpm=0xB5B8, warmup=0xB5A4, cl_en=0xCABC,
             cl_act=0xAADA, cam_en_a=0xA6A3, cam_en_b=0xA6A4,
             rotor_a=0xA444, rotor_b=0xA445, flag=0xA690)

def putf(ram, a, v):
    b = struct.pack('>f', v)
    for i in range(4):
        ram[a + i] = b[i]

def build_ram(t):
    ram = {}
    putf(ram, A + ADDRS['prev'], t['prev'])
    putf(ram, A + ADDRS['rpm'], t['rpm'])
    for key in ('warmup', 'cl_en', 'cl_act', 'cam_en_a', 'cam_en_b',
                'rotor_a', 'rotor_b'):
        ram[A + ADDRS[key]] = t[key] & 0xFF
    return ram

def call_rom(t, cpu):
    return cpu.call(0x12BC8, ram=build_ram(t))

def read_outs(cpu):
    return (cpu.ram[A + ADDRS['flag']],
            cpu.rdf(A + ADDRS['prev']),
            cpu.ram[A + ADDRS['cam_en_a']],
            cpu.ram[A + ADDRS['cam_en_b']])

def ref(t):
    prev, rpm = t['prev'], t['rpm']
    f32 = struct.unpack('>f', struct.pack('>f', rpm))[0]  # ROM stores float32
    drop = prev - rpm
    ok = ((t['warmup'] == 1 or t['cl_en'] == 1) and t['cl_act'] == 1) and \
         ((t['cam_en_a'] == 1 and t['rotor_a'] == 0) or
          (t['cam_en_b'] == 1 and t['rotor_b'] == 0)) and \
         (drop >= 40.0) and (rpm <= 2000.0)
    return (1 if ok else 0, f32, t['rotor_a'], t['rotor_b'])

def main():
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    random.seed(20260731)
    tests = fails = 0

    # exhaustive byte modes with fixed floats
    for warmup in (0, 1):
        for cl_en in (0, 1):
            for cl_act in (0, 1):
                for cea in (0, 1):
                    for ceb in (0, 1):
                        for ra in (0, 1, 2):
                            for rb in (0, 1, 2):
                                for drop in (0.0, 39.9, 40.0, 100.0):
                                    t = dict(prev=1500.0 + drop, rpm=1500.0,
                                             warmup=warmup, cl_en=cl_en,
                                             cl_act=cl_act, cam_en_a=cea,
                                             cam_en_b=ceb, rotor_a=ra,
                                             rotor_b=rb)
                                    call_rom(t, cpu)
                                    got = read_outs(cpu)
                                    exp = ref(t)
                                    tests += 1
                                    if got != exp:
                                        print(f"FAIL {t}: got {got} exp {exp}")
                                        fails += 1

    # random floats + bytes
    for _ in range(3000):
        t = dict(prev=random.uniform(0, 9000), rpm=random.uniform(0, 9000),
                 warmup=random.randint(0, 1), cl_en=random.randint(0, 1),
                 cl_act=random.randint(0, 1), cam_en_a=random.randint(0, 1),
                 cam_en_b=random.randint(0, 1),
                 rotor_a=random.randint(0, 2), rotor_b=random.randint(0, 2))
        call_rom(t, cpu)
        got = read_outs(cpu)
        exp = ref(t)
        tests += 1
        if got != exp:
            print(f"FAIL(random) {t}: got {got} exp {exp}")
            fails += 1
            if fails >= 5:
                break

    print(f"calc_rotor_sync_idle_gate_B: {tests} tests, {fails} failures")
    return 0 if fails == 0 else 1

if __name__ == '__main__':
    sys.exit(main())
