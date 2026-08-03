#!/usr/bin/env python3
"""
test_knock_sensor_adc_fault_C460.py — differential bit-exact test of
knockSensorADCFault @0xC460 (lift: c/knock_sensor_adc_fault.c).

The REAL ROM bytes of 0xC460 are executed in the SH-2E emulator
(tools/sh2emu.py) over the full 16-bit ADC domain with a seeded random RAM
overlay; the result byte of 0xFFFFA325 is compared against a pure-Python
model from the disassembly (the C lift's RAM map uses the same cells).

Disasam with `python3 tools/disasm_sh2e.py 0xC460 60 60E1D400.bin`:

    mov.l 0xC4F8,r6 ; 0xFFFF9F0E     r6 = u16 raw ADC
    mov.w @r6,r6
    mov.l 0xC4FC,r4 ; 0xFFFFA325     out byte
    extu.w r6,r5                     r5 = adc
    mov.l 0xC500,r2 ; 0x0006CF7E
    mov.w @r2,r3 ; extu.w r3          r3 = thr_hi
    cmp/ge r3,r5                     T = (adc >= thr_hi)
    bf/s  0xC47A                     if adc < thr_hi -> check lo
    mov #1,r1
    bra 0xC490
    mov.b r1,@r4                     A325 = 1
    mov.l 0xC504,r3 ; 0x0006CF7C
    mov.w @r3,r0 ; extu.w r0          r0 = thr_lo
    cmp/ge r0,r5 ; bt/s 0xC48C        T = (adc >= thr_lo)
    mov #2,r0
    bra 0xC490
    mov.b r0,@r4                     A325 = 2
    mov #0,r1
    mov.b r1,@r4                     A325 = 0
    rts

    ->  adc>=thr_hi: 1 ; adc>=thr_lo: 0 ; else: 2

Run from repo root:  python3 c/tests/test_knock_sensor_adc_fault_C460.py [N]
"""
import os, random, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2  # noqa: E402

rom = open(os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin'), 'rb').read()
cpu = SH2(rom)

ADDR = 0xC460
ADC = 0xFFFF9F0E   # knock ADC raw (u16, big-endian)
OUT = 0xFFFFA325   # fault byte

THR_HI = int.from_bytes(rom[0x6CF7E:0x6CF80], 'big')
THR_LO = int.from_bytes(rom[0x6CF7C:0x6CF7E], 'big')


def ref(adc):
    if adc >= THR_HI:
        return 1
    if adc >= THR_LO:
        return 0
    return 2


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
    rng = random.Random(0xC460)
    tests = fails = 0
    edge = {0, 1, THR_LO - 1, THR_LO, THR_LO + 1, THR_HI - 1, THR_HI,
            THR_HI + 1, 0xFFFF, 0xFFFE, 0x8000, 0x7FFF}
    cpu = SH2(rom)

    def run(adc):
        return cpu.call(ADDR, ram={ADC: (adc >> 8) & 0xFF, ADC + 1: adc & 0xFF})

    for adc in edge:
        tests += 1
        cpu.ram = {}
        run(adc)
        got = cpu.ram.get(OUT)
        want = ref(adc)
        if got != want:
            fails += 1
            if fails <= 10:
                print("FAIL adc=%d got=%r want=%r" % (adc, got, want))
    for _ in range(N):
        adc = rng.getrandbits(16)
        run(adc)
        got = cpu.ram.get(OUT)
        want = ref(adc)
        tests += 1
        if got != want:
            fails += 1
            if fails <= 10:
                print("FAIL adc=%d got=%r want=%r" % (adc, got, want))
    print("knockSensorADCFault @0xC460: %d tests, %d failures" % (tests, fails))
    if fails == 0:
        print("OK  knockSensorADCFault @0xC460 (%d inputs, 0 mismatches)" % tests)
        return 0
    print("FAIL knockSensorADCFault @0xC460 (%d mismatches)" % fails)
    return 1


if __name__ == '__main__':
    sys.exit(main())