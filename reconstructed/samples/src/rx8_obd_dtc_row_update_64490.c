/*
 * =============================================================================
 * rx8_obd_dtc_row_update_64490.c  —  OBD DTC ROW UPDATE (DELTA-WORD FOLD)
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x64490
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_obd_dtc_row_update_64490.py
 *               (host-gcc vs tools/sh2emu.py over 20000 random + edge vectors;
 *               RAM side-effects compared bit-exactly).
 * Lift (truth): c/obd_dtc_row_update_0x64490.c  (obd_dtc_row_update_0x64490,
 *               0x64490..0x644C4, 52 bytes; also verified in c/tests/).
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * Sibling of the 0x64418 delta-counter fold, but here the driver folds a NEW
 * 16-bit WORD (r4) into the active DTC-table row's 8-bit delta counter.  The
 * active row is picked by a global 16-bit index word (0xFFFF8D74); the table
 * base is 0xFFFF8930 with a 0x34-byte stride.  The row's previous word (+0x02)
 * is folded via its sign-extended half and its high byte; the new word is then
 * stored back at +0x02.  Pure side-effect leaf — r0 merely echoes r4.
 *
 * Disassembly of 60E1D400.bin @ 0x64490:
 *
 *     4F12   sts.l macl,@-r15        ; prologue: mulu.w clobbers macl
 *     E534   mov   #0x34,r5          ; r5 = stride
 *     D25B   mov.l @(0x5B,pc),r2     ; r2 = 0xFFFF8930  (table base)
 *     D35C   mov.l @(0x5C,pc),r3     ; r3 = 0xFFFF8D74  (row-index word)
 *     6631   mov.w @r3,r6            ; r6 = row = s16(word@0xFFFF8D74)
 *     265E   mulu.w r5,r6            ; macl = 0x34 * (row & 0xFFFF)
 *     051A   sts   macl,r5
 *     352C   add   r2,r5             ; r5 = p = 0xFFFF8930 + row*0x34
 *     8551   mov.w @(0x02,r5),r0     ; r0 = w = s16(word@p+0x02)
 *     6703   mov   r0,r7
 *     617D   extu.w r7,r1            ; r1 = w & 0xFFFF
 *     4119   shlr8 r1                ; r1 = (w >> 8) & 0xFF
 *     6603   mov   r0,r6             ; r6 = s16(w)
 *     361C   add   r1,r6             ; r6 = s16(w) + ((w>>8)&0xFF)
 *     674D   extu.w r4,r7            ; r7 = r4 & 0xFFFF
 *     4719   shlr8 r7                ; r7 = ((r4 & 0xFFFF) >> 8) & 0xFF
 *     374C   add   r4,r7             ; r7 = r4 + ((r4&0xFFFF)>>8)   (FULL 32-bit r4!)
 *     3678   sub   r7,r6             ; r6 = delta (mod 2^32)
 *     E032   mov   #0x32,r0
 *     015C   mov.b @(r0,r5),r1       ; r1 = s8(p[0x32])             (old counter)
 *     316C   add   r6,r1             ; r1 = s8(p[0x32]) + delta
 *     0514   mov.b r1,@(r0,r5)       ; p[0x32] = (s8(p[0x32]) + delta) & 0xFF
 *     6043   mov   r4,r0
 *     8151   mov.w r0,@(0x02,r5)     ; word@p+0x02 = r4 & 0xFFFF    (new word)
 *     000B   rts
 *     4F16   lds.l @r15+,macl        ;   (delay slot) restore macl
 *
 * All loads are sign-extending (mov.b/mov.w) and every add/sub is a 32-bit
 * wrap operation; only the low byte of the counter and the low 16 bits of the
 * stored word are observable.  Note the `add r4,r7` uses the FULL 32-bit r4,
 * not r4&0xFFFF — the lift reproduces that (callers pass 16-bit values, but
 * the harness exercises full 32-bit r4 and the mod-2^32 fold is exact either
 * way).
 *
 * CALLING CONVENTION
 * ------------------
 * Entry is the normal ABI: r4 = new 16-bit delta word (uint32_t in C; only
 * low 16 bits are stored, but the fold uses the full register).  Returns
 * nothing meaningful (r0 echoes r4).
 *
 * ROW SPACE / HOST MAPPING
 * ------------------------
 * The reconstructed C dereferences the absolute SH-2 addresses, so the host
 * oracle must MAP_FIXED the pages that back the table.  Rows 0..0x1AA (=426)
 * keep p+0x32 inside the on-chip RAM window (pages 0xFFFF8000..0xFFFFD000);
 * larger rows wrap p below mmap_min_addr and are emulator-only (the harness
 * sweeps them against the same formula on the emulator side).
 * =============================================================================
 */
#include <stdint.h>

#include "rx8_samples.h"

/* 0x64490 — fold r4 into the active DTC row's delta counter.
 *
 *   row = u16@0xFFFF8D74
 *   p   = 0xFFFF8930 + row * 0x34          (32-bit wrap arithmetic)
 *   w   = u16@p+0x02
 *   delta = (s16(w) + ((w>>8)&0xFF)) - (r4 + ((r4&0xFFFF)>>8))
 *   p[0x32] = (s8(p[0x32]) + delta) & 0xFF
 *   word@p+0x02 = r4 & 0xFFFF
 *
 * (int16_t)/(int8_t) casts reproduce the sign-extending mov.w/mov.b loads; the
 * fold is done in 32 bits exactly like the ROM's add/sub sequence, and the
 * `- (int32_t)r4` term reproduces the ROM's full-32-bit `add r4,r7` (a host
 * uint32_t wider than INT32_MAX wraps to the two's-complement value, matching
 * the SH-2E). */
void rx8_obd_dtc_row_update_64490(uint32_t r4)
{
    uint16_t row = *(volatile uint16_t *)0xFFFF8D74;
    uint8_t *p = (uint8_t *)(uintptr_t)(0xFFFF8930u + (uint32_t)row * 0x34u);
    uint16_t w = *(volatile uint16_t *)(p + 0x02);
    int32_t delta = (int32_t)(int16_t)w + (int32_t)((w >> 8) & 0xFF)
                    - (int32_t)r4 - (int32_t)((r4 & 0xFFFF) >> 8);
    p[0x32] = (uint8_t)((int32_t)(int8_t)p[0x32] + delta);
    *(volatile uint16_t *)(p + 0x02) = (uint16_t)r4;
}
