/*
 * =============================================================================
 * rx8_interpolate_u16_table.c  —  UINT16-TABLE LINEAR-INTERPOLATION LEAF
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x26D0
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_interpolate_u16_table.py
 *               (host-gcc vs tools/sh2emu.py over 20000 random + edge vectors,
 *               real u16 cell arrays from ROM map descriptors plus synthetic
 *               extremes; 0 mismatches).
 * Lift (truth): c/interp_leaves.c  (interpolate_uint16Table @ 0x26D0)
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * The typed-cell 1-D interpolation primitives that TwoDLookup (2DLookup.c)
 * dispatches to via its type jump table — this leaf handles type 8 (u16 cells)
 * — and that the 2-D bilinear FP lookups build each row from internally
 * (3dLookup.c's row-bilinear helper @0x25F4 calls it once per row).  It is
 * also the exact handler TwoDLookup_FP_16bit jumps straight to.
 *
 * CALLING CONVENTION (NON-ABI)
 * ----------------------------
 * It is NOT called through the normal r4-r7 / fr4-fr6 C ABI: it is a tiny
 * internal leaf invoked via `bsr` right after the axis-search helper (0x2624)
 * with that helper's results still live in registers:
 *     r0  = cell index i          (already found by axis-search)
 *     r1  = pointer to the u16 cell array (base of the descriptor's values)
 *     fr0 = t, the interpolation fraction in [0,1) (0.0 at both clamp ends)
 * The result is returned in fr2 (NOT fr0): fr0 is left untouched on purpose so
 * the 2-D bilinear callers can reuse it as tx across both row calls.
 *
 * ROM BODY (disassembled 60E1D400.bin @ 0x26D0)
 * ----------------------------------------------
 *     fldi0    fr2           ; fr2 = 0.0
 *     shll     r0            ; r0 = i * 2 (byte stride of the u16 cells)
 *     fcmp/eq  fr0,fr2       ; T = (t == 0.0)
 *     add      r0,r1         ; r1 = cells + i*2
 *     mov.w    @r1+,r0       ; r0 = cell[i] (16-bit load)
 *     extu.w   r0,r0         ; zero-extend -> unsigned 16-bit value
 *     lds      r0,fpul
 *     bt/s     ret           ; t == 0.0 -> return cell[i]
 *     float    fpul,fr2      ;   (delay slot: fr2 = (float)cell[i], runs ALWAYS)
 *     mov.w    @r1,r0        ; r0 = cell[i+1]
 *     extu.w   r0,r0         ; unsigned again
 *     lds      r0,fpul
 *     float    fpul,fr1      ; fr1 = (float)cell[i+1]
 *     fsub     fr2,fr1       ; fr1 = v1 - v0   (ONE rounding)
 *     fmac     fr0,fr1,fr2   ; fr2 = t*(v1-v0) + v0  (ONE rounding)
 *   ret:
 *     rts / nop
 *
 * Semantics preserved verbatim below:
 *   - cell[index] is read UNCONDITIONALLY (the load, zero-extend and lds all sit
 *     before the t==0 branch; the fpul->float conversion is in the branch's
 *     delay slot).  This is what makes the clamp-high case (index == count-1,
 *     t == 0.0) safe: cell[index+1] is never read when t == 0.0.
 *   - When t != 0.0 axis-search guarantees index+1 is in range (the clamp
 *     branches are the only way to reach the last cell, and both force t == 0),
 *     so `cells[index+1]` needs no bounds check — matches the ROM.
 *   - The combine is one `fmac fr0,fr1,fr2` — a genuine fused multiply-add with
 *     a SINGLE rounding.  A plain `v0 + t*(v1-v0)` in C rounds TWICE (multiply,
 *     then add) and measurably diverges from the ROM at the few-ULP level over
 *     enough random t (~1% of random continuous-t inputs differ in the last
 *     bit).  `fmaf()` reproduces the single-rounding hardware behaviour.
 * =============================================================================
 */
#include <stdint.h>
#include <math.h>

#include "rx8_samples.h"

/* TwoDLookup descriptor cell-type tag that dispatches to this leaf (2DLookup.c:
 * type 8 -> handler 0x26D0, u16 cells, no scale/offset). */
#define RX8_INTERP_TYPE_U16 8u

/* The axis-search helper (0x2624) forces exactly t == 0.0 on both clamp paths
 * (below axis[0] and at/above axis[count-1]); the ROM compares against fldi0's
 * zero to select the read-one-cell-only fast path. */
#define RX8_INTERP_U16_T_ZERO 0.0f

float rx8_interpolate_u16_table(int32_t index, const uint16_t *cells, float t)
{
    float v0;

    /* Read cell[index] first, always — matching the ROM, where the 16-bit load
     * and zero-extend execute before the t==0 test (and its delay-slot float
     * conversion) regardless of t.  This is the whole reason the clamp-high
     * case never touches cells[count]: t==0 returns before cell[index+1] is
     * ever accessed. */
    v0 = (float)cells[index];

    if (t == RX8_INTERP_U16_T_ZERO) {
        return v0;
    }

    {
        const float v1 = (float)cells[index + 1];

        /* v1 - v0 is one fsub (single rounding); fmaf(t, diff, v0) is the one
         * fmac — t*(v1-v0) + v0 rounded once, exactly like the hardware. */
        return fmaf(t, v1 - v0, v0);
    }
}
