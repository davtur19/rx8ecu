/*
 * =============================================================================
 * rx8_obd_dtc_row_update_64418.c  —  OBD DTC ROW UPDATE (DELTA-COUNTER FOLD)
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x64418
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_obd_dtc_row_update_64418.py
 *               (host-gcc vs tools/sh2emu.py over 20000 random + edge vectors;
 *               RAM side-effects compared bit-exactly).
 * Lift (truth): c/obd_dtc_row_update_0x64418.c  (obd_dtc_row_update_0x64418,
 *               0x64418..0x6443E, 38 bytes)
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * OBD DTC bookkeeping leaf: the OBD monitor folds the current "count" byte
 * (r4) into the active DTC-table row's delta counter and stores it back as
 * the row's new delta.  The active row is picked by a global 16-bit index word
 * (0xFFFF8D74); the table base is 0xFFFF8930 with a 0x34-byte stride.  It is a
 * pure side-effect leaf — nothing meaningful is returned (r0 just echoes r4).
 *
 * Disassembly of 60E1D400.bin @ 0x64418:
 *
 *     4F12   sts.l pr,@-r15          ; prologue (leaf never calls: PR save
 *     0x64418                        ;   is vestigial)
 *     E534   mov   #0x34,r5          ; r5 = stride
 *     D279   mov.l @(0x79,pc),r2     ; r2 = 0xFFFF8930  (table base)
 *     D37A   mov.l @(0x7A,pc),r3     ; r3 = 0xFFFF8D74  (row-index word)
 *     6631   mov.w @r3,r6            ; r6 = row = s16(word@0xFFFF8D74)
 *     265E   mulu.w r5,r6            ; macl = 0x34 * row
 *     051A   sts   macl,r5
 *     352C   add   r2,r5             ; r5 = p = 0xFFFF8930 + row * 0x34
 *     8458   mov.b @(8,r5),r0        ; r0 = s8(p[8])               (old delta)
 *     6603   mov   r0,r6
 *     3648   sub   r4,r6             ; r6 = s8(p[8]) - r4
 *     E032   mov   #0x32,r0
 *     015C   mov.b @(r0,r5),r1       ; r1 = s8(p[0x32])            (old counter)
 *     316C   add   r6,r1             ; r1 = s8(p[0x32]) + s8(p[8]) - r4
 *     0514   mov.b r1,@(r0,r5)       ; p[0x32] = r1 & 0xFF         (new counter)
 *     6043   mov   r4,r0
 *     8058   mov.b r0,@(8,r5)        ; p[8] = r4 & 0xFF            (new delta)
 *     000B   rts
 *     4F16   lds.l @r15+,pr          ;   (delay slot)
 *
 * All byte loads are sign-extending mov.b; the delta fold is done in 32-bit
 * integer arithmetic and only the low byte is stored back — i.e. the whole
 * expression wraps mod 2^32 then truncates to 8 bits.
 *
 * CALLING CONVENTION
 * ------------------
 * Entry is the normal ABI: r4 = new count byte (the ROM only uses its low
 * byte, but the fold is a 32-bit `sub`, so the C takes uint32_t and the
 * harness exercises full 32-bit r4 values too).
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

/* 0x64418 — fold r4 into the active DTC row's delta counter.
 *
 *   row = u16@0xFFFF8D74
 *   p   = 0xFFFF8930 + row * 0x34          (32-bit wrap arithmetic)
 *   p[0x32] = (s8(p[0x32]) + s8(p[0x08]) - r4) & 0xFF
 *   p[0x08] = r4 & 0xFF
 *
 * (int8_t) casts reproduce the sign-extending mov.b loads; the sum is done in
 * 32 bits exactly like the ROM's sub/add sequence.  `(int32_t)r4` on a host
 * uint32_t wider than INT32_MAX is the two's-complement wrap, matching the
 * SH-2E's 32-bit subtract. */
void rx8_obd_dtc_row_update_64418(uint32_t r4)
{
    uint16_t row = *(volatile uint16_t *)(uintptr_t)0xFFFF8D74u;
    uint8_t *p = (uint8_t *)(uintptr_t)(0xFFFF8930u + (uint32_t)row * 0x34u);
    p[0x32] = (uint8_t)((int32_t)(int8_t)p[0x32] + (int32_t)(int8_t)p[0x08]
                        - (int32_t)r4);
    p[0x08] = (uint8_t)r4;
}
