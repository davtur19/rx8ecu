/*
 * =============================================================================
 * rx8_immo_key_expander_365d6.c  —  IMMOBILIZER KEY-SET EXPANDER (4 SLOTS)
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x365D6
 * Status      : VERIFIED — behavioural equivalence to the ROM held by
 *               reconstructed/samples/tests/harness_immo_key_expander_365d6.py
 *               (host-gcc vs tools/sh2emu.py over random + edge vectors,
 *               all 8 written RAM words compared bit-exactly).
 * Lift (truth): c/ImmoKeyExpander.c  (ImmoKeyExpander_365D6 @ 0x365D6;
 *               called from ImmoWaitForKey_35F92 on first contact / unpaired
 *               to build the expected key set before the challenge CAN id).
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * A memory-to-memory leaf: it reads the current rolling code
 * (IMMO_KEYGEN_ADC @ 0xFFFFC278) and the two EEPROM key words
 * (0xFFFFC2E0 / 0xFFFFC2DC) and derives the four expected transponder key
 * words by driving the key-mixing primitive 4 times, then stores them with a
 * slot-number prefix.  Disassembly of 60E1D400.bin @ 0x365D6 (condensed):
 *
 *   2FE6  mov.l r14,@-r15             ; prologue
 *   4F22  sts.l pr,@-r15
 *   DE27  mov.l 0x36678,r14           ; r14 = 0xFFFFC278 (rolling code)
 *   D327  mov.l 0x3667C,r3            ; r3  = 0xFFFFC2E0 (key word B)
 *   65E2  mov.l @r14,r5               ; r5  = key
 *   B06A  bsr   0x366B8               ; seed_mixer(r4, r5)
 *   6432  mov.l @r3,r4                ;   (delay) r4 = w2E0
 *   D326  mov.l 0x36680,r3            ; r3  = 0xFFFFC24C
 *   2302  mov.l r0,@r3                ; slot0 = seed_mixer(w2E0, key)
 *   65E2  mov.l @r14,r5               ; r5 = key
 *   4519  shlr8 r5                    ;      key >> 8
 *   D123  mov.l 0x3667C,r1
 *   6412  mov.l @r1,r4                ; r4 = w2E0
 *   B062  bsr   0x366B8
 *   4429  shlr16 r4                   ;   (delay) r4 = w2E0 >> 16
 *   ...                               ; slot1 = seed_mixer(w2E0>>16, key>>8)
 *   65E2  mov.l @r14,r5               ; slot2 = seed_mixer(w2DC, key>>16)
 *   4529  shlr16 r5
 *   ...
 *   65E2  mov.l @r14,r5               ; slot3 = seed_mixer(w2DC>>16, key>>24)
 *   4529  shlr16 r5
 *   6412  mov.l @r1,r4
 *   4519  shlr8 r5                    ; r4 = w2DC>>16, r5 = key>>24
 *   ...
 *   213B  or    r3,r1                 ; exp = slot | slot_number (0x01..0x04)
 *   ...                               ; store @ 0xFFFFC260/264/268/26C
 *   4F26  lds.l @r15+,pr
 *   000B  rts
 *   6EF6  mov.l @r15+,r14             ;   (delay) epilogue
 *
 * So, verbatim from the ROM (argument order matches the c/seed_mixer.c
 * signature `seed_mixer(key_word, rolling_word)`):
 *
 *   slot0 = seed_mixer(w2E0,     key)          -> IMMO_KEY_SLOT0 @ 0xFFFFC24C
 *   slot1 = seed_mixer(w2E0>>16, key>>8)       -> IMMO_KEY_SLOT1 @ 0xFFFFC250
 *   slot2 = seed_mixer(w2DC,     key>>16)      -> IMMO_KEY_SLOT2 @ 0xFFFFC254
 *   slot3 = seed_mixer(w2DC>>16, key>>24)      -> IMMO_KEY_SLOT3 @ 0xFFFFC258
 *
 * and then the slot-number-tagged expected words:
 *
 *   IMMO_EXPECTED1..4 @ 0xFFFFC260/0xFFFFC264/0xFFFFC268/0xFFFFC26C
 *       = slot0|0x01000000, slot1|0x02000000, slot2|0x03000000, slot3|0x04000000
 *
 * CALLING CONVENTION
 * ------------------
 * The routine takes NO arguments in r4-r7 and returns nothing meaningful in
 * r0 (it is left pointing at the last literal-pool address it loaded); all
 * of its state lives in RAM.  `cpu.call(ADDR, ram=...)` in the harness is
 * therefore sufficient — there is no non-ABI register convention to drive.
 *
 * DISCREPANCY NOTES vs c/ImmoKeyExpander.c
 * ----------------------------------------
 * None functional: the lift's store sequence matches the ROM literal-pool
 * write targets exactly (slots first, then the OR-tagged expected words).
 * One stylistic difference: the ROM reloads key/w2E0/w2DC from RAM on every
 * slot (4x/2x/2x reads); caching them in locals is behaviourally identical
 * because nothing writes those words between the reads.
 *
 * The seed_mixer primitive (@0x366B8, reached via `bsr`) is inlined here as
 * a static helper instead of a call to rx8_immo_seed_mixer() so the sample
 * stays self-contained under the mandated oracle build (exactly two .c files,
 * no -lm); the body is the verified lift c/seed_mixer.c (see also
 * rx8_immo_seed_mixer.c).
 * =============================================================================
 */
#include <stdint.h>

#include "rx8_samples.h"

/* Immobilizer RAM map (c/eeprom_immo.h macros, verbatim addresses). */
#define IMMO_KEYGEN_ADC    (*(volatile uint32_t *)0xFFFFC278u)
#define IMMO_KEY_WORD_B    (*(volatile uint32_t *)0xFFFFC2E0u)   /* key word B */
#define IMMO_KEY_WORD_A    (*(volatile uint32_t *)0xFFFFC2DCu)   /* key word A */
#define IMMO_KEY_SLOT0     (*(volatile uint32_t *)0xFFFFC24Cu)
#define IMMO_KEY_SLOT1     (*(volatile uint32_t *)0xFFFFC250u)
#define IMMO_KEY_SLOT2     (*(volatile uint32_t *)0xFFFFC254u)
#define IMMO_KEY_SLOT3     (*(volatile uint32_t *)0xFFFFC258u)
#define IMMO_EXPECTED1     (*(volatile uint32_t *)0xFFFFC260u)
#define IMMO_EXPECTED2     (*(volatile uint32_t *)0xFFFFC264u)
#define IMMO_EXPECTED3     (*(volatile uint32_t *)0xFFFFC268u)
#define IMMO_EXPECTED4     (*(volatile uint32_t *)0xFFFFC26Cu)

/* seed_mixer @0x366B8 — the verified key-mixing primitive (c/seed_mixer.c,
 * rx8_immo_seed_mixer.c), inlined for a self-contained sample build. */
static uint32_t key_expander_mix(uint32_t key_word, uint32_t rolling_word)
{
    /* Step 1 — 24-bit rebuild: (key[15:8], rolling[7:0], key[7:0]). */
    uint32_t x = (((key_word >> 8) & 0xFFu) << 16)
               | ((rolling_word & 0xFFu) << 8)
               | (key_word & 0xFFu);

    /* Step 2 — swap 6-bit groups bits 5..10 <-> bits 14..19, fold bit 20
     * into bit 11. */
    x = (x & 0xFFE0301Fu)
      | ((x & 0x00000FE0u) << 9)
      | ((x & 0x001FC000u) >> 9);

    /* Step 3 — byte-wise two's-complement negation of the three bytes. */
    uint32_t y = ((uint32_t)(uint8_t)(0u - (x >> 16)) << 16)
               | ((uint32_t)(uint8_t)(0u - (x >> 8)) << 8)
               | (uint32_t)(uint8_t)(0u - x);

    /* Step 4 — 32-bit fold (NOT a rotate, matches ROM). */
    uint32_t z = (y << 21) | (y >> 3);

    /* Step 5 — byte swap 0 <-> 2. */
    return ((z & 0xFFu) << 16)
         | (((z >> 8) & 0xFFu) << 8)
         | ((z >> 16) & 0xFFu);
}

void rx8_immo_key_expander_365d6(void)
{
    uint32_t key = IMMO_KEYGEN_ADC;
    uint32_t w2E0 = IMMO_KEY_WORD_B;
    uint32_t w2DC = IMMO_KEY_WORD_A;

    IMMO_KEY_SLOT0 = key_expander_mix(w2E0, key);
    IMMO_KEY_SLOT1 = key_expander_mix(w2E0 >> 16, key >> 8);
    IMMO_KEY_SLOT2 = key_expander_mix(w2DC, key >> 16);
    IMMO_KEY_SLOT3 = key_expander_mix(w2DC >> 16, key >> 24);

    IMMO_EXPECTED1 = IMMO_KEY_SLOT0 | 0x01000000u;
    IMMO_EXPECTED2 = IMMO_KEY_SLOT1 | 0x02000000u;
    IMMO_EXPECTED3 = IMMO_KEY_SLOT2 | 0x03000000u;
    IMMO_EXPECTED4 = IMMO_KEY_SLOT3 | 0x04000000u;
}
