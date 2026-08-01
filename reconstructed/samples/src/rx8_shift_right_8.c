/*
 * =============================================================================
 * rx8_shift_right_8.c  —  ARITHMETIC RIGHT-SHIFT BY 8 (SIGNED 32-BIT)
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x467A
 * Status      : VERIFIED — behavioural equivalence to the ROM held by
 *               reconstructed/samples/tests/harness_shift_right_8.py (host-gcc
 *               vs tools/sh2emu.py over 20000 random int32 inputs + edge
 *               vectors), in addition to the existing c/tests/
 *               test_shift_right_8_r0.py entry (100k random, 0 errors).
 * Lift (truth): c/shift_right_8_r0.c  (same address; IDA-ai symbol
 *               `shift_right_8_r0`).
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * A compact building-block used in fixed-point math: calibration values are
 * often stored scaled as (value << 8) and must be normalised back to raw
 * units.  The SH-2E has no "shift by 8" instruction, so Denso emits eight
 * consecutive `shar r0` (arithmetic shift-right-by-1) instructions:
 *
 *     0x467A: shar  r0            ; r0 >>= 1 (sign-replicating)
 *     0x467C: shar  r0
 *     0x467E: shar  r0
 *     0x4680: shar  r0
 *     0x4682: shar  r0
 *     0x4684: shar  r0
 *     0x4686: shar  r0
 *     0x4688: rts                 ; return (delayed)
 *     0x468A: shar  r0            ; (delay slot — this 8th shift still
 *                                 ;  executes before the return)
 *
 * That is exactly 8 sign-extending (arithmetic) right shifts, so the
 * behaviour is `(int32_t)val >> 8`.  `shar` replicates the sign bit; on the
 * host the signed right-shift of a negative value is equally arithmetic with
 * gcc, and the C below is byte-for-byte behaviour-equivalent to the ROM.
 *
 * CALLING CONVENTION: unlike most helpers this one reads its argument from
 * the r0 register (not r4/r5) and returns the result in r0.  The harness
 * drives the emulator with a dedicated r0-based call stub for this reason.
 * =============================================================================
 */
#include <stdint.h>
#include "rx8_samples.h"

/* 0x467A  Arithmetic right-shift of a signed 32-bit value by 8 bit
 * positions (8x `shar r0` on the target).  Returns `val / 256` rounded
 * toward negative infinity, i.e. sign-extending. */
int32_t rx8_shift_right_8(int32_t val)
{
    return val >> 8;
}
