/*
 * =============================================================================
 * rx8_calibration_apply_4b770.c  —  CALIBRATION-APPLY FLAG (IDLE-STATE GATE)
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x4B770
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_calibration_apply_4b770.py
 *               (host-gcc vs tools/sh2emu.py over edge + random vectors,
 *               comparing the side-effected flag byte; 0 mismatches).
 * Lift (truth): c/calibration_apply_4B770.c  (verified there by
 *               c/tests/test_calibration_apply_4B770.{py,c})
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * A tiny side-effect leaf that watches three on-chip-RAM status bytes and
 * writes one calibration flag byte:
 *
 *   flag@0xFFFFCDFD = (b201 != 1 && bCE00 == 0 && bCE01 == 0) ? 1 : 0
 *
 * where
 *   b201  = byte@0xFFFFD201
 *   bCE00 = byte@0xFFFFCE00
 *   bCE01 = byte@0xFFFFCE01
 *
 * i.e. "calibration data is valid / in the idle state": the flag is asserted
 * only while the b201 state byte is not equal to 1 AND both CE-range bytes are
 * zero.  It is called from a periodic scheduler task; the flag byte is then
 * polled elsewhere.
 *
 * Disassembly of 60E1D400.bin @ 0x4B770 (mov.w literals sign-extend, so
 * 0xCDFD/0xD201/0xCE00/0xCE01 are 0xFFFFCDFD/0xFFFFD201/0xFFFFCE00/0xFFFFCE01):
 *
 *     4B770: 940B   mov.w  4B78A,r4      ; r4 = 0xFFFFCDFD (flag byte)
 *     4B772: 9306   mov.w  4B782,r3      ; r3 = 0xFFFFD201 (b201)
 *     4B774: 6030   mov.b  @r3,r0        ; r0 = sign-ext b201
 *     4B776: 600C   extu.b r0,r0         ; r0 = b201 & 0xFF
 *     4B778: 8801   cmp/eq #1,r0         ; T = (b201 == 1)
 *     4B77A: 8F17   bf/s   4B7AC         ; b201 != 1 -> continue checking
 *     4B77C: E500   mov    #0,r5         ;   (delay) r5 = 0 (the "clear" value)
 *     4B77E: A023   bra    4B7C8         ; b201 == 1 -> skip to return
 *     4B780: 2450   mov.b  r5,@r4        ;   (delay) flag = 0
 *     (4B782..4B7AA literal pool: 0xD201 @4B782, 0xCDFD @4B78A, next-function
 *      literals; shared mov.w literals 0xCE00 @4B7F8 / 0xCE01 @4B7FA live in
 *      the next function's pool)
 *     4B7AC: 9124   mov.w  4B7F8,r1      ; r1 = 0xFFFFCE00 (bCE00)
 *     4B7AE: 6210   mov.b  @r1,r2        ; r2 = bCE00
 *     4B7B0: 2228   tst    r2,r2         ; T = (bCE00 == 0)
 *     4B7B2: 8F08   bf/s   4B7C6         ; bCE00 != 0 -> flag = 0
 *     4B7B4: 0009   nop                  ;   (delay)
 *     4B7B6: 9020   mov.w  4B7FA,r0      ; r0 = 0xFFFFCE01 (bCE01)
 *     4B7B8: 6200   mov.b  @r0,r2        ; r2 = bCE01
 *     4B7BA: 2228   tst    r2,r2         ; T = (bCE01 == 0)
 *     4B7BC: 8F03   bf/s   4B7C6         ; bCE01 != 0 -> flag = 0
 *     4B7BE: 0009   nop                  ;   (delay)
 *     4B7C0: E101   mov    #1,r1         ; r1 = 1 (the "set" value)
 *     4B7C2: A001   bra    4B7C8         ; all three inputs idle -> set
 *     4B7C4: 2410   mov.b  r1,@r4        ;   (delay) flag = 1
 *     4B7C6: 2450   mov.b  r5,@r4        ; flag = 0
 *     4B7C8: 000B   rts
 *     4B7CA: 0009   nop                  ;   (delay)
 *
 * Function code runs 0x4B770..0x4B7CB (rts+nop); the next function begins at
 * 0x4B7CC.  The zero write is reached through three distinct control paths
 * (b201==1, bCE00!=0, bCE01!=0) — a compiler artifact of `&&` short-circuiting;
 * the observable effect is a single flag-byte write, exactly as below.
 *
 * CALLING CONVENTION
 * ------------------
 * Plain ABI-clean void leaf: no arguments, no return value, no stack frame.
 * The only observable effect is the flag byte written to RAM[0xFFFFCDFD], so
 * the harness drives it with the standard SH2.call() and compares the
 * side-effected byte against the host's mmap-backed RAM (same MAP_FIXED trick
 * as tests/host_oracle.c).
 *
 * DISCREPANCIES vs THE c/ LIFT (corrected here)
 * ----------------------------------------------
 * 1. The lift header claims "Size: 46 bytes (to 0x4B7CC)"; the real function
 *    code spans 0x4B770..0x4B7CB (50 bytes of code: 0x4B770..0x4B780 and
 *    0x4B7AC..0x4B7CA) and the next function starts at 0x4B7CC.  (The lift's
 *    "0x4B782..0x4B7AA literal pool" note is correct.)
 * 2. The lift reads all three input bytes unconditionally at the top.  The ROM
 *    reads bCE00 only after b201 != 1, and bCE01 only after bCE00 == 0
 *    (`&&` short-circuit).  The C below mirrors the ROM's actual read order.
 *    (All four bytes are plain on-chip RAM, so the observable behaviour is
 *    identical either way — this only matters for strict read-traffic
 *    faithfulness.)
 *
 * RAM SIDE EFFECT: writes one byte @0xFFFFCDFD — the harness compares that
 * byte (the emulator's RAM overlay) against the host's mmap-backed page.
 * =============================================================================
 */
#include <stdint.h>
#include <stddef.h>

#include "rx8_samples.h"

/* These addresses are not (yet) documented in include/rx8_hw.h; they come from
 * the verified lift c/calibration_apply_4B770.c and its ROM literals. */
#define RX8_CAL_B201_ADDR   0xFFFFD201u   /* b201 state byte  (mov.w 0xD201) */
#define RX8_CAL_CE00_ADDR   0xFFFFCE00u   /* CE-range byte 0  (mov.w 0xCE00) */
#define RX8_CAL_CE01_ADDR   0xFFFFCE01u   /* CE-range byte 1  (mov.w 0xCE01) */
#define RX8_CAL_FLAG_ADDR   0xFFFFCDFDu   /* calibration flag  (mov.w 0xCDFD) */

/* 0x4B770 — assert the calibration flag while all inputs are in the idle state
 * (b201 != 1 && bCE00 == 0 && bCE01 == 0).  Reads happen strictly in the ROM's
 * order: b201 first, bCE00 only if needed, bCE01 only if needed. */
void rx8_calibration_apply_4b770(void)
{
    uint8_t v = 0;
    uint8_t b201 = *(volatile uint8_t *)(uintptr_t)RX8_CAL_B201_ADDR;

    if (b201 != 1u &&
        *(volatile uint8_t *)(uintptr_t)RX8_CAL_CE00_ADDR == 0u &&
        *(volatile uint8_t *)(uintptr_t)RX8_CAL_CE01_ADDR == 0u) {
        v = 1u;
    }
    *(volatile uint8_t *)(uintptr_t)RX8_CAL_FLAG_ADDR = v;
}
