/*
 * =============================================================================
 * rx8_obd_dtc_find_643d4.c  —  OBD DTC-TABLE SEARCH LEAF (21 ROWS)
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x643D4
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_obd_dtc_find_643d4.py
 *               (host-gcc vs tools/sh2emu.py over 20000 random + edge vectors,
 *               0 mismatches), in addition to the existing emulator + host
 *               tests c/tests/test_obd_dtc_find_0x643D4.{py,c}.
 * Lift (truth): c/obd_dtc_find_0x643D4.c  (same address; the function is a
 *               leaf of the OBD service handler family at 0x643D4, called with
 *               the 16-bit DTC key in r4).
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * OBD service handlers resolve a diagnostic-trouble-code key against the RAM
 * DTC table (RX8_DTC_TABLE_BASE 0xFFFF8930, RX8_DTC_TABLE_ROWS 21 rows, stride
 * RX8_DTC_TABLE_STRIDE 0x34) and return the byte-0x06 "status" of the first
 * matching row.  The active-row index (word @0xFFFF8D74) is excluded so the
 * just-cleared / just-read row is never re-reported by this path.  Disassembly
 * of 60E1D400.bin @ 0x643D4 (66 bytes, 0x643D4..0x64417; rts @0x64416):
 *
 *     4F12   sts.l  macl,@-r15      ; prologue: save macl only (never popped)
 *     E500   mov    #0x00,r5        ; r5 = i = 0
 *     D78A   mov.l  @(8,pc),r7      ; r7 = 0xFFFF8930 (DTC table base)
 *     E634   mov    #0x34,r6        ; r6 = stride
 *     6153   mov    r5,r1           ; r1 = result default = 0
 *     E015   mov    #0x15,r0        ; r0 = row count (0x15 = 21)
 * .loop: 0567 mul.l  r6,r5          ; macl = i * 0x34
 *     031A   sts    macl,r3
 *     337C   add    r7,r3           ; r3 = p = base + i*0x34
 *     6231   mov.w  @r3,r2          ; r2 = s16(word@p)          (sign-extended)
 *     622D   extu.w r2,r2           ; r2 = word@p (unsigned 16)
 *     634D   extu.w r4,r3           ; r3 = key = r4 & 0xFFFF
 *     3230   cmp/eq r3,r2           ; T = (word@p == key)
 *     8F0C   bf/s   .next           ; word mismatch -> next row
 *     0009   nop
 *     D285   mov.l  @(4,pc),r2      ; r2 = 0xFFFF8D74 (currow addr)
 *     6321   mov.w  @r2,r3          ; r3 = s16(word@0xFFFF8D74)
 *     633D   extu.w r3,r3           ; r3 = currow (unsigned)
 *     3350   cmp/eq r5,r3           ; T = (i == currow)
 *     8D06   bt/s   .next           ; active row skipped -> next row
 *     0009   nop
 *     0567   mul.l  r6,r5           ; found: redo p (macl clobbered)
 *     011A   sts    macl,r1
 *     317C   add    r7,r1
 *     8416   mov.b  @(0x06,r1),r0   ; r0 = s8(byte@p+0x06)      (sign-extended)
 *     A004   bra    .ret
 *     6103   mov    r0,r1           ;   (delay) r1 = result
 * .next: 7501 add    #0x01,r5       ; i++
 *     3503   cmp/ge r0,r5           ; T = (i+1 >= 0x15)
 *     8FE7   bf/s   .loop           ; i < 0x15 -> continue
 *     0009   nop
 * .ret: 6013 mov    r1,r0           ; r0 = result
 *     000B   rts
 *
 * The loop is pure RAM reads; the only side effect is the stack save of macl
 * (unrestored by the ROM — a caller-side imbalance, faithfully reproduced by
 * the emulator and irrelevant to the return value).  Word reads go through
 * mov.w (sign-extend to 32 bits) then extu.w (mask to 16) — i.e. an unsigned
 * 16-bit compare; byte-0x06 goes through mov.b alone, i.e. a SIGN-extended s8
 * that is the 32-bit return value.  Neither is equivalent to the other's
 * masking on the return path.
 *
 * CALLING CONVENTION
 * ------------------
 * Plain ABI entry: r4 = 16-bit DTC key (upper 16 bits ignored, masked by the
 * `extu.w r4,r3` compare); result returned in r0 (int32_t, either 0 or the
 * sign-extended s8 status byte).  No FPU, no arguments beyond r4.
 * =============================================================================
 */
#include <stdint.h>
#include "rx8_hw.h"
#include "rx8_samples.h"

/* Active-row index word: the row that is currently being serviced/cleared by
 * the OBD handler and must therefore never match this search.  Documented in
 * FINDINGS.md (OBD DTC-table family) but not (yet) exported by rx8_hw.h. */
#define RX8_DTC_CURROW 0xFFFF8D74u

/* 0x643D4 — first row whose 16-bit word matches (r4 & 0xFFFF) and whose index
 * differs from the active row index; return its byte-0x06 sign-extended, or 0
 * if no such row. */
int32_t rx8_obd_dtc_find_643d4(uint32_t r4)
{
    uint16_t key = r4 & 0xFFFF;
    uint16_t currow = *(volatile uint16_t *)RX8_DTC_CURROW;
    for (uint32_t i = 0; i < RX8_DTC_TABLE_ROWS; i++) {
        uint8_t *p = (uint8_t *)(uintptr_t)(RX8_DTC_TABLE_BASE
                                          + i * RX8_DTC_TABLE_STRIDE);
        /* mov.w sign-extends but the extu.w right after makes it an unsigned
         * 16-bit compare — exactly `*(volatile uint16_t *)p == key`. */
        if (*(volatile uint16_t *)p == key && i != currow) {
            /* mov.b is a pure sign-extend: the full 32-bit value IS the ROM's
             * r0/r1 return, so (int8_t) then (int32_t) — no extu after. */
            return (int32_t)(int8_t)p[0x06];
        }
    }
    return 0;
}
