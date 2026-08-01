/*
 * =============================================================================
 * rx8_shift_left_logical.c  —  LOGICAL (ZERO-FILL) LEFT SHIFT
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x4308
 * Status      : VERIFIED — behavioural equivalence to the ROM held by
 *               reconstructed/samples/tests/harness_shift_left_logical.py
 *               (host-gcc vs tools/sh2emu.py over random (val, cnt) pairs),
 *               in addition to the existing c/tests/test_shift_left_logical_r0.py
 *               entry (100k random, 0 errors).
 * Lift (truth): c/shift_left_logical_r0.c
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * This is the PCM's general-purpose logical left shift primitive.  The SH-2E
 * has no variable-count shift instruction, so Denso implements the count
 * dispatch as a jump table of 32 signed byte offsets (table @0x42E8) indexing
 * an unrolled chain of fixed-count shift tails based at 0x4332:
 *
 *   base 0x4332 : 7x `shll r0` ; rts            (counts 0..7)
 *   0x4352      : `shll8 r0` ; rts              (count  8)
 *   ...         : `shll8` + 0..7x `shll`        (counts 9..15), `shll16` (16),
 *                 `shll8` + `shll16` + ...      (counts 17..23), and for
 *   0x4378+     : `and #15,r0` ; `rotr r0` xN   (counts 24..31 — a masked
 *                 rotate implementing `(val << cnt) & 0xFFFFFFFF`)
 *
 * Caller-side convention: value in r0, shift count in r1, result in r0, with
 * explicit count clamping:
 *
 *     cnt <  0   -> return val unchanged
 *     cnt >= 32  -> return 0
 *     else       -> val << cnt
 *
 * The count is interpreted as a SIGNED 32-bit value (the ROM tests its sign
 * with `cmp/pz`), so negative counts leave the value untouched.  The C below
 * is behaviour-equivalent on any compiler: shifting a uint32_t left by
 * 0..31 is well-defined, and the result is taken mod 2^32 exactly like the
 * masked-rotate tail for counts 24..31.
 * =============================================================================
 */
#include <stdint.h>
#include "rx8_samples.h"

/* 0x4308 — logical (zero-fill) left shift.  `val` in r0, signed `cnt` in r1,
 * result in r0 (SH-2 convention).  `cnt < 0` leaves `val` unchanged; counts
 * >= 32 yield 0. */
uint32_t rx8_shift_left_logical(uint32_t val, int32_t cnt)
{
    if (cnt < 0) {
        return val;
    }
    if (cnt >= 32) {
        return 0;
    }
    return val << cnt;
}
