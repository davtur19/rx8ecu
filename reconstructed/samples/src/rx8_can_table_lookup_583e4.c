/*
 * =============================================================================
 * rx8_can_table_lookup_583e4.c  —  CAN-ID TABLE SCAN + MATCH ACCUMULATOR
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x583E4  (100 bytes = 0x64, 0x583E4..0x58447)
 * Size        : M2 (100 B) — 0x24 = 36 table entries scanned
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_can_table_lookup_583e4.py
 *               (host-gcc + mmap vs tools/sh2emu.py over edge + N random
 *               vectors, comparing the r0 return value bit-for-bit;
 *               0 mismatches).
 * Lift (truth): c/memory_match_accumulate_583E4.c (same address).  That lift
 *               was drafted before the 60E1D400.bin disassembly was resolved;
 *               the discrepancies listed at the bottom were found by diffing
 *               it against the disassembly during this lift and are corrected
 *               here — the ROM bytes executed by tools/sh2emu.py are the
 *               ground truth.
 *
 * WHAT THE FUNCTION DOES
 * ----------------------
 * Scans a fixed 36-entry, 6-byte-per-entry table in ROM (0x0005FFEE) that
 * looks like a CAN message-ID filter table, and accumulates the data byte of
 * every entry matching three criteria:
 *
 *     1. entry signature (u16 BE at +0) == expected-id cell RAM[0xFFFFD226]
 *     2. entry filter   (u8  at +3)     == (r5 & 0xFF)
 *     3. entry word     (u16 BE at +4)  &  bitmask RAM[0xFFFFD3F0]  != 0
 *
 * and returns `r4 & accum` (the caller ANDs the accumulated sum with a mask,
 * i.e. picks a subset of the accumulated flag bits).
 *
 * The 6-byte entry layout (verified against the disassembly and the ROM
 * bytes):
 *     +0..1  u16  BE  signature / CAN id          (mov.w @r6)
 *     +2     u8        data / flag byte           (mov.b @(2,r7), SIGN-EXT)
 *     +3     u8        filter / type byte         (mov.b @(3,r6))
 *     +4..5  u16  BE  word tested against mask    (mov.w @(4,r14))
 *
 * ROM bytes of the table @0x5FFEE (first of the 36 scanned entries):
 *     09 68 | 01 01 | ff fc     09 68 | 20 01 | ff fc     09 d3 | 01 01 | 15 5c
 *     11 01 | 01 01 | ff fc     11 01 | 02 01 | ff fc     11 01 | 08 01 | ff fc
 *     11 02 | 01 01 | ff fc     11 03 | 04 01 | ff fc     11 03 | 08 01 | ff fc
 *     11 03 | 10 01 | 15 5c     11 03 | 20 01 | ff fc     11 04 | 01 01 | ff fc
 *     11 04 | 10 01 | ff fc     16 31 | 01 01 | ff fc     16 31 | 02 01 | ff fc
 *     16 81 | 40 01 | ff fc     16 88 | 20 01 | ff fc     a2 11 | 04 01 | ff fc
 *     a2 11 | 10 01 | ff fc     a2 11 | 01 02 | 9d dc     17 11 | 80 01 | ff fc
 *     17 06 | 04 01 | ff fc     17 18 | 01 01 | ff fc     17 15 | 40 01 | ff fc
 *     17 15 | 80 01 | ff fc     17 de | 01 01 | ff fc     17 10 | 20 05 | 00 00
 *     17 10 | 10 05 | 00 00     17 10 | 08 05 | 00 00     17 10 | 04 05 | 00 00
 *     17 10 | 02 05 | ff fc     17 10 | 01 05 | ff fc     ff 10 | 40 01 | 00 01
 *     ff 10 | 20 01 | 00 01     ff 10 | 08 01 | 00 01     ff 10 | 04 01 | 00 01
 * (two further 6-byte rows exist at 0x600C6..0x600D1 but are BEYOND the
 * 36-entry scan window and are never read.)
 *
 * Not called by any bsr/jsr in this ROM (dead code in the N3J1 60E1D400
 * variant; in 60E0FC00 the twin at 0x55E68 is bsr'd from ~12 diagnostic
 * callers).  No callees, no RAM writes: the whole effect is the return value.
 *
 * CALLING CONVENTION
 * ------------------
 * `uint32_t rx8_can_table_lookup_583e4(uint32_t mask, uint8_t filter)`
 *   r4 = mask (result AND mask), r5 = filter (only the low byte is used,
 *   `extu.b r5`), return r0 = mask & accum.  SH-2 ABI; prologue pushes
 *   r14/r13/r12/r9/r8 (no pr), r15 restored on exit.  Verified from the
 *   disassembly of 60E1D400.bin @0x583E4:
 *
 *     0x583E4:  2FE6  mov.l  r14,@-r15
 *     0x583E6:  E600  mov    #0x00,r6
 *     0x583E8:  D027  mov.l  @(0x27,pc),r0    ; r0 = 0x0005FFEE (table base)
 *     0x583EA:  E124  mov    #0x24,r1         ; r1 = 36 (entry count)
 *     0x583EC:  934B  mov.w  @(0x4B,pc),r3    ; r3 = s16(0xD3F0) = 0xFFFFD3F0
 *     0x583EE:  6703  mov    r0,r7            ; r7 = table base (+6/iter)
 *     0x583F0:  2FD6  mov.l  r13,@-r15
 *     0x583F2:  6E03  mov    r0,r14           ; r14 = table base (+6/iter)
 *     0x583F4:  2FC6  mov.l  r12,@-r15
 *     0x583F6:  6D63  mov    r6,r13           ; r13 = 0 (counter)
 *     0x583F8:  2F96  mov.l  r9,@-r15
 *     0x583FA:  6C63  mov    r6,r12           ; r12 = 0 (accumulator)
 *     0x583FC:  2F86  mov.l  r8,@-r15
 *     0x583FE:  6603  mov    r0,r6            ; r6 = table base (+6/iter)
 *     0x58400:  6931  mov.w  @r3,r9           ; r9 = RAM16[0xFFFFD3F0] bitmask
 *     0x58402:  D822  mov.l  @(0x22,pc),r8    ; r8 = 0xFFFFD226 (id cell)
 *     0x58404:  6261  mov.w  @r6,r2           ; entry signature (s16)
 *     0x58406:  6381  mov.w  @r8,r3           ; expected id (re-read each iter)
 *     0x58408:  3230  cmp/eq r3,r2            ; signature match?
 *     0x5840A:  8F0E  bf/s   0x5842A
 *     0x5840C:  0009  nop
 *     0x5840E:  635C  extu.b r5,r3            ; r3 = filter & 0xFF
 *     0x58410:  8463  mov.b  @(0x03,r6),r0    ; entry filter byte
 *     0x58412:  600C  extu.b r0,r0
 *     0x58414:  3030  cmp/eq r3,r0            ; filter match?
 *     0x58416:  8F08  bf/s   0x5842A
 *     0x58418:  0009  nop
 *     0x5841A:  639D  extu.w r9,r3            ; r3 = bitmask
 *     0x5841C:  85E2  mov.w  @(0x04,r14),r0   ; entry word +4
 *     0x5841E:  600D  extu.w r0,r0
 *     0x58420:  2308  tst    r0,r3            ; (word & bitmask) == 0 ?
 *     0x58422:  8D02  bt/s   0x5842A
 *     0x58424:  0009  nop
 *     0x58426:  8472  mov.b  @(0x02,r7),r0    ; entry data byte (SIGN-EXT s8)
 *     0x58428:  3C0C  add    r0,r12           ; accum += s8(data)
 *     0x5842A:  7D01  add    #0x01,r13        ; loop tail
 *     0x5842C:  7706  add    #0x06,r7
 *     0x5842E:  7E06  add    #0x06,r14
 *     0x58430:  63DC  extu.b r13,r3
 *     0x58432:  3313  cmp/ge r1,r3            ; (r13&0xFF) >= 36 ?
 *     0x58434:  8FE6  bf/s   0x58404
 *     0x58436:  7606  add    #0x06,r6         ;   (delay) r6 += 6
 *     0x58438:  68F6  mov.l  @r15+,r8
 *     0x5843A:  24C9  and    r12,r4           ; r4 = mask & accum
 *     0x5843C:  69F6  mov.l  @r15+,r9
 *     0x5843E:  6043  mov    r4,r0            ; r0 = result
 *     0x58440:  6CF6  mov.l  @r15+,r12
 *     0x58442:  6DF6  mov.l  @r15+,r13
 *     0x58444:  000B  rts
 *     0x58446:  6EF6  mov.l  @r15+,r14        ;   (delay)
 *
 * NOTE the two `mov.w @(disp,PC)` literals: the SH-2E sign-extends word
 * immediates, so the literal 0xD3F0 becomes the HIGH-page address 0xFFFFD3F0
 * (on-chip RAM bitmask cell) — it is NOT a ROM address.  Likewise 0xFFFFD226
 * (an id / CAN-receive cell, see also the UDS dispatch lift @0x582A6).
 *
 * RAM CELLS (read; both seeded by the harness)
 * --------------------------------------------
 *   0xFFFFD226  u16  expected signature / CAN id   (input)
 *   0xFFFFD3F0  u16  bitmask applied to entry word+4 (input)
 *
 * CAL TABLES (ROM-fixed, read-only)
 * ---------------------------------
 *   0x0005FFEE  36 x 6-byte CAN filter entries (see dump above)
 *
 * CALLEES
 * -------
 *   None — self-contained straight-line loop, no bsr/jsr in the body.
 *
 * DISCREPANCIES vs c/memory_match_accumulate_583E4.c
 * ---------------------------------------------------
 *   1. Bitmask address was a placeholder in the lift
 *      (`*(volatile uint16_t *)((void*)0)`).  The ROM loads the mov.w literal
 *      0xD3F0 SIGN-EXTENDED into 0xFFFFD3F0 and reads RAM there.
 *   2. The lift's accumulate condition `(bitmask & 0xFFFFu) != 0` is table
 *      independent (a constant).  The ROM tests `(entry_word_at_plus4 &
 *      bitmask) != 0` — table-dependent.
 *   3. The lift adds entry byte+2 as an unsigned 8-bit value.  The ROM loads
 *      it with a SIGN-EXTENDING mov.b; the 0x1711/0x1715 rows carry byte2 =
 *      0x80, so a matching signature contributes -128 and accum can be
 *      negative (corrected here: `(uint32_t)(int32_t)(int8_t)`).
 *   4. The lift reads the expected id once; the ROM re-reads RAM[0xFFFFD226]
 *      every iteration (a volatile MMIO-style read — functionally identical
 *      here since nothing writes the cell during the scan).
 *   5. The lift's `expected_sig`/`bitmask` reads were modelled as non-volatile
 *      locals; here both RAM reads are byte-assembled BE (endian-neutral, so
 *      the little-endian host oracle sees the same numbers the BE emulator
 *      does — same pattern as rx8_get_maf_sensor_value.c's rom_u16).
 * =============================================================================
 */
#include <stdint.h>

#include "rx8_hw.h"

/* Fixed machine addresses straight from the mov.l / mov.w literals of the
 * ROM body (see the annotated disassembly in the header). */
#define RX8_CAN_TBL_ADDR   0x0005FFEEu   /* ROM: 36 x 6-byte filter table */
#define RX8_CAN_ENTRY_N    36u           /* 0x24 entries scanned          */
#define RX8_CAN_ENTRY_SZ   6u            /* bytes per entry               */
#define RX8_CAN_SIG_ADDR   0xFFFFD226u   /* u16 expected CAN id (RAM)     */
#define RX8_CAN_BM_ADDR    0xFFFFD3F0u   /* u16 bitmask (RAM)             */

/* Big-endian u16 read (SH-2E is BE; the host oracle maps the ROM pages and
 * seeds the RAM cells big-endian, so byte assembly is endianness-neutral and
 * both sides read the identical number). */
static uint16_t rx8_can_be16(uint32_t addr)
{
    const volatile uint8_t *p = (const volatile uint8_t *)(uintptr_t)addr;
    return (uint16_t)((uint16_t)p[0] << 8) | p[1];
}

uint32_t rx8_can_table_lookup_583e4(uint32_t mask, uint8_t filter)
{
    const uint8_t *table = (const uint8_t *)(uintptr_t)RX8_CAN_TBL_ADDR;
    uint32_t accum = 0;
    uint32_t i;

    /* Criteria, loaded once: bitmask from RAM[0xFFFFD3F0] (ROM: mov.w @r3,r9
     * before the loop); the expected id from RAM[0xFFFFD226] (ROM re-reads it
     * inside the loop — same value, nothing writes it during the scan). */
    uint16_t bitmask = rx8_can_be16(RX8_CAN_BM_ADDR);
    uint16_t exp_sig = rx8_can_be16(RX8_CAN_SIG_ADDR);

    for (i = 0; i < RX8_CAN_ENTRY_N; i++) {
        const uint8_t *e = table + i * RX8_CAN_ENTRY_SZ;
        uint16_t sig   = (uint16_t)((uint16_t)e[0] << 8) | e[1];
        uint16_t word4 = (uint16_t)((uint16_t)e[4] << 8) | e[5];

        /* 0x58408 cmp/eq (signature), 0x58414 cmp/eq (filter byte),
         * 0x58420 tst (word & bitmask).  Byte+2 is added SIGN-EXTENDED
         * (mov.b @(2,r7),r0 = s8, then 32-bit add). */
        if (sig == exp_sig &&
            e[3] == (filter & 0xFFu) &&
            (word4 & bitmask) != 0) {
            accum += (uint32_t)(int32_t)(int8_t)e[2];
        }
    }

    /* 0x5843A: r4 = r4 & r12  ->  return mask & accum. */
    return mask & accum;
}
