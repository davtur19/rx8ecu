"""
Mazda RX-8 Security Access - Seed/Key Algorithm
ECOMcat / PyEcom (public domain, Craig Smith's Car Hacking Handbook)

24-bit Galois LFSR with feedback polynomial taps at bits 23,20,15,12,5,3.
"""

import sys

def _clock(state: int, input_bit: int) -> int:
    """One clock cycle of the 24-bit Galois LFSR."""
    feedback = (state & 1) ^ input_bit
    state >>= 1                    # shift right, bit 23 becomes 0
    if feedback:
        # Set bit 23 = feedback, XOR feedback into taps 20,15,12,5,3
        state ^= 0x909028          # 0x800000|0x100000|0x8000|0x1000|0x20|0x08
    return state & 0xFFFFFF


def compute_key(seed_bytes: bytes, secret_bytes: bytes) -> bytes:
    """
    seed_bytes:   3 bytes from ECU (response to 27 01)
    secret_bytes: 5-byte shared secret (b'MazdA' for stock RX-8)
    Returns:      3-byte key to send (27 02 XX YY ZZ)
    """
    s1, s2, s3, s4, s5 = secret_bytes
    seed = (seed_bytes[0] << 16) | (seed_bytes[1] << 8) | seed_bytes[2]

    # Phase 1 input: s1 in bits 24-31, seed bytes shuffled in bits 0-23
    w1 = (s1 << 24) | ((seed & 0xFF) << 16) | (seed & 0xFF00) | ((seed >> 16) & 0xFF)

    # Phase 2 input: s2..s5 packed little-endian
    w2 = (s5 << 24) | (s4 << 16) | (s3 << 8) | s2

    state = 0xC541A9

    for i in range(32):
        state = _clock(state, (w1 >> i) & 1)

    for i in range(32):
        state = _clock(state, (w2 >> i) & 1)

    # Extract key bytes from final LFSR state
    #   byte 0: nibble[16:20] in low bits,  nibble[0:4]  in high bits
    #   byte 1: nibble[20:24] in low bits,  nibble[12:16] in high bits
    #   byte 2: bits [4:12]
    b0 = ((state >> 16) & 0xF) | (((state) & 0xF) << 4)
    b1 = ((state >> 20) & 0xF) | (((state >> 12) & 0xF) << 4)
    b2 = (state >> 4) & 0xFF

    # Byte 0 and 2 are swapped vs the naive ordering
    return bytes([b2, b1, b0])


def verify():
    """
    Self-test con vettori noti (ROM-verified, 2026-07-31).

    Provenance note (secret bytes):
      Stock ROM 60E1D400 @ 0x5FAC0 : b'MazdA'  (4D 61 7A 64 41)  — confirmed in ROM.
      [REDACTED]-tuned ROM          : b'vendor-family secret'  ([REDACTED])  — provenance: [REDACTED]
                                      captures of a FLASHED/tuned ECU (3 real-world CAN
                                      captures), NOT a stock ECU.
      b'vendor-family secret' ([REDACTED])      : provenance: a Flasher decryptor string.
                                      Both are RX-8 UDS SecurityAccess secrets.
      'vendor-family secret' and 'vendor-family secret' are EQUIVALENT under this algorithm (an LFSR collision):
      compute_key(seed, b'vendor-family secret') == compute_key(seed, b'vendor-family secret') for every tested
      vector — e.g. seed 0x[REDACTED] → key 0x[REDACTED] for BOTH strings, and identically
      for seeds 0x45820A, 0xCBFED4, 0x[REDACTED], 0x123456 (see test vectors below).
      Both are valid 5-byte secrets that yield identical keys because of the
      nibble-interleave/64-bit stream structure — likely because the algorithm
      uses only a subset of the secret bits.

    Algorithm status (RESOLVED — was listed as an open problem in
    docs/notes/RESUME.md; now verified against ROM 60E1D400):
      The ECOMcat Galois LFSR (init 0xC541A9, taps 0x909028) IS the stock ROM
      algorithm.  Evidence:
        - SeedKeyRelated @0x56ADA hardcodes the tap XORs at 0x56C1E-0x56C38:
          xor #8/#32 on the low state byte, xor #16/#128 on the mid byte,
          xor #16 on the high byte + OR 0x80 on the high byte = bits
          {23,20,15,12,5,3} = 0x909028 — identical to ECOMcat's taps.
        - The per-level init table at 0x5FAC5 (entry = level*3 bytes, read
          entry[0]<<16 | entry[1]<<8 | entry[2]) has level 1 = C5 41 A9 =
          0xC541A9 — identical to compute_key's fixed init.
        - sh2emu emulation of @0x56ADA: levels 1-4 x seeds {45820A, CBFED4,
          123456} -> 12/12 keys reproduced by compute_key (level 1), and by a
          ROM-disassembly-derived reference for ALL levels.
        - Real-world [REDACTED] captures (secret 'vendor-family secret'): 3/3.
        - 400 random seeds: compute_key == ROM reference, 0 mismatches.
      The legacy stock vector 0x3B15E1 was WRONG (no ROM/emulation support);
      the ROM-verified value for seed 0x45820A / 'MazdA' / level 1 is 0xA07258.
    """
    # Vettore stock — ROM-verified value (see note above)
    seed     = bytes([0x45, 0x82, 0x0A])
    expected = bytes([0xA0, 0x72, 0x58])
    result   = compute_key(seed, b'MazdA')
    ok = "OK" if result == expected else f"FAIL  got={result.hex().upper()}  want={expected.hex().upper()}"
    print(f"Self-test stock  (MazdA) : {ok}")

    # Vettori verificati empiricamente sull'ECU reale
    real_tests = [
        (bytes.fromhex('CBFED4'), bytes.fromhex('[REDACTED]')),
        (bytes.fromhex('[REDACTED]'), bytes.fromhex('[REDACTED]')),
        (bytes.fromhex('[REDACTED]'), bytes.fromhex('[REDACTED]')),
    ]
    for seed_b, exp_b in real_tests:
        res = compute_key(seed_b, bytes([0x00,0x00,0x00,0x00,0x00]))  # vendor-family secret
        ok2 = "OK" if res == exp_b else f"FAIL got={res.hex().upper()}"
        print(f"Self-test VT     (vendor-family secret)  seed={seed_b.hex().upper()}: {ok2}")

    return result == expected


if __name__ == "__main__":
    sys.exit(0 if verify() else 1)
