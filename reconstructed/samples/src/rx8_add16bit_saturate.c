/*
 * =============================================================================
 * rx8_add16bit_saturate.c  —  SATURATING UNSIGNED 16-BIT ADD
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x2460
 * Status      : VERIFIED — behavioural equivalence to the ROM held by
 *               reconstructed/samples/tests/harness_add16bit_saturate.py
 *               (host-gcc vs tools/sh2emu.py over 20000 random + edge vectors;
 *               0 mismatches, bit-exact 16-bit results).
 * Lift (truth): c/add16bitSaturate.c  — `add16bitSaturate_ADD1_ADD2` @0x2460,
 *               hand-annotated Ghidra RE by equinox311 (program 60E0FC00);
 *               byte-identical helper in 60E1D400 / 60E0FC00 / [REDACTED].
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * A register-only integer leaf (no memory traffic, no stack frame) that adds
 * two 16-bit values and saturates the sum at 0xFFFF.  It is the unsigned
 * sibling of the `addv`-based saturating s32 add @0x2304
 * (rx8_s32_saturate.c): firmware uses it wherever an unsigned counter or
 * integrator must never wrap through zero.  The ROM path, from
 * tools/disasm_sh2e.py, is:
 *
 *     0x2460: extu.w r4,r4        ; add1 = (uint16)add1     (arg0 in r4)
 *     0x2462: extu.w r5,r5        ; add2 = (uint16)add2     (arg1 in r5)
 *     0x2464: add    r5,r4        ; r4 = add1 + add2        (32-bit, no wrap:
 *                                 ;   max sum 0x1FFFE fits the register)
 *     0x2466: mov.l  0x2474,r5    ; r5 = 0x0000FFFF   (literal pool @0x2474)
 *     0x2468: cmp/hs r5,r4        ; T = (r4 >= 0xFFFF)      (unsigned compare)
 *     0x246A: bf/s   0x2470       ; sum < 0xFFFF -> skip the clamp
 *     0x246C: nop                 ;   (delay slot)
 *     0x246E: mov    r5,r4        ; r4 = 0xFFFF              (clamp)
 *     0x2470: rts
 *     0x2472: mov    r4,r0        ; return r4                (delay slot)
 *
 * Semantics:  min(add1 + add2, 0xFFFF).  The clamp is triggered by
 * `cmp/hs` — an UNSIGNED `>=` test — so a sum of exactly 0xFFFF is clamped
 * to 0xFFFF (which is also the raw sum, so the two branches agree there);
 * only sums strictly below 0xFFFF pass through untouched.
 *
 * CALLING CONVENTION
 * ------------------
 * Non-ABI integer leaf: add1 in r4, add2 in r5, result returned in r0
 * (no stack frame, no RAM side-effects).  Because the arguments sit in the
 * first two argument registers, the harness uses plain SH2.call(0x2460,
 * r4=..., r5=...) — the same choice as the sibling math-primitive leaves
 * (rx8_math_primitives_2490.c, rx8_s32_saturate.c).  The `extu.w` in the ROM
 * means both arguments are masked to 16 bits before the add; the C below
 * receives them already as uint16_t, which is exactly that masking.
 *
 * DISCREPANCIES vs THE LIFT
 * -------------------------
 * None.  The ROM bytes, the c/add16bitSaturate.c lift and this source agree
 * on min(add1+add2, 0xFFFF) for every tested input (edges + 20000 random),
 * and the lift has independently been checked against an exact
 * instruction-by-instruction transcription over 20M random inputs in
 * c/tests/test_add16bitSaturate.c.
 * =============================================================================
 */
#include <stdint.h>
#include "rx8_samples.h"

uint16_t rx8_add16bit_saturate(uint16_t add1, uint16_t add2)
{
    /* The sum of two uint16 values fits in 32 bits, so it cannot wrap here
     * (matches the ROM's 32-bit `add r5,r4`).  The clamp threshold is the
     * literal 0x0000FFFF the ROM loads from its pool @0x2474. */
    uint32_t sum = (uint32_t)add1 + (uint32_t)add2;

    /* cmp/hs r5,r4 : T = (sum >= 0xFFFF).  On T the ROM does `mov r5,r4`,
     * forcing the sum to 0xFFFF; otherwise the raw sum survives. */
    if (sum >= 0xFFFFu) {
        return (uint16_t)0xFFFFu;
    }
    return (uint16_t)sum;
}
