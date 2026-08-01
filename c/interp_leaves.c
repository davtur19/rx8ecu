/*
 * interp_leaves.c  —  RX-8 PCM 1-D interpolation LEAVES (equinox names; hand Ghidra RE by
 * equinox311).
 *
 * These are the typed-cell linear-interpolation primitives that TwoDLookup (2DLookup.c)
 * dispatches to via its type jump table (type=4 -> here u8, type=8 -> here u16), and that
 * the 2-D bilinear FP lookups build each row from internally (3dLookup.c's
 * ThreeDLookup_FP_8bit/_16bit call the ROM's row-bilinear helpers @0x25C8/0x25F4, which each
 * call one of these leaves once per row).
 *
 * They are NOT called via the normal r4-r7/fr4-fr6 C ABI: they are tiny internal leaves
 * invoked via `bsr` right after the axis-search helper (0x2624) with its results still live
 * in registers:
 *   r0  = cell index i        (already found by axis-search)
 *   r1  = pointer to the typed cell array (base of the descriptor's `values` field)
 *   fr0 = t, the interpolation fraction in [0,1) from axis-search (0.0 at both clamp ends)
 * The result is returned in fr2 (NOT fr0) — fr0 is left untouched on purpose, since the 2-D
 * bilinear callers reuse it as tx across both row calls without having to reload it.
 *
 * Both leaves share the same shape: read cell[i] first (always — the `float fpul,fr2`
 * conversion sits in the branch's delay slot, so it executes whether or not t==0.0), and if
 * t==0.0 return that immediately WITHOUT ever reading cell[i+1] — this is what makes it safe
 * for axis-search's clamp-high case (i = count-1, t = 0.0) to never read one past the end of
 * the values array. When t!=0, axis-search guarantees i+1 is in range (the clamp branches are
 * the only way to reach the last index, and both force t=0), so cell[i+1] is always a valid
 * read there — modeled below with a plain `cells[i+1]` (no clamp needed) to match.
 *
 * The combine step is one `fmac fr0,fr1,fr2` (fr2 = fr0*fr1 + fr2, i.e. t*(v1-v0) + v0) — a
 * genuine fused multiply-add, single rounding. A plain `v0 + t*(v1-v0)` in C rounds TWICE (the
 * multiply, then the add) and measurably mismatches the ROM at the few-ULP level over enough
 * random t (confirmed empirically: ~1% of random continuous-t inputs differ in the last bit).
 * `fmaf()` is used below to reproduce the single-rounding hardware behavior exactly.
 *
 * interpolate_uint8Table  @ 0x26B0  u8  cells (TwoDLookup type=4; also called by the 3-D
 *                                    row-bilinear helper @0x25C8 for u8 surfaces)
 * interpolate_uint16Table @ 0x26D0  u16 cells (TwoDLookup type=8; this is also the exact
 *                                    handler TwoDLookup_FP_16bit jumps straight to, and the
 *                                    one the 3-D row helper @0x25F4 calls for u16 surfaces)
 *
 * Track A: verified vs the emulated ROM (tools/sh2emu.py). Since these use the r0/r1/fr0->fr2
 * leaf convention rather than the normal ABI, the test harness
 * (c/tests/test_interp_leaves.py) injects r0/r1/fr0 directly via a small SH2 subclass
 * (`call_leaf`, a copy of SH2.call() that accepts arbitrary initial registers) instead of
 * cpu.call()'s r4-r7 args. Real cell arrays from ROM map descriptors (60E0FC00.bin @0x677E8
 * u8, @0x67870 u16, both found by tools/mapscan.py) over 10000+ random + edge inputs (every
 * index 0..count-1, t=0.0 exactly, random t in (0,1), t out of [0,1)) each: 0 mismatches.
 */
#include <stdint.h>
#include <math.h>

float interpolate_uint8Table(int i, const uint8_t *cells, float t)
{
    float v0 = (float)cells[i];
    if (t == 0.0f)
        return v0;
    {
        float v1 = (float)cells[i + 1];
        return fmaf(t, v1 - v0, v0);   /* fmac fr0,fr1,fr2 : t*(v1-v0) + v0, single rounding */
    }
}

float interpolate_uint16Table(int i, const uint16_t *cells, float t)
{
    float v0 = (float)cells[i];
    if (t == 0.0f)
        return v0;
    {
        float v1 = (float)cells[i + 1];
        return fmaf(t, v1 - v0, v0);   /* fmac fr0,fr1,fr2 : t*(v1-v0) + v0, single rounding */
    }
}
