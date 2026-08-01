#!/usr/bin/env python3
"""test_omp_rotor_overshoot_detector_18CC0.py

Differential test for the OMP companion RTOS task omp_rotor_overshoot_detector_18CC0
at ROM 0x18CC0 (lift: c/omp_rotor_overshoot_detector_18CC0.c).  Runs
the actual ROM bytes in the SH-2E emulator and compares the full relevant RAM
against a Python model.

Flow (see the lift header for the fully annotated layout):
  1. always read port 0x807A via readValue_8bit_ADDRESS_VAL(0x807A, 0x37) —
     a broken complementary pair raises the C6AC fault flag every tick
  2. gate (A969 == 1 && A975 == 0):
       A976 == 0 (OMP fault):  A974 > sat8(r, CAL38)   -> A992 = 1
       A976 != 0 (healthy):    band = (r>CAL38)? r-CAL38 : 0;
                               A974 < band             -> A993 = 1
  3. A992==1 && A994 >= CAL39 -> A990 = 1
     A993==1 && A995 >= CAL3A -> A991 = 1
  4. A992==1 -> A994 = sat8(A994,1) else A994 = 0
     A993==1 -> A995 = sat8(A995,1) else A995 = 0

Called leaves (lifted; run natively in the emulator):
  0x3ED3C readValue_8bit_ADDRESS_VAL, 0x2478 addSaturate8Bit — modelled
  inline (complementary byte encoding + C6AC fault flag, saturating add),
  matching test_omp_accessors.py / c/addSaturate8Bit.c.

Run: python3 c/tests/test_omp_rotor_overshoot_detector_18CC0.py [N]
     (N = random inputs per seed; default 20000 -> 100000 across 5 seeds)
"""
import os, sys, random

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from sh2emu import SH2, s8

ROM = os.path.join(ROOT, 'roms', 'stock', '60E1D400.bin')

# ---- RAM map (see c/omp_rotor_overshoot_detector_18CC0.c header) ----
A969 = 0xFFFFA969   # rotor-sync dispatch flag (gate)
A974 = 0xFFFFA974   # position target (captured at entry)
A975 = 0xFFFFA975   # OMP ramp value (gate)
A976 = 0xFFFFA976   # OMP fault-inoperative flag
A990 = 0xFFFFA990   # over-shoot latch
A991 = 0xFFFFA991   # under-shoot latch
A992 = 0xFFFFA992   # over-shoot trigger
A993 = 0xFFFFA993   # under-shoot trigger
A994 = 0xFFFFA994   # over-shoot debounce counter
A995 = 0xFFFFA995   # under-shoot debounce counter
P7A  = 0xFFFF807A   # idle/off port (complementary u16)
C6AC = 0xFFFFC6AC   # ADDRESS_VAL fault flag (leaf 0x3F050)

CAL38 = 0x01   # ROM 0x78E38: band width / sat8 addend
CAL39 = 0x3E   # ROM 0x78E39: A994 debounce threshold (62)
CAL3A = 0x7D   # ROM 0x78E3A: A995 debounce threshold (125)


def model(ram):
    """Python model of the whole task at 0x18CC0.  Returns the full effect
    dict (0xFFFF-prefixed int keys)."""
    m = dict(ram)

    def B(a): return m.get(a, 0) & 0xFF
    def W(a, v): m[a & 0xFFFFFFFF] = v & 0xFF

    # step 1: port read — always executed, before any gating.
    b0 = B(P7A); b1 = B(P7A + 1)
    if b0 == ((~b1) & 0xFF):
        r = s8(b0)
    else:
        W(C6AC, 1)
        r = s8(0x37)

    # step 2: gate
    a974 = B(A974)      # captured at entry
    a992 = 0; a993 = 0
    if B(A969) == 1 and B(A975) == 0:
        if B(A976) == 0:
            # OMP fault path: over-shoot when A974 > sat8(port, CAL38)
            if a974 > min((r & 0xFF) + CAL38, 255):
                a992 = 1
        else:
            # healthy path: under-shoot when A974 < band(port - CAL38)
            ru = r & 0xFF
            band = (ru - CAL38) if ru > CAL38 else 0
            if a974 < band:
                a993 = 1

    # step 3: trigger flags -> latch flags (reads counters pre-increment)
    W(A992, a992)
    W(A993, a993)
    if a992 == 1 and B(A994) >= CAL39:
        W(A990, 1)
    if a993 == 1 and B(A995) >= CAL3A:
        W(A991, 1)

    # step 4: debounce counters (sat8 increment or reset)
    W(A994, min(B(A994) + 1, 255) if a992 == 1 else 0)
    W(A995, min(B(A995) + 1, 255) if a993 == 1 else 0)
    return m


def seed_ram():
    ram = {}

    def fr(addr):
        v = random.randint(0, 255)
        ram[addr] = v
        return v

    # gate / fault inputs (edge-biased)
    ram[A969] = random.choice([0, 1, 0, 1, random.randint(0, 255)])
    ram[A975] = random.choice([0, 1, 0, random.randint(0, 255)])
    ram[A976] = random.choice([0, 1, 0, 1, random.randint(0, 255)])
    # position target: bias around port-relative bands computed later
    ram[A974] = random.choice([0, 1, 2, 0xFE, 0xFF, random.randint(0, 255)])
    # trigger / latch flags (only A990/A991 are kept if already set)
    ram[A992] = random.randint(0, 1)
    ram[A993] = random.randint(0, 1)
    ram[A990] = random.randint(0, 1)
    ram[A991] = random.randint(0, 1)
    # debounce counters: bias around CAL39 / CAL3A thresholds
    ram[A994] = random.choice([0, 61, 62, 63, 254, 255, random.randint(0, 255)])
    ram[A995] = random.choice([0, 124, 125, 126, 254, 255, random.randint(0, 255)])
    # idle/off port: valid complementary pair (edge values) or broken pair
    if random.random() < 0.7:
        v = random.choice([0, 1, 2, 0x37, 0x7F, 0x80, 0xFE, 0xFF,
                           random.randint(0, 255)])
        ram[P7A] = v
        ram[P7A + 1] = (~v) & 0xFF
    else:
        ram[P7A] = random.randint(0, 255)
        ram[P7A + 1] = random.randint(0, 255)
    ram[C6AC] = random.randint(0, 1)
    return ram


def edge_bias(ram):
    # make A974 straddle the computed band so both sides of each comparison
    # get exercised in the same iteration as the port value
    if random.random() < 0.5:
        rv = ram[P7A] & 0xFF
        if (ram[P7A] == ((~ram[P7A + 1]) & 0xFF)) and random.random() < 0.5:
            if random.random() < 0.5:
                ram[A974] = (rv + CAL38) & 0xFF        # == sat8(port,1) edge
            else:
                ram[A974] = (rv + CAL38 + 1) & 0xFF    # just above
        if random.random() < 0.5:
            band = (rv - CAL38) if rv > CAL38 else 0
            if random.random() < 0.5:
                ram[A974] = (band - 1) & 0xFF          # just below band
            else:
                ram[A974] = band                       # == band edge
    # force the gate to fire sometimes so the body paths are hammered
    if random.random() < 0.3:
        ram[A969] = 1
        ram[A975] = 0
    # force the debounce counters one step below / at / above threshold
    if random.random() < 0.5:
        ram[A994] = random.choice([0, 61, 62, 63])
    if random.random() < 0.5:
        ram[A995] = random.choice([0, 124, 125, 126])


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
    rom = open(ROM, 'rb').read()
    cpu = SH2(rom)
    seeds = (0x18CC0, 0xA992, 0xFEED, 0x1234, 0x7777)
    total_fails = 0

    for seed in seeds:
        random.seed(seed)
        fails = 0
        for it in range(N):
            ram = seed_ram()
            edge_bias(ram)
            want = model(ram)
            try:
                cpu.call(0x18CC0, ram=ram, sr=0xF0)
            except Exception as e:
                print('EMULATOR EXC seed=0x%X iter=%d: %s' % (seed, it, e))
                fails += 1
                break
            bad = []
            allk = set(k for k in want if isinstance(k, int)) | set(cpu.ram.keys())
            for k in allk:
                if 0xFFFFDE00 <= k <= 0xFFFFDF00:   # task stack area
                    continue
                got = cpu.ram.get(k, 0)
                exp = want.get(k, 0)
                if got != exp:
                    bad.append((k, got, exp))
            if bad:
                print('MISMATCH seed=0x%X iter=%d: %s' %
                      (seed, it, {hex(k): (hex(g), hex(e)) for k, g, e in bad[:12]}))
                print('  A969=%d A975=%d A976=%d A974=%d port=0x%02X%02X '
                      'A994=%d A995=%d' %
                      (ram[A969], ram[A975], ram[A976], ram[A974],
                       ram[P7A], ram[P7A + 1], ram[A994], ram[A995]))
                fails += 1
                if fails >= 3:
                    break
        print('  seed 0x%X: %d inputs, fails=%d' % (seed, N, fails))
        total_fails += fails
        if total_fails:
            break

    if total_fails:
        print('\n%d FAILURE(S)' % total_fails)
        sys.exit(1)
    print('OK  0x18CC0 omp_rotor_overshoot_detector_18CC0 companion  '
          '(%d random inputs across %d seeds)' % (N * len(seeds), len(seeds)))
    print('\nAll omp_rotor_overshoot_detector_18CC0 tests passed.')
    sys.exit(0)


if __name__ == '__main__':
    main()
