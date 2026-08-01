/*
 * =============================================================================
 * rx8_subtract_absolute.c  —  ABSOLUTE DIFFERENCE OF TWO FLOATS
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x23DC
 * Status      : VERIFIED — bit-exact behavioural equivalence to the ROM held
 *               by reconstructed/samples/tests/harness_subtract_absolute.py
 *               (host-gcc vs tools/sh2emu.py over random float pairs plus
 *               edge vectors), in addition to the existing
 *               c/tests/test_math_primitives.py entry (30000 random inputs,
 *               0 mismatches).
 * Lift (truth): c/math_primitives.c  (same address; part of the scalar-helper
 *               cluster 0x2044..0x2510, the most-called leaf routines in the
 *               firmware).
 *
 * ROM ASM (4 words, 0x23DC):
 *     fsub  fr5,fr4        ; fr4 = fr4 - fr5   (single-precision subtract)
 *     fabs  fr4            ; fr4 = |fr4|
 *     rts                   ; return            (delay slot:)
 *     fmov  fr4,fr0         ;   result in fr0
 *
 * i.e. exactly  |a - b|  computed as ONE IEEE-754 single-precision subtract
 * followed by a sign-bit clear.  The subtraction must not be fused or
 * re-ordered, and the absolute value must preserve the NaN payload, so the
 * sign-bit mask below mirrors the SH-2E `fabs` instruction verbatim instead
 * of calling a libm fabsf().
 *
 * Note |a - b| is symmetric in its arguments, so the fr4/fr5 register order
 * is irrelevant to the result.
 * =============================================================================
 */
#include <stdint.h>
#include "rx8_samples.h"

/* fabs == clearing the IEEE-754 sign bit (bit 31); NaN payload survives. */
#define RX8_SUBTRACT_ABS_SIGN_MASK 0x7FFFFFFFu

float rx8_subtract_absolute(float a, float b)
{
    union {
        float    f;
        uint32_t u;
    } bits;

    bits.f = a - b;            /* fsub: correctly-rounded single precision */
    bits.u &= RX8_SUBTRACT_ABS_SIGN_MASK;   /* fabs: clear sign bit */
    return bits.f;             /* fmov fr4,fr0 -> fr0 */
}
