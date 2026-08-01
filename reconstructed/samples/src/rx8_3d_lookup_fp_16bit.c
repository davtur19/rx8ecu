/*
 * =============================================================================
 * rx8_3d_lookup_fp_16bit.c  —  3-D (BILINEAR) UINT16-CELL LOOKUP, FP INPUTS
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x213C
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_3d_lookup_fp_16bit.py
 *               (host-gcc vs tools/sh2emu.py over the real u16 Map2D
 *               descriptor "Torque To Accel Position" @0x6A96C found by
 *               tools/mapscan.py: all breakpoints / out-of-range / NaN edges
 *               plus N random (x,y) pairs; 0 mismatches).
 * Lift (truth): c/3dLookup.c  (ThreeDLookup_FP_16bit @ 0x213C)
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * The u16-cell FP-input sibling of the 2-axis bilinear calibration-map read.
 * Given a 28-byte Map2D descriptor (two float axes + a row-major u16 cell
 * grid, see the struct below) and two float inputs x/y it returns the bilinear
 * interpolation of the surface, truncated to a 16-bit integer.  It backs the
 * main torque/accel and throttle-position tables of this PCM.  It is
 * hardwired to u16 cells with NO scale/offset applied — the ROM only ever
 * reads count_x/+0, count_y/+2, axis_x/+4, axis_y/+8, values/+12 from the
 * descriptor, never type/scale/offset (+16/+20/+24).
 *
 * SEMANTICS (from the ROM asm, via the verified lift)
 * ---------------------------------------------------
 * 1. Each axis is searched by the shared helper @0x2624, whose clamp rules are
 *    quirky on purpose: the high-clamp test is `!(x < ax[n-1])` — NOT
 *    `x >= ax[n-1]` — so NaN clamps HIGH, and the low clamp is `x < ax[0]`;
 *    both clamp paths force t = 0.0.  In-range, t = (x-ax[k])/(ax[k+1]-ax[k]).
 * 2. The four corners around (ix,iy) are read as u16 (row-major, index
 *    iy*cx+ix), with the +1 column/row clamped to the last one so the clamp
 *    branches never read past the grid.
 * 3. Every blend step is a genuine fused multiply-add — `fmac` in the ROM
 *    (one inside each row helper @0x25F4 and one for the final ty blend) with
 *    a SINGLE rounding.  A plain C `a + t*(b-a)` rounds twice and measurably
 *    diverges from the ROM at the few-ULP level over enough random inputs;
 *    `fmaf()` reproduces the single-rounding hardware behaviour exactly
 *    (confirmed in the lift and in c/interp_leaves.c's u16 leaf @0x26D0).
 * 4. The result is truncated toward zero by the ftrc instruction and
 *    zero-extended to 16 bits — `(uint16_t)(int32_t)interp`.
 *
 * CALLING CONVENTION (ABI)
 * ------------------------
 * Normal r4/fr4/fr5 ABI: descriptor pointer in r4, x in fr4, y in fr5,
 * result returned in r0 (zero-extended u16).  Unlike the inner interpolation
 * leaves (rx8_interpolate_u8_table.c) no custom register injection is needed.
 * =============================================================================
 */
#include <stdint.h>
#include <math.h>

#include "rx8_samples.h"

/* The Map2D calibration-map descriptor, byte layout identical on the SH-2E
 * (28 bytes, big-endian) and the host (natural alignment reproduces the same
 * offsets: 2+2, then 4-aligned pointers, u8+pad, then two floats). */
typedef struct {
    uint16_t     count_x;   /* +0  X-axis breakpoint count                */
    uint16_t     count_y;   /* +2  Y-axis breakpoint count                */
    const float *axis_x;    /* +4  X-axis breakpoints (f32, ascending)    */
    const float *axis_y;    /* +8  Y-axis breakpoints (f32, ascending)    */
    const void  *values;    /* +12 u16 cells, row-major [count_y][count_x] */
    uint8_t      type;      /* +16 cell type tag (NOT read by this func)  */
    uint8_t      _pad[3];
    float        scale;     /* +20 (NOT read by this function)            */
    float        offset;    /* +24 (NOT read by this function)            */
} Rx8Map2D;

/* ROM axis-search @0x2624.  The high-clamp test is `!(x < ax[n-1])`, NOT
 * `x >= ax[n-1]`, so NaN clamps HIGH (fcmp/gt + bf — a NaN compares false,
 * T is cleared, the branch falls through to the clamp).  Both clamp paths
 * return t = 0.0 exactly. */
static void rx8_axis_search(const float *ax, int n, float x, int *pi, float *pt)
{
    if (!(x < ax[n - 1]))   { *pi = n - 1; *pt = 0.0f; }
    else if (x < ax[0])     { *pi = 0;     *pt = 0.0f; }
    else {
        int k = 0;
        while (k + 1 < n && !(ax[k] <= x && x < ax[k + 1])) k++;
        *pi = k;
        *pt = (x - ax[k]) / (ax[k + 1] - ax[k]);
    }
}

/* ThreeDLookup_FP_16bit @0x213C.  Bilinear interpolation of a u16 cell grid
 * against two float inputs, truncated to u16.  Verbatim semantics of the
 * verified lift (c/3dLookup.c). */
uint16_t rx8_three_d_lookup_fp_16bit(const Rx8Map2D *m, float x, float y)
{
    int cx = m->count_x, cy = m->count_y, ix, iy, ix1, iy1;
    float tx, ty, c00, c10, c01, c11, row0, row1, interp;
    const uint16_t *values = (const uint16_t *)m->values;

    rx8_axis_search(m->axis_x, cx, x, &ix, &tx);
    rx8_axis_search(m->axis_y, cy, y, &iy, &ty);

    /* Clamp the +1 neighbour so the clamp branches never read off the grid. */
    ix1 = ix + 1 < cx ? ix + 1 : ix;
    iy1 = iy + 1 < cy ? iy + 1 : iy;

    c00 = (float)values[iy  * cx + ix];
    c10 = (float)values[iy  * cx + ix1];
    c01 = (float)values[iy1 * cx + ix];
    c11 = (float)values[iy1 * cx + ix1];

    /* Each blend is one ROM `fmac` = one rounding (fmaf). */
    row0 = fmaf(tx, c10 - c00, c00);
    row1 = fmaf(tx, c11 - c01, c01);
    interp = fmaf(ty, row1 - row0, row0);

    /* ftrc: trunc toward zero, then zero-extend to 16 bits. */
    return (uint16_t)(int32_t)interp;
}
