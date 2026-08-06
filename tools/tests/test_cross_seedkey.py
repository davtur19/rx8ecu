#!/usr/bin/env python3
"""
test_cross_seedkey.py — Cross-validate OUR seed/key implementation vs the
community implementation in ConnorRigby/rx8-ecu-dump.

WHAT IS CROSS-VALIDATED
------------------------
Ours (VERIFIED against stock ROM 60E1D400):
  * tools/mazda_security.py   : compute_key(), _clock()  (ECOMcat / Car Hacking
                                Handbook 24-bit Galois LFSR)
  * c/security_access.c       : lfsr_clock(), seed_key_related() (direct port
                                of the ROM routine @0x56ADA)
  * c/tests/test_seed_gen_5699A.py : seed GENERATION path (seed_gen @0x5699A)

Community (ConnorRigby/rx8-ecu-dump):
  * src/librx8.cpp RX8::calculateKey() — key COMPUTATION only.  The repo's
    getSeed() just reads the 3 seed bytes out of the ECU's `67 01 s0 s1 s2`
    response; seed GENERATION is done by the ECU itself, so the community
    implementation covers the SAME stage as our seed_key_related (key
    computation from a given 3-byte seed), NOT the seed_gen entropy loop.

  Source: https://github.com/ConnorRigby/rx8-ecu-dump
          commit 5c784eccd5d399c8593cecd13a6fcf0dcd973ae1 (main, v0.9.0,
          2022-11-05)
          file src/librx8.cpp, function RX8::calculateKey
          (Apache-2.0, reference only — no code copied into this repo).

REFERENCE VECTORS
-----------------
* 12/12 ROM-verified vectors (levels 1-4 x seeds {45820A, CBFED4, 123456},
  secret 'MazdA') extracted by emulating SeedKeyRelated @0x56ADA with
  tools/sh2emu.py — table in c/tests/test_security_access.py (ROM_VECTORS).

Run from repo root:  python3 tools/tests/test_cross_seedkey.py
Exit: 0 if both implementations agree on every case, 1 otherwise.
"""
import os
import random
import sys

# ---------------------------------------------------------------------------
# Our implementation — imported from the VERIFIED repo module.
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))
from mazda_security import compute_key, _clock        # noqa: E402

LFSR_INIT = 0xC541A9        # per-level init, level 1 (== community 0xc541a9)
LFSR_TAPS = 0x909028        # bits {23,20,15,12,5,3} (hardcoded in ROM @0x56C1E)
SECRET = b'MazdA'

# ---------------------------------------------------------------------------
# Community implementation — faithful Python port of RX8::calculateKey().
#
# ORIGINAL C++ (ConnorRigby/rx8-ecu-dump, src/librx8.cpp, commit 5c784ec):
#
#   size_t RX8::calculateKey(uint8_t* seedInput, uint8_t** keyOut)
#   {
#       *keyOut = (uint8_t*)malloc(3);
#       if (!(*keyOut)) return ENOMEM;
#
#       uint8_t secret[5] = MAZDA_KEY_SECRET;              // {'M','a','z','d','A'}
#       uint32_t seed = (seedInput[0] << 16) + (seedInput[1] << 8) + seedInput[2];
#       uint32_t or_ed_seed = ((seed & 0xFF0000) >> 16) | (seed & 0xFF00)
#                           | (secret[0] << 24) | (seed & 0xff) << 16;
#       uint32_t mucked_value = 0xc541a9;
#       for (size_t i = 0; i < 32; i++) {
#           uint32_t a_bit = ((or_ed_seed >> i) & 1 ^ mucked_value & 1) << 23;
#           uint32_t v9, v10, v8;
#           v9 = v10 = v8 = a_bit | (mucked_value >> 1);
#           mucked_value = v10 & 0xEF6FD7
#               | ((((v9 & 0x100000) >> 20) ^ ((v8 & 0x800000) >> 23)) << 20)
#               | (((((mucked_value >> 1) & 0x8000) >> 15)
#                   ^ ((v8 & 0x800000) >> 23)) << 15)
#               | (((((mucked_value >> 1) & 0x1000) >> 12)
#                   ^ ((v8 & 0x800000) >> 23)) << 12)
#               | 32 * ((((mucked_value >> 1) & 0x20) >> 5)
#                   ^ ((v8 & 0x800000) >> 23))
#               | 8 * ((((mucked_value >> 1) & 8) >> 3)
#                   ^ ((v8 & 0x800000) >> 23));
#       }
#       for (size_t j = 0; j < 32; j++) {
#           uint32_t a_bit = ((((secret[4] << 24) | (secret[3] << 16)
#                           | secret[1] | (secret[2] << 8)) >> j) & 1
#                           ^ mucked_value & 1) << 23;
#           uint32_t v14, v13, v12;
#           v14 = v13 = v12 = a_bit | (mucked_value >> 1);
#           mucked_value = v14 & 0xEF6FD7
#               | ((((v13 & 0x100000) >> 20) ^ ((v12 & 0x800000) >> 23)) << 20)
#               | (((((mucked_value >> 1) & 0x8000) >> 15)
#                   ^ ((v12 & 0x800000) >> 23)) << 15)
#               | (((((mucked_value >> 1) & 0x1000) >> 12)
#                   ^ ((v12 & 0x800000) >> 23)) << 12)
#               | 32 * ((((mucked_value >> 1) & 0x20) >> 5)
#                   ^ ((v12 & 0x800000) >> 23))
#               | 8 * ((((mucked_value >> 1) & 8) >> 3)
#                   ^ ((v12 & 0x800000) >> 23));
#       }
#       uint32_t key = ((mucked_value & 0xF0000) >> 16) | 16 * (mucked_value & 0xF)
#                   | ((((mucked_value & 0xF00000) >> 20)
#                       | ((mucked_value & 0xF000) >> 8)) << 8)
#                   | ((mucked_value & 0xFF0) >> 4 << 16);
#       (*keyOut)[0] = (key & 0xff0000) >> 16;
#       (*keyOut)[1] = (key & 0xff00) >> 8;
#       (*keyOut)[2] = key & 0xff;
#       return 0;
#   }
#
# The C++ is itself a decompiler-style port of the same stock ROM routine
# (variable names v8/v9/v10/v12/v13/v14, "mucked_value").  Decoded:
#   * init state 0xc541a9 == our LFSR_INIT (level-1 table entry, ROM @0x5FAC8);
#   * mask 0xEF6FD7 clears tap bits {3,5,12,15,20}; the OR terms recompute them
#     as (shifted bit) XOR feedback and place feedback at bit 23  == Galois
#     clock with taps 0x909028, bit-for-bit our _clock();
#   * phase-1 input or_ed_seed = seed[0] | seed[1]<<8 | seed[2]<<16 |
#     secret[0]<<24 (LSB-first) == our w1;
#   * phase-2 input (secret[4]<<24 | secret[3]<<16 | secret[2]<<8 | secret[1])
#     LSB-first == our w2;
#   * key = b0 | b1<<8 | b2<<16, returned as bytes [b2, b1, b0] == our
#     nibble-interleave extraction.
# ---------------------------------------------------------------------------

COMMUNITY_TAPS_MASK = 0xEF6FD7   # 0xEF6FD7 == all taps cleared except bit 23


def community_clock(state, inp):
    """One Galois clock, transcribed 1:1 from the C++ mucked_value update."""
    a_bit = (((inp & 1) ^ (state & 1)) << 23)       # feedback into bit 23
    v8 = v9 = v10 = a_bit | (state >> 1)
    new = (v10 & COMMUNITY_TAPS_MASK
           | ((((v9 & 0x100000) >> 20) ^ ((v8 & 0x800000) >> 23)) << 20)
           | (((((state >> 1) & 0x8000) >> 15) ^ ((v8 & 0x800000) >> 23)) << 15)
           | (((((state >> 1) & 0x1000) >> 12) ^ ((v8 & 0x800000) >> 23)) << 12)
           | 32 * ((((state >> 1) & 0x20) >> 5) ^ ((v8 & 0x800000) >> 23))
           | 8 * ((((state >> 1) & 8) >> 3) ^ ((v8 & 0x800000) >> 23)))
    return new & 0xFFFFFF


def community_calculateKey(seedInput):
    """RX8::calculateKey port.  seedInput: 3 bytes; returns 3-byte key."""
    secret = [0x4d, 0x61, 0x7a, 0x64, 0x41]         # 'M','a','z','d','A'
    seed = (seedInput[0] << 16) + (seedInput[1] << 8) + seedInput[2]
    or_ed_seed = ((seed & 0xFF0000) >> 16) | (seed & 0xFF00) \
        | (secret[0] << 24) | ((seed & 0xff) << 16)
    mucked = 0xc541a9
    for i in range(32):
        mucked = community_clock(mucked, (or_ed_seed >> i) & 1)
    w2 = (secret[4] << 24) | (secret[3] << 16) | secret[1] | (secret[2] << 8)
    for j in range(32):
        mucked = community_clock(mucked, (w2 >> j) & 1)
    b0 = ((mucked & 0xF0000) >> 16) | 16 * (mucked & 0xF)
    b1 = ((mucked & 0xF00000) >> 20) | ((mucked & 0xF000) >> 8)
    b2 = (mucked & 0xFF0) >> 4
    key = b0 | (b1 << 8) | (b2 << 16)
    return bytes([(key & 0xff0000) >> 16, (key & 0xff00) >> 8, key & 0xff])


# ---------------------------------------------------------------------------
# ROM-verified reference vectors (12/12) — extracted by emulating
# SeedKeyRelated @0x56ADA with tools/sh2emu.py; table ROM_VECTORS in
# c/tests/test_security_access.py.  (level, seed, key)
# ---------------------------------------------------------------------------
ROM_VECTORS = [
    (1, '45820A', 'A07258'), (2, '45820A', '30823E'),
    (3, '45820A', '4F850D'), (4, '45820A', 'F81A48'),
    (1, 'CBFED4', '75491A'), (2, 'CBFED4', 'E5B97C'),
    (3, 'CBFED4', '9ABE4F'), (4, 'CBFED4', '2D210A'),
    (1, '123456', '86CA06'), (2, '123456', '163A60'),
    (3, '123456', '693D53'), (4, '123456', 'DEA216'),
]

# Live-capture seed (rnd-ash wiki, bench RX-8 ICM) was previously used here as
# an input vector.  It was captured with a tuning tool (VersaTuner), NOT from a
# stock PCM, so its seed/key pair is not stock-key evidence — removed.

ROM_PATH = os.path.join(os.path.dirname(__file__), os.pardir, os.pardir,
                        'roms', 'stock', '60E1D400.bin')


def rom_reference_key(level, seed_hex):
    """Reference model derived from the SeedKeyRelated disassembly (per-level
    init table @0x5FAC5, 64-bit LSB-first stream seed+secret, 64 Galois
    clocks with taps 0x909028, nibble extraction).  Same as rom_lfsr() in
    c/tests/test_security_access.py."""
    with open(ROM_PATH, 'rb') as f:
        f.seek(0x5FAC5)
        table = f.read(24)
    t = table[level * 3: level * 3 + 3]
    state = (t[0] << 16) | (t[1] << 8) | t[2]
    buf = int.from_bytes(bytes.fromhex(seed_hex) + b'MazdA', 'little')
    for _ in range(64):
        fb = (buf & 1) ^ (state & 1)
        buf >>= 1
        state >>= 1
        if fb:
            state ^= LFSR_TAPS
        state &= 0xFFFFFF
    s0 = state & 0xFF
    s1 = (state >> 8) & 0xFF
    s2 = (state >> 16) & 0xFF
    return bytes([((s1 & 0x0F) << 4) | ((s0 & 0xF0) >> 4),
                  (s1 & 0xF0) | ((s2 & 0xF0) >> 4),
                  ((s0 & 0x0F) << 4) | (s2 & 0x0F)])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
def test_clock_equivalence(n=100000):
    """Prove community_clock == our _clock on random (state, bit) inputs."""
    rng = random.Random(20260804)
    mism = 0
    for _ in range(n):
        st = rng.getrandbits(24)
        b = rng.getrandbits(1)
        if _clock(st, b) != community_clock(st, b):
            mism += 1
    print(f"  clock equivalence (_clock vs community_clock): {n} cases, "
          f"{mism} mismatches")
    return mism == 0


def test_rom_vectors():
    """Both implementations vs the ROM-verified vectors.
    Level 1 (init 0xC541A9) is the cross-implementation-comparable set: both
    our compute_key() and the community calculateKey() hardcode 0xC541A9.
    Levels 2-4 need the per-level table (@0x5FAC5) — only our ROM reference
    model covers them (12/12), reported for completeness."""
    all_ok = True
    l1_ok = True
    print("  ── level 1 (init 0xC541A9): ours == community == ROM-verified ──")
    for level, seed_hex, want_hex in ROM_VECTORS:
        if level != 1:
            continue
        seed = bytes.fromhex(seed_hex)
        ours = compute_key(seed, SECRET)
        comm = community_calculateKey(seed)
        ok = ours.hex().upper() == want_hex and comm == ours
        l1_ok = l1_ok and ok
        all_ok = all_ok and ok
        print(f"    seed {seed_hex}: ours={ours.hex().upper()} "
              f"community={comm.hex().upper()} want={want_hex} "
              f"{'PASS' if ok else 'FAIL'}")
    print("  ── levels 1-4 via our ROM reference model (12/12) ──")
    rom_ok = True
    if not os.path.exists(ROM_PATH):
        print(f"    SKIP: ROM not found at {ROM_PATH}")
    else:
        for level, seed_hex, want_hex in ROM_VECTORS:
            got = rom_reference_key(level, seed_hex)
            ok = got.hex().upper() == want_hex
            rom_ok = rom_ok and ok
            all_ok = all_ok and ok
            print(f"    level={level} seed={seed_hex}: ref={got.hex().upper()} "
                  f"want={want_hex} {'PASS' if ok else 'FAIL'}")
    return all_ok, l1_ok, rom_ok


def test_random_seeds(n=400):
    """Fixed pseudo-random seeds: ours vs community must agree everywhere."""
    rng = random.Random(0xC541A9)   # fixed seed -> reproducible
    mismatches = []
    for _ in range(n):
        seed = bytes([rng.getrandbits(8) for _ in range(3)])
        ours = compute_key(seed, SECRET)
        comm = community_calculateKey(seed)
        if ours != comm:
            mismatches.append((seed.hex().upper(), ours.hex().upper(),
                               comm.hex().upper()))
            if len(mismatches) >= 5:
                break
    if mismatches:
        print(f"  {n} random seeds: {n - len(mismatches)} match, "
              f"{len(mismatches)}+ divergent (first 5):")
        for s, o, c in mismatches[:5]:
            print(f"    seed {s}: ours={o} community={c}")
    else:
        print(f"  {n} random seeds: ours == community, 0 mismatches")
    return not mismatches


def main():
    print("═" * 70)
    print("Seed/key cross-validation: repo (VERIFIED) vs ConnorRigby/rx8-ecu-dump")
    print("community implementation (librx8.cpp calculateKey @ 5c784ec)")
    print("═" * 70)

    results = {}
    print("\n─── 1. LFSR clock equivalence ───")
    results['clock_eq'] = test_clock_equivalence()
    print("\n─── 2. ROM-verified vectors ───")
    all_ok, l1_ok, rom_ok = test_rom_vectors()
    results['level1_vectors'] = l1_ok
    results['rom_12of12'] = rom_ok
    print("\n─── 3. 400 fixed random seeds (ours vs community) ───")
    results['random_400'] = test_random_seeds(400)

    print("\n" + "═" * 70)
    for name, ok in results.items():
        print(f"  {'PASS' if ok else 'FAIL'}: {name}")
    verdict = all(results.values())
    if verdict:
        print("\n  VERDICT: CONFIRMED-CROSS — the two implementations are the "
              "same transformation")
        print("           (seed GENERATION stays on the ECU; the KEY "
              "computation is identical:")
        print("           24-bit Galois LFSR, init 0xC541A9, taps 0x909028, "
              "64-bit LSB-first")
        print("           stream seed+'MazdA', nibble-interleave extraction).")
    else:
        print("\n  VERDICT: MISMATCH — see rows above.")
    print("═" * 70)
    return verdict


if __name__ == '__main__':
    sys.exit(0 if main() else 1)
