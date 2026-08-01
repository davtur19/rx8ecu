/*
 * =============================================================================
 * rx8_immo_seed_mixer.c  —  IMMOBILIZER KEY-MIXING PRIMITIVE
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x366B8
 * Status      : VERIFIED — behavioural equivalence to the ROM held by
 *               restored/samples/tests/harness_seed_mixer.py (host-gcc vs
 *               tools/sh2emu.py over random 32-bit word pairs), in addition
 *               to the existing c/tests/verify_emu.py entry (100k random,
 *               0 errors).
 * Lift (truth): c/seed_mixer.c  (same address; IDA-ai symbol
 *               `bitwise_field_encoder_366B8`).
 *
 * CALLERS / ROLE
 * --------------
 * Called 4 times by ImmoKeyExpander_365D6 (@0x365D6) with the two EEPROM key
 * words (RX8_IMMO_KEY_WORD_A @0xFFFFC2DC, RX8_IMMO_KEY_WORD_B @0xFFFFC2E0,
 * shifted) and the rolling code (RX8_IMMO_ROLLING_CODE @0xFFFFC278).  The
 * four outputs become the expected transponder key words
 * (RX8_IMMO_EXPECTED1..4 @0xFFFFC260..0xFFFFC26C), each tagged with a slot
 * prefix (0x01..0x04).
 *
 * The mixing is deliberately non-linear for an anti-replay property: a tiny
 * change in the EEPROM key or in the rolling code must spread across all 24
 * key bits so that a captured seed/response pair cannot be replayed or
 * algebraically inverted.  The ROM does this with four cheap integer steps:
 * a 24-bit byte rebuild, a 6-bit group swap with a fold, a byte-wise
 * two's-complement negation, and a final 32-bit fold.
 *
 * STEP-BY-STEP SEMANTICS (all 32-bit; byte extracts zero-extended)
 *   1. x = rebuild24( key_word[15:8], rolling_word[7:0], key_word[7:0] )
 *   2. swap 6-bit groups: bits 5..10 <-> bits 14..19, fold bit 20 -> bit 11
 *   3. y = byte-wise two's-complement negation of the three low bytes of x
 *   4. z = 32-bit fold: (y << 21) | (y >> 3)   -- NOT a rotate; the high
 *        bits are OR-folded back into the low bits (unknown why, matches ROM)
 *   5. result = byte-swap of z bytes 0 <-> 2
 * =============================================================================
 */
#include <stdint.h>
#include "rx8_samples.h"

/* Step 2 masks (derived from the ROM literal constants):
 *   KEEP     0xFFE0301F — all bits not involved in the swap survive as-is.
 *   SWAP_LO  0x00000FE0 — bits  5..10, shifted up 9 into bits 14..19.
 *   SWAP_HI  0x001FC000 — bits 14..20, shifted down 9 into bits  5..11
 *                         (bit 20 therefore FOLDS into bit 11).          */
#define MIX_KEEP       0xFFE0301Fu
#define MIX_SWAP_LO    0x00000FE0u
#define MIX_SWAP_HI    0x001FC000u

/* Step 4 fold constant: the ROM emits `(y << 21) | (y >> 3)`.  A plain
 * 32-bit rotate would use `(y << 29) | (y >> 3)`; the real code is a fold,
 * so it is preserved verbatim (behavioural equivalence over elegance). */
#define MIX_FOLD_SHL   21u
#define MIX_FOLD_SHR    3u

/* Two's-complement negation of a single byte (0x00 -> 0x00). */
static inline uint8_t rx8_byte_negate(uint8_t v)
{
    return (uint8_t)(0u - (uint32_t)v);
}

uint32_t rx8_immo_seed_mixer(uint32_t key_word, uint32_t rolling_word)
{
    /* Step 1 — 24-bit rebuild: (key[15:8], rolling[7:0], key[7:0]). */
    uint32_t x = (((key_word >> 8) & 0xFFu) << 16)
               | ((rolling_word & 0xFFu) << 8)
               | (key_word & 0xFFu);

    /* Step 2 — swap the 6-bit groups and fold bit 20 into bit 11. */
    x = (x & MIX_KEEP)
      | ((x & MIX_SWAP_LO) << 9)
      | ((x & MIX_SWAP_HI) >> 9);

    /* Step 3 — byte-wise two's complement of the three bytes. */
    uint32_t y = ((uint32_t)rx8_byte_negate((uint8_t)(x >> 16)) << 16)
               | ((uint32_t)rx8_byte_negate((uint8_t)(x >> 8)) << 8)
               | (uint32_t)rx8_byte_negate((uint8_t)x);

    /* Step 4 — 32-bit fold (verbatim from the ROM, see note above). */
    uint32_t z = (y << MIX_FOLD_SHL) | (y >> MIX_FOLD_SHR);

    /* Step 5 — byte swap 0 <-> 2 (bits 7..0 <-> bits 23..16). */
    return ((z & 0xFFu) << 16)
         | (((z >> 8) & 0xFFu) << 8)
         | ((z >> 16) & 0xFFu);
}
