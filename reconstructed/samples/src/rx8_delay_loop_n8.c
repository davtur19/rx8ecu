/*
 * =============================================================================
 * rx8_delay_loop_n8.c  —  BUSY-WAIT TIMING DELAY (n × 8 iterations)
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x239C
 * Status      : VERIFIED — behavioural equivalence to the ROM held by
 *               reconstructed/samples/tests/harness_delay_loop_n8.py
 *               (host-gcc vs tools/sh2emu.py): for every in-budget vector the
 *               emulated ROM leaves r0 == 0 and r4 == r5 == n*8 after the
 *               call (loop-count relationship pinned against the actual ROM
 *               bytes), and the reconstructed C returns void after the same
 *               n*8-trip counter loop.
 * Lift (truth): c/delay_loop_n8.c  (same address; Ghidra/IDA mislabel the
 *               ROM symbol `mul16_unsigned` — the code is NOT a multiply
 *               helper but a counter loop whose trip count is 8 × r4; the
 *               name came from the `shll2; shll` sequence that multiplies
 *               the argument by 8).
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * A small-integer timing delay.  Denso implements short timed pauses with a
 * raw busy-wait: the caller zero-extends a byte and hands it in r4, and the
 * SH-2E burns exactly 8 cycles-worth of iterations per unit.  The function is
 * dispatched through a function-pointer table, so it appears in ROM as a
 * standalone leaf rather than being inlined.
 *
 * SH-2E asm (10 instructions, 20 bytes):
 *
 *     mov  #0x00,r5     ; r5 = 0
 *     shll2 r4          ; r4 <<= 2               (×4)
 *     shll  r4          ; r4 <<= 1               (×2, total ×8)
 *     cmp/hs r4,r5      ; T = (r5 >= r4)
 *     bt    .done       ; r5 >= r4 -> skip the loop (n == 0)
 * .loop:                ;                          (hot: 3 instructions/trip)
 *     add  #0x01,r5     ; r5++
 *     cmp/hs r4,r5      ; T = (r5 >= r4)
 *     bf   .loop        ; while (r5 < r4)
 * .done:
 *     rts               ; return r0 untouched (0) — no meaningful value
 *     nop               ; (delay slot)
 *
 * i.e. r4 is first scaled by 8 (`shll2` + `shll`) and then r5 counts from 0
 * up to r4 — exactly `for (i = 0; i < n*8; i++) ;`.  The only observables
 * are execution time (the function's purpose) and the register side-effects
 * r4 = r5 = n*8; r0 is never written.
 *
 * NOTE ON THE LOOP: as in the lift (c/delay_loop_n8.c) the counter is
 * ordinary C, so a compiler is free to delete the loop entirely.  That is
 * fine — the C has no observable side effects (its only "output" is time,
 * which the harness deliberately does not measure), and its structure
 * mirrors the ROM instruction-for-instruction.
 * =============================================================================
 */
#include <stdint.h>
#include "rx8_samples.h"

/* The ROM prologue scales the argument by 8 (`shll2` then `shll`). */
#define RX8_DELAY_N8_ITER_PER_UNIT  8u

/* 0x239C  busy-wait timing delay, trip count n × 8  (was "mul16_unsigned").
 * r4: n<<3  —  r5: loop counter —  r0: never written (return value 0). */
void rx8_delay_loop_n8(uint16_t n)
{
    uint32_t count = (uint32_t)n * RX8_DELAY_N8_ITER_PER_UNIT;  /* r4       */
    uint32_t i = 0;                                             /* r5       */
    while (i < count) {                    /* cmp/hs r4,r5 + bf pair        */
        i++;                               /* add #0x01,r5                  */
    }
}
