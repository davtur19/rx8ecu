/*
 * =============================================================================
 * rx8_min_value.c  —  MINIMUM OF TWO FLOATS
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x23F4
 * Status      : VERIFIED — behavioural equivalence to the ROM held by
 *               reconstructed/samples/tests/harness_min_value.py (host-gcc vs
 *               tools/sh2emu.py over 20000 random + edge vectors; bit-exact
 *               IEEE-754 single-precision results).
 * Lift (truth): c/math_primitives.c  (`minValue`, one of the thirteen scalar
 *               helpers in the 0x2044..0x2510 cluster; comment there reads
 *               "minimum of two floats").  The ROM symbol is IDA-named
 *               `minValue` and the code really is a plain FPU min — unlike
 *               some of its neighbours, the name is accurate.
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * The most-called scalar leaves (clamping, min/max, float<->fixed-point
 * conversions) are on every sensor/fuel/ignition path.  `minValue` is the
 * low-side partner of `saturateLow` (0x23E4, max) and is a pure register-only
 * FPU leaf: no memory traffic, no stack frame, result in FR0.
 *
 * The ROM path (0x23F4..0x2402) is:
 *
 *     fcmp/gt FR5,FR4        ; T = (FR5 > FR4) = (b > a)
 *     bf/s    0x23FE         ; !(b > a) -> FR6 = b   (delay: nop)
 *     nop
 *     bra     0x2400         ;   b > a  (delay: FR6 = a)
 *     fmov    FR4,FR6        ;   (delay slot of the bra)
 *     fmov    FR5,FR6        ;   !(b > a): FR6 = b
 *     rts                    ; (delay: FR0 = FR6)
 *     fmov    FR6,FR0
 *
 * i.e. `result = (b > a) ? a : b`.  The two paths are sequenced so that on a
 * tie (a == b, incl. +0.0/-0.0) the SECOND operand b wins, and NaN is not
 * special-cased anywhere: `NaN > x` compares false, so a NaN in b propagates
 * out of the function while a NaN in a is discarded (b is returned).  The C
 * below keeps the identical `(b > a) ? a : b` operand order so the tie/NaN
 * behaviour is preserved bit-for-bit.
 *
 * Calling convention (SH-2E FPU): fr4 = a, fr5 = b; result returned in fr0.
 * =============================================================================
 */
#include "rx8_samples.h"

float rx8_min_value(float a, float b)
{
    /* fcmp/gt semantics: T = (b > a).  On ties (incl. ±0.0) and when a is NaN
     * the comparison is false and b is returned — matching the ROM exactly. */
    return (b > a) ? a : b;
}
