#!/usr/bin/env python3
"""
test_sensorADCRead_68A8.py — differential test of sensorADCRead @0x68A8
(ROM bytes run in tools/sh2emu.py with a mock A/D MMIO register file).

Previously BLOCKED: the function busy-waits on the A/D conversion-complete
flags (bit 0x80 / ADF of ADCSR at 0xFFFFF818 / 0xFFFFF838 / 0xFFFFF858).
tools/sh2emu.py had no MMIO model, so the flags never asserted and the run
tripped the 500k-step runaway guard at 0x6908.

Unblocked by the additive `mmio` hook in SH2.call(): a plain {addr: byte}
dict.  Reads of an address present in the dict return the mocked byte (the
mock wins over the RAM overlay — hardware registers are not RAM); stores to
MMIO addresses are accepted into the emulated RAM but reads still return the
mock value.  Default mmio=None → behaviour identical to before (all other
tests unaffected).  If the running sh2emu.py predates the hook, the test
reports itself BLOCKED and exits 2 (as before).

What the ROM actually does (disasm 0x68A8..0x6A04):
  1. configure AD0/AD1/AD2 via ADCSR writes (0x33/0x2B) — no RAM effect
  2. seed diagnostic sentinels at 0xFFFF9F27..0xFFFF9F30
  3. busy-wait ADF of all three A/D units (released by the mock)
  4. copy 32 result words 0xFFFFF800..0xFFFFF84E -> 0xFFFF9EE4..0xFFFF9F22
  5. rts (r0 = 0x3C, a leftover loop displacement — no voltage math here)

The pure-Python model mirrors steps 2 & 4 (the only observable RAM effects)
bit-exactly.

Run from repo root:  python3 c/tests/test_sensorADCRead_68A8.py [N]
"""
import inspect
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2  # noqa: E402

ENTRY = 0x00068A8
ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')

# A/D conversion-complete flag: ADCSR (AD0/AD1/AD2), bit 0x80 = ADF.
ADF = 0x80
ADCSR = {0xFFFFF818: ADF, 0xFFFFF838: ADF, 0xFFFFF858: ADF}

# The 32 result-word addresses read by the copy loop, in ROM order.
RESULT_ADDRS = [
    0xFFFFF800, 0xFFFFF802, 0xFFFFF804, 0xFFFFF806,
    0xFFFFF808, 0xFFFFF80A, 0xFFFFF80C, 0xFFFFF80E,
    0xFFFFF810, 0xFFFFF812, 0xFFFFF814, 0xFFFFF816,
    0xFFFFF820, 0xFFFFF822, 0xFFFFF824, 0xFFFFF826,
    0xFFFFF828, 0xFFFFF82A, 0xFFFFF82C, 0xFFFFF82E,
    0xFFFFF830, 0xFFFFF832, 0xFFFFF834, 0xFFFFF836,
    0xFFFFF840, 0xFFFFF842, 0xFFFFF844, 0xFFFFF846,
    0xFFFFF848, 0xFFFFF84A, 0xFFFFF84C, 0xFFFFF84E,
]
DST = 0xFFFF9EE4

# Diagnostic sentinels seeded by the ROM (RAM, not MMIO).
SENTINELS = {0xFFFF9F27: 0x00, 0xFFFF9F28: 0xFF, 0xFFFF9F2A: 0x00,
             0xFFFF9F2D: 0x00, 0xFFFF9F30: 0x00}


def mmio_supported():
    return 'mmio' in inspect.signature(SH2.call).parameters


def build_mmio(words, adf=ADF):
    """words: {addr: u16 result word} -> the {addr: byte} MMIO mock dict."""
    mmio = {a: adf for a in ADCSR}
    for a, w in words.items():
        mmio[a] = (w >> 8) & 0xFF
        mmio[a + 1] = w & 0xFF
    return mmio


def ram16(ram, a):
    return (ram.get(a, 0) << 8) | ram.get(a + 1, 0)


def run_one(cpu, words, adf=ADF):
    """Run the ROM bytes; return (r0, cpu.ram)."""
    r0 = cpu.call(ENTRY, ram={}, mmio=build_mmio(words, adf))
    return r0, cpu.ram


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    if not mmio_supported():
        print("BLOCKED sensorADCRead @0x68A8: tools/sh2emu.py has no `mmio`"
              " A/D mock (this emulator predates the additive"
              " SH2.call(mmio=...) hook); not verified.")
        return 2

    cpu = SH2(open(ROM, 'rb').read())
    rng = random.Random(0x68A8)
    tests = fails = 0
    first_fail = []

    def check(words, adf, tag):
        nonlocal tests, fails
        r0, ram = run_one(cpu, words, adf)
        tests += 1
        bad = []
        if r0 != 0x3C:
            bad.append('r0=0x%X (want 0x3C)' % r0)
        for a, v in SENTINELS.items():
            got = ram.get(a, -1)
            if got != v:
                bad.append('[0x%X]=0x%02X (want 0x%02X)' % (a, got, v))
        for i, sa in enumerate(RESULT_ADDRS):
            got = ram16(ram, DST + 2 * i)
            want = words.get(sa, 0) & 0xFFFF
            if got != want:
                bad.append('dst+%d src=0x%X: got 0x%04X want 0x%04X'
                           % (2 * i, sa, got, want))
        if bad:
            fails += 1
            if len(first_fail) < 10:
                first_fail.append('%s: %s' % (tag, '; '.join(bad[:3])))

    # Edge set: uniform / alternating / full-scale result words, plus an ADF
    # variant with the low bits set too (bit 0x80 still asserted).
    for u in (0x0000, 0xFFFF, 0xAAAA, 0x5555, 0x8000, 0x7FFF, 0x00FF, 0xFF00):
        check({a: u for a in RESULT_ADDRS}, ADF, 'uniform=0x%04X' % u)
    check({a: 0x0000 for a in RESULT_ADDRS}, 0xFF, 'ADF=0xFF')

    # Random result words (deterministic seed).
    for it in range(N):
        words = {a: rng.getrandbits(16) for a in RESULT_ADDRS}
        adf = ADF if rng.getrandbits(4) else 0xFF
        check(words, adf, 'random#%d' % it)

    for line in first_fail:
        print('FAIL', line)
    print("sensorADCRead @0x68A8: %d tests, %d failures" % (tests, fails))
    if fails == 0:
        print("OK  sensorADCRead @0x68A8 (%d inputs, 0 mismatches)" % tests)
        return 0
    print("FAIL sensorADCRead @0x68A8 (%d mismatches)" % fails)
    return 1


if __name__ == '__main__':
    sys.exit(main())
