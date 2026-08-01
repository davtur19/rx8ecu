/*
 * =============================================================================
 * rx8_rev_limit_fuel_cut_init.c  —  REV-LIMITER FUEL-CUT COUNTER INIT
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0xF0FC  (30 bytes: 0xF0FC..0xF11A)
 * Status      : VERIFIED — behavioural equivalence to the ROM held by
 *               reconstructed/samples/tests/harness_rev_limit_fuel_cut_init.py
 *               (host-gcc + mmap vs tools/sh2emu.py over random + edge
 *               pre-states; bit-exact RAM side effects incl. sentinels).
 * Lift (truth): c/revLimitFuelCutInit.c  (revLimitFuelCutInit @ 0x00F0FC,
 *               30 bytes, same semantics; cross-checked with
 *               c/tests/test_revLimitFuelCutInit.py's byte assertions).
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * Startup / re-enable initialisation of the rev-limiter fuel-cut counters in
 * on-chip RAM.  If the rev-limit enable flag at 0xFFFF9F8C equals 1, three
 * counter cells are zeroed; otherwise the function is a pure no-op.  The ROM
 * sequence (60E1D400.bin @ 0xF0FC) is:
 *
 *     D33D  mov.l @(0x3D,pc),r3   ; r3 = 0xFFFF9F8C  (rev-limit enable flag)
 *     6030  mov.b @r3,r0          ; r0 = (int8) flag
 *     600C  extu.b r0,r0          ; r0 = (uint8) flag
 *     8801  cmp/eq #1,r0          ; T = (flag == 1)
 *     8F07  bf  0xF116            ; flag != 1  -> skip the stores, rts
 *     0009  nop
 *     9168  mov.w @(0x68,pc),r1   ; r1 = 0xFFFFA4A4  (16-bit lit, sign-ext)
 *     E400  mov   #0,r4
 *     9267  mov.w @(0x67,pc),r2   ; r2 = 0xFFFFA4A5
 *     2140  mov.b r4,@r1          ; counter cell A = 0   (BYTE store)
 *     2240  mov.b r4,@r2          ; counter cell B = 0   (BYTE store)
 *     D339  mov.l @(0x39,pc),r3   ; r3 = 0xFFFFA4A8
 *     2341  mov.w r4,@r3          ; counter cell C = 0   (WORD store!)
 *     000B  rts
 *     0009  nop                   ;   (delay slot)
 *
 * STORE-WIDTH SUBTLETY (verified against the ROM, matches the lift):
 *   The three zeroing stores are NOT all the same width: cells A (0xFFFFA4A4)
 *   and B (0xFFFFA4A5) are `mov.b` (byte), but cell C is `mov.w r4,@r3`
 *   (0x2341, low nibble 1 = word) — a 16-bit store that also clears the
 *   adjacent byte 0xFFFFA4A9.  The lift's `*accum = 0` with accum a uint16_t
 *   @ 0xFFFFA4A8 is therefore exactly right.  An initial byte-store reading
 *   of 0x2341 was caught by this harness's sentinel byte at 0xFFFFA4A9 (the
 *   ROM clears it; a byte-store C would leave it) — the sentinel pins the
 *   width, and the reconstruction below uses RX8_IO16 for cell C.
 *
 * CALLING CONVENTION
 * ------------------
 * Standard leaf entry: no arguments (ABI r4-r7 / fr4-fr7 untouched by the
 * caller side), return via `rts`/PR.  `cpu.call()` is sufficient for the
 * harness — the function reads no input registers, only the RAM flag.
 *
 * The three cells (0xFFFFA4A4, 0xFFFFA4A5, 0xFFFFA4A8) have no rx8_hw.h
 * entries yet (not in the project notes); their roles as rev-limiter fuel-cut
 * counters come from the verified lift and are annotated *unknown, matches
 * ROM* accordingly.  Note the family of sibling functions at 0xF26x/0xF34x
 * (lit pool at 0xF272..0xF36A) that consume these same cells.
 * =============================================================================
 */
#include <stdint.h>
#include "rx8_samples.h"
#include "rx8_hw.h"

/* Rev-limit enable flag — when == 1 the counter cells are cleared on init.
 * Role: *unknown, matches ROM* (c/revLimitFuelCutInit.c). */
#define RX8_REV_LIMIT_EN_FLAG   0xFFFF9F8Cu

/* Rev-limiter fuel-cut counter cells in on-chip RAM; roles *unknown, matches
 * ROM* (lift c/revLimitFuelCutInit.c).  Cells A and B are single bytes; cell
 * C is a 16-bit word cleared with `mov.w r4,@r3` (also clears 0xFFFFA4A9). */
#define RX8_RL_CNT_A_ADDR       0xFFFFA4A4u  /* counter cell A (u8) */
#define RX8_RL_CNT_B_ADDR       0xFFFFA4A5u  /* counter cell B (u8) */
#define RX8_RL_ACCUM_ADDR       0xFFFFA4A8u  /* counter cell C (u16, WORD store!) */

/* 0xF0FC — initialise the rev-limiter fuel-cut counters (no-op unless the
 * rev-limit enable flag == 1). */
void rx8_rev_limit_fuel_cut_init(void)
{
    if (RX8_IO8(RX8_REV_LIMIT_EN_FLAG) == 1u) {
        RX8_IO8(RX8_RL_CNT_A_ADDR)  = 0u;
        RX8_IO8(RX8_RL_CNT_B_ADDR)  = 0u;
        RX8_IO16(RX8_RL_ACCUM_ADDR) = 0u;   /* 16-bit, exactly the ROM's
                                             * `mov.w r4,@r3` (see header) */
    }
}
