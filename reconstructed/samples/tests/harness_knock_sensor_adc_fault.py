#!/usr/bin/env python3
"""
harness_knock_sensor_adc_fault.py — equivalence of rx8_knock_sensor_adc_fault.

Reconstructed source: samples/src/rx8_knock_sensor_adc_fault.c
Verified lift   : c/knockSensorADCFault.c  (knockSensorADCFault)

ADDRESS NOTE: the lift's header cites entry 0xC290 in roms/stock/60E0FC00.bin.
In the harness ROM 60E1D400.bin the IDENTICAL code lives at 0xC460 (same
first 16 bytes: D6 25 66 61 D4 25 65 6D D2 25 63 21 63 3D 35 33); calling
0xC290 here would execute unrelated bytes.  The emulator is therefore driven
at 0xC460, and the ROM threshold pointers are taken from 0x6CF7C/0x6CF7E
(the literal pool of 60E1D400.bin @0xC500/0xC504) instead of the lift's
0x6D47C/0x6D47E — both hold the same values (OPEN=51249, SHRT=16121).

CALLING CONVENTION: the routine is a void, argument-less leaf (reads one u16
from 0xFFFF9F0E, writes one u8 to 0xFFFFA325, returns nothing in r0).  The
plain `cpu.call()` entry point works; the harness seeds the ADC cell and a
sentinel fault byte in the RAM overlay and compares the fault byte after the
call.  That byte is the ONLY RAM side effect (verified: the emulator's RAM
key set never grows beyond the seeded ADC/sentinel cells).

Procedure (Track-A pattern):
  1. build the host oracle (system gcc; -O2, -Wall, -Wextra),
  2. edge vectors (0, max, sign-flip words, both thresholds -1/0/+1 and
     +/-2, interval midpoint) + N random 16-bit ADC samples,
  3. run the ROM bytes @0xC460 in tools/sh2emu.py on the same vectors,
  4. run the host C on the same vectors (thresholds shipped inline so the
     oracle mirrors the exact ROM values),
  5. compare the fault byte — 0 mismatches required.

Usage:  python3 harness_knock_sensor_adc_fault.py [N]   (default N = 20000)
"""
import os
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROM_PATH, make_rng, report, run_oracle  # noqa: E402
from sh2emu import SH2  # noqa: E402

# Identical code sits at 0xC290 in 60E0FC00.bin; 60E1D400.bin hosts it at 0xC460.
ADDR = 0xC460
N_DEFAULT = 20000

ADC_ADDR = 0xFFFF9F0E          # u16 knock-sensor ADC sample (RAM)
OUT_ADDR = 0xFFFFA325          # u8  fault-code byte (RAM)
OPEN_ADDR = 0x0006CF7E         # u16 over-range threshold (ROM, 60E1D400 literal)
SHRT_ADDR = 0x0006CF7C         # u16 under-range threshold (ROM, 60E1D400 literal)

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = os.path.join('/tmp', 'rx8-recon-knock_sensor_adc_fault')


def build_oracle(cc='cc'):
    """Compile the reconstructed source + its own oracle into a host binary."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_knock_sensor_adc_fault.c'),
           os.path.join(SAMPLES, 'src', 'rx8_knock_sensor_adc_fault.c'),
           '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def gen_edges(open_v, shrt_v):
    """Boundary ADC vectors: 0, max, sign-flip words, both thresholds
    straddled by 1 and 2 counts, and the interval midpoint."""
    v = [0x0000, 0x0001, 0x7FFF, 0x8000, 0xFFFE, 0xFFFF]
    for t in (shrt_v, open_v):
        v += [t - 2, t - 1, t, t + 1, t + 2]
    v += [(shrt_v + open_v) // 2]
    return v


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    with open(ROM_PATH, 'rb') as f:
        cpu = SH2(f.read())
    oracle = build_oracle()
    rng = make_rng(0x60E1D400)

    open_v = struct.unpack_from('>H', cpu.rom, OPEN_ADDR)[0]
    shrt_v = struct.unpack_from('>H', cpu.rom, SHRT_ADDR)[0]

    vectors = list(gen_edges(open_v, shrt_v))
    vectors += [rng.getrandbits(16) & 0xFFFF for _ in range(n)]

    # (a) ROM behaviour via the emulator: seed ADC cell + sentinel fault byte.
    # The fault byte at OUT_ADDR is the routine's only RAM side effect; the
    # emulator's RAM key set must never grow beyond the seeded cells.
    emu = []
    side_effect_leak = False
    for adc in vectors:
        ram = {ADC_ADDR: (adc >> 8) & 0xFF, ADC_ADDR + 1: adc & 0xFF,
               OUT_ADDR: 0x55}
        cpu.call(ADDR, ram=ram)
        if set(cpu.ram) != set(ram):
            side_effect_leak = True
        emu.append(cpu.ram[OUT_ADDR])

    # (b) host C on the same inputs (thresholds shipped inline as the exact
    #     ROM values, so the oracle's mapped slots mirror the ROM bytes).
    lines = ['knock %04X %04X %04X' % (adc, open_v, shrt_v) for adc in vectors]
    host = [int(x, 16) for x in run_oracle(oracle, lines)]

    # (c) compare the fault byte (the function's only RAM side effect).
    mismatches = []
    if side_effect_leak:
        mismatches.append('emulator wrote outside the ADC/OUT cells')
    for i, (adc, e, h) in enumerate(zip(vectors, emu, host)):
        if e != h:
            mismatches.append(
                'vec#%d adc=0x%04X ROM=%02X C=%02X' % (i, adc, e, h))
            if len(mismatches) >= 5:
                break

    report('knockSensorADCFault', ADDR, n, mismatches, edges=len(gen_edges(open_v, shrt_v)))


if __name__ == '__main__':
    main()
