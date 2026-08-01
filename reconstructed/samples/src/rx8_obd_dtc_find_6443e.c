/*
 * =============================================================================
 * rx8_obd_dtc_find_6443e.c  —  OBD DTC-TABLE SEARCH LEAF
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x6443E
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_obd_dtc_find_6443e.py
 *               (host-gcc + mmap vs tools/sh2emu.py over edge + N random
 *               vectors; return value AND DTC-table RAM checksum compared).
 * Lift (truth): c/obd_dtc_find_0x6443E.c  (verified bit-exact vs the ROM
 *               emulator in c/tests/test_obd_dtc_find_0x6443E.{py,c})
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * The OBD-II response path walks the 21-row DTC table at RX8_DTC_TABLE_BASE
 * (0xFFFF8930, stride 0x34) looking for the first row whose byte at +0x06
 * matches the caller's byte key (r4) — but never the row whose index equals
 * the "current row" word @0xFFFF8D74 (that fault is already being serviced).
 * On a hit it returns the row's byte at +0x08 SIGN-EXTENDED to 32 bits; with
 * no hit it returns the default 0x08.  Disassembly of 60E1D400.bin @ 0x6443E:
 *
 *     E500   mov   #0x00,r5            ; i = 0
 *     D770   mov.l 0x64604,r7          ; r7 = 0xFFFF8930 (table base)
 *     E634   mov   #0x34,r6            ; r6 = 0x34 (stride)
 *     2FE6   mov.l r14,@-r15           ; prologue: push r14
 *     E115   mov   #0x15,r1            ; r1 = 0x15 (21 rows)
 *     4F12   sts.l macl,@-r15          ;          push macl
 *     EE08   mov   #0x08,r14           ; r14 = default return value
 *     loop:
 *     0567   mul.l r6,r5               ; macl = 0x34 * i
 *     031A   sts   macl,r3
 *     337C   add   r7,r3               ; p = base + 0x34*i
 *     8436   mov.b @(0x06,r3),r0       ; r0 = s8(byte@p+6)
 *     600C   extu.b r0,r0
 *     634C   extu.b r4,r3              ; key = r4 & 0xFF
 *     3030   cmp/eq r3,r0              ; byte@p+6 == key ?
 *     8F0C   bf/s  .next               ; no  -> continue
 *     0009   nop
 *     D26A   mov.l 0x64608,r2          ; r2 = &0xFFFF8D74 (current-row word)
 *     6321   mov.w @r2,r3
 *     633D   extu.w r3,r3              ; currow = u16 word
 *     3350   cmp/eq r5,r3              ; i == currow ?
 *     8D06   bt/s  .next               ; yes -> skip this row
 *     0009   nop
 *     0567   mul.l r6,r5
 *     0E1A   sts   macl,r14
 *     3E7C   add   r7,r14              ; p = base + 0x34*i
 *     84E8   mov.b @(0x08,r14),r0      ; r0 = s8(byte@p+8)
 *     A009   bra   .ret
 *     6E03   mov   r0,r14              ;   (delay) r14 = s8(byte@p+8)
 *     .next:
 *     0567   mul.l r6,r5
 *     031A   sts   macl,r3
 *     337C   add   r7,r3
 *     8437   mov.b @(0x07,r3),r0       ; r0 = s8(byte@p+7)  <-- see note below
 *     7501   add   #0x01,r5            ; i++
 *     2008   tst   r0,r0               ; T = (byte@p+7 == 0)
 *     3513   cmp/ge r1,r5              ; T = (i >= 0x15)   <-- overwrites T!
 *     8FE2   bf/s  loop                ; continue while i < 21
 *     0009   nop
 *     .ret:
 *     4F16   lds.l @r15+,macl
 *     60E3   mov   r14,r0              ; result in r0
 *     000B   rts
 *     6EF6   mov.l @r15+,r14           ;   (delay) pop r14
 *
 * The loop runs exactly 21 iterations (i = 0..0x14): after row 20 it reads
 * byte@p+7, i becomes 21, `cmp/ge` sees 21 >= 21 and the `bf/s` falls through
 * to the default return.  Note the `mov.b @(0x07,r3),r0` + `tst r0,r0` pair in
 * the loop tail: the T bit it sets is IMMEDIATELY overwritten by the following
 * `cmp/ge r1,r5`, so byte@p+7 has NO effect on control flow.  That read is a
 * dead compiler artifact of the original source (probably a dropped
 * `p[7] == 0` term) and is deliberately NOT modelled — behaviourally the loop
 * is the plain bounded scan of the lift.
 *
 * CALLING CONVENTION
 * ------------------
 * Normal ABI entry: r4 = byte search key (only the low 8 bits are used —
 * `extu.b r4,r3`).  Result returned in r0 as a sign-extended 32-bit int.
 *
 * RAM SIDE EFFECTS
 * ----------------
 * None on the DTC table itself: the only writes are the r14/macl stack pushes
 * in the prologue/epilogue.  The harness still compares a checksum of the
 * whole DTC region (0xFFFF8930..0xFFFF8D73) before/after to prove it.
 * =============================================================================
 */
#include <stdint.h>

#include "rx8_samples.h"
#include "rx8_hw.h"

/* Current-row index word @0xFFFF8D74, one word past the last table row.
 * (Documented in rx8_hw.h's RX8_DTC_TABLE_* block; not itself a macro there.) */
#define RX8_DTC_CURROW_ADDR 0xFFFF8D74u

/* 0x6443E — find the first DTC-table row matching the byte key whose index
 * differs from the active row; return its +0x08 byte sign-extended, else 0x08. */
int32_t rx8_obd_dtc_find_6443e(uint32_t r4)
{
    uint8_t key = (uint8_t)r4;                          /* extu.b r4,r3        */
    uint16_t currow = *(volatile uint16_t *)RX8_DTC_CURROW_ADDR;   /* mov.w + extu.w */

    for (uint32_t i = 0; i < RX8_DTC_TABLE_ROWS; i++) {
        uint8_t *p = (uint8_t *)(uintptr_t)(RX8_DTC_TABLE_BASE + i * RX8_DTC_TABLE_STRIDE);
        if (p[0x06] == key && i != currow) {
            return (int32_t)(int8_t)p[0x08];            /* mov.b sign-extends  */
        }
    }
    return 0x08;                                        /* r14 default 0x08     */
}
