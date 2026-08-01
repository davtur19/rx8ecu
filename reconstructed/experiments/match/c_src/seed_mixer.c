/*
 * seed_mixer — ROM 0x366B8 (60E1D400.bin), Immobilizer key-mixing primitive.
 *
 * Behavioral reference only (semantics VERIFIED in c/seed_mixer.c against the
 * emulated ROM, see c/tests/verify_emu.py).  The ROM body (164 bytes,
 * rom_hex/seed_mixer_366B8.txt) is low-optimization codegen that stores and
 * reloads byte fields through stack slots; an idiomatic -O2 rewrite compiles
 * to very different bytes.  Byte-identity for this function is NOT expected
 * from idiomatic C — see REPORT.md §4/§5.
 */
#include <stdint.h>

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
