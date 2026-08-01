#!/usr/bin/env python3
"""
Test idle_speed_control_18054 (0x18054) via SH-2E emulator.

Model (verified against disassembly, including 0x3ED3C / 0x2460 / 0x9668):
  state = RAM[0xA428]; mode = RAM[0xAAE0]; ac = RAM[0xA979]
  running = RAM[0xA998]; load_comp = RAM[0xA978]
  idle_en = RAM[0xA96C]; old_status = RAM[0xA96A]
  duty = RAM[0xFFFFA96E] (u16); learn = RAM[0xA970]
  if (state==0 && mode==1):        f24=1; RAM[A979]=0; RAM[A975]=2
  elif (state==1 && !ac && !running): f20=1
  else:
     if ac==1: r9=1
     if mode==0 && r9==1 && !running && check_3ED3C(0x807C,0)==0: r10=1
     if r10==0 && !load_comp && learn==1: r13=1
     if idle_en==0 && r13==1: duty=0
  RAM[A96B]=f24; RAM[A968]=f20; RAM[A969]=r9; RAM[A96A]=r10
  thr = 500 if (-40.0 > O2@0xAA10) else 156     # cal 0x78E64/0x78E42/0x78E44
  if duty >= thr: r13=0
  RAM[A96C]=r13
  duty = min(duty+1, 0xFFFF)                     # 0x2460 add16bitSaturate
  RAM[0xFFFFA96E]=duty; RAM[A970]=load_comp
  if old_status==0 && r10==1: osTaskScheduler(0,2)   # 0x9668 (no-op w/ empty table)
"""
import os, sys, struct, random
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'tools'))
from sh2emu import SH2

ROM = os.path.join(os.path.dirname(__file__), '..', '..', 'roms', 'stock', '60E1D400.bin')

A = 0xFFFF0000
IN  = dict(state=0xA428, mode=0xAAE0, ac=0xA979, running=0xA998,
           load_comp=0xA978, idle_en=0xA96C, old_status=0xA96A,
           learn=0xA970, c807c=0x807C, c807d=0x807D)
OUT = dict(a96b=0xA96B, a968=0xA968, a969=0xA969, a96a=0xA96A,
           a96c=0xA96C, a970=0xA970)
DUTY = 0xFFFFA96E
O2   = 0xFFFFAA10

def build_ram(t):
    ram = {}
    for key, addr in IN.items():
        ram[A + addr] = t[key] & 0xFF
    # u16 stored big-endian (SH-2), like the ROM's mov.w
    ram[DUTY] = (t['duty'] >> 8) & 0xFF
    ram[DUTY + 1] = t['duty'] & 0xFF
    b = struct.pack('>f', t['o2'])
    for i in range(4):
        ram[O2 + i] = b[i]
    return ram

def call_rom(t, cpu):
    return cpu.call(0x18054, ram=build_ram(t))

def check_3ed3c(t):
    a, b_ = t['c807c'], t['c807d']
    return a if a == ((~b_) & 0xFF) else 0

def ref(t):
    state, mode, ac, running = t['state'], t['mode'], t['ac'], t['running']
    load_comp, idle_en = t['load_comp'], t['idle_en']
    old_status, learn, duty, o2 = t['old_status'], t['learn'], t['duty'], t['o2']
    f24 = f20 = 0
    r9 = r10 = 0
    r13 = idle_en
    path_a = False
    if state == 0 and mode == 1:
        f24 = 1
        path_a = True
    elif state == 1 and ac == 0 and running == 0:
        f20 = 1
    else:
        if ac == 1:
            r9 = 1
        if mode == 0 and r9 == 1 and running == 0 and check_3ed3c(t) == 0:
            r10 = 1
        if r10 == 0 and load_comp == 0 and learn == 1:
            r13 = 1
        if idle_en == 0 and r13 == 1:
            duty = 0
    thr = 500 if (-40.0 > o2) else 156
    if duty >= thr:
        r13 = 0
    duty = min(duty + 1, 0xFFFF)
    out = dict(a96b=f24, a968=f20, a969=r9, a96a=r10,
               a96c=r13, a96e=duty, a970=load_comp)
    if path_a:
        out['a979'] = 0
        out['a975'] = 2
    return out

def read_outs(cpu, path_a):
    out = {}
    for key, addr in OUT.items():
        out[key] = cpu.ram[A + addr]
    out['a96e'] = (cpu.ram[DUTY] << 8) | cpu.ram[DUTY + 1]
    if path_a:
        out['a979'] = cpu.ram[A + 0xA979]
        out['a975'] = cpu.ram[A + 0xA975]
    return out

def main():
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    random.seed(20260731)
    tests = fails = 0

    # exhaustive byte modes with fixed duty/o2
    base = dict(load_comp=0, idle_en=0, old_status=0, learn=1,
                duty=100, o2=0.0, c807c=0x24, c807d=0x62)
    for state in (0, 1, 2):
        for mode in (0, 1, 2):
            for ac in (0, 1):
                for running in (0, 1):
                    t = dict(base, state=state, mode=mode, ac=ac,
                             running=running)
                    call_rom(t, cpu)
                    exp = ref(t)
                    got = read_outs(cpu, exp.get('a979') is not None)
                    tests += 1
                    if got != exp:
                        print(f"FAIL {t}\n  got {got}\n  exp {exp}")
                        fails += 1

    # boundary + saturation sweep on duty
    for duty in (0, 1, 155, 156, 157, 499, 500, 501, 0xFFFE, 0xFFFF):
        for o2 in (-41.0, -40.0, -39.0):
            t = dict(base, state=0, mode=1, ac=0, running=0, duty=duty, o2=o2)
            call_rom(t, cpu)
            exp = ref(t)
            got = read_outs(cpu, exp.get('a979') is not None)
            tests += 1
            if got != exp:
                print(f"FAIL(sat) {t}\n  got {got}\n  exp {exp}")
                fails += 1

    # random
    for _ in range(3000):
        t = dict(state=random.randint(0, 3), mode=random.randint(0, 3),
                 ac=random.randint(0, 1), running=random.randint(0, 1),
                 load_comp=random.randint(0, 1), idle_en=random.randint(0, 1),
                 old_status=random.randint(0, 1), learn=random.randint(0, 1),
                 duty=random.randint(0, 0xFFFF), o2=random.uniform(-80, 80),
                 c807c=random.randint(0, 255), c807d=random.randint(0, 255))
        call_rom(t, cpu)
        exp = ref(t)
        got = read_outs(cpu, exp.get('a979') is not None)
        tests += 1
        if got != exp:
            print(f"FAIL(random) {t}\n  got {got}\n  exp {exp}")
            fails += 1
            if fails >= 5:
                break

    print(f"idle_speed_control_18054: {tests} tests, {fails} failures")
    return 0 if fails == 0 else 1

if __name__ == '__main__':
    sys.exit(main())
