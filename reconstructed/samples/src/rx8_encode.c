/*
 * =============================================================================
 * rx8_encode.c  —  VALUE/COMPLEMENT BYTE ENCODER  (enc8)
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x2420
 * Status      : VERIFIED — behavioural equivalence to the ROM held by
 *               reconstructed/samples/tests/harness_encode.py (host-gcc vs
 *               tools/sh2emu.py over random inputs spanning the full uint32
 *               range plus masking edges), in addition to the existing
 *               c/tests/test_math_primitives.py entry (30k random, 0 errors).
 * Lift (truth): c/math_primitives.c (same address; the 13-function scalar
 *               cluster 0x2044..0x2510, verified vs the emulator).
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * Denso stores small values redundantly as a 16-bit (value, complement) cell:
 * the high byte holds the value, the low byte its ones' complement.  Reading
 * back, a pair whose high and low bytes are not mutual complements is treated
 * as corrupted (see invertAndReturn_8bit_ADDR @0x2044, the checksum residual
 * that is exactly 0 for self-consistent pairs).  enc8() is the writer half:
 *
 *     enc8(x) = (x << 8) | ~x      (both operands kept to 8 bits)
 *
 * The ROM path is:
 *
 *     extu.b r4,r3   ; r3 = x & 0xFF           (only the low byte matters)
 *     shll8  r3      ; r3 <<= 8
 *     mov    r4,r2
 *     not    r2,r2   ; ~x
 *     extu.b r2,r2   ; ~x & 0xFF
 *     or     r3,r2,r0 -> result               (well, or r2,r0)
 *     rts
 *
 * The caller-side 16-bit run-sum cells (0xFFFF8E98/9A) are written by exactly
 * this leaf (obd_service_handler_648B4 @0x648B4); the `extu.b` on entry makes
 * the function a pure function of the low byte of r4, so any upper bits in the
 * argument are ignored — the C signature below preserves that semantics.
 * =============================================================================
 */
#include <stdint.h>
#include "rx8_samples.h"

/* Width of the byte being encoded; the ROM's `extu.b` on entry forces every
 * input to exactly this, regardless of what was in r4. */
#define RX8_ENCODE_BYTE_MASK 0xFFu

uint16_t rx8_encode(uint8_t x)
{
    /* High byte = value, low byte = ones' complement; explicit masks keep
     * this well-defined on any host int width while remaining byte-identical
     * to the ROM's extu.b/shll8/not/or sequence. */
    uint16_t hi = (uint16_t)((uint16_t)x << 8);
    uint8_t  lo = (uint8_t)~x;
    return (uint16_t)(hi | lo);
}
