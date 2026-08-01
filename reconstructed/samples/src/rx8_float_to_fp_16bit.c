/*
 * =============================================================================
 * rx8_float_to_fp_16bit.c  —  UNSIGNED 16-BIT FIXED-POINT -> FLOAT (fmac-fused)
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x24C0
 * Status      : VERIFIED — behavioural equivalence to the ROM held by
 *               reconstructed/samples/tests/harness_float_to_fp_16bit.py
 *               (host-gcc vs tools/sh2emu.py over random vectors + edge
 *               sweep, 0 mismatches).
 * Lift (truth): c/math_primitives.c  ->  fixedPointToFloat_16bit (0x24C0)
 *
 * NAME NOTE: the "floatToFP_16bit @ 0x24C0" label is a misnomer.  The verified
 * lift and the ROM bytes at 0x24C0 both describe the INVERSE direction: a
 * 16-bit unsigned fixed-point value (raw, in r4) is widened to float and
 * scaled:
 *
 *     fr0 = mult * raw + off
 *
 * The float->fixed-point helper that the name would suggest
 * (`floatToFP_16bit`, round((n-off)/scalar) clamp [0,65535]) is the NEIGHBOR
 * at 0x2490 and is NOT this function.
 *
 * ROM path (6 instructions):
 *     extu.w r4,r4        ; raw &= 0xFFFF
 *     lds    r4,fpul
 *     float  fpul,fr3     ; fr3 = (float)raw          (exact: u16 subset of f32)
 *     fmov   fr4,fr0      ; fr0 = mult
 *     fmac   fr0,fr3,fr5  ; fr5 = fr0*fr3 + fr5       (fused: single rounding)
 *     rts                 ; delay slot fmov fr5,fr0 -> fr0 = mult*raw + off
 *
 * ROUNDING: `fmac` accumulates with a SINGLE rounding.  A host expression in
 * pure float (`mult * (float)raw + off`) rounds twice (mul->f32 then add->f32)
 * and provably diverges from the ROM (thousands of mismatches per 30k random
 * vectors).  Keeping the exact product in double and rounding once to float
 * reproduces the fused result bit-for-bit — the same "fmac-faithful" model
 * used by c/tests/test_2DLookup_type0.py.
 * =============================================================================
 */
#include <stdint.h>
#include "rx8_samples.h"

float rx8_fixed_point_to_float_16bit(float mult, float off, uint16_t raw)
{
    /* extu.w masking is done by the uint16_t parameter itself; the (double)
     * casts keep the 16x24-bit product exact (40 bits << 53) so the single
     * final float rounding mirrors the SH-2E `fmac`. */
    return (float)((double)mult * (double)raw + (double)off);
}
