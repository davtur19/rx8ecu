/*
 * shift_right_8_r0.c  —  RX-8 PCM arithmetic right-shift by 8 (0x00467A)
 *
 * Arithmetically right-shifts a signed 32-bit value by 8 bit positions.
 * This is a building-block used in fixed-point math where calibration
 * values stored as (value << 8) need to be normalised.
 *
 * SH-2E asm:
 *   0x00467A: shar  r0          ; r0 >>= 1  (arithmetic, sign-extending)
 *   0x00467C: shar  r0
 *   0x00467E: shar  r0
 *   0x004680: shar  r0
 *   0x004682: shar  r0
 *   0x004684: shar  r0
 *   0x004686: shar  r0          ; 8× shar = arithmetic right shift by 8
 *   0x004688: rts
 *   0x00468A: shar  r0          ; (delay slot — never reached after rts)
 *
 * C equivalent: (int32_t)val >> 8
 * The `shar` instruction replicates the sign bit (arithmetic, not logical).
 *
 * Track A: verified behavior-equivalent to emulated ROM over
 * 100000 random int32_t inputs.
 */
#include <stdint.h>

/* 0x00467A  Arithmetic right-shift int32_t by 8 bits                  */
int32_t shift_right_8_r0(int32_t val)
{
    return val >> 8;
}
