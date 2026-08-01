/*
 * =============================================================================
 * rx8_complement_shift_u16.c  —  VALUE + ONES'-COMPLEMENT PACK (16-BIT)
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x2430
 * Status      : VERIFIED — behavioural equivalence to the ROM held by
 *               reconstructed/samples/tests/harness_complement_shift_u16.py
 *               (host-gcc vs tools/sh2emu.py over random 16-bit values), in
 *               addition to the existing c/tests/test_complement_shift_u16.py
 *               entry (100k random, 0 errors).
 * Lift (truth): c/complement_shift_u16.c  (same address; IDA-ai symbol
 *               `complement_shift_u16`, identical name).
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * Packs a 16-bit value together with its ones' complement into a 32-bit word:
 *
 *     word[31:16] = val & 0xFFFF     (the value, zero-extended)
 *     word[15:0]  = (~val) & 0xFFFF  (its ones' complement)
 *
 * This is the redundant-storage encoding used for calibration tables and
 * safety-critical variables: any single-bit memory corruption breaks the
 * value/`~value` relationship and is detected when the word is read back.
 * It is the 16-bit sibling of the 8-bit encoder @0x2420; the ROM call graph
 * lists ~22 call sites across the fuel, ignition and DTC paths.
 *
 * SH-2E asm (matches the lift verbatim):
 *     extu.w  r4,r3       ; val  = r4 & 0xFFFF
 *     shll16  r3          ; val  = val << 16          (shift to upper half)
 *     not     r4,r2       ; comp = ~r4                (bitwise complement)
 *     extu.w  r2,r2       ; comp = comp & 0xFFFF
 *     mov     r3,r4
 *     add     r2,r4       ; r4   = val + comp
 *     rts                 ; return r0 = r4
 *     mov     r4,r0       ;   (delay slot)
 *
 * C equivalent: ((uint32_t)(val & 0xFFFF) << 16) | (uint32_t)(~val & 0xFFFF)
 * (ADD is equivalent to OR here because the complement has zeros in the upper
 * 16 bits, so the addition can never carry into the value half.)
 * =============================================================================
 */
#include <stdint.h>
#include "rx8_samples.h"

/* 16-bit width mask.  The ROM's leading `extu.w` zero-extends the argument,
 * so a caller passing a full 32-bit register value only ever contributes the
 * low half; this constant is that mask spelled out.  (0xFFFF, matches ROM.) */
#define RX8_COMPLEMENT_MASK_16  0xFFFFu

/* 0x2430 — pack a 16-bit value with its ones' complement into a 32-bit word
 * (redundant-storage encoding for corruption detection). */
uint32_t rx8_complement_shift_u16(uint16_t val)
{
    /* Upper half: the value, zero-extended and shifted into bits 31..16. */
    uint32_t value = (uint32_t)(val & RX8_COMPLEMENT_MASK_16) << 16;

    /* Lower half: the ones' complement, masked to 16 bits.  (`~val` promotes
     * to int on the host; the mask keeps exactly the 16 low bits the ROM's
     * second `extu.w` produces.) */
    uint32_t comp = (uint32_t)(~val) & RX8_COMPLEMENT_MASK_16;

    return value | comp;
}
