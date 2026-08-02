/*
 * =============================================================================
 * rx8_calculate_immo_seed.c  —  IMMOBILIZER SEED CALCULATOR (PURE)
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x3675C
 * Status      : VERIFIED — behavioural equivalence to the ROM held by
 *               reconstructed/samples/tests/harness_calculate_immo_seed.py
 *               (host-gcc vs tools/sh2emu.py over edge + N random 32-bit
 *               triples, comparing the returned seed word; 0 mismatches).
 * Lift (truth): c/calculateImmoSeed.c  (IDA symbol `calculateImmoSeed_3675C`;
 *               same address; already verified against the emulated ROM in
 *               c/tests/test_ImmoGetSeed.py).
 *
 * CALLING CONVENTION / ROLE
 * ------------------------
 * ABI-clean, PURE leaf function of three 32-bit words passed in the first
 * three argument registers and returning the seed in r0:
 *
 *     uint32_t calculateImmoSeed(uint32_t r4, uint32_t r5, uint32_t r6);
 *
 * It is called exactly once from ImmoGetSeed_3664E (c/ImmoGetSeed.c) with
 *
 *     r4 = *(u32*)0xFFFFC2DC   (EEPROM key word A, EEPROM[0x02..05])
 *     r5 = *(u32*)0xFFFFC2E0   (EEPROM key word B, EEPROM[0x06..09])
 *     r6 = *(u32*)0xFFFFC278   (rolling code / keygen output)
 *
 * and the returned r0 is stored by the caller to IMMO_SEED_OUT @0xFFFFC270.
 *
 * RAM SIDE EFFECTS
 * ----------------
 * NONE.  The routine itself neither reads nor writes any RAM cell — all of
 * its working state lives in registers and in the 0xF8-byte stack frame it
 * allocates (r15 -= 0xF8, then restored).  It is a pure function of r4/r5/r6.
 *
 *   read  (caller side, ImmoGetSeed_3664E, NOT this function):
 *      0xFFFFC2DC  u32  EEPROM key word A   -> r4
 *      0xFFFFC2E0  u32  EEPROM key word B   -> r5
 *      0xFFFFC278  u32  rolling code        -> r6
 *   write (caller side, ImmoGetSeed_3664E, NOT this function):
 *      0xFFFFC270  u32  IMMO_SEED_OUT = returned seed
 *
 * CALIBRATION TABLES
 * ------------------
 * None.  The only magic constant is the immediate 0x0D (13) loaded as the
 * SH-2 `mulu.w` multiplier (mov #0x0D,r2 @0x36770) — the ROM repeats the
 * same multiply four times over shifted copies of the two sums.
 *
 * INTERNAL CALLEES
 * ----------------
 * None — leaf function; no bsr/jsr/braf inside the 0x3675C..0x3686E body.
 *
 * DISASSEMBLY of 60E1D400.bin @ 0x3675C (condensed; 0x3675C..0x3686E):
 *
 *   2FE6  mov.l r14,@-r15            ; prologue (r14 saved, r15 -= 0xF8)
 *   7FF8  add    #0xF8,r15
 *   6743  mov    r4,r7 ; 4729 shlr16 r7     ; r7 = r4>>16
 *   6263  mov    r6,r2 ; 4229 shlr16 r2     ; r2 = r6>>16
 *   372C  add    r2,r7                       ; r7 = sum16
 *   346C  add    r6,r4                       ; r4 = sum32
 *   667D  extu.w r7,r6 ; 4619 shlr8 r6       ; r6 = (sum16>>8)&0xFF
 *   E20D  mov    #0x0D,r2
 *   262E  mulu.w r2,r6 ; 061A sts macl,r6   ; r6 = m1
 *   272E  mulu.w r2,r7 ; 071A sts macl,r7   ; r7 = m2
 *   2F70  mov.b  r7,@r15                     ; byte0 -> stack[0]
 *   674D  extu.w r4,r7 ; 4719 shlr8 r7       ; r7 = (sum32>>8)&0xFF
 *   272E  mulu.w r2,r7 ; 071A sts macl,r7   ; r7 = m3
 *   242E  mulu.w r2,r4 ; 001A sts macl,r0   ; r0 = m4
 *   646C  extu.b r6,r4                       ; x1 = m1&0xFF
 *   80F4  mov.b  r0,@(0x04,r15)              ; byte1 -> stack[4]
 *   4408x3,4400 shll2/shl -> r4 = x1<<7 ; 664D extu.w, 4619 shlr8, 364C add
 *                                           ; r6 = sc1
 *   6E53  mov r5,r14 ; 4E29 shlr16 r14       ; r14 = r5>>16
 *   64F0  mov.b @r15,r4                      ; b0 = byte0
 *   (<<7, extu.w, shlr8, add)                ; r3 = sc2 ; 2F30 mov.b r3,@r15
 *   647C  extu.b r7,r4                       ; x3 = m3&0xFF
 *   84F4  mov.b @(0x04,r15),r0               ; b1 = byte1
 *   (<<7, extu.w, shlr8, add)                ; r7 = sc3 ; r4 = sc4 (via r1)
 *   6153  mov r5,r1 ; 4129 shlr16 ; 4119 shlr8  ; r1 = r5>>24 (orig)
 *   2E3A  xor r3,r14                         ; r14 ^= sc2
 *   6053  mov r5,r0 ; 4019 shlr8 ; 270A xor  ; r7 ^= r5>>8
 *   254A  xor r4,r5                          ; r5 ^= sc4
 *   635C  extu.b r5,r3 ; E001 mov #1,r0 ; 2038 tst r3,r0
 *   8F1D  bf/s 0x36828  (odd -> 0x36828)
 *   261A  xor r1,r6                          ;  (delay) r6 ^= r5>>24
 *   even 0x367EE:  b0=fold4(r14&0xFF), b1=fold4(r6&0xFF), b2=r7, b3=r5
 *   odd  0x36828:  b0=r6, b1=r14, b2=fold4(r5&0xFF), b3=fold4(r7&0xFF)
 *   644C  extu.b r4 ; shll2+shll8 -> b0<<24 ; 666C extu.b r6 ; shll16 -> b1<<16
 *   346C  add ; 6EEC extu.b r14 ; shll8 ; 34EC add ; 633C extu.b r3 ; 343C add
 *   6043  mov r4,r0 ; 7F08 add #0x08,r15     ; epilogue
 *   000B  rts
 *   6EF6  mov.l @r15+,r14                    ;  (delay)
 *
 * STEP-BY-STEP SEMANTICS (all 32-bit; byte extracts zero-extended)
 * ---------------------------------------------------------------
 *   1. sum16 = (r4>>16) + (r6>>16);   sum32 = r4 + r6
 *   2. four 16x16->32 multiplies by 0x0D (mulu.w, result in macl):
 *        m1 = 0x0D * ((sum16 & 0xFFFF) >> 8)
 *        m2 = 0x0D * (sum16 & 0xFFFF)
 *        m3 = 0x0D * ((sum32 & 0xFFFF) >> 8)
 *        m4 = 0x0D * (sum32 & 0xFFFF)
 *      byte0 = m2 & 0xFF;  byte1 = m4 & 0xFF
 *   3. per-byte scale "x<<7 plus its high half" (ROM idiom: shll2/shll8/
 *      shll to make <<7, extu.w then shlr8 for >>8, then add):
 *        sc1 = ((x1 << 7) >> 8) + (x1 << 7),  x1 = m1 & 0xFF
 *        sc2 = ((b0 << 7) >> 8) + (b0 << 7),  b0 = byte0
 *        sc3 = ((x3 << 7) >> 8) + (x3 << 7),  x3 = m3 & 0xFF
 *        sc4 = ((b1 << 7) >> 8) + (b1 << 7),  b1 = byte1
 *      (the <<7 operands are capped at 0xFFFF by extu.w before the >>8,
 *      which is a no-op for these byte values — kept for exactness)
 *   4. mix with the second key word r5:
 *        r14 = (r5 >> 16) ^ sc2
 *        r7  = sc3 ^ (r5 >> 8)
 *        r5  = r5  ^ sc4
 *        r6  = sc1 ^ (r5_orig >> 24)         -- original r5 high byte
 *   5. branch on bit 0 of the mixed r5 (ROM bf/s @0x367EA):
 *      odd  (bit 0 set,  @0x36828):
 *        b0 = r6  & 0xFF      b1 = r14 & 0xFF
 *        b2 = fold4(r5 & 0xFF)  b3 = fold4(r7 & 0xFF)
 *      even (bit 0 clear, @0x367EE):
 *        b0 = fold4(r14 & 0xFF)  b1 = fold4(r6 & 0xFF)
 *        b2 = r7 & 0xFF      b3 = r5 & 0xFF
 *      where fold4(v) = (v << 4) + (v >> 4) over a zero-extended byte
 *      (the ROM's ">>4" is `shar`; v < 256 so arithmetic == logical here).
 *   6. result = (b0 << 24) | (b1 << 16) | (b2 << 8) | b3   in r0.
 *
 * DISCREPANCY NOTES vs c/calculateImmoSeed.c
 * ------------------------------------------
 * None functional: the lift was re-derived from a fresh disassembly of the
 * ROM bytes at 0x3675C and matches instruction-for-instruction.  One
 * cosmetic difference: the lift names the mixed key words r5n/r6n while this
 * file keeps the ROM's register names (r5, r6, r7, r14) to stay close to the
 * original assembly.  The `& 0xFFFFu` in the sc1..sc4 terms is redundant for
 * byte values and is carried over verbatim from the lift for exactness.
 * =============================================================================
 */
#include <stdint.h>

#include "rx8_samples.h"

/* ROM idiom `(v << 4) + (v >> 4)`, v is a zero-extended byte. */
static inline uint32_t rx8_fold4(uint32_t v)
{
    return ((v << 4) & 0xFFFFFFFFu) + (v >> 4);
}

uint32_t rx8_calculate_immo_seed(uint32_t r4, uint32_t r5, uint32_t r6)
{
    /* Step 1 — the two 32-bit sums the seed is built from. */
    uint32_t sum16 = (r4 >> 16) + (r6 >> 16);
    uint32_t sum32 = r4 + r6;

    /* Step 2 — four 16x16->32 multiplies by the constant 0x0D (mulu.w). */
    uint32_t m1 = 0x0Du * (((sum16 & 0xFFFFu) >> 8) & 0xFFFFu);
    uint32_t m2 = 0x0Du * (sum16 & 0xFFFFu);
    uint32_t m3 = 0x0Du * (((sum32 & 0xFFFFu) >> 8) & 0xFFFFu);
    uint32_t m4 = 0x0Du * (sum32 & 0xFFFFu);

    uint32_t byte0 = m2 & 0xFFu;
    uint32_t byte1 = m4 & 0xFFu;

    /* Step 3 — per-byte scale: ((b << 7) >> 8) + (b << 7). */
    uint32_t sc1 = ((((m1 & 0xFFu) << 7) & 0xFFFFu) >> 8) + ((m1 & 0xFFu) << 7);
    uint32_t sc2 = ((((byte0 << 7) & 0xFFFFu) >> 8) + (byte0 << 7));
    uint32_t sc3 = ((((m3 & 0xFFu) << 7) & 0xFFFFu) >> 8) + ((m3 & 0xFFu) << 7);
    uint32_t sc4 = ((((byte1 << 7) & 0xFFFFu) >> 8) + ((byte1 << 7) & 0xFFFFu));

    /* Step 4 — mix with the second EEPROM key word (r5).  The ROM reads the
     * original r5 high byte (`shlr16`+`shlr8` @0x367D4..0x367D8) into r1
     * BEFORE r5 is overwritten by the sc4 xor (@0x367E2), so the high byte
     * is captured first. */
    uint32_t r5_hi = r5 >> 24;
    uint32_t r14 = (r5 >> 16) ^ sc2;
    uint32_t r7  = sc3 ^ (r5 >> 8);
    r5           = r5 ^ sc4;
    r6           = sc1 ^ r5_hi;

    uint32_t b0, b1, b2, b3;

    if (r5 & 1u) {
        /* odd — byte0 = r6, byte1 = r14, byte2/3 = folded r5 / r7 */
        b0 = r6  & 0xFFu;
        b1 = r14 & 0xFFu;
        b2 = rx8_fold4(r5 & 0xFFu) & 0xFFu;
        b3 = rx8_fold4(r7 & 0xFFu) & 0xFFu;
    } else {
        /* even — byte0/1 = folded r14 / r6, byte2 = r7, byte3 = r5 */
        b0 = rx8_fold4(r14 & 0xFFu) & 0xFFu;
        b1 = rx8_fold4(r6  & 0xFFu) & 0xFFu;
        b2 = r7 & 0xFFu;
        b3 = r5 & 0xFFu;
    }

    /* Step 6 — assemble the 4 seed bytes big-endian into the result. */
    return (b0 << 24) | (b1 << 16) | (b2 << 8) | b3;
}
