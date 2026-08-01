/*
 * shift_right_arithmetic_r0  —  RX-8 PCM arithmetic right shift @ ROM 0x43C8
 *
 * Arg in r0, shift count in r1, result in r0 (SH-2 convention).
 *
 * Semantics: sign-extending right shift with explicit count clamping:
 *     cnt < 0             -> return val unchanged
 *     cnt >= 32           -> return (val < 0) ? 0xFFFFFFFF : 0
 *     else                -> val >> cnt   (arithmetic, sign-extending)
 *
 * Implementation (the most elaborate of the shift family):
 *   - cnt < 0  -> rts immediately (r0 unchanged)                @0x4442
 *   - cnt >= 32-> `shll r0` moves bit31 into T; T==1 -> return
 *                 -1, else 0 (0x4404..0x4412) — the arithmetic >>32
 *                 clamp (all ones vs zero).
 *   - `rotl r2` copies bit31 into T to split by sign of val:
 *       * val < 0: jump-table @0x43C0 (8 entries for cnt 24..31) onto
 *         base 0x4446 — the swap/rotate sign-extension tails
 *         (swap.w/swap.b + or #-128/... for >>24..>>31), and for
 *         cnt 0..23 the same table read (cnt-24 bytes earlier) walks
 *         INTO the 0x4414..0x4440 `shar r0` chain (n shar = >>n).
 *       * val >= 0: cnt <= 8 uses the same shar chain (logical ==
 *         arithmetic for non-negative); cnt > 8 jumps into the shared
 *         logical-shift tail of 0x44E0 (L_004400 -> 0x44EC).
 *
 * Track A (behavior-equivalent): verified against the emulated ROM over
 * 300k random (val, cnt) inputs with cnt in [-40, 72] — 0 mismatches.
 * Test: c/tests/test_shift_right_arithmetic_r0.py
 */
#include <stdint.h>

/* 0x43C8  arithmetic right shift, count in r1 (clamped) */
int32_t shift_right_arithmetic_r0(int32_t val, int32_t cnt)
{
    if (cnt < 0) return val;
    if (cnt >= 32) return (val < 0) ? -1 : 0;
    return val >> cnt;
}
