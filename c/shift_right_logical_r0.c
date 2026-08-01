/*
 * shift_right_logical_r0  —  RX-8 PCM logical right shift @ ROM 0x44E0
 *
 * Arg in r0, shift count in r1, result in r0 (SH-2 convention).
 *
 * Semantics: logical (zero-fill) right shift with explicit count clamping:
 *     cnt < 0   -> return val unchanged
 *     cnt >= 32 -> return 0
 *     else      -> val >> cnt            (zero-extended)
 *
 * Implementation: identical skeleton to shift_left_logical_r0 (0x4308) —
 * a 32-byte jump table @0x44C0 (same byte values as @0x42E8) indexes an
 * unrolled chain of `shlr r0`/`shlr8 r0`/`shlr16 r0` tails based at 0x450A.
 * 0x4308's sibling uses the shared `jmp @r1` tail of this function for its
 * positive-count path (0x43C8's L_004400 jumps straight to 0x44EC).
 *
 * Track A (behavior-equivalent): verified against the emulated ROM over
 * 300k random (val, cnt) inputs with cnt in [-40, 72] — 0 mismatches.
 * Test: c/tests/test_shift_right_logical_r0.py
 */
#include <stdint.h>

/* 0x44E0  logical right shift, count in r1 (clamped) */
uint32_t shift_right_logical_r0(uint32_t val, int32_t cnt)
{
    if (cnt < 0) return val;
    if (cnt >= 32) return 0;
    return val >> cnt;
}
