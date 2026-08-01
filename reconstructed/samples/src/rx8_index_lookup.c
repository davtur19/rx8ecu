/*
 * =============================================================================
 * rx8_index_lookup.c  —  TWO-AXIS BREAKPOINT SEARCH (MAP2D index + fraction)
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x2658
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_index_lookup.py
 *               (host-gcc vs tools/sh2emu.py over random + edge (x,y) pairs on
 *               two REAL Map2D descriptors of this ROM, 0 mismatches).
 * Lift (truth): c/3dLookup.c  (indexLookupSomething @ 0x2658, hand Ghidra RE)
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * The shared 2-axis search step of the 3-D bilinear calibration-map lookups
 * (ThreeDLookup and its FP typed-cell variants in 3dLookup.c).  For a given
 * Map2D descriptor it finds, on each axis independently, the breakpoint
 * interval the input falls into and returns the lower-endpoint index plus the
 * within-interval interpolation fraction t in [0,1).  The caller then does the
 * actual bilinear blend with those four values.
 *
 * CALLING CONVENTION
 * ------------------
 * Standard SH-2E C ABI at entry: r4 = Map2D descriptor, fr4 = x, fr5 = y.
 * The four results come back in registers, NOT as a single C return value
 * (confirmed from asm; there is no memory result area):
 *     r2 = ix, r3 = iy, fr0 = tx, fr1 = ty
 * The body runs the SAME 1-D axis-search helper (@0x2624, the verified
 * `axis_search()` of 3dLookup.c / 2DLookup.c) once per axis and packs the two
 * (index,t) pairs together — the C shape below uses out-parameters so the
 * multi-value register return maps 1:1 onto the caller's ABI view.
 *
 * ROM BODY (disassembled 60E1D400.bin @ 0x2658)
 * ----------------------------------------------
 *     sts.l  pr,@-r15
 *     mov.w  @(0x0,r4),r0      ; r0 = count_x
 *     mov.l  @(0x4,r4),r1      ; r1 = axis_x
 *     bsr    0x2624            ;   axis_search(x)  (delay: fmov fr4,fr0)
 *     mov    r0,r2             ; r2 = ix
 *     fmov   fr0,fr3           ; save tx
 *     mov.w  @(0x2,r4),r0      ; r0 = count_y
 *     mov.l  @(0x8,r4),r1      ; r1 = axis_y
 *     bsr    0x2624            ;   axis_search(y)  (delay: fmov fr5,fr0)
 *     mov    r0,r3             ; r3 = iy
 *     lds.l  @r15+,pr
 *     fmov   fr0,fr1           ; fr1 = ty
 *     rts
 *     fmov   fr3,fr0           ;   (delay: restore tx into fr0)
 *
 * SEMANTICS (per-axis, from the 0x2624 helper)
 * --------------------------------------------
 *   - x >= last breakpoint  -> index = n-1, t = 0.0   (clamp HIGH)
 *   - x <  first breakpoint -> index = 0,   t = 0.0   (clamp LOW)
 *   - otherwise find the k with  ax[k] <= x < ax[k+1] and
 *     t = (x - ax[k]) / (ax[k+1] - ax[k]).
 *   - The high clamp is tested as `!(x < ax[n-1])`, NOT `x >= ax[n-1]`: the
 *     ROM's `fcmp/gt` sets T = (ax[n-1] > x) and branches on its negation, so
 *     a NaN input (for which every comparison is false) also clamps HIGH — an
 *     input the rest of the code can never reach.
 *   - Each fsub and the fdiv round to single precision independently; the C
 *     float arithmetic below rounds identically (one rounding per operator).
 *   - A 1-breakpoint axis (n==1) always yields index 0, t = 0.0 (the ROM's
 *     top-down loop hits the tst r0,r0 / mov #0 branch immediately).
 * =============================================================================
 */
#include <stdint.h>

#include "rx8_samples.h"

/* Map2D descriptor — first two entries of the full 28-byte layout used by the
 * 3-D bilinear lookups (3dLookup.c); only the count and axis-pointer fields
 * are consumed here (the ROM reads +0/+2/+4/+8 and nothing else). */
typedef struct {
    uint16_t     count_x;   /* +0 */
    uint16_t     count_y;   /* +2 */
    const float *axis_x;    /* +4 */
    const float *axis_y;    /* +8 */
} rx8_map2d_axes_t;

/* One axis of breakpoint search — the ROM helper @0x2624, behavior-identical
 * to the verified axis_search() of c/3dLookup.c and c/2DLookup.c. */
static void rx8_axis_search(const float *ax, int32_t n, float x,
                            int32_t *pi, float *pt)
{
    /* High clamp: `!(x < ax[n-1])` so NaN clamps high like the ROM's fcmp/gt
     * (the emulated `fcmp/gt FRm,FRn` is T = (FRn > FRm), i.e. ax[n-1] > x,
     * and the ROM branches when T is clear — false for any NaN). */
    if (!(x < ax[n - 1])) {
        *pi = n - 1;
        *pt = 0.0f;
    } else if (x < ax[0]) {          /* low clamp */
        *pi = 0;
        *pt = 0.0f;
    } else {
        int32_t k = 0;

        while (k + 1 < n && !(ax[k] <= x && x < ax[k + 1])) {
            k++;
        }
        *pi = k;
        /* (x - ax[k]) / (ax[k+1] - ax[k]): fsub / fsub / fdiv, one single-
         * precision rounding per operator — matches the ROM exactly. */
        *pt = (x - ax[k]) / (ax[k + 1] - ax[k]);
    }
}

/* Search both axes of a Map2D descriptor.  Returns ix/iy (breakpoint indices)
 * and tx/ty (interpolation fractions) via out-parameters — the C shape of the
 * ROM's register-level multi-value return (r2/r3/fr0/fr1). */
void rx8_index_lookup(const rx8_map2d_axes_t *m, float x, float y,
                      int32_t *ix, int32_t *iy, float *tx, float *ty)
{
    rx8_axis_search(m->axis_x, m->count_x, x, ix, tx);
    rx8_axis_search(m->axis_y, m->count_y, y, iy, ty);
}
