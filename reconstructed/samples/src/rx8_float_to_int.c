/*
 * =============================================================================
 * rx8_float_to_int.c  —  FLOAT TO UNSIGNED 8-BIT FIXED-POINT
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x24D0
 * Status      : VERIFIED — behavioural equivalence to the ROM held by
 *               reconstructed/samples/tests/harness_float_to_int.py (host-gcc vs
 *               tools/sh2emu.py over single-precision random inputs), in addition
 *               to the existing c/tests/test_math_primitives.py entry (30k random,
 *               0 errors).
 * Lift (truth): c/math_primitives.c  (same address; `floatToInt`)
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * Sensor and trim-table values arrive as single-precision "physical" numbers
 * (voltage, temperature, fraction) and must be quantized into the unsigned 8-bit
 * cells the calibration tables index.  The SH-2E `ftrc` instruction truncates
 * toward zero, so Denso adds 0.5 *before* the conversion: the result is
 * round-to-nearest for every non-negative value the clamp keeps, exactly like
 * the neighbouring 16-bit converter floatToFP_16bit @0x2490.
 *
 * The ROM path is (SH-2E FPU convention: fr4=signal, fr5=mult, fr6=offset;
 * r0 returns the clamped value):
 *
 *     mova  @(0x0A,PC),r0   ; r0 = &0.5f literal (0x24FC)
 *     fsub  FR6,FR4         ; tmp = signal - offset
 *     mov.w @(0x10,PC),r5   ; r5 = 0x00FF   (upper clamp constant)
 *     fdiv  FR5,FR4         ; tmp = (signal - offset) / mult
 *     fmov.s @R0,FR3        ; fr3 = 0.5f
 *     fmov  FR4,FR2
 *     fadd  FR3,FR2         ; tmp = tmp + 0.5f
 *     ftrc  FR2,FPUL        ; i = (int)tmp        (truncate toward zero)
 *     sts   FPUL,R4
 *     cmp/gt R5,R4 / bf/s   ; if (i > 255) i = 255
 *     cmp/pz R4    / bt/s   ; if (i < 0)   i = 0
 *     rts / mov r4,r0       ; return the clamped i
 *
 * The C below reproduces this byte-for-byte: every operation is single
 * precision, the int32 cast truncates toward zero exactly like `ftrc`, and the
 * two clamps are signed comparisons like the ROM's cmp/gt + cmp/pz.
 * =============================================================================
 */
#include <stdint.h>
#include "rx8_samples.h"

uint8_t rx8_float_to_int(float signal, float mult, float offset)
{
    int32_t i = (int32_t)(((signal - offset) / mult) + 0.5f); /* ftrc: trunc toward zero */
    if (i > 0xFF) i = 0xFF;
    if (i < 0)    i = 0;
    return (uint8_t)i;
}
