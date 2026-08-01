/*
 * addS32Saturate  —  RX-8 PCM saturating signed 32-bit add @ ROM 0x2304
 *
 * Function name in IDA: `fpu_compare_float` — WRONG. There is no FPU logic
 * here at all; this is an integer helper built on the SH-2 `addv` (signed
 * overflow detect) instruction.  Confirmed by byte-level disassembly and by
 * matching against the emulated ROM over 200k random int32 pairs.
 *
 * Original SH-2 (big-endian):
 *     addv   r4,r5            ; r5 = r4 + r5 (32-bit wrap); T=1 if signed overflow
 *     bf/s   .ret             ; if !T (no overflow) return r5 (delay slot below)
 *     mov    r5,r0            ; r0 = r5                        [delay]
 *     mov.l  @(.lit,pc),r0    ; r0 = 0x7FFFFFFF
 *     cmp/pz r5               ; T = (r5 >= 0)  (sign of the WRAPPED sum)
 *     mov    #0,r5
 *     addc   r5,r0            ; r0 += 0 + T
 * .ret:
 *     rts
 *     nop                     ; (delay — never executed after rts)
 * .lit: .long 0x7FFFFFFF
 *
 * Semantics: return a + b, clamped to [INT32_MIN, INT32_MAX].
 *   - no overflow            -> wrapped sum (correct)
 *   - positive overflow      -> wrapped sum < 0  => return  0x7FFFFFFF
 *   - negative overflow      -> wrapped sum >= 0 => return -0x80000000
 * (The `addc` adds T==1 exactly when the wrapped sum is >= 0, flipping the
 * 0x7FFFFFFF literal to 0x80000000 for negative overflow.)
 *
 * Track A (behavior-equivalent): verified against the emulated ROM
 * (tools/sh2emu.py, `addv` added 2026-07-31) over 200k random int32 pairs —
 * 0 mismatches.  Test: c/tests/test_add_s32_saturate.py.
 */
#include <stdint.h>

/* 0x2304  saturating signed 32-bit add: a + b clamped to int32 range */
int32_t addS32Saturate(int32_t a, int32_t b)
{
    int64_t s = (int64_t)a + (int64_t)b;
    if (s > 0x7FFFFFFF) return 0x7FFFFFFF;
    if (s < -0x80000000LL) return (int32_t)0x80000000;
    return (int32_t)s;
}
