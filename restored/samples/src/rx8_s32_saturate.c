/*
 * =============================================================================
 * rx8_s32_saturate.c  —  SATURATING SIGNED 32-BIT ADD
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x2304
 * Status      : VERIFIED — behavioural equivalence to the ROM held by
 *               restored/samples/tests/harness_add_s32.py (host-gcc vs
 *               tools/sh2emu.py over random int32 pairs), in addition to the
 *               existing c/tests/verify_emu.py entry (100k random, 0 errors).
 * Lift (truth): c/addS32Saturate.c  (same address; IDA mislabels the ROM
 *               symbol `fpu_compare_float` — there is no FPU code here, the
 *               function is built on the SH-2 `addv` instruction).
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * The SH-2E core has no automatic saturating arithmetic; Denso implements it
 * with the `addv` instruction, whose T bit reports signed overflow of the
 * 32-bit sum.  The ROM path is:
 *
 *     addv   r4,r5            ; r5 = r4 + r5 (32-bit wrap); T = overflow
 *     bf/s   .ret             ; no overflow -> return the wrapped sum
 *     mov    r5,r0            ;   (delay slot)
 *     mov.l  @lit,r0          ; r0 = 0x7FFFFFFF
 *     cmp/pz r5               ; T = (wrapped sum >= 0)     (sign of wrap)
 *     mov    #0,r5
 *     addc   r5,r0            ; r0 += T   (0x7FFFFFFF -> 0x80000000 on -ve)
 * .ret: rts / nop
 *
 * i.e. positive overflow clamps to +INT32_MAX and negative overflow clamps to
 * INT32_MIN.  The clamp direction is taken from the SIGN OF THE WRAPPED SUM,
 * which is exactly the classic saturating-add idiom below.  This helper is
 * hot-path code in the O2 / wideband and knock-trim pipelines, where a
 * wrapped integrator would produce a wrong AFR command.
 *
 * The C below never executes the overflowing addition, so it is well-defined
 * on any compiler while remaining byte-semantically equal to `addv` on the
 * target.
 * =============================================================================
 */
#include <stdint.h>
#include <limits.h>
#include "rx8_samples.h"

int32_t rx8_add_s32_saturate(int32_t a, int32_t b)
{
    /* Positive overflow: both operands positive and a would push the sum
     * past INT32_MAX. */
    if (a > 0 && b > 0 && a > INT32_MAX - b) {
        return INT32_MAX;
    }
    /* Negative overflow: both negative and a would push the sum below
     * INT32_MIN.  (`INT32_MIN - b` cannot itself overflow while b < 0.) */
    if (a < 0 && b < 0 && a < INT32_MIN - b) {
        return INT32_MIN;
    }
    return a + b;
}
