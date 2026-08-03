#!/usr/bin/env python3
"""
test_get_iat_threshold_3C214.py — differential test of get_iat_threshold
@0x3C214 (lift: c/iat_sensor.c).

Real ROM bytes of 0x3C214 run in the SH-2E emulator with a seeded random RAM
overlay; five result bytes (0xFFFFC5F4/F5/F6/F8/F9) are compared against a
pure-Python model derived from the disassembly.

Disasm (`python3 tools/disasm_sh2e.py 0x3C214 240 60E1D400.bin`) — a 5-flag
IAT threshold latch:

    r6 = byte[0xFFFFD201] ; thr_a = byte[0x7A9A8] ; thr_b = byte[0x7A9A9]
    C5F4 = (byte[C5EC]  > thr_a) ? 1 : 0
    C5F5 = (byte[C5ED]  > thr_a) ? 1 : 0
    C5F6 = (byte[C5EE]  > thr_a) ? 1 : 0
    C5F8: if C5F5==1 or C5F4==1 or r6==1: 0
          elif byte[C5EF] > thr_b: 1
          elif byte[C5F7]==1: 1
          else: unchanged
    C5F9: if C5F6==1 or C5F4==1 or r6==1: 0
          elif byte[C5F0] > thr_b: 1
          elif byte[C5F7]==1: 1
          else: unchanged

Run from repo root:  python3 c/tests/test_get_iat_threshold_3C214.py [N]
"""
import os, random, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2  # noqa: E402

rom = open(os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin'), 'rb').read()
cpu = SH2(rom)

ADDR = 0x3C214
R6   = 0xFFFFD201
C5EC, C5ED, C5EE = 0xFFFFC5EC, 0xFFFFC5ED, 0xFFFFC5EE
C5EF, C5F0, C5F7 = 0xFFFFC5EF, 0xFFFFC5F0, 0xFFFFC5F7
C5F4, C5F5, C5F6 = 0xFFFFC5F4, 0xFFFFC5F5, 0xFFFFC5F6
C5F8, C5F9 = 0xFFFFC5F8, 0xFFFFC5F9
THR_A = rom[0x7A9A8]
THR_B = rom[0x7A9A9]


def ref(t, prev8, prev9):
    e5f4 = 1 if t['c5ec'] > THR_A else 0
    e5f5 = 1 if t['c5ed'] > THR_A else 0
    e5f6 = 1 if t['c5ee'] > THR_A else 0
    # C5F8
    if e5f5 == 1 or e5f4 == 1 or t['r6'] == 1:
        e5f8 = 0
    elif t['c5ef'] > THR_B:
        e5f8 = 1
    elif t['c5f7'] == 1:
        e5f8 = 1
    else:
        e5f8 = prev8 & 0xFF
    # C5F9
    if e5f6 == 1 or e5f4 == 1 or t['r6'] == 1:
        e5f9 = 0
    elif t['c5f0'] > THR_B:
        e5f9 = 1
    elif t['c5f7'] == 1:
        e5f9 = 1
    else:
        e5f9 = prev9 & 0xFF
    return (e5f4, e5f5, e5f6, e5f8, e5f9)


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
    rng = random.Random(0x3C214)
    tests = fails = 0

    def run(t, prev8, prev9):
        ram = {
            R6: t['r6'] & 0xFF,
            C5EC: t['c5ec'] & 0xFF, C5ED: t['c5ed'] & 0xFF,
            C5EE: t['c5ee'] & 0xFF, C5EF: t['c5ef'] & 0xFF,
            C5F0: t['c5f0'] & 0xFF, C5F7: t['c5f7'] & 0xFF,
            C5F8: prev8 & 0xFF, C5F9: prev9 & 0xFF,
        }
        cpu.call(ADDR, ram=ram)
        return (cpu.ram.get(C5F4, 0), cpu.ram.get(C5F5, 0),
                cpu.ram.get(C5F6, 0), cpu.ram.get(C5F8, prev8 & 0xFF),
                cpu.ram.get(C5F9, prev9 & 0xFF))

    # random + structure
    for _ in range(N):
        t = dict(
            r6=rng.getrandbits(8),
            c5ec=rng.getrandbits(8), c5ed=rng.getrandbits(8),
            c5ee=rng.getrandbits(8), c5ef=rng.getrandbits(8),
            c5f0=rng.getrandbits(8), c5f7=rng.getrandbits(8),
        )
        # edge hits against ROM thresholds
        for k in ('c5ec', 'c5ed', 'c5ee', 'c5ef', 'c5f0'):
            if rng.random() < 0.3:
                t[k] = rng.choice((THR_A - 1, THR_A, THR_A + 1,
                                   THR_B - 1, THR_B, THR_B + 1)) & 0xFF
        prev8 = rng.getrandbits(8)
        prev9 = rng.getrandbits(8)
        got = run(t, prev8, prev9)
        want = ref(t, prev8, prev9)
        tests += 1
        if got != want:
            fails += 1
            if fails <= 10:
                print("FAIL t=%s got=%s want=%s" % (t, got, want))
    print("get_iat_threshold @0x3C214: %d tests, %d failures" % (tests, fails))
    if fails == 0:
        print("OK  get_iat_threshold @0x3C214 (%d inputs, 0 mismatches)" % tests)
        return 0
    print("FAIL get_iat_threshold @0x3C214 (%d mismatches)" % fails)
    return 1


if __name__ == '__main__':
    sys.exit(main())