#!/usr/bin/env python3
"""
Test calc_intake_pressure_pid_output_1252C (0x1252C) via SH-2E emulator.

Model (verified against disassembly):
  r1 = complement_shift_u32(target, 0.0, 1e-5)   # 1 if |target| > 1e-5
  r2 = complement_shift_u32(error,  0.0, 1e-5)   # 1 if |error|  > 1e-5
  if (cl_active==1 && r1==0 && rpm>2000 && idle_flag==1):  corr = -5.0
  elif (fuel_cut==0 && lambda>0 && (cal_en==0 || r2==0)):  corr = RAM[A9A8]
  else:                                                  corr = RAM[A640]
  RAM[A63C] = clamp(corr, RAM[A658], 65.0)
"""
import os, sys, struct, random
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'tools'))
from sh2emu import SH2

ROM = os.path.join(os.path.dirname(__file__), '..', '..', 'roms', 'stock', '60E1D400.bin')

A = 0xFFFF0000
ADDRS = dict(rpm=0xB5B8, target=0xA790, error=0xBCE4, cl_active=0xAADA,
             idle_flag=0xCE58, fuel_cut=0xBC36, lambda_st=0xA9B8,
             alt_ref=0xA9A8, default_ref=0xA640, clamp_lo=0xA658,
             out=0xA63C)

def putf(ram, a, v):
    b = struct.pack('>f', v)
    for i in range(4):
        ram[a + i] = b[i]

def build_ram(t):
    ram = {}
    for key in ('rpm', 'target', 'error', 'lambda_st', 'alt_ref',
                'default_ref', 'clamp_lo'):
        putf(ram, A + ADDRS[key], t[key])
    for key in ('cl_active', 'idle_flag', 'fuel_cut'):
        ram[A + ADDRS[key]] = t[key] & 0xFF
    return ram

def call_rom(t, cpu):
    return cpu.call(0x1252C, ram=build_ram(t))

def read_out(cpu):
    return cpu.rdf(A + ADDRS['out'])

def ref(t):
    """Python model of the C lift."""
    def deadband(v):
        return 1 if abs(v - 0.0) > 1e-5 else 0
    r1 = deadband(t['target'])
    r2 = deadband(t['error'])
    if (t['cl_active'] == 1 and r1 == 0 and t['rpm'] < 2000.0
            and t['idle_flag'] == 1):
        corr = -5.0
    elif (t['fuel_cut'] == 0 and t['lambda_st'] > 0.0
            and (0 == 0 or r2 == 0)):   # cal byte @0x6E3D4 == 0
        corr = t['alt_ref']
    else:
        corr = t['default_ref']
    return min(max(corr, t['clamp_lo']), 65.0)

def main():
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    random.seed(20260731)
    tests = fails = 0

    # ---- exhaustive mode/byte combos with fixed floats ----
    floats = dict(rpm=2500.0, target=0.0, error=0.0, lambda_st=1.0,
                  alt_ref=10.0, default_ref=5.0, clamp_lo=-10.0)
    for cl in (0, 1):
        for idlef in (0, 1):
            for fc in (0, 1):
                for lam in (1.0, -1.0):
                    for trg in (0.0, 0.5):
                        for err in (0.0, 0.5):
                            for rpm in (1500.0, 2500.0):
                                t = dict(floats, cl_active=cl, idle_flag=idlef,
                                         fuel_cut=fc, lambda_st=lam, target=trg,
                                         error=err, rpm=rpm)
                                call_rom(t, cpu)
                                got = read_out(cpu)
                                exp = ref(t)
                                tests += 1
                                if abs(got - exp) > 1e-4 and not (got != got and exp != exp):
                                    print(f"FAIL {t}: got {got} exp {exp}")
                                    fails += 1

    # ---- random floats ----
    for _ in range(3000):
        t = dict(
            rpm=random.uniform(0, 9000), target=random.uniform(-20, 20),
            error=random.uniform(-20, 20), lambda_st=random.uniform(-5, 5),
            alt_ref=random.uniform(-50, 50), default_ref=random.uniform(-50, 50),
            clamp_lo=random.uniform(-50, 50),
            cl_active=random.randint(0, 1), idle_flag=random.randint(0, 1),
            fuel_cut=random.randint(0, 1),
        )
        call_rom(t, cpu)
        got = read_out(cpu)
        exp = ref(t)
        tests += 1
        if abs(got - exp) > 1e-3 and not (got != got and exp != exp):
            print(f"FAIL(random) {t}: got {got} exp {exp}")
            fails += 1
            if fails >= 5:
                break

    print(f"calc_intake_pressure_pid_output_1252C: {tests} tests, {fails} failures")
    return 0 if fails == 0 else 1

if __name__ == '__main__':
    sys.exit(main())
