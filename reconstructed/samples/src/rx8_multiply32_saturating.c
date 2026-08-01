/*
 * =============================================================================
 * rx8_multiply32_saturating.c  —  SATURATING SIGNED 32×32 MULTIPLY (Q16.16)
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x231C
 * Status      : VERIFIED — behavioural equivalence to the ROM held by
 *               reconstructed/samples/tests/harness_multiply32_saturating.py
 *               (host-gcc vs tools/sh2emu.py over edge vectors plus 20000
 *               random int32 pairs; 0 mismatches).
 * Lift (truth): c/math_primitives.c → multiply32Bit_saturating @0x231C
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * Q16.16 fixed-point scalar multiply.  Two 32-bit signed fixed-point operands
 * (16 integer bits, 16 fraction bits) are multiplied into an exact signed
 * 64-bit product, the result is arithmetic-shifted right by 16 to land back
 * in Q16.16, and the final value is clamped to the int32 range.  A plain
 * 32×32 multiply would wrap for any operand pair whose product needs more
 * than 16 guard bits — i.e. essentially any scaled value, not just near-
 * overflow inputs — so every call must go through the saturating variant.
 *
 * The ROM path (disassembly-verified) is:
 *
 *     sts  mach,r1           ; preserve caller's MAC pair
 *     sts  macl,r2
 *     dmuls.l r4,r5          ; {macl:mach} = r4 * r5 (exact signed 64-bit)
 *     sts  macl,r5           ; r5 = low  word of product
 *     sts  mach,r4           ; r4 = high word of product
 *     lds  r1,mach           ; restore caller's MAC pair
 *     lds  r2,macl
 *     16 × ( shar r4         ; arithmetic shift of the 64-bit {r4:r5} right
 *             rotcr r5 )     ;   by 16 — carry chain through the T flag
 *     cmp/pz r4 ; bf .neg    ; sign of the shifted 64-bit result
 *     ... saturation: high word 0 && low word non-negative -> fits (keep),
 *         otherwise clamp to +0x7FFFFFFF; high word -1 && low word
 *         negative -> fits (keep), otherwise clamp to -0x80000000.
 *
 * The C below is behaviour-identical and never relies on overflowing signed
 * arithmetic: the 64-bit product is computed in an int64_t (exact for any
 * pair of int32_t operands) and the comparison against INT32_MAX/INT32_MIN
 * is done before truncation, so it is well-defined on any compiler.
 * =============================================================================
 */
#include <stdint.h>
#include <limits.h>
#include "rx8_samples.h"

/* 0x231C — Q16.16 fixed-point multiply with 32-bit saturation:
 *         clamp(((int64_t)a * (int64_t)b) >> 16, INT32_MIN, INT32_MAX). */
int32_t rx8_multiply32_saturating(int32_t a, int32_t b)
{
    int64_t product = (int64_t)a * (int64_t)b;  /* exact: 62 bits, no overflow */
    int64_t scaled  = product >> 16;            /* arithmetic (sign-preserving) */
    if (scaled > INT32_MAX) {
        return INT32_MAX;
    }
    if (scaled < INT32_MIN) {
        return INT32_MIN;
    }
    return (int32_t)scaled;
}
