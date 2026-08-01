#!/usr/bin/env python3
"""
harness_get_maf_sensor_value.py — equivalence of rx8_get_maf_sensor_value @0x745C.

Reconstructed source: samples/src/rx8_get_maf_sensor_value.c
Verified lift   : c/maf_sensor_value.c (getMAFSensorValue @ 0x745C; the lift's
                  status logic, limit addresses, cal-table address and scale
                  constant were corrected against the ROM bytes — see the
                  sample header's DISCREPANCIES section).

The ROM function is a plain `void` routine with NO ABI arguments: it reads the
MAF raw ADC from RAM[0xFFFF9EEA] (u16), scales it to volts, interpolates the
MAF "voltage -> g/s" curve via a REAL `jsr` call to TwoDLookup @0x2068, stores
the flow to RAM[0xFFFF9F78] (float) and a range status byte to RAM[0xFFFF9F7C],
so the INPUT is the ADC word and the OUTPUTS are the two RAM side-effects.  The
emulator executes the actual ROM bytes (including the real TwoDLookup callee
and its axis-search/interp leaves); the host oracle mirrors the RAM on mmap'd
pages and reads the SAME calibration constants from the ROM file mmap'd at the
virtual addresses (descriptor 0x6A0E4, limits 0x6CF02/0x6CF04, axis/values
0x6FB18/0x6FBD8), so both sides see byte-identical tables.

Procedure (Track-A pattern):
  1. build host oracle (system gcc; own binary, common.build_oracle untouched),
  2. edge vectors (0, limits +/-1, full-scale, ADC counts that land exactly on
     axis breakpoints) + N random (seeded) ADC counts,
  3. run the ROM bytes @0x745C in tools/sh2emu.py on the same vectors,
  4. run the host C on the same vectors,
  5. compare the raw float bits of the flow and the status byte — 0 mismatches.

Usage:  python3 harness_get_maf_sensor_value.py [N]   (default N = 20000)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_cpu, make_rng, report, run_oracle  # noqa: E402
# common.py already put <repo>/tools on sys.path; sh2emu is importable here.
from sh2emu import f2bits  # noqa: E402

ADDR = 0x745C
N_DEFAULT = 20000

# RAM addresses the ROM function reads/writes (big-endian on the SH-2E).
MAF_ADC = 0xFFFF9EEA    # input:  u16 raw ADC count
MAF_FLOW = 0xFFFF9F78   # output: float processed MAF value (g/s)
MAF_STATUS = 0xFFFF9F7C # output: u8 status (0=OK, 1=high, 2=low)

# Range limits in this ROM: lower 0x0AC0 (2752), upper 0xFAE1 (64225).
LOWER = 0x0AC0
UPPER = 0xFAE1

# Edge ADC counts: zero, low-end, the two limits +/-1, mid-scale, full-scale.
EDGE = [
    0x0000, 0x0001, 0x0002, 0x0003,
    LOWER - 1, LOWER, LOWER + 1,
    0x7FFF, 0x8000,
    UPPER - 1, UPPER, UPPER + 1,
    0xFFFE, 0xFFFF,
]

# ADC counts whose scaled voltage lands EXACTLY on an axis breakpoint of the
# MAF curve (axis[k] * 65536 / 5 is an integer), exercising the f32 handler's
# t==0.0 fast path and the clamp boundaries.
BREAKPOINT_ADC = [0x2C00, 0x4000, 0x6000, 0xA000]   # 11264, 16384, 24576, 40960

SAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = '/tmp/rx8-recon-get_maf_sensor_value'


def build_oracle(cc='cc'):
    """Compile THIS sample + its own oracle into /tmp (same command as the
    verification line in the task; do NOT touch common.build_oracle)."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    oracle = os.path.join(BUILD_DIR, 'oracle')
    cmd = [cc, '-O2', '-Wall', '-Wextra',
           '-I', os.path.join(SAMPLES, 'include'),
           '-I', os.path.join(SAMPLES, 'src'),
           os.path.join(SAMPLES, 'tests', 'oracle_get_maf_sensor_value.c'),
           os.path.join(SAMPLES, 'src', 'rx8_get_maf_sensor_value.c'),
           '-lm', '-o', oracle]
    subprocess.run(cmd, check=True)
    return oracle


def call_maf(cpu, adc):
    """Run the ROM bytes @0x745C with RAM[0xFFFF9EEA] = adc (u16 big-endian);
    return (flow_bits, status) — the two RAM side-effects."""
    cpu.call(ADDR, ram={MAF_ADC: (adc >> 8) & 0xFF, MAF_ADC + 1: adc & 0xFF})
    return f2bits(cpu.rdf(MAF_FLOW)), cpu._rb(MAF_STATUS)


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    cpu = load_cpu()
    oracle = build_oracle()
    rng = make_rng(ADDR)

    vectors = list(EDGE) + list(BREAKPOINT_ADC) + \
              [rng.randrange(0x10000) for _ in range(n)]

    # (a) ROM behaviour via the emulator: seed RAM[0xFFFF9EEA], read back the
    #     flow float bits + status byte.
    emu = [call_maf(cpu, adc) for adc in vectors]

    # (b) host C on the same inputs.
    lines = ['maf %04X' % adc for adc in vectors]
    host = [tuple(x.split()) for x in run_oracle(oracle, lines)]

    # (c) compare bit-exact (float flow bits) and byte-exact (status).
    mismatches = []
    for i, (adc, e, h) in enumerate(zip(vectors, emu, host)):
        if e[0] != int(h[0], 16) or e[1] != int(h[1], 16):
            mismatches.append(
                'vec#%d adc=0x%04X ROM=flow_%08X/st_%d C=flow_%s/st_%d'
                % (i, adc, e[0], e[1], h[0], int(h[1], 16)))
            if len(mismatches) >= 5:
                break

    report('getMAFSensorValue', ADDR, n, mismatches,
           edges=len(EDGE) + len(BREAKPOINT_ADC))


if __name__ == '__main__':
    main()
