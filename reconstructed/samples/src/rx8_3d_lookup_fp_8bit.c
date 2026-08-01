/*
 * =============================================================================
 * rx8_3d_lookup_fp_8bit.c  —  BILINEAR CALIBRATION-MAP LOOKUP (u8 CELLS)
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x2120
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_3d_lookup_fp_8bit.py
 *               (host-gcc vs tools/sh2emu.py over real 60E1D400.bin map
 *               descriptors plus one synthetic extremes grid, edge + 20000
 *               random (x, y) pairs; 0 mismatches).
 * Lift (truth): c/3dLookup.c  (ThreeDLookup_FP_8bit @ 0x2120)
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * The u8-cell, float-input sibling of the 2-D bilinear map primitive
 * (c/3dLookup.c's ThreeDLookup @ 0x20DC): interpolates a surface value
 * against two inputs (e.g. RPM x engine load) on a Map2D calibration
 * descriptor.  This variant is hardwired to u8 cells and applies NO
 * scale/offset — confirmed from asm: it only ever reads count_x@+0,
 * count_y@+2, axis_x@+4, axis_y@+8 and values@+12 of the descriptor, never
 * m->type/m->scale/m->offset at +16/+20/+24.  It is the 2-D analog of the
 * relationship between TwoDLookup_FP_16bit and TwoDLookup in c/2DLookup.c.
 *
 * CALLING CONVENTION
 * ------------------
 * Standard ABI entry: r4 = Map2D* descriptor, fr4 = x, fr5 = y; the u8 result
 * is returned zero-extended in r0 (the emulator returns r0, mask 0xFF).
 * (Internally the ROM blends each row through the non-ABI 1-D u8 leaf @0x26B0
 * — see rx8_interpolate_u8_table.c for that register convention — but that is
 * hidden inside the ROM body and irrelevant to callers of 0x2120.)
 *
 * ALGORITHM (ROM semantics preserved verbatim)
 * --------------------------------------------
 *   1. axis_search the X breakpoints and Y breakpoints (ROM helper @0x2624)
 *      -> (ix, tx) and (iy, ty).  Both clamp branches (below axis[0], at/above
 *      axis[n-1]) force t == 0.0; `!(x < axis[n-1])` (not `x >= axis[n-1]`)
 *      is what makes NaN clamp high exactly like the ROM.
 *   2. Read the four surrounding u8 cells row-major [count_y][count_x], with
 *      the upper neighbour clamped to the last cell per axis (the axis-search
 *      clamp branches are the only way tx/ty can be 0, so reading the clamped
 *      neighbour is safe and yields the same value the ROM's skip-row fast
 *      paths produce).
 *   3. row0 = tx*(c10-c00)+c00, row1 = tx*(c11-c01)+c01, then
 *      interp = ty*(row1-row0)+row0.  Each combine is ONE `fmac` in the ROM
 *      (single rounding) on a separately-rounded `fsub` difference —
 *      `fmaf()` reproduces that exactly, while plain `a + t*(b-a)` rounds
 *      twice and measurably diverges at the few-ULP level over enough random
 *      inputs (confirmed empirically; same finding as interp_leaves.c).
 *   4. ftrc truncates the interpolant toward zero; the result is
 *      zero-extended to 8 bits.  The interpolant always lies in [0, 255]
 *      (u8 cells, t clamped to [0,1)), so truncation equals a plain floor.
 * =============================================================================
 */
#include <stdint.h>
#include <math.h>

#include "rx8_samples.h"

/* Map2D calibration descriptor (28 bytes, big-endian on the SH-2E) — same
 * layout as c/3dLookup.c.  Only the first five fields are read by this
 * function; type/scale/offset are kept so callers can share the descriptor. */
typedef struct {
    uint16_t     count_x;   /* +0  X-axis breakpoint count          */
    uint16_t     count_y;   /* +2  Y-axis breakpoint count          */
    const float *axis_x;    /* +4  X breakpoints (count_x f32)      */
    const float *axis_y;    /* +8  Y breakpoints (count_y f32)      */
    const void  *values;    /* +12 row-major [count_y][count_x] u8  */
    uint8_t      type;      /* +16 never read here (always u8)      */
    uint8_t      _pad[3];
    float        scale;     /* +20 never read here (no scaling)     */
    float        offset;    /* +24 never read here                  */
} Map2D;

/* 1-D axis search — the ROM helper @0x2624 (already verified; c/2DLookup.c's
 * axis_search).  `!(x < ax[n-1])` instead of `x >= ax[n-1]` so a NaN input
 * clamps high exactly like the ROM; both clamp ends force t == 0.0. */
static void axis_search(const float *ax, int n, float x, int *pi, float *pt)
{
    if (!(x < ax[n - 1]))    { *pi = n - 1; *pt = 0.0f; }
    else if (x < ax[0])      { *pi = 0;     *pt = 0.0f; }
    else {
        int k = 0;
        while (k + 1 < n && !(ax[k] <= x && x < ax[k + 1])) k++;
        *pi = k; *pt = (x - ax[k]) / (ax[k + 1] - ax[k]);
    }
}

uint8_t rx8_3d_lookup_fp_8bit(const Map2D *m, float x, float y)
{
    const int cx = m->count_x, cy = m->count_y;
    const uint8_t *cells = (const uint8_t *)m->values;
    int ix, iy, ix1, iy1;
    float tx, ty, c00, c10, c01, c11, row0, row1, interp;

    axis_search(m->axis_x, cx, x, &ix, &tx);
    axis_search(m->axis_y, cy, y, &iy, &ty);

    /* Upper neighbour clamps to the last cell per axis (safe: tx/ty are 0
     * exactly there, so the clamped read equals the ROM's skip-row result). */
    ix1 = ix + 1 < cx ? ix + 1 : ix;
    iy1 = iy + 1 < cy ? iy + 1 : iy;

    c00 = (float)cells[iy  * cx + ix];
    c10 = (float)cells[iy  * cx + ix1];
    c01 = (float)cells[iy1 * cx + ix];
    c11 = (float)cells[iy1 * cx + ix1];

    /* Each blend is a fused multiply-add (`fmac`) in the ROM on a
     * separately-rounded difference (`fsub`): fmaf gives single rounding. */
    row0 = fmaf(tx, c10 - c00, c00);
    row1 = fmaf(tx, c11 - c01, c01);
    interp = fmaf(ty, row1 - row0, row0);

    /* ftrc: truncate toward zero, then zero-extend to u8 (r0 on the ROM). */
    return (uint8_t)(int32_t)interp;
}
