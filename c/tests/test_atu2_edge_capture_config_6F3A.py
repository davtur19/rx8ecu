#!/usr/bin/env python3
"""
Verify atu2_edge_capture_config_6F3A (0x6F3A) against the ACTUAL ROM bytes,
run in the SH-2E emulator.

SFR bit-config leaf taking r4 (32-bit): r4 == 0 → enable sequence, else
disable sequence.  Byte RMWs on 7 SFRs (see lift header for the exact
sequence).  Only the writes to 0xFFFFF818 / 0xFFFFF838 differ between the
branches (0x0B/0x4B vs 0x0A/0x4A); the rest is a common tail.

C:
  void atu2_edge_capture_config_6F3A(uint32_t r4)

Model (per branch, computed from seeded initial bytes):
  [0xFFFFF818] = 0x0B if r4==0 else 0x0A
  [0xFFFFF838] = 0x4B if r4==0 else 0x4A
  [0xFFFFF819] = (init & 0xDF & 0xAF) | 0x80
  [0xFFFFF76E] = (init & 0x7F) | 0x80
  [0xFFFFF839] = (init & 0xDF & 0xAF) | 0x80
  [0xFFFFF72E] = (init & 0x7F) | 0x80
  [0xFFFF9F27] = 0x01

Run from repo root:  python3 c/tests/test_atu2_edge_capture_config_6F3A.py [N]
"""
import os, sys, random

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sh2emu import SH2

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')
ENTRY = 0x0006F3A

SFR = [0xFFFFF818, 0xFFFFF838, 0xFFFFF819, 0xFFFFF76E,
       0xFFFFF839, 0xFFFFF72E, 0xFFFF9F27]


def expected(init, r4):
    v = dict(init)
    v[0xFFFFF818] = 0x0B if r4 == 0 else 0x0A
    v[0xFFFFF838] = 0x4B if r4 == 0 else 0x4A
    v[0xFFFFF819] = (init[0xFFFFF819] & 0xDF & 0xAF) | 0x80
    v[0xFFFFF76E] = (init[0xFFFFF76E] & 0x7F) | 0x80
    v[0xFFFFF839] = (init[0xFFFFF839] & 0xDF & 0xAF) | 0x80
    v[0xFFFFF72E] = (init[0xFFFFF72E] & 0x7F) | 0x80
    v[0xFFFF9F27] = 0x01
    return v


def run_one(cpu, r4, init):
    cpu.call(ENTRY, r4=r4, ram=dict(init))
    return {a: cpu.ram.get(a, -1) for a in SFR}


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)

    # Deterministic edge set.
    edges = [
        {a: 0x00 for a in SFR},
        {a: 0xFF for a in SFR},
        {a: 0x7F for a in SFR},
        {a: 0x80 for a in SFR},
        {a: 0xDF for a in SFR},
        {a: 0xAF for a in SFR},
        {a: (a & 0xFF) for a in SFR},
    ]
    for r4 in (0, 1):
        for init in edges:
            got = run_one(cpu, r4, init)
            exp = expected(init, r4)
            for a in SFR:
                if got[a] != exp[a]:
                    print("FAIL: r4=%d init=%X -> [0x%X]=0x%02X expected 0x%02X" % (
                        r4, init[a], a, got[a], exp[a]))
                    sys.exit(1)

    # Random: both r4 values, random initial bytes.
    for _ in range(N):
        r4 = random.randint(0, 1)
        init = {a: random.randint(0, 255) for a in SFR}
        got = run_one(cpu, r4, init)
        exp = expected(init, r4)
        for a in SFR:
            if got[a] != exp[a]:
                print("FAIL: r4=%d init -> [0x%X]=0x%02X expected 0x%02X" % (
                    r4, a, got[a], exp[a]))
                sys.exit(1)

    print("OK  atu2_edge_capture_config_6F3A @0x%04X  (%d edge + %d random x2)" % (
        ENTRY, len(edges) * 2, N))
    sys.exit(0)


if __name__ == '__main__':
    main()
