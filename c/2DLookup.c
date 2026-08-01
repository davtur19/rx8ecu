/*
 * 2DLookup  —  RX-8 PCM primitive @ ROM 0x2068  (equinox name; from the hand
 * Ghidra RE by equinox311).  C function named TwoDLookup (C ids can't start '2').
 *
 * The core calibration-table read: 1-D piecewise-linear interpolation of a mapped
 * value against an input, with typed cells and an optional unit scale/offset. Used
 * everywhere the ECU reads a 1-D map (RPM->timing, temp->enrichment, ...).
 *
 * Descriptor (20 bytes, big-endian on the SH-2E):
 *   +0  u16   count     number of axis breakpoints
 *   +2  u8    type      cell encoding + scale/offset select (see table)
 *   +4  f32*  axis      ascending breakpoints (count floats)
 *   +8  void* values    count cells, width/sign per `type`
 *   +12 f32   scale       } result units:  result = scale*interp + offset
 *   +16 f32   offset      }
 *
 * type -> ROM handler / cell:  4->0x26B0 u8 | 8->0x26D0 u16 | 12->0x26F4 s8 |
 *                              16->0x2690 s16 | 0->0x2678 (f32 cells, no scale/offset)
 *   (0x269A is NOT a float entry — it is inside the s16 handler @0x2690, the delay-slot
 *    lds r0,fpul right after the mov.w cell read; type 0 dispatches to the separate
 *    f32 handler @0x2678, shll2 r0 = 4-byte fmov.s cells, confirmed from the jump table
 *    @0x2098: table[0]=0x2678, table[4]=0x26B0, table[8]=0x26D0, table[12]=0x26F4,
 *    table[16]=0x2690)
 *
 * Algorithm (helper 0x2624 = axis search; jump-table handler = typed interp):
 *   find i,t :  axis[i] <= x < axis[i+1],   t = (x-axis[i])/(axis[i+1]-axis[i])
 *               x <  axis[0]    -> i=0,      t=0   (clamp low)
 *               x >= axis[last] -> i=last,   t=0   (clamp high)
 *   interp = cell[i] + t*(cell[i+1]-cell[i])
 *   result = (type==0) ? interp : scale*interp + offset
 *
 * Track A: verified behavior-equivalent to the emulated ROM (tools/sh2emu.py) for
 * type=16 (s16 cells + scale/offset) over 15000/15000 random tables & inputs; the
 * axis-search helper (0x2624) verified 20000/20000 separately. Other cell types
 * differ only in the cell read and are verifiable identically.
 */
#include <stdint.h>
#include <math.h>

/*
 * dataLookup  —  RX-8 PCM primitive @ ROM 0x2624 (equinox name; hand Ghidra RE by
 * equinox311). The 1-D axis-search LEAF that every lookup in this file / 3dLookup.c calls
 * (via `bsr`) to turn a raw input into a breakpoint index + interpolation fraction. Its
 * logic is inlined into TwoDLookup / TwoDLookup_FP_16bit / TwoDLookup_FP_8bit above (and
 * 3dLookup.c's axis_search()) — this is the first time it is lifted and verified as its
 * OWN standalone function against the real ROM bytes at 0x2624, rather than only indirectly
 * through its callers.
 *
 * NOT the normal r4-r7/fr4-fr6 ABI — leaf-level register convention (confirmed from asm;
 * matches every call site, e.g. TwoDLookup_FP_16bit @0x20C4 loads r0=count/r1=axis then
 * `bsr 0x2624` with fr0=x moved into place in the delay slot):
 *   in:  r0 = count (n), r1 = axis pointer (ascending f32 breakpoints), fr0 = x
 *   out: r0 = index i, fr0 = t          (NOT fr2 — the interpolate_* leaves in
 *                                         interp_leaves.c return via fr2 instead)
 *
 * The ROM implements a BACKWARD linear search (starts at axis[count-1], walks the index
 * down comparing `fcmp/gt fr0,fr1` i.e. axis[k] > x, confirmed from asm) rather than the
 * forward search used in the rest of this codebase — for a strictly-ascending axis with
 * exactly one matching interval the two produce an identical (i,t) (already cross-checked
 * via every calling lookup's edge-fuzz testing), so the shared forward form is kept here
 * for consistency with TwoDLookup / TwoDLookup_FP_16bit / TwoDLookup_FP_8bit / axis_search().
 * Edge behavior (byte for byte from asm):
 *   x >= axis[n-1]  -> i = n-1, t = 0.0   (clamp high; `fcmp/gt` is false for NaN too, so
 *                                          NaN also clamps high, same as every caller)
 *   x <  axis[0]    -> i = 0,   t = 0.0   (clamp low, incl. the count==1 fast path — the
 *                                          asm special-cases count==1 via `tst r0,r0`
 *                                          right after the high-clamp check, but it lands
 *                                          on the exact same i=0/t=0 result)
 *   else            -> axis[i] <= x < axis[i+1], t = (x-axis[i])/(axis[i+1]-axis[i])
 *
 * Track A: verified vs the emulated ROM (tools/sh2emu.py), leaf-level register injection
 * (`call_leaf`, same technique as c/tests/test_interp_leaves.py), real axis array from
 * 60E0FC00.bin @0x67870 (the 16-point table TwoDLookup_FP_16bit's test also uses;
 * breakpoints -40..110 step 10) over 20000+ random + edge inputs (all breakpoints,
 * +/-0.001 either side, out-of-range clamps, NaN), 0 mismatches. Test:
 * c/tests/test_dataLookup.py.
 */
void dataLookup(int n, const float *axis, float x, int *out_i, float *out_t)
{
    int i; float t;

    if (!(x < axis[n - 1])) { i = n - 1; t = 0.0f; }
    else if (x < axis[0])   { i = 0;     t = 0.0f; }
    else {
        i = 0;
        while (i + 1 < n && !(axis[i] <= x && x < axis[i + 1])) i++;
        t = (x - axis[i]) / (axis[i + 1] - axis[i]);
    }
    *out_i = i;
    *out_t = t;
}

typedef struct {
    uint16_t     count;   /* +0  */
    uint8_t      type;    /* +2  */
    uint8_t      _pad;    /* +3  */
    const float *axis;    /* +4  */
    const void  *values;  /* +8  */
    float        scale;   /* +12 */
    float        offset;  /* +16 */
} Map1D;

static float map1d_cell(const void *v, uint8_t type, int i)
{
    switch (type) {
    case 4:  return (float)((const uint8_t  *)v)[i];   /* u8  (handler 0x26B0) */
    case 8:  return (float)((const uint16_t *)v)[i];   /* u16 (handler 0x26D0) */
    case 12: return (float)((const int8_t   *)v)[i];   /* s8  (handler 0x26F4) */
    case 16: return (float)((const int16_t  *)v)[i];   /* s16 (handler 0x2690) */
    default: return ((const float *)v)[i];             /* type 0 = f32 cells (handler 0x2678) */
    }
}

float TwoDLookup(const Map1D *m, float x)
{
    int n = (int)m->count, i;
    float t, v0, v1, interp;

    /* clamp-high test written as the ROM's `!(X < axis[last])` so NaN clamps high
       too (fcmp/gt is false for NaN) — matches 0x2624 exactly (edge-fuzz-checked). */
    if (!(x < m->axis[n - 1])) { i = n - 1; t = 0.0f; }
    else if (x < m->axis[0])   { i = 0;     t = 0.0f; }
    else {
        i = 0;
        while (i + 1 < n && !(m->axis[i] <= x && x < m->axis[i + 1])) i++;
        t = (x - m->axis[i]) / (m->axis[i + 1] - m->axis[i]);
    }

    v0 = map1d_cell(m->values, m->type, i);
    v1 = map1d_cell(m->values, m->type, i + 1 < n ? i + 1 : i);
    interp = v0 + t * (v1 - v0);
    return m->type == 0 ? interp : m->scale * interp + m->offset;
}

/*
 * 2DLookup_FP_16bit  —  RX-8 PCM primitive @ ROM 0x20C4 (equinox name; hand Ghidra RE).
 * C function named TwoDLookup_FP_16bit for the same reason as above.
 *
 * A leaner sibling of TwoDLookup: same axis search (calls the SAME helper @0x2624), but
 * then jumps straight into the u16-cell interpolation handler (@0x26D0) instead of going
 * through TwoDLookup's type-dispatch + scale/offset path. Confirmed from asm: this wrapper
 * only ever reads count(+0), axis(+4), values(+8) from the descriptor — it never reads
 * m->type or m->scale/m->offset — so it is hardwired to u16 cells and returns the raw
 * interpolated cell value truncated to an unsigned 16-bit int, with NO scale/offset applied
 * (unlike TwoDLookup, whose type!=0 path always applies scale*interp+offset).
 *
 * Track A: verified vs the emulated ROM (tools/sh2emu.py) using a REAL ROM map descriptor
 * (60E0FC00.bin @0x67870 — a 16-point u16 table found by tools/mapscan.py, breakpoints
 * -40..110 step 10, likely a temp-indexed target-idle-RPM-style curve) over 20000+ random +
 * edge inputs (all 16 breakpoints, +/-0.001 either side of each, out-of-range clamps): 0
 * mismatches. Test: c/tests/test_2DLookup_FP_16bit.py.
 */
uint16_t TwoDLookup_FP_16bit(const Map1D *m, float x)
{
    int n = (int)m->count, i;
    float t, v0, v1, interp;
    const uint16_t *values = (const uint16_t *)m->values;

    if (!(x < m->axis[n - 1])) { i = n - 1; t = 0.0f; }
    else if (x < m->axis[0])   { i = 0;     t = 0.0f; }
    else {
        i = 0;
        while (i + 1 < n && !(m->axis[i] <= x && x < m->axis[i + 1])) i++;
        t = (x - m->axis[i]) / (m->axis[i + 1] - m->axis[i]);
    }

    v0 = (float)values[i];
    v1 = (float)values[i + 1 < n ? i + 1 : i];
    interp = v0 + t * (v1 - v0);
    return (uint16_t)(int32_t)interp;   /* ftrc: trunc toward zero, then zero-extend 16 bits */
}

/*
 * 2DLookup_FP_8bit  —  RX-8 PCM primitive @ ROM 0x20AC (equinox name; hand Ghidra RE).
 * C function named TwoDLookup_FP_8bit — the u8-cell sibling of TwoDLookup_FP_16bit above.
 *
 * Byte-for-byte the same shape as TwoDLookup_FP_16bit: same axis search (calls the SAME
 * helper @0x2624), same descriptor fields read (count@+0, axis@+4, values@+8 only — type/
 * scale/offset at +2/+12/+16 are never read), same final `(int32_t)interp` truncation. The
 * only difference (confirmed from asm) is the cell-read handler it jumps to after the axis
 * search: @0x26B0 (u8 cells, see c/interp_leaves.c's interpolate_uint8Table for the
 * standalone leaf) instead of @0x26D0, and the final mask is 8 bits (`extu.b`) instead of 16.
 *
 * Combine step uses a genuine fused multiply-add (`fmac fr0,fr1,fr2` in the leaf @0x26B0,
 * single rounding) — `fmaf()` reproduces that exactly; a plain `v0 + t*(v1-v0)` rounds twice
 * and measurably mismatches the ROM at the few-ULP level over enough random t (confirmed
 * empirically, same as interp_leaves.c's leaves).
 *
 * Track A: verified vs the emulated ROM (tools/sh2emu.py) using a REAL ROM map descriptor
 * (60E0FC00.bin @0x677E8 — a 16-point u8 table found by tools/mapscan.py, breakpoints 800..6800
 * step 400, values 120/80/60 — an RPM-indexed table) over 10000+ random + edge inputs (all
 * breakpoints, +/-0.001 either side, out-of-range clamps): 0 mismatches. Test:
 * c/tests/test_2DLookup_FP_8bit.py.
 */
uint8_t TwoDLookup_FP_8bit(const Map1D *m, float x)
{
    int n = (int)m->count, i;
    float t, v0, v1, interp;
    const uint8_t *values = (const uint8_t *)m->values;

    if (!(x < m->axis[n - 1])) { i = n - 1; t = 0.0f; }
    else if (x < m->axis[0])   { i = 0;     t = 0.0f; }
    else {
        i = 0;
        while (i + 1 < n && !(m->axis[i] <= x && x < m->axis[i + 1])) i++;
        t = (x - m->axis[i]) / (m->axis[i + 1] - m->axis[i]);
    }

    v0 = (float)values[i];
    v1 = (float)values[i + 1 < n ? i + 1 : i];
    interp = fmaf(t, v1 - v0, v0);
    return (uint8_t)(int32_t)interp;   /* ftrc: trunc toward zero, then zero-extend 8 bits */
}
