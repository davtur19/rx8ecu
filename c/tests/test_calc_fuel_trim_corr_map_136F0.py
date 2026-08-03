#!/usr/bin/env python3
"""
test_calc_fuel_trim_corr_map_136F0.py — differential bit-exact test of
calc_fuel_trim_correction_map @0x136F0 (lift: c/calc_fuel_trim_corr_map_136F0.c).

Method (repo Track-A pattern): the REAL ROM bytes of 0x136F0 are executed in
the SH-2E emulator (tools/sh2emu.py) with a seeded random RAM overlay; the
resulting RAM overlay is compared bit-exactly against a pure-Python model
derived from the disassembly.

RAM footprint (byte logic only — no FPU, no callees):

  read: 0xFFFFA415 (ch1 in), 0xFFFFA414 (ch2 in),
        0xFFFFA716/0xFFFFA717 (previous-value shadows),
        0xFFFFA714/0xFFFFA715 (active flags, conditionally written)
  cal:  ROM 0x6E432..0x6E435 = {0x00, 0x0C, 0x00, 0x03} (threshold levels)
  write:0xFFFFA714, 0xFFFFA715 (only on an edge), 0xFFFFA716/0xFFFFA717 (always)

Semantics (2-line): per-channel rising/falling EDGE detector — when the input
byte just became equal to the channel's SET level (and was not it last call)
the active flag is forced 1; when it just became equal to the CLEAR level the
flag is forced 0; otherwise the flag is left untouched; the input byte is
latched into the shadow cell each call so the next call sees the crossing.

Run from repo root:  python3 c/tests/test_calc_fuel_trim_corr_map_136F0.py [N]
                     (N = random vectors per seed; default 20000)
"""
import os, random, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'tools'))
from sh2emu import SH2  # noqa: E402

ROM = os.path.join(os.path.dirname(__file__), '..', '..', 'roms', 'stock', '60E1D400.bin')
ADDR = 0x136F0

A415 = 0xFFFFA415   # ch1 input byte (r4)
A414 = 0xFFFFA414   # ch2 input byte (r6)
A716 = 0xFFFFA716   # ch1 shadow (prev value)
A717 = 0xFFFFA717   # ch2 shadow
A714 = 0xFFFFA714   # ch1 active flag
A715 = 0xFFFFA715   # ch2 active flag

# ROM calibration thresholds (bytes in the binary)
TH1_SET, TH1_CLR, TH2_SET, TH2_CLR = 0x00, 0x0C, 0x00, 0x03

IN_KEYS = ((A415, 0), (A414, 1), (A716, 2), (A717, 3), (A714, 4), (A715, 5))
OUT_CELLS = (A414, A415, A714, A715, A716, A717)


def build_ram(t):
    ram = {}
    for a, k in IN_KEYS:
        ram[a] = t[k] & 0xFF
    return ram


def ref(t):
    """Pure-Python model of 0x136F0 — see header doc in the C lift."""
    a1, a2 = t[0], t[1]
    p1, p2 = t[2], t[3]
    f1, f2 = t[4], t[5]
    if a1 == TH1_SET and p1 != TH1_SET:
        f1 = 1
    if a1 == TH1_CLR and p1 != TH1_CLR:
        f1 = 0
    if a2 == TH2_SET and p2 != TH2_SET:
        f2 = 1
    if a2 == TH2_CLR and p2 != TH2_CLR:
        f2 = 0
    return (a2, a1, f1, f2, a1, a2)


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    seeds = (0x136F0, 0x6E432, 0xABCD, 0x1234, 0x0D7A)
    tests = fails = 0

    for seed in seeds:
        rng = random.Random(seed)
        vectors = []
        # structured edges: every combination of threshold-hit transitions
        for a1 in (0x00, 0x0C, 0x01, 0x0B, 0x0D, 0xFF):
            for a2 in (0x00, 0x03, 0x01, 0x02, 0x04, 0xFF):
                for p1 in (0x00, 0x0C, 0xFF):
                    for p2 in (0x00, 0x03, 0xFF):
                        for f1 in (0, 1, 0xFF):
                            for f2 in (0, 1, 0xFF):
                                vectors.append((a1, a2, p1, p2, f1, f2))
        for _ in range(N):
            v = [rng.getrandbits(8) for _ in range(6)]
            if rng.random() < 0.3:          # bias toward threshold values
                v[0] = rng.choice((0x00, 0x0C))
                v[2] = rng.choice((0x00, 0x0C, rng.getrandbits(8)))
            if rng.random() < 0.3:
                v[1] = rng.choice((0x00, 0x03))
                v[3] = rng.choice((0x00, 0x03, rng.getrandbits(8)))
            vectors.append(tuple(v))

        for t in vectors:
            ram = build_ram(t)
            cpu.call(ADDR, ram=ram)
            got = tuple(cpu.ram.get(a, 0) for a in OUT_CELLS)
            exp = ref(t)
            tests += 1
            if got != exp:
                fails += 1
                if fails <= 8:
                    print("FAIL seed=0x%X in=%02X,%02X,%02X,%02X,%02X,%02X "
                          "got=%s exp=%s"
                          % (seed, *t, ' '.join('%02X' % x for x in got),
                             ' '.join('%02X' % x for x in exp)))
            # no writes outside the 6 footprint cells (+ stack area)
            for a in cpu.ram:
                if a in OUT_CELLS or a in ram or a in range(0xFFFFDEF8, 0xFFFFDF00):
                    continue
                fails += 1
                if fails <= 8:
                    print("FAIL(unexpected write) 0x%08X = %d" % (a, cpu.ram[a]))
            if fails >= 8:
                break
        if fails:
            break

    print(f"calc_fuel_trim_corr_map_136F0 @0x136F0: {tests} tests, {fails} failures")
    if fails == 0:
        print(f"OK  calc_fuel_trim_corr_map_136F0 @0x136F0  ({tests} inputs, 0 mismatches)")
        return 0
    print(f"FAIL calc_fuel_trim_corr_map_136F0 @0x136F0  ({fails} mismatches)")
    return 1


if __name__ == '__main__':
    sys.exit(main())
