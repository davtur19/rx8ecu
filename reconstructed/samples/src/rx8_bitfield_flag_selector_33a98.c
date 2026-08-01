/*
 * =============================================================================
 * rx8_bitfield_flag_selector_33a98.c  —  FLAG-SELECTOR LEAF (TOP-NIBBLE CODE)
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x33A98  (43 words, 82 bytes, to 0x33AEA)
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_bitfield_flag_selector_33a98.py
 *               (host-gcc vs tools/sh2emu.py over edge + random status bytes,
 *               comparing the side-effected output byte; 0 mismatches), in
 *               addition to the existing c/tests/test_bitfield_flag_selector_33A98.py
 *               (exhaustive 0..255, 0 errors).
 * Lift (truth): c/bitfield_flag_selector_33A98.c  (IDA-ai symbol
 *               `bitfield_flag_selector`, 0x33A98..0x33AEA).
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * A side-effect-only leaf: it reads a status byte at RAM[0xFFFFCD4E] and packs
 * a priority-select code into the TOP NIBBLE of RAM[0xFFFFC05C] (the low
 * nibble of the output byte is left untouched by construction — v is 0..3 so
 * v<<4 never sets bits 3:0):
 *
 *   b = byte@0xFFFFCD4E
 *   v = (b & 0x40) ? 0 : (b & 0x20) ? 1 : (b & 0x80) ? 2 : 3
 *   byte@0xFFFFC05C = v << 4
 *
 * Priority: 0x40 (bit 6) -> 0, 0x20 (bit 5) -> 1, 0x80 (bit 7) -> 2, else 3,
 * checked in that order.  The result occupies bits 7:4 of the output byte.
 *
 * Disassembly of 60E1D400.bin @ 0x33A98 (43 words, 82 bytes):
 *
 *     33A98: 9455   mov.w  @(0x55,PC),r4   ; r4 = sign-extend(0xCD4E)
 *     33A9A: 6043   mov    r4,r0           ; r0 = input address 0xFFFFCD4E
 *     33A9C: 6000   mov.b  @r0,r0          ; r0 = sign-extend(b), b = byte@0xFFFFCD4E
 *     33A9E: C840   tst    #0x40,r0        ; T = ((b & 0x40) == 0)
 *     33AA0: 0029   movt   r0              ; r0 = (b & 0x40) ? 0 : 1
 *     33AA2: 70FF   add    #-1,r0          ; r0 = (b & 0x40) ? -1 : 0
 *     33AA4: 600B   neg    r0,r0           ; r0 = (b & 0x40) ?  1 : 0
 *     33AA6: 8801   cmp/eq #0x01,r0        ; T = (b & 0x40) != 0
 *     33AA8: 8F02   bf/s   0x33AB0         ;   bit6 CLEAR -> try bit5
 *     33AAA: 0009   nop                    ;   (delay slot)
 *     33AAC: A017   bra    0x33ADE         ;   bit6 SET   -> v = 0
 *     33AAE: E400   mov    #0x00,r4        ;   (delay slot) r4 = 0 (v)
 *     33AB0: 6043   mov    r4,r0           ; .Lbit5: r0 = input address again
 *     33AB2: 6000   mov.b  @r0,r0          ;   re-load b
 *     33AB4: C820   tst    #0x20,r0        ;   same idiom, bit 5
 *     33AB6: 0029   movt   r0
 *     33AB8: 70FF   add    #-1,r0
 *     33ABA: 600B   neg    r0,r0
 *     33ABC: 8801   cmp/eq #0x01,r0
 *     33ABE: 8F02   bf/s   0x33AC6         ;   bit5 CLEAR -> try bit7
 *     33AC0: 0009   nop
 *     33AC2: A00C   bra    0x33ADE         ;   bit5 SET   -> v = 1
 *     33AC4: E401   mov    #0x01,r4        ;   (delay slot) r4 = 1 (v)
 *     33AC6: 6043   mov    r4,r0           ; .Lbit7: r0 = input address again
 *     33AC8: 6000   mov.b  @r0,r0          ;   re-load b
 *     33ACA: C880   tst    #0x80,r0        ;   same idiom, bit 7
 *     33ACC: 0029   movt   r0
 *     33ACE: 70FF   add    #-1,r0
 *     33AD0: 600B   neg    r0,r0
 *     33AD2: 8801   cmp/eq #0x01,r0
 *     33AD4: 8F02   bf/s   0x33ADC         ;   bit7 CLEAR -> v = 3
 *     33AD6: 0009   nop
 *     33AD8: A001   bra    0x33ADE         ;   bit7 SET   -> v = 2
 *     33ADA: E402   mov    #0x02,r4        ;   (delay slot) r4 = 2 (v)
 *     33ADC: E403   mov    #0x03,r4        ;   v = 3 (no priority bit set)
 *     33ADE: 644C   extu.b r4,r4           ;   v &= 0xFF (v is already 0..3)
 *     33AE0: D31D   mov.l  0x33B58,r3      ;   r3 = 0xFFFFC05C (output byte)
 *     33AE2: 4408   shll2  r4              ;   v <<= 2
 *     33AE4: 4408   shll2  r4              ;   v <<= 2   (total v << 4)
 *     33AE6: 000B   rts
 *     33AE8: 2340   mov.b  r4,@r3          ;   (delay slot) byte@0xFFFFC05C = v << 4
 *
 * The bit-test idiom `tst #imm; movt; add #-1; neg; cmp/eq #1` is the same
 * compiler pattern as the sibling status decoder @0x339AC
 * (c/bitfield_flag_status_decoder_339AC.c): the neg flips the movt result so
 * `cmp/eq #1` leaves T = "bit SET", and the following bf/s skips the `bra` that
 * loads the matched v when the bit is clear.
 *
 * DISCREPANCIES vs the lift (documented; behaviour unchanged):
 *   1. The lift's parenthetical "(shll2 r4; shll2 r4 in delay of rts)" is
 *      imprecise about placement: the two shll2 r4 sit at 0x33AE2/0x33AE4,
 *      BEFORE the rts at 0x33AE6; the actual delay slot is the final
 *      `mov.b r4,@r3`.  The shift count (v << 4) is correct.
 *   2. The lift's note "Return r0 is the last-loaded input byte (sign-extended)"
 *      is wrong.  On return r0 holds the matched test block's `neg` result:
 *      0x00000001 if ANY of the priority bits (0x40/0x20/0x80) is set, else
 *      0x00000000 (verified on the emulator over all 256 bytes).  It is not the
 *      input byte and is not part of the ABI contract, so the void lift stands.
 *   3. The ROM re-reads the input byte once per test block (up to 3 loads of
 *      RAM[0xFFFFCD4E]); it is plain RAM (not MMIO), so all reads are identical
 *      and the single volatile read in the C below is behaviourally equivalent.
 *
 * RAM SIDE EFFECT: writes one byte @0xFFFFC05C — the harness compares that
 * byte (the emulator's RAM overlay) against the host's mmap-backed page.
 * =============================================================================
 */
#include <stdint.h>
#include <stddef.h>

#include "rx8_samples.h"

/* Status/flag input byte and select-code output byte are on the on-chip RAM
 * page (0xFFFFC000) but are not (yet) documented in include/rx8_hw.h; they
 * come from the verified lift c/bitfield_flag_selector_33A98.c. */
#define RX8_FLAG_SELECT_IN_ADDR   0xFFFFCD4Eu   /* flag status byte (bit 5/6/7) */
#define RX8_FLAG_SELECT_OUT_ADDR  0xFFFFC05Cu   /* select-code byte (top nibble) */

/* 0x33A98 — select a priority flag code and pack it into the top nibble.
 * Priority: 0x40 -> 0, 0x20 -> 1, 0x80 -> 2, else 3; result written as v << 4.
 * Void leaf: observable effect is the single byte write (r0 is scratch). */
void rx8_bitfield_flag_selector_33a98(void)
{
    uint8_t b = *(volatile uint8_t *)(uintptr_t)RX8_FLAG_SELECT_IN_ADDR;
    uint8_t v = (b & 0x40u) ? 0u : (b & 0x20u) ? 1u : (b & 0x80u) ? 2u : 3u;
    *(volatile uint8_t *)(uintptr_t)RX8_FLAG_SELECT_OUT_ADDR = (uint8_t)(v << 4);
}
