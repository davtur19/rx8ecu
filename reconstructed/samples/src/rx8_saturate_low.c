/*
 * =============================================================================
 * rx8_saturate_low.c  —  LOW-SIDE SATURATION (SIGNAL CLAMP TO A FLOOR)
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x23E4  (file offset == address; SH-2E `fcmp/gt` + branch)
 * Status      : VERIFIED — behavioural equivalence to the ROM held by
 *               reconstructed/samples/tests/harness_saturate_low.py (host-gcc
 *               vs tools/sh2emu.py over edge + random single-precision
 *               inputs, bit-exact IEEE-754 comparison, 0 mismatches).
 * Lift (truth): c/math_primitives.c, `saturateLow` @0x23E4 (hand-Ghidra RE by
 *               equinox311, independently confirmed against the emulated ROM
 *               by c/tests/test_math_primitives.py over 30000 random inputs).
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * `saturateLow` clamps a signal to a lower bound: it returns the larger of
 * the two arguments (low-side saturation).  It lives in the 0x2044..0x2510
 * cluster of scalar-math leaf helpers that the fueling / ignition / sensor
 * pipelines call constantly; Denso emits every one of these clamps as an
 * `fcmp/gt` + branch pair rather than a compare-and-move sequence.  The ROM
 * path is:
 *
 *     fcmp/gt FR4,FR5          ; T = (FR4 > FR5)   (sig > lower)
 *     bt/s  .L_sig             ; if so, return sig (delay: nop)
 *     flds   FR4,FPUL          ; (else path, delay of the unconditional bra)
 *     bra    .L_ret
 *     .L_sig:
 *     fsts   FPUL,FR0          ; FR0 = FPUL = FR4
 *     .L_ret:
 *     rts                      ; FR0 holds the result
 *
 * i.e. exactly `(sig > lower) ? sig : lower`.  Note the semantics differ from
 * a plain `fmax` at equal-argument ties only in *which* operand is returned
 * (the lift returns `lower` on ties), so the reconstruction keeps the ROM's
 * comparison order verbatim instead of calling fmaxf().
 *
 * Floating-point comparison order matters here: NaN sig makes `sig > lower`
 * false and the ROM returns `lower`; the C below inherits the identical
 * IEEE-754 unordered-compare behaviour.
 * =============================================================================
 */
#include <stdint.h>
#include "rx8_samples.h"

float rx8_saturate_low(float sig, float lower)
{
    /* Low-side saturation: never let the signal fall below `lower`.
     * Strict > (not >=) is deliberate — on equality the ROM's false branch
     * returns `lower`, and with a NaN `sig` the comparison is false too,
     * so both cases resolve to `lower` exactly as the firmware does. */
    return (sig > lower) ? sig : lower;
}
