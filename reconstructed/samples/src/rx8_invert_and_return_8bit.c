/*
 * =============================================================================
 * rx8_invert_and_return_8bit.c  —  8-BIT VALUE/COMPLEMENT CHECKSUM RESIDUAL
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x2044
 * Status      : VERIFIED — behavioural equivalence to the ROM held by
 *               reconstructed/samples/tests/harness_invert_and_return_8bit.py
 *               (host-gcc vs tools/sh2emu.py over random + edge (hi,lo) pairs),
 *               in addition to the existing c/tests/test_math_primitives.py
 *               entry (30000 random + exact-complement edge pairs, 0 errors).
 * Lift (truth): c/math_primitives.c (function invertAndReturn_8bit_ADDR @0x2044).
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * The SH-2E is a 16-bit big-endian machine; Denso stores the value/complement
 * checksummed byte pairs that `encode()` (0x2420) produces as one 16-bit cell
 * and validates them with this tiny reader.  The ROM path is:
 *
 *     mov.w  @r4,r3       ; r3 = 16-bit big-endian cell (hi<<8 | lo), sign-ext
 *     mov    r3,r0
 *     shlr8  r3           ; r3 = hi (logical shift; upper half discarded)
 *     not    r0,r0        ; r0 = ~cell  (low byte is ~lo)
 *     sub    r3,r0        ; r0 = ~cell - hi
 *     rts
 *     extu.b r0,r0        ;   (delay slot) return low byte: (~lo - hi) & 0xFF
 *
 * Modulo 256, `~lo - hi` equals `~(hi + lo)`, so the function computes the
 * ones'-complement residual of the pair.  It is 0 exactly when hi == ~lo (i.e.
 * the cell is self-consistent, the same convention `encode()` and the
 * c/mem_accessors.c redundant-cell family use); any other value is the amount
 * of corruption, so this reader doubles as a sanity check for the value/
 * complement cell pairs sprinkled through calibration RAM.
 *
 * The reconstructed C reads the two bytes individually instead of one 16-bit
 * load so the model is endian-neutral and byte-exact on any host compiler.
 * =============================================================================
 */
#include <stdint.h>
#include "rx8_samples.h"

uint8_t rx8_invert_and_return_8bit(const uint8_t *addr)
{
    uint8_t hi = addr[0];
    uint8_t lo = addr[1];
    return (uint8_t)~(uint8_t)(hi + lo);
}
