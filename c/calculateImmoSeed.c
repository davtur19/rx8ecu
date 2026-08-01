/*
 * calculateImmoSeed_3675C  —  RX-8 PCM @ ROM 0x3675C (60E1D400.bin)
 *
 * Immobilizer seed calculator (pure function of three 32-bit words).
 * Called from ImmoGetSeed_3664E with:
 *     r4 = *(u32*)0xFFFFC2DC, r5 = *(u32*)0xFFFFC2E0, r6 = 0xFFFFC278 (key)
 *
 * Sums and byte-arithmetic:
 *     sum16 = (r4>>16) + (r6>>16);   sum32 = r4 + r6
 *     m1 = 0x0D * ((sum16 & 0xFFFF) >> 8)
 *     m2 = 0x0D * (sum16 & 0xFFFF)
 *     m3 = 0x0D * ((sum32 & 0xFFFF) >> 8)
 *     m4 = 0x0D * (sum32 & 0xFFFF)              (mulu.w: 16x16 -> 32)
 *     byte0 = m2 & 0xFF;  byte1 = m4 & 0xFF
 *
 * Scale each byte by <<7 plus its high-half:
 *     sc1 = ((x1<<7)>>8) + (x1<<7)   with x1 = m1 & 0xFF
 *     sc2 = ((b0<<7)>>8) + (b0<<7)   with b0 = byte0
 *     sc3 = ((x3<<7)>>8) + (x3<<7)   with x3 = m3 & 0xFF
 *     sc4 = ((b1<<7)>>8) + (b1<<7)   with b1 = byte1   (used as r5 xor mask)
 *
 * Mix with r5 (the second key word):
 *     r14 = (r5>>16) ^ sc2
 *     r7  = sc3 ^ (r5>>8)
 *     r5  = r5  ^ sc4
 *     r6  = sc1 ^ (r5_orig>>24)
 *
 * Then branch on bit 0 of the mixed r5:
 *   odd  (0x36828): byte0 = (r6)          & 0xFF   (unmasked low byte)
 *                   byte1 = (r14)         & 0xFF
 *                   byte2 = fold4(r5 & 0xFF) & 0xFF
 *                   byte3 = fold4(r7 & 0xFF) & 0xFF
 *   even (0x367EE): byte0 = fold4(r14 & 0xFF) & 0xFF
 *                   byte1 = fold4(r6  & 0xFF) & 0xFF
 *                   byte2 = (r7)          & 0xFF
 *                   byte3 = (r5)          & 0xFF
 * where fold4(v) = ((v << 4) + (v >> 4))  (v is a zero-extended byte).
 *
 * Result = (byte0<<24) | (byte1<<16) | (byte2<<8) | byte3.
 *
 * Verified against the emulated ROM in tests/test_ImmoGetSeed.py.
 */
#include "eeprom_immo.h"

static inline uint32_t fold4(uint32_t v)
{
    return ((v << 4) & 0xFFFFFFFFu) + (v >> 4);
}

uint32_t calculateImmoSeed(uint32_t r4, uint32_t r5, uint32_t r6)
{
    uint32_t sum16 = (r4 >> 16) + (r6 >> 16);
    uint32_t sum32 = r4 + r6;

    uint32_t m1 = 0x0Du * (((sum16 & 0xFFFFu) >> 8) & 0xFFFFu);
    uint32_t m2 = 0x0Du * (sum16 & 0xFFFFu);
    uint32_t m3 = 0x0Du * (((sum32 & 0xFFFFu) >> 8) & 0xFFFFu);
    uint32_t m4 = 0x0Du * (sum32 & 0xFFFFu);

    uint32_t byte0 = m2 & 0xFFu;
    uint32_t byte1 = m4 & 0xFFu;

    uint32_t sc1 = ((((m1 & 0xFFu) << 7) & 0xFFFFu) >> 8) + ((m1 & 0xFFu) << 7);
    uint32_t sc2 = ((((byte0 << 7) & 0xFFFFu) >> 8) + (byte0 << 7));
    uint32_t sc3 = ((((m3 & 0xFFu) << 7) & 0xFFFFu) >> 8) + ((m3 & 0xFFu) << 7);
    uint32_t sc4 = ((((byte1 << 7) & 0xFFFFu) >> 8) + ((byte1 << 7) & 0xFFFFu));

    uint32_t r14 = (r5 >> 16) ^ sc2;
    uint32_t r7  = sc3 ^ (r5 >> 8);
    uint32_t r5n = r5 ^ sc4;
    uint32_t r6n = sc1 ^ (r5 >> 24);

    uint32_t b0, b1, b2, b3;

    if (r5n & 1u) {
        /* odd */
        b0 = r6n  & 0xFFu;
        b1 = r14  & 0xFFu;
        b2 = fold4(r5n & 0xFFu) & 0xFFu;
        b3 = fold4(r7  & 0xFFu) & 0xFFu;
    } else {
        /* even */
        b0 = fold4(r14 & 0xFFu) & 0xFFu;
        b1 = fold4(r6n & 0xFFu) & 0xFFu;
        b2 = r7   & 0xFFu;
        b3 = r5n  & 0xFFu;
    }

    return (b0 << 24) | (b1 << 16) | (b2 << 8) | b3;
}
