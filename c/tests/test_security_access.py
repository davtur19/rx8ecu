#!/usr/bin/env python3
"""
test_security_access.py — Verification of the Mazda RX-8 SecurityAccess LFSR

Tests the 24-bit Galois LFSR seed↔key algorithm against:
  1. The existing mazda_security.py implementation
  2. Real-world CAN captures ([REDACTED]-tuned ECU)
  3. Cross-checks with the ROM data tables at 0x5FAC0
  4. ROM-verified reference vectors (SeedKeyRelated @0x56ADA, emulated)

STATUS UPDATE (2026-07-31): the stock-vs-ECOMcat discrepancy is RESOLVED.
  The ECOMcat LFSR (init 0xC541A9, taps 0x909028) IS the stock ROM algorithm.
  The legacy stock vector 0x3B15E1 was wrong; the ROM-verified value for
  seed 0x45820A / 'MazdA' / level 1 is 0xA07258.  See the module docstring
  in tools/mazda_security.py and the evidence comment block in
  c/security_access.c (seed_key_related).  RESOLVED 2026-08-01, commit
  a84eaba: stock LFSR is ECOMcat 24-bit Galois, ROM-verified vector 0xA07258;
  see tools/mazda_security.py.

References:
  - tools/mazda_security.py     (ECOMcat / Car Hacking Handbook)
  - c/security_access.c         (C reconstruction)
  - ROM 60E1D400.bin @ 0x584A0  (SecurityAccess handler)
  - ROM 60E1D400.bin @ 0x56ADA  (SeedKeyRelated key routine)
  - ROM 60E1D400.bin @ 0x5FAC0  (secret "MazdA")
  - ROM 60E1D400.bin @ 0x5FAC5  (per-level LFSR INIT table, 3 bytes/level)
"""

import os
import sys
import struct

# mazda_security.py lives in tools/ (2 levels up from c/tests/ -> repo root/tools).
sys.path.insert(0, os.path.join(os.path.dirname(__file__),
                os.pardir, os.pardir, 'tools'))
from mazda_security import compute_key, _clock


# ═══════════════════════════════════════════════════════════════════
# 1.  LFSR core reference — the canonical 24-bit Galois LFSR
# ═══════════════════════════════════════════════════════════════════

LFSR_INIT = 0xC541A9
LFSR_TAPS = 0x909028   # from ECOMcat literature: bits 23,20,15,12,5,3

# ROM 60E1D400 @ 0x5FAC5 stores a PER-LEVEL INIT table (3 bytes/level), not
# (init,taps) pairs:
#   level 1 (0x5FAC8): C5 41 A9 -> init 0xC541A9  (== LFSR_INIT)
#   level 2 (0x5FACB): A3 95 82 -> init 0xA39582  (was misread as "ROM taps")
# The TAPS are hardcoded in the ROM code (SeedKeyRelated @0x56ADA, xor
# #8/#32/#16/#128/#16 at 0x56C1E-0x56C38 == 0x909028), so 0xA39582 is an
# INIT value, not an alternative tap mask.
ROM_INIT_L1 = 0xC541A9   # == ECOMcat init; ROM @0x5FAC8 (level 1 entry)


def lfsr_clock(state, inp_bit):
    """Single 24-bit Galois LFSR clock with external input bit."""
    fb = (state & 1) ^ inp_bit
    state >>= 1
    if fb:
        state ^= LFSR_TAPS
    return state & 0xFFFFFF


def compute_key_ref(seed_bytes, secret_bytes, init=LFSR_INIT, taps=LFSR_TAPS):
    """
    Reference key computation matching mazda_security.py.
    
    The existing Python implementation is a 24-bit LFSR with:
      - Phase 1: clock 32 bits of w1 (secret[0] + seed bytes shuffled)
      - Phase 2: clock 32 bits of w2 (secret[4..1])
      - Key extraction: nibble permutation of final state
    """
    s1, s2, s3, s4, s5 = secret_bytes
    seed = (seed_bytes[0] << 16) | (seed_bytes[1] << 8) | seed_bytes[2]

    # Phase 1 input: s1 MSB, seed bytes LSB (shuffled)
    w1 = (s1 << 24) | ((seed & 0xFF) << 16) | (seed & 0xFF00) | ((seed >> 16) & 0xFF)

    # Phase 2 input: s5..s2 packed LE
    w2 = (s5 << 24) | (s4 << 16) | (s3 << 8) | s2

    state = init
    for i in range(32):
        fb = (state & 1) ^ ((w1 >> i) & 1)
        state >>= 1
        if fb:
            state ^= taps
        state &= 0xFFFFFF

    for i in range(32):
        fb = (state & 1) ^ ((w2 >> i) & 1)
        state >>= 1
        if fb:
            state ^= taps
        state &= 0xFFFFFF

    # Key extraction: nibble permutation
    b0 = ((state >> 16) & 0xF) | (((state) & 0xF) << 4)
    b1 = ((state >> 20) & 0xF) | (((state >> 12) & 0xF) << 4)
    b2 = (state >> 4) & 0xFF

    # Byte swap: return [b2, b1, b0]
    return bytes([b2, b1, b0])


# ═══════════════════════════════════════════════════════════════════
# 2.  ROM-data-driven LFSR (using parameters stored in the binary)
# ═══════════════════════════════════════════════════════════════════

ROM_PATH = os.path.join(os.path.dirname(__file__),
                        os.pardir, os.pardir,
                        'roms', 'stock', '60E1D400.bin')


def get_rom_lfsr_params():
    """Read the LFSR parameters directly from the ROM binary.
    
    ROM layout at 0x5FAC0:
      0x5FAC0:  4D 61 7A 64 41  FF FF FF  C5 41 A9  A3 95 82  FF FF
                'M' 'a' 'z' 'd' 'A'  pad pad pad  init[2..0] taps[2..0] pad pad
    
    The per-level INIT table starts at 0x5FAC5 (3 bytes per level, indexed by
    level*3).  The SeedKeyRelated code (0x56B1E-0x56B40) loads entry[2] into
    the LOW state byte and entry[0] into the HIGH state byte, i.e. the 24-bit
    init = entry[0]<<16 | entry[1]<<8 | entry[2].  Level 1 therefore reads
    C5 41 A9 -> 0xC541A9 (== ECOMcat init).  Level 2 reads A3 95 82 ->
    0xA39582 (a level-2 INIT, previously misread as "alternative taps").
    """
    with open(ROM_PATH, 'rb') as f:
        f.seek(0x5FAC0)
        data = f.read(16)

    secret = data[0:5]        # "MazdA"
    
    # Level 1 entry (init):   data[8:11]  = 0xC5, 0x41, 0xA9  -> 0xC541A9
    # Level 2 entry (init):   data[11:14] = 0xA3, 0x95, 0x82  -> 0xA39582
    init_raw = data[8:11]
    taps_raw = data[11:14]
    
    # Verified byte order (SeedKeyRelated disasm 0x56B1E-0x56B40):
    #   state_hi = entry[0], state_mid = entry[1], state_lo = entry[2]
    lfsr_init = (init_raw[0] << 16) | (init_raw[1] << 8) | init_raw[2]
    lfsr_taps_rom = (taps_raw[0] << 16) | (taps_raw[1] << 8) | taps_raw[2]
    
    return secret, lfsr_init, lfsr_taps_rom


def compute_key_rom_params(seed_bytes, secret_bytes, init, taps):
    """
    Alternative key computation using the RAW byte order from ROM.
    The ROM stores LFSR parameters with reversed byte order.
    """
    # Use the standard LFSR but with ROM-order parameters
    return compute_key_ref(seed_bytes, secret_bytes, init, taps)


# ═══════════════════════════════════════════════════════════════════
# 3.  Test vectors
# ═══════════════════════════════════════════════════════════════════

# Known stock test vector (ROM-VERIFIED, 2026-07-31)
#   seed 0x45820A / secret 'MazdA' / level 1 -> key 0xA07258.
#   Verified three ways: (a) sh2emu emulation of SeedKeyRelated @0x56ADA
#   reads the same state bytes the ROM compares at 0x56CC4; (b) a reference
#   implementation derived from the disassembly reproduces it; (c) the
#   existing ECOMcat compute_key() already produces it.
#   The legacy value 0x3B15E1 (kept for history) had NO ROM/emulation
#   support and was the cause of the old self_test FAIL; docs/notes/RESUME.md
#   still lists the stock algorithm as open — that entry is now out of date.
STOCK_TEST = {
    'secret': b'MazdA',
    'seed': bytes([0x45, 0x82, 0x0A]),
    'expected_key': bytes([0xA0, 0x72, 0x58]),
    'legacy_wrong_key': bytes([0x3B, 0x15, 0xE1]),  # historical, superseded
}

# Real-world captures from [REDACTED]-tuned ECU (from mazda_security.py)
REAL_CAPTURES = [
    {'secret': b'vendor-family secret', 'seed': bytes.fromhex('CBFED4'), 'expected': bytes.fromhex('[REDACTED]')},
    {'secret': b'vendor-family secret', 'seed': bytes.fromhex('[REDACTED]'), 'expected': bytes.fromhex('[REDACTED]')},
    {'secret': b'vendor-family secret', 'seed': bytes.fromhex('[REDACTED]'), 'expected': bytes.fromhex('[REDACTED]')},
]


# ═══════════════════════════════════════════════════════════════════
# 4.  Tests
# ═══════════════════════════════════════════════════════════════════

def test_mazda_security_self_test():
    """Verify the mazda_security.py module's own self-test vectors.

    HISTORICAL NOTE: this test used to FAIL.  The expected stock key was the
    legacy value 0x3B15E1, which the ROM does not produce.  The discrepancy
    is now resolved: the ROM (SeedKeyRelated @0x56ADA, emulated) computes
    0xA07258 for this seed/secret/level, and the existing ECOMcat compute_key
    already yields 0xA07258 — the vector, not the algorithm, was wrong.
    (docs/notes/RESUME.md still lists the stock LFSR as an open issue; that
    entry is out of date.)
    """
    result = compute_key(STOCK_TEST['seed'], STOCK_TEST['secret'])
    expected = STOCK_TEST['expected_key']
    
    ok = result == expected
    print(f"\n  Stock self-test:     seed={STOCK_TEST['seed'].hex()}, "
          f"secret={STOCK_TEST['secret']}")
    print(f"    Computed: {result.hex()}")
    print(f"    Expected: {expected.hex()}  (ROM-verified, was 3B15E1)")
    print(f"    Result:   {'PASS' if ok else 'FAIL'}")
    
    if not ok:
        print(f"    NOTE: see test_rom_reference_vectors for the emulator/"
              f"disassembly-derived ROM reference vectors.")
    
    return ok


def test_real_captures():
    """Verify the real-world CAN captures from [REDACTED]-tuned ECU."""
    all_ok = True
    print(f"\n  Real-world captures (secret=vendor-family secret):")
    for tc in REAL_CAPTURES:
        result = compute_key(tc['seed'], tc['secret'])
        ok = result == tc['expected']
        print(f"    seed={tc['seed'].hex()}: {result.hex()} "
              f"{'== ' + tc['expected'].hex() if ok else '!= ' + tc['expected'].hex()}"
              f"  {'PASS' if ok else 'FAIL'}")
        all_ok = all_ok and ok
    
    return all_ok


def test_rom_data_integrity():
    """Cross-check the ROM binary data at the secret/LFSR locations."""
    print(f"\n  ROM data integrity:")
    
    if not os.path.exists(ROM_PATH):
        print(f"    SKIP: ROM file not found at {ROM_PATH}")
        return True
    
    secret, lfsr_init, lfsr_taps = get_rom_lfsr_params()
    
    print(f"    ROM secret:         {secret}  ({secret.hex()})")
    print(f"    ROM LFSR init:      0x{lfsr_init:06X}")
    print(f"    ROM LFSR taps:      0x{lfsr_taps:06X}")
    print(f"    (ECOMcat init:      0x{LFSR_INIT:06X})")
    print(f"    (ECOMcat taps:      0x{LFSR_TAPS:06X})")
    
    # Check if the secret in ROM matches
    ok = (secret == STOCK_TEST['secret'])
    print(f"    Secret match:       {'PASS' if ok else 'FAIL'}")
    if not ok:
        print(f"      Expected: {STOCK_TEST['secret']}, Got: {secret}")
    
    return ok


def test_rom_params_vs_standard():
    """
    Compare the ROM-stored LFSR parameters against the ECOMcat standard.
    
    RESOLVED (2026-07-31): the ROM table at 0x5FAC5 is a PER-LEVEL INIT
    table, not an (init, taps) pair list:
      Level 1 entry (0x5FAC8): C5 41 A9 -> state 0xC541A9 == ECOMcat init.
      Level 2 entry (0x5FACB): A3 95 82 -> state 0xA39582 (level-2 INIT,
      previously misread as "alternative taps").
    The TAPS are not stored in the table at all — they are hardcoded in the
    SeedKeyRelated code (xor #8/#32/#16/#128/#16 @0x56C1E-0x56C38, plus the
    OR 0x80 feedback into bit 23 == 0x909028 == ECOMcat taps).
    """
    print(f"\n  ROM vs ECOMcat parameter comparison:")
    
    _, rom_init, rom_taps = get_rom_lfsr_params()
    
    print(f"    ROM level-1 init (MSB-first):   0x{rom_init:06X}")
    print(f"    ECOMcat init:                   0x{LFSR_INIT:06X}")
    print(f"    Match:                          {rom_init == LFSR_INIT}")
    
    print(f"    ROM level-2 init (MSB-first):   0x{rom_taps:06X}")
    print(f"    ECOMcat taps:                   0x{LFSR_TAPS:06X}")
    print(f"    (Not comparable: 0xA39582 is a level-2 INIT value, not taps.)")
    
    print(f"\n  NOTE: The old reading ('ROM stores taps=0xA39582 which do not ")
    print(f"  match ECOMcat 0x909028') was based on misreading the per-level ")
    print(f"  init table.  The ROM code hardcodes taps 0x909028 (disasm ")
    print(f"  0x56C1E-0x56C38); the table only supplies per-level INIT states. ")


def test_all_tap_permutations():
    """
    Verify the ROM-stored init values against the verified ECOMcat algorithm.

    HISTORICAL NOTE: this test used to FAIL.  It brute-forced all byte-order
    permutations of the ROM table trying to reproduce the legacy vector
    0x3B15E1 — which the ROM never produces.  With the ROM-verified vector
    0xA07258 (seed 0x45820A / 'MazdA' / level 1) the search succeeds: the
    ROM level-1 init C5 41 A9 -> 0xC541A9 == ECOMcat init, and the taps are
    hardcoded in ROM code as 0x909028 (SeedKeyRelated @0x56C1E-0x56C38).
    The algorithm is the ECOMcat Galois LFSR; docs/notes/RESUME.md's "open
    issue" entry is out of date.
    """
    print(f"\n  ROM param vs ECOMcat verification:")
    
    rom_data_at_5fac8 = bytes([0xC5, 0x41, 0xA9, 0xA3, 0x95, 0x82])
    
    import itertools
    
    init_bytes = rom_data_at_5fac8[0:3]
    lvl2_bytes = rom_data_at_5fac8[3:6]   # level-2 INIT (not taps)
    
    # Verify the ROM level-1 init reproduces the ROM-verified stock vector
    # when paired with the ECOMcat taps (hardcoded in the ROM code).
    found = False
    for init_perm in itertools.permutations(init_bytes):
        init_val = (init_perm[0] << 16) | (init_perm[1] << 8) | init_perm[2]
        for taps_val in (LFSR_TAPS,):     # taps are hardcoded in ROM code
            key = compute_key_ref(STOCK_TEST['seed'], STOCK_TEST['secret'],
                                  init_val, taps_val)
            if key == STOCK_TEST['expected_key']:
                print(f"    FOUND: init=0x{init_val:06X} "
                      f"(bytes={bytes(init_perm).hex()}) "
                      f"taps=0x{taps_val:06X} (hardcoded in ROM code) "
                      f"-> key {key.hex()} == expected")
                found = True
    
    if not found:
        print(f"    No init permutation of the ROM level-1 entry reproduces "
              f"the ROM-verified stock vector {STOCK_TEST['expected_key'].hex()} "
              f"with ECOMcat taps 0x{LFSR_TAPS:06X}.")
        print(f"    (The old failure — searching for legacy vector 3B15E1 — "
              f"was caused by that vector being wrong, not by the algorithm.)")
    
    # Cross-check: the legacy brute-force result (no permutation of the ROM
    # params reproduced 0x3B15E1) is consistent with 0x3B15E1 being wrong.
    legacy = STOCK_TEST['legacy_wrong_key']
    legacy_hit = any(
        compute_key_ref(STOCK_TEST['seed'], STOCK_TEST['secret'],
                        (p[0] << 16) | (p[1] << 8) | p[2],
                        (q[0] << 16) | (q[1] << 8) | q[2]) == legacy
        for p in itertools.permutations(init_bytes)
        for q in itertools.permutations(lvl2_bytes))
    print(f"    (Legacy check: any param permutation produce old 3B15E1? "
          f"{'yes' if legacy_hit else 'no — as expected, 3B15E1 is unsupported'})")
    
    return found


def test_rom_reference_vectors():
    """
    ROM-verified reference vectors for the stock 60E1D400 SeedKeyRelated.

    Vectors were extracted by emulating the handler at 0x56ADA with
    tools/sh2emu.py and reading the three state bytes at the ROM's own
    comparison point (0x56CC4), for levels 1-4 x seeds {45820A, CBFED4,
    123456}, secret 'MazdA' (ROM @0x5FAC0).  They are additionally
    reproduced by a reference implementation derived purely from the
    disassembly (init from table @0x5FAC5 per level, 64-bit LSB-first input
    stream seed[0..2]+secret[0..4], 64 Galois clocks with taps 0x909028,
    nibble extraction) — 21/21 matches across levels 0-6.

    compute_key() (ECOMcat, fixed init 0xC541A9) must match the level-1
    vectors; levels 2-4 are checked via the table-driven ROM reference.
    """
    print(f"\n  ROM reference vectors (SeedKeyRelated @0x56ADA, emulated):")

    # (level, seed, key) extracted from the ROM handler via sh2emu
    # (state bytes at compare 0x56CC4, secret 'MazdA' from ROM @0x5FAC0).
    ROM_VECTORS = [
        (1, '45820A', 'A07258'), (2, '45820A', '30823E'),
        (3, '45820A', '4F850D'), (4, '45820A', 'F81A48'),
        (1, 'CBFED4', '75491A'), (2, 'CBFED4', 'E5B97C'),
        (3, 'CBFED4', '9ABE4F'), (4, 'CBFED4', '2D210A'),
        (1, '123456', '86CA06'), (2, '123456', '163A60'),
        (3, '123456', '693D53'), (4, '123456', 'DEA216'),
    ]

    with open(ROM_PATH, 'rb') as f:
        f.seek(0x5FAC5)
        ROM_TABLE = f.read(24)      # per-level init table, 3 bytes/level

    def rom_lfsr(level, seed_hex):
        """Reference implementation derived from SeedKeyRelated disassembly."""
        t = ROM_TABLE[level * 3: level * 3 + 3]
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

    all_ok = True
    for level, seed_hex, want_hex in ROM_VECTORS:
        want = bytes.fromhex(want_hex)
        got = rom_lfsr(level, seed_hex)
        ok = (got == want)
        all_ok = all_ok and ok
        print(f"    level={level} seed={seed_hex}: ref={got.hex().upper()} "
              f"{'==' if ok else '!='} {want_hex}  {'PASS' if ok else 'FAIL'}")

    # Cross-check: ECOMcat compute_key (fixed init 0xC541A9 == ROM level 1)
    for level, seed_hex, want_hex in ROM_VECTORS:
        if level == 1:
            got = compute_key(bytes.fromhex(seed_hex), b'MazdA')
            ok = got == bytes.fromhex(want_hex)
            all_ok = all_ok and ok
            print(f"    compute_key lvl1 seed={seed_hex}: {got.hex().upper()} "
                  f"{'==' if ok else '!='} {want_hex}  {'PASS' if ok else 'FAIL'}")

    return all_ok


def test_key_byte_swap():
    """
    The existing mazda_security.py applies a final byte swap to the
    computed key: return [b2, b1, b0].  The ROM stores the key in a
    different order.  Test if the byte swap is correct.
    """
    print(f"\n  Key byte-order verification:")
    
    # Test with a known seed/key pair
    for tc in REAL_CAPTURES:
        result = compute_key(tc['seed'], tc['secret'])
        
        # Try without the final byte swap
        seed = (tc['seed'][0] << 16) | (tc['seed'][1] << 8) | tc['seed'][2]
        s1, s2, s3, s4, s5 = tc['secret']
        w1 = (s1 << 24) | ((seed & 0xFF) << 16) | (seed & 0xFF00) | ((seed >> 16) & 0xFF)
        w2 = (s5 << 24) | (s4 << 16) | (s3 << 8) | s2
        
        state = LFSR_INIT
        for i in range(32):
            state = _clock(state, (w1 >> i) & 1)
        for i in range(32):
            state = _clock(state, (w2 >> i) & 1)
        
        # No swap
        noswap = bytes([(state >> 16) & 0xFF, (state >> 8) & 0xFF, state & 0xFF])
        
        # With mazda_swap
        swapped = compute_key(tc['seed'], tc['secret'])
        
        # Try all 6 permutations
        import itertools
        for perm in itertools.permutations([(state >> 16) & 0xFF, (state >> 8) & 0xFF, state & 0xFF]):
            candidate = bytes(perm)
            if candidate == tc['expected']:
                print(f"    seed={tc['seed'].hex()}: key permutation {perm} = "
                      f"{candidate.hex()} matches!")
                break
        else:
            print(f"    seed={tc['seed'].hex()}: noswap={noswap.hex()}, "
                  f"swapped={swapped.hex()}, expected={tc['expected'].hex()}")
    
    return True


# ═══════════════════════════════════════════════════════════════════
# 5.  Main
# ═══════════════════════════════════════════════════════════════════

def main():
    print("═" * 60)
    print("Mazda RX-8 SecurityAccess LFSR — Test Suite")
    print("═" * 60)
    
    results = {}
    
    print("\n─── 1. Self-test (stock secret 'MazdA') ───")
    results['self_test'] = test_mazda_security_self_test()
    
    print("\n─── 2. Real-world captures ([REDACTED] 'vendor-family secret') ───")
    results['real_captures'] = test_real_captures()
    
    print("\n─── 3. ROM data integrity ───")
    results['rom_integrity'] = test_rom_data_integrity()
    
    print("\n─── 4. ROM vs ECOMcat params ───")
    test_rom_params_vs_standard()
    
    print("\n─── 5. ROM param vs ECOMcat (was: brute-force search) ───")
    results['param_search'] = test_all_tap_permutations()
    
    print("\n─── 5b. ROM reference vectors (SeedKeyRelated @0x56ADA) ───")
    results['rom_reference_vectors'] = test_rom_reference_vectors()
    
    print("\n─── 6. Key byte-order verification ───")
    test_key_byte_swap()
    
    # Summary
    print("\n" + "═" * 60)
    print("SUMMARY")
    print("═" * 60)
    all_pass = True
    for name, ok in results.items():
        status = "PASS" if ok else "FAIL"
        all_pass = all_pass and ok
        print(f"  {status}: {name}")
    
    print(f"\n  Overall: {'ALL TESTS PASS' if all_pass else 'SOME TESTS FAILED'}")
    
    # Interpretation
    print("\n" + "─" * 60)
    print("KEY FINDINGS")
    print("─" * 60)
    print("""
  1. RESOLVED (2026-07-31): the ECOMcat LFSR (init 0xC541A9, taps 0x909028)
     IS the stock ROM 60E1D400 algorithm.  compute_key() now passes the stock
     self-test with the ROM-verified vector 0xA07258 (was 0x3B15E1, which was
     wrong and caused the old failure).

  2. The ROM table at 0x5FAC5 is a PER-LEVEL INIT table (3 bytes/level):
       level 1 (0x5FAC8): C5 41 A9 -> 0xC541A9 (== ECOMcat init)
       level 2 (0x5FACB): A3 95 82 -> 0xA39582 (level-2 init; previously
       misread as "alternative taps").  The taps are hardcoded in the ROM
       code (SeedKeyRelated @0x56C1E-0x56C38: xor #8/#32/#16/#128/#16 +
       feedback OR 0x80 == 0x909028).

  3. The ROM reference-vector test validates levels 1-4 x 3 seeds (12
     vectors) extracted by emulating SeedKeyRelated @0x56ADA; the reference
     also matches the existing compute_key() at level 1 and reproduces all 3
     real-world [REDACTED] captures ('vendor-family secret').

  4. Seed-key handling differs from ECOMcat only in structure, not in the
     LFSR core: the ROM feeds a 64-bit LSB-first stream
     (seed[0],seed[1],seed[2],secret[0..4]) through 64 Galois clocks and
     extracts the key via nibble permutations; compute_key's word-packing is
     bit-equivalent to that stream for level 1.

  5. Remaining unknowns: exact UDS-handler-level semantics (which subfunction
     maps to which level), and the seed GENERATION path (seed_gen @0x5699A
     entropy loop).  The seed↔key transform itself is solved.
""")

    # Propagate pass/fail to the process exit code so CI / scripts can rely
    # on the return status (previously main() never called sys.exit, so a
    # FAIL still exited 0).
    return all_pass


if __name__ == '__main__':
    sys.exit(0 if main() else 1)
