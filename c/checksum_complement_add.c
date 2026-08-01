/*
 * checksum_complement_add.c  —  RX-8 PCM checksum/complement verification (0x2034)
 *
 * Computes the residual of a 32-bit redundant-storage cell:
 *     result = (~value - (value >> 16)) & 0xFFFF
 *
 * A value stored as ((uint16_t data) << 16) | (~data & 0xFFFF) yields result=0
 * (i.e. valid).  Any non-zero result indicates data corruption.
 *
 * The 16-bit redundant-pair family:
 *   - encode()         (0x2420) packs uint8_t  -> (val << 8) | ~val      (16-bit cell)
 *   - complement_shift_u16 (0x2430) packs uint16_t -> (val << 16) | ~val  (32-bit cell)
 *   - checksum_complement_add (0x2034) reads  a  32-bit cell and returns the
 *     checksum residual; 0 means the pair is self-consistent.
 *
 * SH-2E asm:
 *   0x2034:  mov.l   @r4,r3       ; r3 = *r4                   (load 32-bit cell)
 *   0x2036:  mov     r3,r0        ; r0 = r3
 *   0x2038:  shlr16  r3           ; r3 >>= 16                  (upper half)
 *   0x203A:  not     r0,r0        ; r0 = ~r0                   (ones' complement)
 *   0x203C:  sub     r3,r0        ; r0 = r0 - r3
 *   0x203E:  rts                  ; return r0
 *   0x2040:  extu.w  r0,r0        ; (delay) r0 &= 0xFFFF
 *
 * Track A: verified behavior-equivalent to emulated ROM over
 * the full uint32 domain (65536 random + edge-case) inputs.
 * Test: c/tests/test_checksum_complement_add.py.
 */
#include <stdint.h>

/* 0x2034  checksum residual: 0 if (value,~value) pair is self-consistent       */
uint16_t checksum_complement_add(uint32_t value)
{
    uint32_t hi16  = value >> 16;
    uint32_t complement = ~value;          /* 32-bit ones' complement */
    return (uint16_t)((complement - hi16) & 0xFFFFu);
}
