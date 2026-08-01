/*
 * =============================================================================
 * rx8_data_lookup.c  —  1-D AXIS-SEARCH LEAF (INDEX + INTERPOLATION FRACTION)
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x2624
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_data_lookup.py (host-gcc
 *               vs tools/sh2emu.py over 20000 random + edge vectors, real
 *               f32 axis arrays from ROM map descriptors plus synthetic
 *               count==1 / count==2 extremes; 0 mismatches).
 * Lift (truth): c/2DLookup.c  (dataLookup @ 0x2624)
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * The 1-D axis-search helper every calibration-table lookup is built on:
 * TwoDLookup / TwoDLookup_FP_16bit / TwoDLookup_FP_8bit (2DLookup.c) and the
 * 2-D bilinear lookups (3dLookup.c) all invoke it via `bsr` to turn a raw
 * input value into a breakpoint index i plus an interpolation fraction t
 * (the typed-cell interpolate_* leaves in c/interp_leaves.c then finish the
 * job).  It reads the ascending f32 breakpoint array and never writes RAM,
 * so its callers can point r1 straight at the ROM table.
 *
 * CALLING CONVENTION (NON-ABI)
 * ----------------------------
 * It is NOT called through the normal r4-r7 / fr4-fr6 C ABI: it is a tiny
 * internal leaf invoked via `bsr` with its arguments already in place:
 *     in:  r0 = count n, r1 = axis pointer (ascending f32 breakpoints),
 *          fr0 = x
 *     out: r0 = index i, fr0 = t    (NOT fr2 — the interpolate_* leaves in
 *          c/interp_leaves.c return their result via fr2 instead)
 *
 * ROM BODY (disassembled 60E1D400.bin @ 0x2624)
 * ----------------------------------------------
 *   add #-1,r0 ; shll2 r0         ; r0 = (n-1)*4  = byte offset of axis[n-1]
 *   fmov.s @(r0,r1),fr1           ; fr1 = axis[n-1]
 *   fcmp/gt fr0,fr1               ; T = (axis[n-1] > x)     [false for NaN]
 *   bf/s  clamp_high              ; NOT T (x >= axis[n-1], incl. NaN)
 *   tst   r0,r0                   ;   delay: T = (n == 1)
 * loop:                           ; (first entry falls through when x < axis[n-1])
 *   bt/s  clamp_low               ; T (k == 0) -> x < axis[0]
 *   add   #-4,r0                  ;   delay: r0 = (k-1)*4
 *   fmov.s @(r0,r1),fr1           ; fr1 = axis[k]
 *   fcmp/gt fr0,fr1               ; T = (axis[k] > x)
 *   bt/s  loop                    ; x < axis[k] -> walk on down
 *   tst   r0,r0                   ;   delay: T = (k == 0)
 *   fsub  fr1,fr0                 ; fr0 = x - axis[k]           (one rounding)
 *   add #4,r0 ; fmov.s @(r0,r1),fr2   ; fr2 = axis[k+1]
 *   add #-4,r0 ; fsub fr1,fr2     ; fr2 = axis[k+1] - axis[k]   (one rounding)
 *   fdiv  fr2,fr0                 ; fr0 = (x-axis[k])/(axis[k+1]-axis[k])
 *   rts   ; shlr2 r0              ;   delay: r0 = k
 * clamp_high: shlr2 r0 ; rts ; fldi0 fr0      ; i = n-1, t = 0.0
 * clamp_low:  mov #0,r0 ; rts ; fldi0 fr0     ; i = 0,   t = 0.0
 *
 * So the ROM performs a BACKWARD linear search: it starts at k = n-2 and
 * steps DOWN while axis[k] > x, stopping at the last index with axis[k] <= x
 * (the forward form used in c/2DLookup.c is behaviourally identical on a
 * strictly-ascending axis with exactly one matching interval, but the walk
 * below is the verbatim shape of the machine code).
 *
 * Semantics preserved verbatim below:
 *   - x >= axis[n-1]  -> i = n-1, t = 0.0   (clamp high; `fcmp/gt` is false
 *                                            for NaN, so NaN clamps high too)
 *   - n == 1          -> i = 0,   t = 0.0   (single-breakpoint fast path)
 *   - x <  axis[0]    -> i = 0,   t = 0.0   (clamp low)
 *   - otherwise       -> axis[i] <= x < axis[i+1] and
 *                        t = (x - axis[i]) / (axis[i+1] - axis[i]), where each
 *                        fsub / fdiv is a single-precision operation with ONE
 *                        rounding, exactly like the SH-2E hardware FPU.
 * =============================================================================
 */
#include <stdint.h>

#include "rx8_samples.h"

void rx8_data_lookup(int32_t n, const float *axis, float x,
                     int32_t *out_index, float *out_t)
{
    int32_t k;

    /* Clamp high: x >= axis[n-1] (and NaN — fcmp/gt compares false). */
    if (!(x < axis[n - 1])) {
        *out_index = n - 1;
        *out_t = 0.0f;
        return;
    }

    /* Single-breakpoint fast path: only one cell, always (0, t=0). */
    if (n <= 1) {
        *out_index = 0;
        *out_t = 0.0f;
        return;
    }

    /* Backward linear search, exactly like the ROM: walk k = n-2 down while
     * axis[k] > x; k == 0 with x < axis[0] is the clamp-low exit. */
    k = n - 2;
    while (x < axis[k]) {
        if (k == 0) {           /* x < axis[0]: clamp low */
            *out_index = 0;
            *out_t = 0.0f;
            return;
        }
        k--;
    }

    /* axis[k] <= x < axis[k+1]: each FP op below rounds once, like the FPU. */
    *out_index = k;
    *out_t = (x - axis[k]) / (axis[k + 1] - axis[k]);
}
