/*
 * =============================================================================
 * rx8_shift_right_logical.c  —  LOGICAL (ZERO-FILL) RIGHT SHIFT, CLAMPED COUNT
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x44E0
 * Status      : VERIFIED — behavioural equivalence to the ROM held by
 *               reconstructed/samples/tests/harness_shift_right_logical.py
 *               (host-gcc vs tools/sh2emu.py over edge + 20000 random
 *               (val, cnt) vectors), in addition to the existing
 *               c/tests/test_shift_right_logical_r0.py entry (100k random,
 *               0 errors).
 * Lift (truth): c/shift_right_logical_r0.c  (same address).
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * The SH-2E has no variable-count shift instruction, so Denso unrolls the
 * shift into a chain of `shlr r0` (1 bit), `shlr8 r0` (8 bits) and
 * `shlr16 r0` (16 bits) "tails" based at 0x450A and dispatches into the right
 * tail via a 32-byte jump table at 0x44C0 (signed byte offsets) — the shift
 * count never needs a loop.  The ROM path (SH-2 convention: value in r0,
 * count in r1, result in r0) is:
 *
 *     mov.l  r2,@-r15          ; save scratch
 *     cmp/pz r1                ; T = (cnt >= 0)
 *     bf/s   .ret_same         ;   cnt < 0   -> return val unchanged
 *     mov    #0x20,r2          ;   (delay slot) r2 = 32
 *     cmp/ge r2,r1             ; T = (cnt >= 32)
 *     bt     .ret_zero         ;   cnt >= 32 -> return 0
 *     mov.l  @lit,r2           ; r2 = 0x44C0 (jump table of 32 signed bytes)
 *     add    r1,r2
 *     mov.b  @r2,r2            ; signed byte offset
 *     mov.l  @lit,r1           ; r1 = 0x450A (tail base)
 *     add    r2,r1
 *     jmp    @r1               ;   -> the matching shlr/shlr8/shlr16 tail
 *     nop
 * .ret_zero:                   ; 0x4504
 *     mov    #0x00,r0          ; r0 = 0
 * .ret_same:                   ; 0x4518 (rts in delay slot pops r2)
 *     rts
 *     mov.l  @r15+,r2
 *
 * Jump-table layout (cnt -> tail, verified against the ROM):
 *     cnt  0..7 : 7x `shlr r0` chain   (base 0x450A; cnt 0 jumps straight to
 *                                       the rts at 0x4518 — zero shifts)
 *     cnt  8..15: `shlr8 r0` + up to 7x `shlr r0`   (base 0x452A)
 *     cnt 16..23: `shlr16 r0` + `shlr8 r0` + up to 7x `shlr r0` (base 0x4544)
 *     cnt 24..31: masked `rotl r0` idiom (e.g. cnt 28: 4x rotl + and #0x0F)
 * This dispatch block (0x44EC) doubles as the positive-count path of the
 * sibling left-shift helper at 0x4308, which jumps straight into 0x44EC.
 *
 * The C below is the byte-semantic equivalent: a logical (zero-fill) right
 * shift with the count clamped to [0, 31].  `val` is unsigned so `>>` is a
 * logical shift and the result is the zero-extended value the ROM produces.
 * =============================================================================
 */
#include <stdint.h>
#include "rx8_samples.h"

/* 0x44E0  logical right shift, count in r1 (clamped to [0, 31]) */
uint32_t rx8_shift_right_logical_r0(uint32_t val, int32_t cnt)
{
    if (cnt < 0) {
        return val;
    }
    if (cnt >= 32) {
        return 0;
    }
    return val >> cnt;
}
