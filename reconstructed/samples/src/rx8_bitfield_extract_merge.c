/*
 * =============================================================================
 * rx8_bitfield_extract_merge.c  —  FREXP-STYLE FLOAT BIT-PATTERN DECOMPOSITION
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x48C8  (identical bytes at 0x48C8 in 60E0FC00.bin)
 * Status      : VERIFIED — behavioural equivalence to the ROM held by
 *               reconstructed/samples/tests/harness_bitfield_extract_merge.py
 *               (host-gcc vs tools/sh2emu.py over random IEEE-754 bit patterns
 *               plus the full special-value edge set), in addition to the
 *               existing c/tests/test_bitfield_extract_merge.py entry
 *               (200k random + edges, 0 errors).
 * Lift (truth): c/bitfield_extract_merge.c  (IDA-ai symbol
 *               `bitfield_extract_merge`, 0x48C8..0x492A).
 *
 * PURPOSE / CALLERS
 * -----------------
 * Decompose a single-precision float into a (exponent, significand) pair in
 * frexp style: x = sig * 2^e with sig in [1.0, 2.0).  The only caller in the
 * ROM is checkFloatValidity @0x46CC (call site 0x46D8), which feeds the two
 * words straight into mul16_signed_saturated @0x4740 as stack arguments.
 *
 * Calling convention (confirmed from that single call site):
 *   - float argument in FR4 (FPU register),
 *   - result pointer pushed by the caller on the stack BEFORE the call:
 *         jsr   @r3
 *         mov.l r15,@-r15     ; delay slot: [r15] = ptr to 8-byte buffer
 *   - writes out[0] = exponent word, out[1] = significand word.
 *
 * RESULT LAYOUT
 * -------------
 * out[0] — exponent word:
 *   bit 31     sign of the input float.  EXCEPTION: NaN.  The ROM zeroes r2
 *              on the NaN path, so a negative NaN loses its sign while
 *              -Inf keeps it.
 *   bits 15:0  signed 16-bit exponent e with x = sig * 2^e, sig in [1,2).
 *   specials:  ±0.0 -> 0x00008001 (sentinel -32767)
 *              ±Inf -> 0x00007FFF (saturated +32767)
 *              NaN  -> 0x00007FFF, sign dropped
 * out[1] — significand word:
 *   bit 31     implicit leading 1 (always set for finite non-zero values)
 *   bits 30:8  23-bit mantissa << 8
 *   specials:  0.0 / ±Inf -> 0x00000000,  NaN -> 0xFFFFFFFF
 *
 * Subnormals are normalized: the mantissa is shifted left until its top bit
 * sits at bit 31 and e is decreased by one per shift, so a subnormal comes
 * out as a normal pair (sig in [1,2)) with e in [-149,-127].
 * =============================================================================
 */
#include <stdint.h>
#include "rx8_samples.h"

/* ---------------------------------------------------------------------------
 * IEEE-754 single-precision field masks (SH-2E big-endian bit numbering:
 * bit 31 = sign, bits 30..23 = exponent, bits 22..0 = fraction).
 * ------------------------------------------------------------------------- */
#define BFE_SIGN_MASK      0x80000000u    /* sign bit                        */
#define BFE_EXP_MASK       0x7F800000u    /* exponent field, bits 30..23     */
#define BFE_EXP_SHIFT      23u            /* exponent -> bits 7..0 of byte   */
#define BFE_EXP_BIAS       127            /* e = exponent byte - 127         */
#define BFE_EXP_ALL_ONES   0xFFu          /* exponent byte 0xFF -> Inf/NaN   */
#define BFE_MANT_MASK      0x007FFFFFu    /* 23-bit fraction                 */

/* Output-word constants (from the ROM literal pool / result contract). */
#define BFE_SIG_IMPLICIT   0x80000000u    /* implicit leading 1 at bit 31    */
#define BFE_MANT_SHIFT     8u             /* mantissa -> bits 30..8          */
#define BFE_SIG_NAN        0xFFFFFFFFu    /* significand word for NaN (-1)   */
#define BFE_EXP_ZERO       0x00008001u    /* exponent word for ±0.0 (0x8001) */
#define BFE_EXP_SAT        0x00007FFFu    /* exponent word for ±Inf/NaN      */

/* Bit pattern of the float argument, as a 32-bit word (endian-agnostic: the
 * numeric value is the IEEE-754 pattern on both the BE target and LE host). */
typedef union {
    float    f;
    uint32_t u;
} rx8_float_bits_t;

/* 0x48C8  frexp-style float decomposition: x = sig * 2^e, sig in [1,2). */
void rx8_bitfield_extract_merge(float value, uint32_t *out)
{
    rx8_float_bits_t raw;
    raw.f = value;

    uint32_t bits = raw.u;
    uint32_t sign = bits & BFE_SIGN_MASK;
    uint32_t exp8 = (bits & BFE_EXP_MASK) >> BFE_EXP_SHIFT;
    uint32_t mant = bits & BFE_MANT_MASK;
    uint32_t frac;                          /* out[1]: significand << 8      */
    int32_t  e;                             /* out[0]: signed exponent       */

    if (exp8 == BFE_EXP_ALL_ONES) {
        /* Exponent 0xFF: Inf or NaN. */
        if (mant == 0u) {
            /* ±Inf: exponent saturated to +32767, sign preserved. */
            out[0] = BFE_EXP_SAT | sign;
            out[1] = 0u;
        } else {
            /* NaN: exponent saturated, sign DROPPED (the ROM zeroes r2 on
             * this path, so -NaN comes out indistinguishable from +NaN). */
            out[0] = BFE_EXP_SAT;
            out[1] = BFE_SIG_NAN;
        }
        return;
    }

    if (exp8 == 0u) {
        /* Exponent 0: zero or subnormal. */
        if (mant == 0u) {
            /* ±0.0: exponent sentinel 0x8001 (-32767), sign preserved. */
            out[0] = BFE_EXP_ZERO | sign;
            out[1] = 0u;
            return;
        }
        /* Subnormal: normalize so the top mantissa bit lands at bit 31,
         * decreasing e once per shift (sig ends in [1,2)).  Bit 31 of
         * (mant << 9) is the mantissa's bit 22, so the already-normalized
         * case (bit 22 set) skips the loop entirely. */
        frac = mant << 9u;
        e = 0;
        while ((frac & BFE_SIG_IMPLICIT) == 0u) {
            e--;
            frac <<= 1u;
        }
        frac |= BFE_SIG_IMPLICIT;           /* implicit leading 1            */
        e -= BFE_EXP_BIAS;
    } else {
        /* Normal: exponent byte in [1,254]. */
        e = (int32_t)exp8 - BFE_EXP_BIAS;
        frac = (mant << BFE_MANT_SHIFT) | BFE_SIG_IMPLICIT;  /* 1.mantissa */
    }

    /* 16-bit two's-complement exponent packed with the sign in bit 31. */
    out[0] = (uint32_t)(uint16_t)e | sign;
    out[1] = frac;
}
