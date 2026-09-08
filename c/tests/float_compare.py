#!/usr/bin/env python3
"""float_compare.py — shared NaN-payload-insensitive float-bits oracle helper.

Several differential suites compare a float result from the SH-2E emulator
(tools/sh2emu.py) against a host-computed reference.  Comparing exact bit
patterns is over-strict for NaN: the ROM builds results with INTEGER ops
(e.g. ldexp_481C returns the exact signaling-NaN pattern 0x7F800001 in r0 —
verified by emulating 0x481C and reading integer r0, no float conversion
involved), and the C lifts preserve it with memcpy.  The test oracle,
however, reads results through cpu.fr[] (host Python floats) plus
struct.pack('>f', ...), and on x86 that round-trip QUIETENS signaling-NaN
payloads: 0x7F800001 -> 0x7FC00001 (quiet bit forced by the host FPU/SSE
cvt).  fmov.s on real SH hardware is a pure bit move with no such
quieting, so exact-NaN-payload comparison across the host boundary would
flag a host artifact as a ROM/C mismatch.  Hence: when BOTH sides are NaN,
compare sign bit only; every other pair of patterns — including NaN vs
Inf, which must FAIL — compares exactly.

Reference implementation: c/tests/test_check_float_validity_0x46CC.py
(same_result_bits, first fixed in 6a86224); this module is the shared copy
so all oracles use one definition.

Seeding rule: NaN edge inputs must be seeded from RAW BITS via
struct.pack('>I', bits) where the test stages RAM bytes — never via a host
float (struct.unpack('>f', struct.pack('>I', bits)) round-trips through the
host FPU and quietens signaling payloads before the emulator sees them).
"""

# Representative NaN payloads every float oracle must cover:
#   0x7F800001 — signaling NaN, minimal payload (+): the exact pattern the
#                ROM integer path produces (ldexp_481C in r0).
#   0xFF800001 — signaling NaN, minimal payload (-): sign-bit handling.
#   0x7FC00001 — quiet NaN (+): what x86 host quieting turns 0x7F800001
#                into after an fr[] + struct.pack('>f') round-trip.
EDGE_NAN_BITS = [0x7F800001, 0xFF800001, 0x7FC00001]


def same_result_bits(a_bits, b_bits):
    """NaN-payload-insensitive comparison of two float bit patterns (ints).

    Both-NaN (any payloads) -> compare sign bit only; anything else ->
    exact int equality, so NaN-vs-Inf FAILS as it must.
    """
    a_bits &= 0xFFFFFFFF
    b_bits &= 0xFFFFFFFF
    a_nan = (a_bits & 0x7F800000) == 0x7F800000 and (a_bits & 0x007FFFFF) != 0
    b_nan = (b_bits & 0x7F800000) == 0x7F800000 and (b_bits & 0x007FFFFF) != 0
    if a_nan and b_nan:
        return (a_bits >> 31) == (b_bits >> 31)
    return a_bits == b_bits
