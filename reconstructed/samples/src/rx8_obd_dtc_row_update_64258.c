/*
 * =============================================================================
 * rx8_obd_dtc_row_update_64258.c  —  OBD DTC-TABLE ACTIVE-ROW COUNTER UPDATE
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x64258  (70 bytes: 0x64258..0x6429D)
 * Status      : VERIFIED — behavioural equivalence to the ROM held by
 *               reconstructed/samples/tests/harness_obd_dtc_row_update_64258.py
 *               (host-gcc + mmap vs tools/sh2emu.py over edge + random
 *               pre-states of the DTC row; 0 mismatches).
 * Lift (truth): c/obd_dtc_row_update_0x64258.c  (same address, same bytes;
 *               the lift was verified bit-exact against the ROM via the
 *               emulator in tools/sh2emu.py — c/tests/test_obd_dtc_row_update_0x64258.py).
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * A side-effect-only leaf (no arguments, no meaningful return) that refreshes
 * the two "persistence" counters of the ACTIVE OBD DTC-table row.  The table
 * lives at 0xFFFF8930 with 0x34-byte rows (21 rows, 0..0x14); the active row
 * index is the 16-bit word at 0xFFFF8D74 — which is exactly the first two
 * bytes of row 21, bounding the table.  The ROM path is:
 *
 *     4F12   sts.l  macl,@-r15        ; prologue (macl is clobbered by mulu.w)
 *     E434   mov    #0x34,r4          ; r4 = stride
 *     9372   mov.w  0x64344,r3        ; r3 = 0x00FF  (+255 == -1)
 *     D73C   mov.l  0x64350,r7        ; r7 = &row-index word (0xFFFF8D74)
 *     D63C   mov.l  0x64354,r6        ; r6 = DTC table base (0xFFFF8930)
 *     6571   mov.w  @r7,r5            ; r5 = active row index (16-bit)
 *     254E   mulu.w r4,r5             ; macl = stride * row
 *     041A   sts    macl,r4
 *     346C   add    r6,r4             ; p = base + row*stride  (32-bit wrap)
 *     8447   mov.b  @(0x07,r4),r0     ; r0 = p[7] (sign-extended)
 *     6503   mov    r0,r5
 *     353C   add    r3,r5             ; p[7] + 0xFF
 *     E032   mov    #0x32,r0
 *     024C   mov.b  @(r0,r4),r2       ; r2 = p[0x32]
 *     325C   add    r5,r2
 *     0424   mov.b  r2,@(r0,r4)       ; p[0x32] = (p[0x32] + p[7] + 0xFF) & 0xFF
 *     9265   mov.w  0x64346,r2        ; r2 = 0x00F9  (+249 == -7)
 *     E001   mov    #0x01,r0
 *     8047   mov.b  r0,@(0x07,r4)     ; p[7] = 1
 *     E434   mov    #0x34,r4          ; second pass: re-loads the row index
 *     6571   mov.w  @r7,r5            ; (same row — the first pass never wrote
 *     254E   mulu.w r4,r5             ;  the index word), re-derives p
 *     041A   sts    macl,r4
 *     346C   add    r6,r4
 *     8448   mov.b  @(0x08,r4),r0     ; r0 = p[8] (sign-extended)
 *     6503   mov    r0,r5
 *     352C   add    r2,r5             ; p[8] + 0xF9
 *     E032   mov    #0x32,r0
 *     014C   mov.b  @(r0,r4),r1       ; r1 = p[0x32] (just updated above)
 *     315C   add    r5,r1
 *     0414   mov.b  r1,@(r0,r4)       ; p[0x32] = (p[0x32] + p[8] + 0xF9) & 0xFF
 *     E007   mov    #0x07,r0
 *     8048   mov.b  r0,@(0x08,r4)     ; p[8] = 7
 *     000B   rts
 *     4F16   lds.l  @r15+,macl        ; (delay slot) epilogue
 *
 * BIT-EXACTNESS NOTES
 * -------------------
 *  - `mulu.w` + `sts macl` produce the full 32-bit product; the host model
 *    uses (uint32_t)row * stride in 32-bit unsigned arithmetic (row is a
 *    uint16_t, so the product always fits — no wrap ever occurs).
 *  - `mov.b @(disp,rn),r0` SIGN-extends the byte, so p[7]/p[8]/p[0x32] are
 *    loaded as int8/int16; but every add feeds a `mov.b` store that keeps only
 *    the low byte, and sign-extension is congruent mod 256 — the lift's plain
 *    uint8_t arithmetic is bit-identical.
 *  - The two `+0xFF` / `+0xF9` constants are small 16-bit unsigned literals
 *    (mov.w sign-extends 0x00FF to +255, 0x00F9 to +249).
 * =============================================================================
 */
#include <stdint.h>
#include "rx8_samples.h"
#include "rx8_hw.h"

/* Active OBD DTC-table row index (16-bit word).  Not yet in rx8_hw.h; it
 * aliases the first two bytes of row 0x14 — the table is bounded by its own
 * index word (RX8_DTC_TABLE_BASE + 0x14*0x34 == 0xFFFF8D74). */
#define RX8_DTC_ROW_INDEX_ADDR  0xFFFF8D74u

/* 0x64258 — refresh the two persistence counters of the active DTC-table row:
 *   p[0x32] = (p[0x32] + p[0x07] + 0xFF) & 0xFF   (decrement-by-one update)
 *   p[0x07] = 1
 *   p[0x32] = (p[0x32] + p[0x08] + 0xF9) & 0xFF   (decrement-by-seven update)
 *   p[0x08] = 7
 * Side-effect only; return r0 (= 7) is not meaningful, lift returns void. */
void rx8_obd_dtc_row_update_64258(void)
{
    uint16_t row = *(volatile uint16_t *)RX8_DTC_ROW_INDEX_ADDR;
    uint8_t *p = (uint8_t *)(uintptr_t)(RX8_DTC_TABLE_BASE
                                        + (uint32_t)row * RX8_DTC_TABLE_STRIDE);
    p[0x32] = (uint8_t)(p[0x32] + p[0x07] + 0xFFu);
    p[0x07] = 1u;
    p[0x32] = (uint8_t)(p[0x32] + p[0x08] + 0xF9u);
    p[0x08] = 7u;
}
