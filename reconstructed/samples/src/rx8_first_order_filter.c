/*
 * =============================================================================
 * rx8_first_order_filter.c  —  FIRST-ORDER IIR FILTER (BOOTSTRAP + DEADBAND)
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x23B0
 * Status      : VERIFIED — behavioural equivalence to the ROM held by
 *               reconstructed/samples/tests/harness_first_order_filter.py
 *               (host-gcc vs tools/sh2emu.py over 20000 random + edge vectors;
 *               bit-exact IEEE-754 single-precision results).
 * Lift (truth): c/firstOrderFilter.c  (IDA mislabels the ROM symbol
 *               `fpu_abs_float` — there is no absolute value here; the
 *               function is the generic first-order low-pass filter used by
 *               the knock/throttle/boost sensor pipelines).
 *
 * Calling convention (SH-2E FPU): fr4 = sig (current sample),
 * fr5 = sigprev (previous output), fr6 = ff (filter factor 0..1),
 * fr7 = min (deadband); result returned in fr0.
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * A register-only FPU leaf (no memory traffic, no stack frame) that smooths a
 * noisy signal with a first-order IIR and snaps back to the raw input when the
 * change is below a minimum.  The ROM path is:
 *
 *     flds   FR5,FPUL             ; FPUL = bit pattern of sigprev
 *     mov.l  @(0x24,PC),R4        ; R4 = 0x7F800000 (single-precision exp mask)
 *     sts    FPUL,R0              ; R0 = bits(sigprev)
 *     and    R4,R0                ; R0 = exponent field of sigprev
 *     cmp/eq R4,R0                ; T = (exponent == all ones -> inf/NaN)
 *     bt/s   .snap                ; bootstrap: no valid history -> pass sig
 *     fsub   FR4,FR5              ;   (delay) FR5 = sigprev - sig
 *     fldi1  FR0                  ; FR0 = 1.0
 *     fsub   FR6,FR0              ; FR0 = 1.0 - ff
 *     fmov   FR4,FR6              ; FR6 = sig
 *     fmac   FR0,FR5,FR6          ; FR6 = (1-ff)*(sigprev-sig) + sig  (fused)
 *     fmov   FR4,FR5              ; FR5 = sig
 *     fsub   FR6,FR5              ; FR5 = sig - filtered
 *     fabs   FR5                  ; FR5 = |sig - filtered|
 *     fcmp/gt FR5,FR7             ; T = (min > |sig - filtered|)
 *     bf/s   .ret                 ; small change -> keep the filtered value
 *     nop
 * .snap: fmov FR4,FR6             ; deadband (or bootstrap) -> FR6 = sig
 * .ret:  rts
 *     fmov   FR6,FR0              ;   (delay) FR0 = result
 *
 * Two behavioural details matter for bit-exactness:
 *  1. the multiply-accumulate is a genuine fused FMAC (single rounding);
 *     C's fmaf() is the portable match — plain `a*b + c` double-rounds;
 *  2. the operand order is (1-ff)*(sigprev - sig) + sig, which is NOT
 *     bit-identical to the algebraically-equal ff*sig + (1-ff)*sigprev.
 *     (`fmaf(1.0f - ff, sigprev - sig, sig)` keeps the ROM's exact rounding.)
 *
 * The bootstrap check is a pure bit test of sigprev's exponent field, i.e.
 * `!isfinite(sigprev)` covers +inf, -inf and every NaN payload.
 * =============================================================================
 */
#include <math.h>
#include <stdint.h>
#include "rx8_samples.h"

float rx8_first_order_filter(float sig, float sigprev, float ff, float min)
{
    /* Bootstrap: if the previous sample is not finite its single-precision
     * exponent field is all ones (+/-inf or NaN) and there is no valid filter
     * history yet — pass the raw current sample through untouched
     * (0x23B0-0x23BA `flds/and/cmp-eq/bt`). */
    if (!isfinite(sigprev)) {
        return sig;
    }

    /* First-order IIR update, exactly as the ROM's fused `fmac` computes it:
     * filtered = (1 - ff) * (sigprev - sig) + sig. */
    float filtered = fmaf(1.0f - ff, sigprev - sig, sig);

    /* Minimum-change deadband: if the input moved by strictly less than `min`,
     * snap the output back to the current input instead of smoothing it.
     * (`fcmp/gt` is a strict greater-than, so an exactly-equal change keeps
     * the filtered value.) */
    return (min > fabsf(sig - filtered)) ? sig : filtered;
}
