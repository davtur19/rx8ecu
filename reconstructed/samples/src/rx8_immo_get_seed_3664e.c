/*
 * =============================================================================
 * rx8_immo_get_seed_3664e.c  —  IMMOBILIZER SEED COMPUTATION (EEPROM KEYS +
 *                               ROLLING CODE)
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x3664E
 * Status      : VERIFIED — behavioural equivalence to the ROM held by
 *               reconstructed/samples/tests/harness_immo_get_seed_3664e.py
 *               (host-gcc vs tools/sh2emu.py over edge + random vectors,
 *               comparing the side-effected seed word @0xFFFFC270 and the
 *               function's r0; 0 mismatches).
 * Lift (truth): c/ImmoGetSeed.c  (IDA symbol `ImmoGetSeed`; same address).
 *
 * CALLING CONVENTION / ROLE
 * ------------------------
 * ABI-clean void function: NO arguments are used — the incoming r4 (caller's
 * setImmoLight result) is clobbered by the branch-to-subroutine delay slot
 * before the call — and the only observable effects are the 32-bit RAM write
 * to IMMO_SEED_OUT (0xFFFFC270) and the seed value left in r0.
 *
 * ImmoGetSeed recomputes the immobilizer seed from the two EEPROM key words
 * (RAM[0xFFFFC2DC], RAM[0xFFFFC2E0]) and the current rolling code
 * (RAM[0xFFFFC278]) and stores the result into RAM[0xFFFFC270]:
 *
 *     IMMO_SEED_OUT = calculateImmoSeed( *(u32*)0xFFFFC2DC,
 *                                        *(u32*)0xFFFFC2E0,
 *                                        *(u32*)0xFFFFC278 );
 *
 * The heavy lifting is the pure helper calculateImmoSeed @0x3675C (its own
 * verified lift is c/calculateImmoSeed.c).  It is embedded below as a static
 * function so this sample is self-contained.
 *
 * Disassembly of 60E1D400.bin @ 0x3664E (12 words, 24 bytes):
 *
 *     4F22   sts.l   pr,@-r15             ; save return address
 *     D309   mov.l   0x36678,r3           ; r3 = 0xFFFFC278 (rolling code)
 *     6632   mov.l   @r3,r6               ; r6 = rolling code
 *     D209   mov.l   0x3667C,r2           ; r2 = 0xFFFFC2E0 (key word B)
 *     6522   mov.l   @r2,r5               ; r5 = key word B
 *     D10B   mov.l   0x36688,r1           ; r1 = 0xFFFFC2DC (key word A)
 *     B07F   bsr     0x3675C              ; call calculateImmoSeed
 *     6412   mov.l   @r1,r4               ;   (delay) r4 = key word A
 *     D215   mov.l   0x366B4,r2           ; r2 = 0xFFFFC270 (IMMO_SEED_OUT)
 *     4F26   lds.l   @r15+,pr
 *     000B   rts
 *     2202   mov.l   r0,@r2               ;   (delay) IMMO_SEED_OUT = seed
 *
 * Big-endian literals confirmed from the ROM:
 *     0x36678 = 0xFFFFC278   0x3667C = 0xFFFFC2E0
 *     0x36688 = 0xFFFFC2DC   0x366B4 = 0xFFFFC270
 *
 * RAM SIDE EFFECT: writes one 32-bit word @0xFFFFC270 — the harness compares
 * that word (the emulator's RAM overlay) and r0 against the host's
 * mmap-backed page.
 * =============================================================================
 */
#include <stdint.h>

#include "rx8_hw.h"

/* ---------------------------------------------------------------------------
 * calculateImmoSeed @0x3675C — pure seed calculator (verified lift
 * c/calculateImmoSeed.c, which in turn was verified against the emulated ROM
 * in c/tests/test_ImmoGetSeed.py).  Embedded here so the sample is
 * self-contained.  Exact word-for-word 32-bit integer arithmetic of the ROM.
 * ------------------------------------------------------------------------- */
static inline uint32_t rx8_fold4(uint32_t v)
{
    /* ROM idiom `((v << 4) + (v >> 4))`, v is a zero-extended byte. */
    return ((v << 4) & 0xFFFFFFFFu) + (v >> 4);
}

static uint32_t rx8_calculate_immo_seed(uint32_t r4, uint32_t r5, uint32_t r6)
{
    uint32_t sum16 = (r4 >> 16) + (r6 >> 16);
    uint32_t sum32 = r4 + r6;

    uint32_t m1 = 0x0Du * (((sum16 & 0xFFFFu) >> 8) & 0xFFFFu);
    uint32_t m2 = 0x0Du * (sum16 & 0xFFFFu);
    uint32_t m3 = 0x0Du * (((sum32 & 0xFFFFu) >> 8) & 0xFFFFu);
    uint32_t m4 = 0x0Du * (sum32 & 0xFFFFu);          /* 16x16 -> 32 mulu.w */

    uint32_t byte0 = m2 & 0xFFu;
    uint32_t byte1 = m4 & 0xFFu;

    /* Scale each byte by <<7 plus its high half (SH-2 `extu.w` / `shlr8`). */
    uint32_t sc1 = ((((m1 & 0xFFu) << 7) & 0xFFFFu) >> 8) + ((m1 & 0xFFu) << 7);
    uint32_t sc2 = ((((byte0 << 7) & 0xFFFFu) >> 8) + (byte0 << 7));
    uint32_t sc3 = ((((m3 & 0xFFu) << 7) & 0xFFFFu) >> 8) + ((m3 & 0xFFu) << 7);
    uint32_t sc4 = ((((byte1 << 7) & 0xFFFFu) >> 8) + ((byte1 << 7) & 0xFFFFu));

    /* Mix with the second EEPROM key word. */
    uint32_t r14 = (r5 >> 16) ^ sc2;
    uint32_t r7  = sc3 ^ (r5 >> 8);
    uint32_t r5n = r5 ^ sc4;
    uint32_t r6n = sc1 ^ (r5 >> 24);

    uint32_t b0, b1, b2, b3;

    if (r5n & 1u) {
        /* odd: byte0 = r6, byte1 = r14, byte2/3 = folded r5 / r7 */
        b0 = r6n & 0xFFu;
        b1 = r14 & 0xFFu;
        b2 = rx8_fold4(r5n & 0xFFu) & 0xFFu;
        b3 = rx8_fold4(r7 & 0xFFu) & 0xFFu;
    } else {
        /* even: byte0/1 = folded r14 / r6, byte2 = r7, byte3 = r5 */
        b0 = rx8_fold4(r14 & 0xFFu) & 0xFFu;
        b1 = rx8_fold4(r6n & 0xFFu) & 0xFFu;
        b2 = r7 & 0xFFu;
        b3 = r5n & 0xFFu;
    }

    return (b0 << 24) | (b1 << 16) | (b2 << 8) | b3;
}

/* 0x3664E — recompute the immobilizer seed into IMMO_SEED_OUT (0xFFFFC270).
 * The seed is not read back; it is recomputed on demand (e.g. to answer a
 * key-challenge) from the EEPROM key words and the rolling code. */
void rx8_immo_get_seed(void)
{
    RX8_IMMO_SEED_OUT = rx8_calculate_immo_seed(
        RX8_IMMO_KEY_WORD_A,       /* *(u32*)0xFFFFC2DC, EEPROM[0x02..05] */
        RX8_IMMO_KEY_WORD_B,       /* *(u32*)0xFFFFC2E0, EEPROM[0x06..09] */
        RX8_IMMO_ROLLING_CODE);    /* *(u32*)0xFFFFC278 rolling code      */
}
