/*
 * firstOrderFilter_SIG_SIGPREV_MIN_FF  —  RX-8 PCM @ ROM 0x23B0  (equinox name,
 * hand Ghidra RE by equinox311).  First-order IIR filter with a not-finite
 * bootstrap and a minimum-change deadband.
 *
 * Args (SH-2E FP convention): fr4 = sig (current), fr5 = sigprev (previous),
 *                             fr6 = ff (filter factor 0..1), fr7 = min (deadband).
 *
 * Original SH-2E:
 *   flds fr5,fpul ; and 0x7F800000 ; cmp/eq  -> if fr5 exponent is all-ones (inf/NaN)
 *                                               return sig (bootstrap / first sample)
 *   else: filtered = sig + (1-ff)*(sigprev - sig)      ( == ff*sig + (1-ff)*sigprev )
 *         return (min > |sig - filtered|) ? sig : filtered   (snap to sig on tiny change)
 *
 * Track A: verified behavior-equivalent to the emulated ROM (tools/sh2emu.py): 30004/30004
 * random + edge inputs incl. sigprev = inf/NaN. (First drafted by a Haiku sub-agent, then
 * exact-lifted and verified here.)
 */
#include <math.h>

float firstOrderFilter(float sig, float sigprev, float ff, float min)
{
    if (!isfinite(sigprev))                       /* fr5 exponent == 0xFF -> inf or NaN */
        return sig;                               /* bootstrap: no valid previous sample */

    /* SH-2E uses fmac fr0,fr5,fr6 = fr6 + fr0*fr5 (fused multiply-add with no
     * intermediate rounding).  C's fmaf() matches the IEEE-754 fused operation. */
    float filtered = fmaf(1.0f - ff, sigprev - sig, sig);
                                                   /* = ff*sig + (1-ff)*sigprev */

    return (min > fabsf(sig - filtered)) ? sig : filtered;  /* min-change deadband */
}
