/*
 * seed_mixer_366B8  —  RX-8 PCM @ ROM 0x366B8 (60E1D400.bin)
 *
 * Immobilizer key-mixing primitive (pure function of two 32-bit words).
 * Called from ImmoKeyExpander_365D6 (4 times) with the EEPROM key words
 * (0xFFFFC2E0 / 0xFFFFC2DC, shifted) and the rolling code (0xFFFFC278).
 *
 * Step 1: byte-rebuild x from (r4&0xFFFF)>>8, r5&0xFF, r4&0xFF:
 *         x = ((r4>>8)&0xFF)<<16 | (r5&0xFF)<<8 | (r4&0xFF)
 * Step 2: swap 6-bit groups bits 5..10 <-> bits 14..19, fold bit 20 -> bit 11:
 *         x = (x & 0xFFE0301F) | ((x & 0x0FE0) << 9) | ((x & 0x001FC000) >> 9)
 * Step 3: byte-wise two's-complement negate (0x6n7m not / 0x6nBm neg):
 *         y = (-(x>>16)&0xFF)<<16 | (-(x>>8)&0xFF)<<8 | (-(x)&0xFF)
 * Step 4: fold: z = (y << 21) | (y >> 3)
 * Step 5: byte-swap 0<->2: ((z&0xFF)<<16) | ((z>>8)&0xFF)<<8 | ((z>>16)&0xFF)
 *
 * All arithmetic is 32-bit; byte extracts are zero-extended.  Verified against
 * the emulated ROM in tests/test_ImmoKeyExpander.py.
 */
#include "eeprom_immo.h"

uint32_t seed_mixer(uint32_t r4, uint32_t r5)
{
    uint32_t x = ((r4 >> 8) & 0xFF) << 16 | ((r5 & 0xFF) << 8) | (r4 & 0xFF);

    x = (x & 0xFFE0301Fu) | ((x & 0x0FE0u) << 9) | ((x & 0x001FC000u) >> 9);

    uint32_t y = ((uint32_t)(uint8_t)(0u - (x >> 16)) << 16)
               | ((uint32_t)(uint8_t)(0u - (x >> 8)) << 8)
               | (uint32_t)(uint8_t)(0u - x);

    uint32_t z = ((y << 21) & 0xFFFFFFFFu) | (y >> 3);

    return ((z & 0xFFu) << 16) | (((z >> 8) & 0xFFu) << 8) | ((z >> 16) & 0xFFu);
}
