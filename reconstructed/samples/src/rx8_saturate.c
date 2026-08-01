/*
 * =============================================================================
 * rx8_saturate.c  —  SIGNAL CLAMP INTO [lower, upper]
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x2404
 * Status      : VERIFIED — behavioural equivalence to the ROM held by
 *               reconstructed/samples/tests/harness_saturate.py (host-gcc vs
 *               tools/sh2emu.py over 20000 random + edge vectors; bit-exact
 *               IEEE-754 single-precision results).
 * Lift (truth): c/math_primitives.c — function `saturate` @0x2404 (equinox
 *               hand Ghidra RE of the 0x2044..0x2510 scalar-math cluster; the
 *               same address is cross-checked against the emulator over 30000
 *               random float triples in c/tests/test_math_primitives.py).
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * A register-only FPU leaf (no memory traffic, no stack frame) that clamps a
 * signal into [lower, upper] — the workhorse guard the fueling/ignition/sensor
 * pipelines call whenever a commanded or measured value must never leave its
 * legal band.  The ROM path, from tools/disasm_sh2e.py, is:
 *
 *     0x2404: fcmp/gt fr5,fr4   ; T = (sig > lower)
 *     0x2406: bt/s   0x240E     ; sig > lower  -> go test the upper bound
 *     0x2408: nop
 *     0x240A: bra    0x241A     ; else: return lower
 *     0x240C: fmov   fr5,fr7    ;   (delay slot) fr7 = lower
 *     0x240E: fcmp/gt fr4,fr6   ; T = (upper > sig)
 *     0x2410: bt/s   0x2418     ; upper > sig  -> return sig
 *     0x2412: nop
 *     0x2414: bra    0x241A     ; else: return upper
 *     0x2416: fmov   fr6,fr7    ;   (delay slot) fr7 = upper
 *     0x2418: fmov   fr4,fr7    ; fr7 = sig
 *     0x241A: rts
 *     0x241C: fmov   fr7,fr0    ;   (delay slot) fr0 = result
 *
 * Calling convention (SH-2E FPU): fr4 = sig, fr5 = lower, fr6 = upper;
 * result returned in fr0.  Both bounds checks are the SH-2E `fcmp/gt` — a
 * STRICT greater-than that clears T for NaN operands and treats +0.0/-0.0 as
 * equal — so the three-way outcome is:
 *
 *     sig <= lower  -> lower        (exact register value, bit-for-bit)
 *     lower < sig < upper -> sig
 *     sig >= upper  -> upper
 *
 * The returned value is the source register's raw single-precision bit
 * pattern (the ROM copies registers with `fmov`, never re-rounds), which the
 * branch-for-branch C below preserves exactly — including the corner cases
 * lower == upper, inverted bounds (lower > upper) and NaN in any position.
 * =============================================================================
 */
#include <stdint.h>
#include "rx8_samples.h"

float rx8_saturate(float sig, float lower, float upper)
{
    /* Bounds guard — low side: any sig not strictly above `lower`
     * (equal, below, or unordered-vs-NaN) snaps to `lower` itself.
     * (0x2404 fcmp/gt fr5,fr4 -> bt/s 0x240E) */
    if (!(sig > lower)) {
        return lower;
    }

    /* In-band test: strictly below the upper bound means sig is untouched.
     * (0x240E fcmp/gt fr4,fr6 -> bt/s 0x2418) */
    if (upper > sig) {
        return sig;
    }

    /* Otherwise sig is at or past the ceiling — clamp to `upper`.
     * (0x2414 bra 0x241A with fr7 = fr6) */
    return upper;
}
