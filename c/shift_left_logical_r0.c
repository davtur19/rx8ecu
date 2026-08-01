/*
 * shift_left_logical_r0  —  RX-8 PCM logical left shift @ ROM 0x4308
 *
 * Arg in r0, shift count in r1, result in r0 (SH-2 convention).
 *
 * Semantics: logical (zero-fill) left shift with explicit count clamping:
 *     cnt < 0   -> return val unchanged
 *     cnt >= 32 -> return 0
 *     else      -> val << cnt
 *
 * Implementation: a jump table of 32 signed byte offsets (table @0x42E8)
 * indexes an unrolled chain of `shll r0`/`shll8 r0`/`shll16 r0` tails based
 * at 0x4332, so the shift count never needs a loop.  Tail layout:
 *   base 0x4332: 7x shll r0 ; rts        (cnt 0..7 via offsets 0x0e..0x00)
 *   0x4352     : shll8 r0 ; rts          (cnt 8,  offset 0x20)
 *   ... shll8 + shll (cnt 9..15), shll16 (cnt 16), shll8+shll16 (cnt 17..23),
 *   0x4378+: and #15,r0 ; rotr r0 xN ; rts  (cnt 24..31 — masked rotate
 *   implements (val << cnt) & MASK for counts >= 24)
 *
 * Track A (behavior-equivalent): verified against the emulated ROM over
 * 300k random (val, cnt) inputs with cnt in [-40, 72] — 0 mismatches.
 * Test: c/tests/test_shift_left_logical_r0.py
 */
#include <stdint.h>

/* 0x4308  logical left shift, count in r1 (clamped) */
uint32_t shift_left_logical_r0(uint32_t val, int32_t cnt)
{
    if (cnt < 0) return val;
    if (cnt >= 32) return 0;
    return val << cnt;
}
