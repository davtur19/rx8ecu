/*
 * 3dLookup  —  RX-8 PCM primitive @ ROM 0x20DC  (equinox name; hand Ghidra RE by
 * equinox311).  C function named ThreeDLookup.
 *
 * The 2-D **bilinear** calibration-map read: interpolates a surface value against two
 * inputs (e.g. RPM x engine-load). This is the primitive behind the main fuel and
 * ignition maps. Same descriptor pattern as the 1-D `2DLookup`, with a second axis.
 *
 * Descriptor (28 bytes, big-endian on the SH-2E):
 *   +0  u16   count_x    X-axis breakpoints
 *   +2  u16   count_y    Y-axis breakpoints
 *   +4  f32*  axis_x
 *   +8  f32*  axis_y
 *   +12 void* values     row-major [count_y][count_x] cells, width/sign per `type`
 *   +16 u8    type       0->f32 cells | 4->u8 | 8->u16 | 12->s8 | 16->s16
 *   +20 f32   scale        } result = (type==0) ? interp : scale*interp + offset
 *   +24 f32   offset       }
 *
 * Algorithm (helper 0x2658 searches both axes via 0x2624; jump-table handler 0x210C
 * does bilinear interp via the per-row 1-D helper 0x2678/0x2690/...):
 *   (ix,tx) = search(axis_x, x);   (iy,ty) = search(axis_y, y)
 *   row0 = cell[iy][ix]   + tx*(cell[iy][ix+1]   - cell[iy][ix])
 *   row1 = cell[iy+1][ix] + tx*(cell[iy+1][ix+1] - cell[iy+1][ix])
 *   interp = row0 + ty*(row1 - row0)
 *   result = (type==0) ? interp : scale*interp + offset
 *
 * Track A: verified behavior-equivalent to the emulated ROM (tools/sh2emu.py) for
 * type=16 (s16 cells + scale/offset): 10000/10000 random surfaces & inputs.
 */
#include <stdint.h>
#include <math.h>

typedef struct {
    uint16_t     count_x;   /* +0  */
    uint16_t     count_y;   /* +2  */
    const float *axis_x;    /* +4  */
    const float *axis_y;    /* +8  */
    const void  *values;    /* +12 (row-major [count_y][count_x]) */
    uint8_t      type;      /* +16 */
    uint8_t      _pad[3];
    float        scale;     /* +20 */
    float        offset;    /* +24 */
} Map2D;

static float cell2(const void *v, uint8_t type, int idx)
{
    switch (type) {
    case 4:  return (float)((const uint8_t  *)v)[idx];
    case 8:  return (float)((const uint16_t *)v)[idx];
    case 12: return (float)((const int8_t   *)v)[idx];
    case 16: return (float)((const int16_t  *)v)[idx];
    default: return ((const float *)v)[idx];        /* type 0 = f32 cells */
    }
}

static void axis_search(const float *ax, int n, float x, int *pi, float *pt)
{
    /* `!(x < ax[last])` (not `x >= ax[last]`) so NaN clamps high like the ROM (0x2624) */
    if (!(x < ax[n - 1]))    { *pi = n - 1; *pt = 0.0f; }
    else if (x < ax[0])      { *pi = 0;     *pt = 0.0f; }
    else {
        int k = 0;
        while (k + 1 < n && !(ax[k] <= x && x < ax[k + 1])) k++;
        *pi = k; *pt = (x - ax[k]) / (ax[k + 1] - ax[k]);
    }
}

float ThreeDLookup(const Map2D *m, float x, float y)
{
    int cx = m->count_x, cy = m->count_y, ix, iy, ix1, iy1;
    float tx, ty, c00, c10, c01, c11, row0, row1, interp;

    axis_search(m->axis_x, cx, x, &ix, &tx);
    axis_search(m->axis_y, cy, y, &iy, &ty);
    ix1 = ix + 1 < cx ? ix + 1 : ix;
    iy1 = iy + 1 < cy ? iy + 1 : iy;

    c00 = cell2(m->values, m->type, iy  * cx + ix);
    c10 = cell2(m->values, m->type, iy  * cx + ix1);
    c01 = cell2(m->values, m->type, iy1 * cx + ix);
    c11 = cell2(m->values, m->type, iy1 * cx + ix1);
    row0 = c00 + tx * (c10 - c00);
    row1 = c01 + tx * (c11 - c01);
    interp = row0 + ty * (row1 - row0);
    return m->type == 0 ? interp : m->scale * interp + m->offset;
}

/*
 * indexLookupSomething  —  RX-8 PCM primitive @ ROM 0x2658 (equinox name: axis_search_2d;
 * hand Ghidra RE by equinox311). C function keeps the equinox name (no C-id restriction here).
 *
 * The 2-axis search helper ThreeDLookup's variants dispatch through: runs the SAME 1-D
 * axis-search helper (0x2624, already verified — see this file's `axis_search()` and
 * 2DLookup.c's header) once per axis and packs the two (index,t) results together. Standard
 * ABI: descriptor in r4, x in fr4, y in fr5 — reads count_x@+0/axis_x@+4 for the first
 * search and count_y@+2/axis_y@+8 for the second, exactly the Map2D fields above.
 *
 * Register-level result (confirmed from asm, NOT a normal single-value C return):
 *   r2 = ix, r3 = iy, fr0 = tx, fr1 = ty
 * (fr0 holds the caller's x-fraction both before and after the call — the asm reuses fr0
 * across both axis_search calls and restores it from a saved copy before returning — modeled
 * here with out-parameters so the C shape matches the real multi-value register return.)
 *
 * Track A: verified vs the emulated ROM (tools/sh2emu.py), standard ABI call at entry (r4/fr4/
 * fr5), reading r2/r3/fr0/fr1 after return: real Map2D axis arrays (60E0FC00.bin @0x67898,
 * a 16x6 u8 surface) over 10000+ random (x,y) pairs incl. all breakpoints and out-of-range,
 * 0 mismatches. Test: c/tests/test_indexLookupSomething.py.
 */
void indexLookupSomething(const Map2D *m, float x, float y, int *ix, int *iy, float *tx, float *ty)
{
    axis_search(m->axis_x, m->count_x, x, ix, tx);
    axis_search(m->axis_y, m->count_y, y, iy, ty);
}

/*
 * ThreeDLookup_FP_8bit  —  RX-8 PCM primitive @ ROM 0x2120 (hand Ghidra RE by equinox311).
 *
 * The u8-cell FP-input sibling of ThreeDLookup: same 2-axis search (indexLookupSomething /
 * 0x2658) but hardwired to u8 cells with NO scale/offset applied — confirmed from asm: it
 * only ever reads count_x@+0, count_y@+2, axis_x@+4, axis_y@+8, values@+12 from the Map2D
 * descriptor, never m->type/m->scale/m->offset (at +16/+20/+24). Same relationship as
 * TwoDLookup_FP_16bit -> TwoDLookup in 2DLookup.c, one dimension up.
 *
 * Internally the ROM computes each row via a call into the row-bilinear helper @0x25C8 (which
 * itself calls the 1-D u8 leaf @0x26B0, c/interp_leaves.c's interpolate_uint8Table, once
 * per row) and blends the two rows by ty — skipping the second row's read entirely when
 * ty==0.0 (same clamp-safety shortcut the 1-D leaves use for t==0.0). That is behaviorally
 * identical to the direct 4-corner-then-blend formula below (axis-search's clamp branches are
 * the only way ty can be 0, and they always pick iy = count_y-1, so the "skip row1" path and
 * "read row1 = row0's own row" path produce the same result).
 *
 * Each combine step (row0, row1, and the final row-blend) is a genuine fused multiply-add
 * (`fmac` in the ROM: once inside the leaf per row, once for the final ty blend) — `fmaf()`
 * reproduces that single-rounding behavior exactly; plain `a + t*(b-a)` rounds twice and
 * measurably mismatches the ROM at the few-ULP level over enough random inputs (confirmed
 * empirically, same effect as interp_leaves.c's leaves).
 *
 * Track A: verified vs the emulated ROM (tools/sh2emu.py) using a REAL ROM map descriptor
 * (60E0FC00.bin @0x67898 — a 16x6 u8 surface found by tools/mapscan.py, X=temp -40..110, Y=1..6,
 * values 1050..2150) over 10000+ random + edge (x,y) pairs (all breakpoints on both axes,
 * out-of-range on both), 0 mismatches. Test: c/tests/test_3DLookup_FP.py.
 */
uint8_t ThreeDLookup_FP_8bit(const Map2D *m, float x, float y)
{
    int cx = m->count_x, cy = m->count_y, ix, iy, ix1, iy1;
    float tx, ty, c00, c10, c01, c11, row0, row1, interp;
    const uint8_t *values = (const uint8_t *)m->values;

    indexLookupSomething(m, x, y, &ix, &iy, &tx, &ty);
    ix1 = ix + 1 < cx ? ix + 1 : ix;
    iy1 = iy + 1 < cy ? iy + 1 : iy;

    c00 = (float)values[iy  * cx + ix];
    c10 = (float)values[iy  * cx + ix1];
    c01 = (float)values[iy1 * cx + ix];
    c11 = (float)values[iy1 * cx + ix1];
    row0 = fmaf(tx, c10 - c00, c00);
    row1 = fmaf(tx, c11 - c01, c01);
    interp = fmaf(ty, row1 - row0, row0);
    return (uint8_t)(int32_t)interp;   /* ftrc: trunc toward zero, then zero-extend 8 bits */
}

/*
 * ThreeDLookup_FP_16bit  —  RX-8 PCM primitive @ ROM 0x213C (hand Ghidra RE by equinox311).
 *
 * The u16-cell FP-input sibling — identical to ThreeDLookup_FP_8bit above except the row
 * helper it calls (@0x25F4) is hardwired to u16 cells (jumps to the 1-D u16 leaf @0x26D0,
 * interpolate_uint16Table) and the final truncation masks 16 bits instead of 8. Same
 * descriptor fields only (no type/scale/offset read).
 *
 * Track A: verified vs the emulated ROM (tools/sh2emu.py) using a REAL ROM map descriptor
 * (60E0FC00.bin @0x68114 — a 13x7 u16 surface found by tools/mapscan.py) over 10000+ random +
 * edge (x,y) pairs (all breakpoints on both axes, out-of-range on both), 0 mismatches. Test:
 * c/tests/test_3DLookup_FP.py.
 */
uint16_t ThreeDLookup_FP_16bit(const Map2D *m, float x, float y)
{
    int cx = m->count_x, cy = m->count_y, ix, iy, ix1, iy1;
    float tx, ty, c00, c10, c01, c11, row0, row1, interp;
    const uint16_t *values = (const uint16_t *)m->values;

    indexLookupSomething(m, x, y, &ix, &iy, &tx, &ty);
    ix1 = ix + 1 < cx ? ix + 1 : ix;
    iy1 = iy + 1 < cy ? iy + 1 : iy;

    c00 = (float)values[iy  * cx + ix];
    c10 = (float)values[iy  * cx + ix1];
    c01 = (float)values[iy1 * cx + ix];
    c11 = (float)values[iy1 * cx + ix1];
    row0 = fmaf(tx, c10 - c00, c00);
    row1 = fmaf(tx, c11 - c01, c01);
    interp = fmaf(ty, row1 - row0, row0);
    return (uint16_t)(int32_t)interp;   /* ftrc: trunc toward zero, then zero-extend 16 bits */
}
