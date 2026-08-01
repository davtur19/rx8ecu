/*
 * =============================================================================
 * rx8_math_primitives_2490.c  —  THREE MATH-PRIMITIVE LEAVES: 0x2490, 0x2500,
 *                                0x2510 (float<->fixed-point cluster)
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Addresses   : 0x2490  floatToFP_16bit        (float -> u16 fixed-point)
 *               0x2500  fixedPointToFloat_8bit  (u8 fixed-point -> float)
 *               0x2510  fixedPointScaling       (inverse-weighted int blend)
 * Status      : VERIFIED — behavioural equivalence to the ROM held by
 *               reconstructed/samples/tests/harness_math_primitives_2490.py
 *               (host-gcc vs tools/sh2emu.py over edge vectors + N random
 *               vectors per function; 0 mismatches).
 * Lift (truth): c/math_primitives.c  (floatToFP_16bit @0x2490,
 *               fixedPointToFloat_8bit @0x2500, fixedPointScaling @0x2510)
 *
 * ----------------------------------------------------------------------------
 * 0x2490  floatToFP_16bit — float -> UNSIGNED 16-BIT FIXED-POINT
 * ----------------------------------------------------------------------------
 *   fr0=r0  round((number - offset) / scalar)  clamped to [0, 65535]
 *
 * ROM path:
 *     mova  @(0x24,pc),r0    ; r0 = &0.5f literal   (0x24B8 = 3F000000)
 *     fsub  fr6,fr4          ; t = number - offset                 (1 rounding)
 *     mov.l 0x24BC,r5        ; r5 = 0x0000FFFF  (upper clamp const)
 *     fdiv  fr5,fr4          ; t = t / scalar                      (1 rounding)
 *     fmov.s @r0,fr3         ; fr3 = 0.5f
 *     fmov  fr4,fr2
 *     fadd  fr3,fr2          ; t = t + 0.5f                        (1 rounding)
 *     ftrc  fr2,fpul         ; i = (int)trunc(t)   (truncate toward zero)
 *     sts   fpul,r4
 *     cmp/gt r5,r4 / bf/s    ; if (i > 0xFFFF) i = 0xFFFF  (signed cmp)
 *     cmp/pz r4    / bt/s    ; if (i < 0)      i = 0
 *     rts / mov r4,r0
 *
 * The `ftrc` truncates toward zero, so the +0.5 in front of it makes the
 * conversion round-to-nearest for the non-negative results that survive the
 * clamp (exactly the same idiom as the u8 sibling floatToInt @0x24D0).
 *
 * ----------------------------------------------------------------------------
 * 0x2500  fixedPointToFloat_8bit — UNSIGNED 8-BIT FIXED-POINT -> FLOAT
 * ----------------------------------------------------------------------------
 *   fr0 = mult * raw + off   (raw zero-extended to 8 bits: `extu.b`)
 *
 * ROM path:
 *     extu.b r4,r4           ; raw &= 0xFF
 *     lds    r4,fpul
 *     float  fpul,fr3        ; fr3 = (float)raw          (exact: u8 subset of f32)
 *     fmov   fr4,fr0         ; fr0 = mult
 *     fmac   fr0,fr3,fr5     ; fr5 = fr0*fr3 + fr5       (fused: SINGLE rounding)
 *     rts                    ; delay slot fmov fr5,fr0 -> fr0 = mult*raw + off
 *
 * ROUNDING: `fmac` fuses multiply+add into ONE rounding.  A plain float
 * `mult * (float)raw + off` rounds twice (mul->f32 then add->f32) and diverges
 * from the ROM.  Keeping the exact product in double and rounding once to
 * float reproduces the fused result bit-for-bit — the same fmac-faithful
 * model used by the 16-bit sibling (rx8_float_to_fp_16bit.c @0x24C0).  With
 * raw<=255 the product is at most 32 significant bits, so the double
 * intermediate is exact and the model is provably the single f32 rounding.
 *
 * ----------------------------------------------------------------------------
 * 0x2510  fixedPointScaling — INVERSE-WEIGHTED BLEND OF TWO INTs
 * ----------------------------------------------------------------------------
 *   result = a + (int)trunc((b - a) * (1 - frac/256))     (frac extu.w)
 *
 * ROM path:
 *     mova  @(0x24,pc),r0    ; r0 = &1/256 literal (0x2538 = 3B800000 = 2^-8)
 *     fldi1 fr1              ; fr1 = 1.0
 *     fmov.s @r0,fr2         ; fr2 = 1/256
 *     extu.w r6,r6           ; frac &= 0xFFFF
 *     lds   r6,fpul
 *     float fpul,fr3         ; fr3 = (float)frac                       (exact)
 *     fmul  fr2,fr3          ; fr3 = frac * (1/256)                    (1 rnd)
 *     fsub  fr3,fr1          ; t = 1 - frac/256                        (1 rnd)
 *     lds   r5,fpul ; float  ; fr3 = (float)b                          (1 rnd)
 *     lds   r4,fpul ; float  ; fr0 = (float)a                          (1 rnd)
 *     fsub  fr0,fr3          ; diff = (float)b - (float)a              (1 rnd)
 *     fmul  fr3,fr1          ; fr1 = t * diff                          (1 rnd)
 *     ftrc  fr1,fpul         ; d = (int)trunc(t*diff)  (truncate toward 0)
 *     sts   fpul,r3
 *     add   r3,r4            ; result = a + d           (mod 2^32 add)
 *     rts                    ; delay slot mov r4,r0
 *
 * frac==0 -> t=1.0 -> b exactly; frac==256 -> t=0 -> a exactly.  The typical
 * firmware use is frac counting 0..255 as a ramp/fade progresses between b and
 * a.  Every FP operation in the ROM is a separate single-precision rounding,
 * so the C below keeps each intermediate as `float` (single rounding each) —
 * any double intermediate here would change intermediate roundings and break
 * bit-exactness (verified empirically).
 *
 * DOMAIN NOTE (0x2510 and 0x2490): the emulator models `ftrc` as
 * int(f)&MASK (wraps) whereas a C `(int32_t)` cast is only defined inside the
 * int32 range (host cvttss2si saturates to INT32_MIN outside).  Real SH-2E
 * ftrc is hardware-undefined out of range, and firmware never reaches it
 * (frac<=256 keeps |t|<=1; the harness pins |a|,|b|<=2^30 and
 * |number-offset|/|scalar| <= 1e9 accordingly).  See harness header for the
 * exact domains.
 * =============================================================================
 */
#include <stdint.h>
#include "rx8_samples.h"

/* 0x2490 — float -> unsigned 16-bit fixed point:
 *         round((number - offset) / scalar), clamped to [0, 65535].
 * Every op is a separate single-precision rounding (fsub / fdiv / fadd with
 * the 0.5f literal); `(int32_t)` truncates toward zero exactly like `ftrc`,
 * and the two clamps are signed comparisons like the ROM's cmp/gt + cmp/pz. */
uint16_t rx8_float_to_fixed_16bit(float number, float scalar, float offset)
{
    int32_t i = (int32_t)(((number - offset) / scalar) + 0.5f);
    if (i > 0xFFFF) i = 0xFFFF;
    if (i < 0)      i = 0;
    return (uint16_t)i;
}

/* 0x2500 — unsigned 8-bit fixed point -> float:  mult * raw + off.
 * The (double) casts keep the 24x8-bit product exact (32 bits << 53) and the
 * addition exact too, so the single final float rounding mirrors the SH-2E
 * `fmac` (fused multiply-add with ONE rounding). */
float rx8_fixed_point_to_float_8bit(float mult, float off, uint8_t raw)
{
    return (float)((double)mult * (double)raw + (double)off);
}

/* 0x2510 — inverse-weighted blend between two ints using an 8-bit fractional
 * counter:  a + (int)trunc((b - a) * (1 - frac/256.0)).
 * Each intermediate stays `float` (single rounding), matching the ROM's
 * fmul/fsub/fsub/fmul sequence instruction-for-instruction. */
int32_t rx8_fixed_point_scaling(int32_t a, int32_t b, uint16_t frac)
{
    float t    = 1.0f - (float)frac * (1.0f / 256.0f);
    float diff = (float)b - (float)a;
    int32_t d  = (int32_t)(diff * t);    /* ftrc: truncate toward zero */
    return a + d;
}
