/*
 * =============================================================================
 * rx8_2d_lookup_fp_8bit.c  —  FLOAT-INPUT 1-D MAP LOOKUP (u8 CELLS)
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x20AC
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_2d_lookup_fp_8bit.py
 *               (host-gcc vs tools/sh2emu.py over 20000 random + edge vectors,
 *               real u8 map descriptors from this ROM; 0 mismatches).
 * Lift (truth): c/2DLookup.c  (TwoDLookup_FP_8bit @ 0x20AC)
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * A lean u8-cell sibling of TwoDLookup (0x2068): same axis search (it calls
 * the SAME helper 0x2624 via `bsr`) but then jumps straight into the u8-cell
 * interpolation leaf (0x26B0) instead of TwoDLookup's type-dispatch +
 * scale/offset path.  Disassembly of 60E1D400.bin @ 0x20AC:
 *
 *     4F22   sts.l pr,@-r15          ; prologue
 *     8540   mov.w @(0,r4),r0        ; r0 = count        (desc +0)
 *     5141   mov.l @(4,r4),r1        ; r1 = axis ptr     (desc +4)
 *     B2B7   bsr  0x2624             ; axis search: r0=i, fr0=t
 *     F04C   fmov  fr4,fr0           ;   (delay slot) fr0 = x
 *     B2FB   bsr  0x26B0             ; u8 interp leaf: fr2 = result
 *     5142   mov.l @(8,r4),r1        ;   (delay slot) r1 = values ptr (desc +8)
 *     F23D   ftrc  fr2,fpul          ; truncate toward zero
 *     005A   sts   fpul,r0
 *     4F26   lds.l @r15+,pr          ; epilogue
 *     000B   rts
 *     600C   extu.b r0,r0            ;   (delay slot) mask to 8 bits
 *
 * The wrapper only ever reads count(+0), axis(+4) and values(+8) from the
 * descriptor — type/scale/offset at +2/+12/+16 are never read — so it is
 * hardwired to u8 cells and returns the raw interpolated cell value truncated
 * to an unsigned 8-bit int with NO scale/offset applied.
 *
 * CALLING CONVENTION
 * ------------------
 * Entry is the normal ABI: r4 = Map1D descriptor pointer, fr4 = x.  Internally
 * it drives the non-ABI leaf pair (see rx8_interpolate_u8_table.c for the
 * leaf-level register convention: r0=index / r1=cell array / fr0=t -> fr2).
 *
 * FP EXACTNESS
 * ------------
 * The leaf @0x26B0 combines with one `fmac fr0,fr1,fr2` — a fused multiply-add
 * with a SINGLE rounding.  `fmaf()` reproduces that exactly; a plain
 * `v0 + t*(v1-v0)` rounds twice (multiply then add) and measurably mismatches
 * the ROM at the few-ULP level.  The `v1 - v0` fsub is one separate rounding
 * (kept as its own float expression, exactly like the leaf).  Final ftrc =
 * truncation toward zero, extu.b = mask low 8 bits: `(uint8_t)(int32_t)`.
 *
 * Semantics verbatim from c/2DLookup.c (verified 10000+ there, re-verified
 * against the 60E1D400.bin bytes here):
 *   x <  axis[0]     -> i=0,    t=0.0   (clamp low)
 *   x >= axis[last]  -> i=n-1,  t=0.0   (clamp high; NaN also clamps high,
 *                                        `!(x < axis[last])` matches fcmp/gt)
 *   else             -> axis[i] <= x < axis[i+1], t=(x-axis[i])/(axis[i+1]-axis[i])
 * =============================================================================
 */
#include <stdint.h>
#include <math.h>

#include "rx8_samples.h"

/* TwoDLookup calibration-table descriptor (c/2DLookup.c Map1D, same fields;
 * the +4/+8 offsets in the comments are the SH-2E's — on the host the pointers
 * are 8 bytes, but only count/axis/values are ever read by this function). */
typedef struct {
    uint16_t     count;   /* +0  number of axis breakpoints                 */
    uint8_t      type;    /* +2  cell encoding (unused here: hardwired u8)   */
    uint8_t      _pad;    /* +3                                           */
    const float *axis;    /* +4  ascending f32 breakpoints (count of them)  */
    const void  *values;  /* +8  count u8 cells                             */
    float        scale;   /* +12 ignored by this wrapper                    */
    float        offset;  /* +16 ignored by this wrapper                    */
} rx8_map1d_t;

uint8_t rx8_2d_lookup_fp_8bit(const rx8_map1d_t *m, float x)
{
    const int n = (int)m->count;
    int i;
    float t, v0, v1;
    const uint8_t *values = (const uint8_t *)m->values;

    /* Axis search (helper 0x2624).  `!(x < axis[n-1])` reproduces the ROM's
     * fcmp/gt exactly, so NaN clamps high just like the hardware. */
    if (!(x < m->axis[n - 1])) { i = n - 1; t = 0.0f; }
    else if (x < m->axis[0])   { i = 0;     t = 0.0f; }
    else {
        i = 0;
        while (i + 1 < n && !(m->axis[i] <= x && x < m->axis[i + 1])) i++;
        t = (x - m->axis[i]) / (m->axis[i + 1] - m->axis[i]);
    }

    v0 = (float)values[i];
    v1 = (float)values[i + 1 < n ? i + 1 : i];

    /* Leaf @0x26B0: fsub (single rounding) then one fmac (single rounding). */
    return (uint8_t)(int32_t)fmaf(t, v1 - v0, v0);
}
