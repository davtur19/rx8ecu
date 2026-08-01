/*
 * =============================================================================
 * rx8_shift_right_arithmetic.c  —  SIGN-EXTENDING (ARITHMETIC) RIGHT SHIFT
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x43C8
 * Status      : VERIFIED — behavioural equivalence to the ROM held by
 *               reconstructed/samples/tests/harness_shift_right_arithmetic.py
 *               (host-gcc vs tools/sh2emu.py over ~40 edge vectors plus 20k
 *               random (val, cnt) pairs with cnt in [-40, 72]; 0 mismatches).
 * Lift (truth): c/shift_right_arithmetic_r0.c
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * The most elaborate member of the 0x43C8 shift family (the logical shift
 * @0x44E0 and the 8-bit shift @0x467A are siblings).  Denso uses it wherever
 * a signed value must be scaled by a runtime-computed power of two — e.g.
 * normalising/denormalising 16-bit sensor words — and the shift amount is
 * NOT guaranteed to be in range, so the count is clamped before it ever
 * reaches the shifter.
 *
 * CALLING CONVENTION
 * ------------------
 * The shift family does NOT use the r4/r5 ABI: the value arrives in r0, the
 * shift count in r1 and the result is left in r0 (SH-2 convention, mirrored
 * by the prototype below).  The harness therefore drives the emulator with a
 * small wrapper that seeds r0/r1 (tools/sh2emu.py is untouched).
 *
 * ROM PATH (disassembly-verified)
 * -------------------------------
 *     mov.l r2,@-r15          ; preserve r2 (r0/r1 are caller-saved)
 *     cmp/pz r1 ; bf/s .rts   ; cnt < 0             -> return val unchanged
 *     mov  #0x20,r2
 *     cmp/ge r2,r1 ; bt .big  ; cnt >= 32:
 *         shll r0             ;   T = sign bit of val
 *         bt   .neg           ;   val < 0 -> r0 = -1 (0xFFFFFFFF)
 *         mov  #0,r0          ;   else    -> r0 =  0
 *     mov r0,r2 ; rotl r2     ; T = sign bit of val   (cnt in [0, 31])
 *     bf  .nneg               ; val >= 0 -> shar chain or logical tail
 *     ... (val < 0) jump-table @0x43C0: offsets for cnt 24..31 jump onto the
 *         swap/rotate sign-extension tails @0x4446..; for cnt 0..23 the same
 *         table read walks BACKWARD into the 0x4414..0x4440 `shar r0` chain
 *         (cnt consecutive shar = arithmetic shift by cnt).
 *     .nneg: cnt <= 8 -> shar chain (logical == arithmetic for non-negative);
 *            cnt >  8 -> shared logical-shift tail @0x44EC.
 *
 * i.e. a sign-extending right shift with explicit count clamping.  The C
 * below is behaviour-identical but, unlike the ROM, never reaches a shift
 * of 32 or more.  For negative values in [0, 31] it relies on the host
 * compiler's arithmetic (sign-extending) right shift of a signed int32_t,
 * which the harness checks byte-for-byte against the emulated ROM.
 * =============================================================================
 */
#include <stdint.h>
#include "rx8_samples.h"

/* 0x43C8 — sign-extending right shift; value in r0, count in r1, result in
 * r0.  Counts outside [0, 31] never reach the shifter:
 *     cnt < 0   -> value unchanged
 *     cnt >= 32 -> (val < 0) ? -1 : 0
 *     else      -> val >> cnt  (arithmetic, sign-extending)                  */
int32_t rx8_shift_right_arithmetic(int32_t val, int32_t cnt)
{
    if (cnt < 0) {
        return val;
    }
    if (cnt >= 32) {
        return (val < 0) ? -1 : 0;
    }
    return val >> cnt;
}
