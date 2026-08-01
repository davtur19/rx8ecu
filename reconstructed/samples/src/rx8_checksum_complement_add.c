/*
 * =============================================================================
 * rx8_checksum_complement_add.c  —  CHECKSUM RESIDUAL OF A 32-BIT REDUNDANT
 *                                   VALUE/~VALUE CELL
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x2034
 * Status      : VERIFIED — behavioural equivalence to the ROM held by
 *               reconstructed/samples/tests/harness_checksum_complement_add.py
 *               (host-gcc vs tools/sh2emu.py over random + edge 32-bit
 *               values), in addition to the existing c/tests/
 *               test_checksum_complement_add.py entry (100k random, 0 errors).
 * Lift (truth): c/checksum_complement_add.c  (same address; IDA-ai symbol
 *               `checksum_complement_add`, identical name).
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * Computes the checksum residual of a 32-bit redundant-storage cell:
 *
 *     residual = (~value - (value >> 16)) & 0xFFFF
 *
 * A value stored as ((uint16_t data) << 16) | (~data & 0xFFFF) — the same
 * encoding produced by complement_shift_u16 @0x2430 — yields residual == 0,
 * i.e. the (data, ~data) pair is self-consistent.  Any non-zero residual
 * indicates memory corruption of the calibration / safety-critical variable
 * (a single flipped bit breaks the value/~value relationship).
 *
 * SH-2E asm (matches the lift verbatim; r4 = pointer to the 32-bit cell):
 *     0x2034:  mov.l   @r4,r3       ; value  = *r4             (32-bit load)
 *     0x2036:  mov     r3,r0        ; r0     = value
 *     0x2038:  shlr16  r3           ; r3     = value >> 16     (upper half)
 *     0x203A:  not     r0,r0        ; r0     = ~value          (ones' complement)
 *     0x203C:  sub     r3,r0        ; r0     = (~value) - (value >> 16)
 *     0x203E:  rts                  ; return r0
 *     0x2040:  extu.w  r0,r0        ;   (delay slot) r0 &= 0xFFFF
 *
 * The arithmetic happens in 32 bits (`not`/`sub` are full-width); only the
 * delay-slot `extu.w` narrows the result to 16 bits, so the final & 0xFFFF
 * below is mandatory and must NOT be simplified away.
 * =============================================================================
 */
#include <stdint.h>
#include "rx8_samples.h"

/* 16-bit result mask.  The delay-slot `extu.w r0,r0` zero-extends the result
 * to 16 bits; this constant is that mask spelled out.  (0xFFFF, matches ROM.) */
#define RX8_CHECKSUM_RESIDUAL_MASK  0xFFFFu

/* 0x2034 — checksum residual of a 32-bit redundant cell; 0 means the
 * (value, ~value) pair is self-consistent.  NOTE: the ROM reads the cell via
 * the pointer in r4; taking the value by copy is behaviourally identical to
 * the caller-side `*r4` load performed by the harness/emulator. */
uint16_t rx8_checksum_complement_add(uint32_t value)
{
    /* Upper half of the cell — the stored data word.  (`shlr16 r3`.) */
    uint32_t hi16 = value >> 16;

    /* Ones' complement of the whole 32-bit cell.  (`not r0,r0` is full-width,
     * so this stays a 32-bit complement, not a 16-bit one.) */
    uint32_t complement = ~value;

    /* Residual: 0 iff cell == ((data << 16) | ~data).  The subtraction is
     * unsigned 32-bit arithmetic (implicit wrap), and the mask reproduces the
     * delay-slot `extu.w r0,r0`. */
    return (uint16_t)((complement - hi16) & RX8_CHECKSUM_RESIDUAL_MASK);
}
