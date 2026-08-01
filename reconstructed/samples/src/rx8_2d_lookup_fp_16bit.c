/*
 * =============================================================================
 * rx8_2d_lookup_fp_16bit.c  —  1-D U16-CELL LOOKUP WITH FLOAT AXIS (FP 16-BIT)
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x20C4   (FILE OFFSET == ROM address: the emulator maps the
 *               binary 1:1, so this is both the file offset and the virtual
 *               address the test harness passes to sh2emu)
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_2d_lookup_fp_16bit.py
 *               (host-gcc vs tools/sh2emu.py over 20000 random + edge vectors,
 *               real u16 map descriptors from this ROM; 0 mismatches).
 * Lift (truth): c/2DLookup.c  (TwoDLookup_FP_16bit @ 0x20C4)
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * The RX-8 PCM's core calibration-table read primitive.  Given a "map
 * descriptor" (20-byte header + a float breakpoint array + a typed cell
 * array) and one scalar input x, it finds the surrounding breakpoints,
 * interpolates linearly and returns the result.  This is the *leaner* u16
 * sibling of the generic TwoDLookup @0x2068: it is hardwired to unsigned
 * 16-bit cells and applies NO scale/offset — the wrapper only ever reads
 * count(+0), axis(+4) and values(+8) from the descriptor (confirmed from
 * asm; the type/scale/offset fields are never touched) and returns the raw
 * interpolated cell value truncated to 16 bits.
 *
 * CALLING CONVENTION (NORMAL ABI AT THE ENTRY POINT)
 * --------------------------------------------------
 * 0x20C4 is a full wrapper entered through the standard C ABI:
 *     in:  r4 = Map descriptor pointer, fr4 = x (float input)
 *     out: r0 = uint16 result (ftrc-truncated, then zero-extended)
 * Inside, it calls the axis-search leaf 0x2624 (r0=count/r1=axis/fr0=x ->
 * r0=i/fr0=t — a NON-ABI leaf convention, see rx8_interpolate_u8_table.c)
 * and then jumps into the u16-cell interpolation leaf 0x26D0.  The harness
 * therefore uses a plain `cpu.call(0x20C4, r4=desc, fr={4: x})`.
 *
 * ALGORITHM / EDGE SEMANTICS (byte-for-byte from asm, cross-checked in the
 * lift and its c/tests/test_2DLookup_FP_16bit.py):
 *   find i,t :  axis[i] <= x < axis[i+1],  t = (x-axis[i])/(axis[i+1]-axis[i])
 *               x <  axis[0]    -> i=0,      t=0.0   (clamp low)
 *               x >= axis[last] -> i=last,   t=0.0   (clamp high; the ROM's
 *                 `!(x < axis[last])` test also clamps NaN high, as fcmp is
 *                 false for NaN)
 *   interp = cell[i] + t*(cell[i+1]-cell[i])     (u16 cells, no scale/offset)
 *   result = (uint16_t)(int32_t)interp           (ftrc: trunc toward zero,
 *                                                  then zero-extend 16 bits)
 *
 * ROUNDING
 * --------
 * The combine is ONE `fmac fr0,fr1,fr2` (leaf 0x26D0): fsub gives v1-v0 with
 * one rounding, then the fused multiply-add rounds t*(v1-v0)+v0 a SINGLE
 * time.  A plain `v0 + t*(v1-v0)` rounds twice and diverges from the ROM at
 * the few-ULP level over enough random t (confirmed empirically on the
 * sibling leaf).  `fmaf()` reproduces the single-rounding hardware exactly.
 *
 * The ROM's axis search is a BACKWARD linear scan (starts at axis[count-1],
 * walks down while axis[k] > x); for a strictly-ascending axis — which every
 * real calibration map satisfies, and which all the test descriptors are —
 * it yields the same (i,t) as the forward form used below (documented in the
 * lift's dataLookup @0x2624).
 * =============================================================================
 */
#include <stdint.h>
#include <math.h>

#include "rx8_samples.h"

/* Map descriptor (20 bytes, big-endian on the SH-2E).  Field offsets are the
 * ROM layout; the C struct layout below is the host compiler's and the two
 * need not coincide — the oracle constructs this struct explicitly. */
typedef struct {
    uint16_t     count;   /* +0  number of axis breakpoints                */
    uint8_t      type;    /* +2  cell encoding + scale/offset select (UNUSED
                           *     by this wrapper — hardwired u16)           */
    uint8_t      _pad;    /* +3  alignment                                 */
    const float *axis;    /* +4  ascending breakpoints (count floats)      */
    const void  *values;  /* +8  count u16 cells (big-endian)              */
    float        scale;   /* +12 result units scale  (NEVER read here)     */
    float        offset;  /* +16 result units offset (NEVER read here)     */
} Rx8Map1D;

/* 0x20C4 — 1-D lookup, float axis, u16 cells, no scale/offset (see header). */
uint16_t rx8_2d_lookup_fp_16bit(const Rx8Map1D *m, float x)
{
    int n = (int)m->count;
    int i;
    float t;
    const uint16_t *values = (const uint16_t *)m->values;

    /* Clamp-high test written as the ROM's `!(X < axis[last])` so NaN clamps
     * high too (fcmp is false for NaN) — matches 0x2624 exactly. */
    if (!(x < m->axis[n - 1])) {
        i = n - 1;
        t = 0.0f;
    } else if (x < m->axis[0]) {
        i = 0;
        t = 0.0f;
    } else {
        i = 0;
        while (i + 1 < n && !(m->axis[i] <= x && x < m->axis[i + 1])) {
            i++;
        }
        t = (x - m->axis[i]) / (m->axis[i + 1] - m->axis[i]);
    }

    /* Clamp-high (i == n-1) reaches the last cell with t == 0.0; cell[i+1]
     * is only ever read on the i < n-1 paths, exactly like the ROM leaf. */
    {
        const float v0 = (float)values[i];
        const float v1 = (float)values[i + 1 < n ? i + 1 : i];
        /* fsub (v1-v0) + fmac fr0,fr1,fr2 — single-rounding fused combine. */
        const float interp = fmaf(t, v1 - v0, v0);

        /* ftrc: truncate toward zero, then zero-extend 16 bits. */
        return (uint16_t)(int32_t)interp;
    }
}
