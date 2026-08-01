/*
 * =============================================================================
 * rx8_vis_intake_control.c  —  VARIABLE-INTAKE-SYSTEM (VIS) VALVE CONTROL TASK
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x23718  (304 bytes)
 * Status      : VERIFIED — behavioural equivalence to the ROM held by
 *               reconstructed/samples/tests/harness_vis_intake_control.py
 *               (host-gcc + mmap vs tools/sh2emu.py over edge + random
 *               vectors; all 14 f32 cells of the rolling table AND the u8
 *               index byte compared bit-exact, RAM side-effects included),
 *               in addition to the existing emulator test
 *               c/tests/test_vis_intake_control.py (10000 random, 0 fail).
 * Lift (truth): c/vis_intake_control.c  (same address; ground truth for this
 *               port — with TWO corrections found by re-verifying here, see
 *               "DISCREPANCIES vs THE LIFT" below).
 *
 * WHAT THIS IS
 * ------------
 * The periodic VIS valve-control task.  It picks one of four 2-D boost-vs-RPM
 * calibration maps (u16 cells, type 8) from three status bytes, bilinearly
 * looks the map up, clamps the result to [0, 84] and pushes it into a 14-cell
 * rolling-history table that downstream code consumes.
 *
 * ROM path (60E1D400.bin @0x23718, walk-through):
 *
 *   1. select the Map2D descriptor by the three selector bytes (checked in
 *      order, each `== 1`):
 *        RAM[0xFFFFB33C]==1 -> 0x6AC60 ; RAM[0xFFFFB33D]==1 -> 0x6AC7C
 *        RAM[0xFFFFB33E]==1 -> 0x6AC98 ; none -> 0x6ACB4
 *      (0x2372C-0x2376C)
 *   2. jsr 0x20DC  — the type-8 (u16-cell) 3-D map read:
 *        (ix,tx) = axis_search(axis_x, x)      ; (iy,ty) = axis_search(axis_y, y)
 *        v0 = u16_interp(row iy,     ix, tx)   ; v1 = u16_interp(row iy+1, ix, tx)
 *        interp = v0 + ty*(v1 - v0)  (skipped entirely when ty==0.0)
 *        result = scale*interp + offset        (scale = 1/327.68, offset = 0)
 *      (descriptor: count_x@+0, count_y@+2, axis_x@+4, axis_y@+8, values@+12,
 *       type@+16, scale@+20, offset@+24 — 28 bytes, c/3dLookup.c Map2D)
 *   3. jsr 0x2404  — clamp result to [0, ROM[0x73F6C]]  (ROM[0x73F6C] = 84.0)
 *   4. store the clamped value into table[0] (RAM[0xFFFFB408])
 *   5. index: ROM[0x73F68] (the "counter-mode" cal byte) is 1 in the stock
 *      bin, so table index = 0 unconditionally.  Only when it is 0 does the
 *      dead-path run: d = RAM[0xFFFFB5C8]*ROM[0x73F74]*0.125 - ROM[0x73F78]
 *      (= b5c8*2*0.125-2), clamp d >= 0, r = trunc(d/1 + 0.5) clamped to
 *      [0,255] (jsr 0x24D0), idx = min(r, 12)   <-- CORRECTED, see below
 *   6. RAM[0xFFFFB45C] = idx
 *   7. table[13] = table[idx]  (reads through the just-written index byte)
 *   8. rolling shift: table[12]=old table[11], ..., table[1]=old table[0]
 *      (loop @0x237E2 reads cell r4&0xFF and writes to --r12, 12 iterations)
 *
 * CALLING CONVENTION
 * ------------------
 * No ABI parameters and no return value: a `void rx8_vis_intake_control(void)`
 * task entry.  Its whole effect is on RAM (the 14 f32 cells @0xFFFFB408 and
 * the u8 index @0xFFFFB45C), so the equivalence harness compares RAM side
 * effects, not a return register.
 *
 * FP EXACTNESS
 * ------------
 * Every interpolation combine in the type-8 path is a genuine fused multiply-
 * add (`fmac` in the ROM) preceded by a separate single-rounded `fsub`:
 * `fmaf(t, f32(v1 - v0), v0)`.  A plain `v0 + t*(v1-v0)` rounds twice and
 * measurably mismatches the ROM at the few-ULP level (confirmed empirically).
 * The final map combine is `fmaf(scale, interp, offset)`.
 *
 * DISCREPANCIES vs THE LIFT (c/vis_intake_control.c) — both found by
 * re-verifying against the 60E1D400.bin bytes via tools/sh2emu.py and
 * corrected here:
 *   1. dead-path index clamp: the lift computes `idx = max(r, 12)`; the ROM
 *      computes `idx = min(r, 12)` (0x237B8 `cmp/gt r13,r2` is "Rn > Rm" with
 *      Rn = r2, so `bf/s` keeps r4 for r2 <= 12 and r4 = 12 otherwise).
 *      Not reachable in the stock bin (ROM[0x73F68] == 1), but wrong as a
 *      faithful lift; corrected here and verified over 5000 cmode=0 vectors.
 *   2. clamp NaN: the lift's clampf_rom() returns NaN for a NaN input; the
 *      ROM's fcmp/gt pair treats every comparison with NaN as false and
 *      therefore returns the LOW bound (0.0).  Corrected here; verified.
 * =============================================================================
 */
#include <stdint.h>
#include <math.h>

#include "rx8_samples.h"
#include "rx8_hw.h"

/* ---------------------------------------------------------------------------
 * RAM window for this task (on-chip RAM, 0xFFFF6000..0xFFFFDFFF).
 * ------------------------------------------------------------------------- */
#define RAM_X_ADDR      0xFFFFB5B8u   /* f32 x for the 2-D lookup (boost)    */
#define RAM_Y_ADDR      0xFFFFAA40u   /* f32 y for the 2-D lookup (rpm/other) */
#define RAM_SEL_C_ADDR  0xFFFFB33Cu   /* u8  table selector ==1 -> 0x6AC60   */
#define RAM_SEL_D_ADDR  0xFFFFB33Du   /* u8  table selector ==1 -> 0x6AC7C   */
#define RAM_SEL_E_ADDR  0xFFFFB33Eu   /* u8  table selector ==1 -> 0x6AC98   */
#define RAM_TABLE_ADDR  0xFFFFB408u   /* 14 f32 cells, rolling history       */
#define RAM_IDX_ADDR    0xFFFFB45Cu   /* u8  table index (0 in stock ROM)    */
#define RAM_DP_IN_ADDR  0xFFFFB5C8u   /* f32 dead-path input                 */

/* ---------------------------------------------------------------------------
 * Calibration constants the ROM reads (stock values; the oracle maps the ROM
 * pages so these pointers stay live on the host exactly as on the target).
 * ------------------------------------------------------------------------- */
#define ROM_CLAMP_HI    (*(const float  *)0x00073F6Cu)   /* 84.0            */
#define ROM_CMODE       (*(const uint8_t *)0x00073F68u)  /* 1 (stock)       */
#define ROM_DP_SCALE    (*(const float  *)0x00073F74u)   /* 2.0 (dead path) */
#define ROM_DP_OFFSET   (*(const float  *)0x00073F78u)   /* 2.0 (dead path) */

#define RAM_F32(addr)   (*(volatile float  *)(uintptr_t)(addr))
#define RAM_U8(addr)    (*(volatile uint8_t *)(uintptr_t)(addr))

/* ---------------------------------------------------------------------------
 * Map2D descriptor (c/3dLookup.c) — only the fields the type-8 path reads.
 * The ROM stores it big-endian with 32-bit *address* fields (28 bytes, the
 * SH-2E's layout); the host oracle translates those bytes to host-native at
 * the fixed addresses, so this struct is read exactly as the ROM lays it out.
 * The axis_x/axis_y/values fields are ROM addresses, cast to pointers only
 * at dereference time (matching the 32-bit pointers the SH-2E dereferences).
 * ------------------------------------------------------------------------- */
typedef struct {
    uint16_t          count_x;   /* +0  X-axis breakpoints                  */
    uint16_t          count_y;   /* +2  Y-axis breakpoints                  */
    uint32_t          axis_x;    /* +4  ROM address of the f32 axis         */
    uint32_t          axis_y;    /* +8  ROM address of the f32 axis         */
    uint32_t          values;    /* +12 ROM address of the u16 grid         */
    uint8_t           type;      /* +16 8 = u16 cells (the VIS maps)        */
    uint8_t           _pad[3];
    float             scale;     /* +20 result = scale*interp + offset      */
    float             offset;    /* +24                                     */
} rx8_map2d_t;

/* 1-D axis search (helper @0x2624, verified in c/2DLookup.c): `!(x < last)`
 * reproduces the ROM's fcmp/gt exactly, so NaN clamps high like the hardware. */
static void axis_search(const float *ax, int n, float x, int *pi, float *pt)
{
    if (!(x < ax[n - 1]))    { *pi = n - 1; *pt = 0.0f; }
    else if (x < ax[0])      { *pi = 0;     *pt = 0.0f; }
    else {
        int k = 0;
        while (k + 1 < n && !(ax[k] <= x && x < ax[k + 1])) k++;
        *pi = k;
        *pt = (x - ax[k]) / (ax[k + 1] - ax[k]);
    }
}

/* 1-D u16 interpolation leaf @0x26D0: fsub (single rounding) then one fmac
 * (single rounding); when t == 0.0 only the first cell is read (ROM bt/s). */
static float interp_u16_row(const uint16_t *row, int i, float t)
{
    float v0 = (float)row[i];
    if (t == 0.0f) return v0;
    float v1 = (float)row[i + 1];
    return fmaf(t, v1 - v0, v0);
}

/* 3-D map read @0x20DC, type-8 (u16) leaf @0x25F4: row iy gives v0, row iy+1
 * gives v1 (only read when ty != 0), blended by ty — then scale/offset.
 * (Model of c/3dLookup.c's verified type-8 path with the leaf's exact fp.) */
static float sh_3dlookup_type8(const rx8_map2d_t *m, float x, float y)
{
    const int cx = m->count_x, cy = m->count_y;
    const float *axis_x = (const float *)(uintptr_t)m->axis_x;
    const float *axis_y = (const float *)(uintptr_t)m->axis_y;
    const uint16_t *values = (const uint16_t *)(uintptr_t)m->values;
    int ix, iy;
    float tx, ty;

    axis_search(axis_x, cx, x, &ix, &tx);
    axis_search(axis_y, cy, y, &iy, &ty);

    const uint16_t *row0 = values + (uintptr_t)iy * cx;
    float v0 = interp_u16_row(row0, ix, tx);
    float interp;
    if (ty == 0.0f) {
        interp = v0;                              /* ROM skips row1 entirely */
    } else {
        const uint16_t *row1 = values + (uintptr_t)(iy + 1) * cx;
        float v1 = interp_u16_row(row1, ix, tx);
        interp = fmaf(ty, v1 - v0, v0);
    }
    return fmaf(m->scale, interp, m->offset);
}

/* Clamp @0x2404.  NOTE: the ROM compares with `fcmp/gt` only, so a NaN input
 * makes both tests false and the result is the LOW bound (not NaN). */
static float clampf_rom(float v, float lo, float hi)
{
    if (v > lo) return (hi > v) ? v : hi;
    return lo;
}

/* float->index @0x24D0: trunc((v - lower)/range + 0.5), clamped to [0,255].
 * (ftrc = truncation toward zero; the upper bound only matters when the
 * caller does not re-clamp.) */
static uint8_t float_to_index_rom(float v, float range, float lower)
{
    int32_t r = (int32_t)(((v - lower) / range) + 0.5f);
    if (r < 0)    r = 0;
    if (r > 255)  r = 255;
    return (uint8_t)r;
}

/* Select the 2-D map descriptor from the three selector bytes (checked in
 * order, exactly like 0x2372C-0x2376C). */
static const rx8_map2d_t *vis_desc(void)
{
    if (RAM_U8(RAM_SEL_C_ADDR) == 1u) return (const rx8_map2d_t *)0x6AC60u;
    if (RAM_U8(RAM_SEL_D_ADDR) == 1u) return (const rx8_map2d_t *)0x6AC7Cu;
    if (RAM_U8(RAM_SEL_E_ADDR) == 1u) return (const rx8_map2d_t *)0x6AC98u;
    return (const rx8_map2d_t *)0x6ACB4u;
}

/* 0x23718 — pick a boost-vs-RPM map, clamp, push into the rolling table. */
void rx8_vis_intake_control(void)
{
    float x = RAM_F32(RAM_X_ADDR);
    float y = RAM_F32(RAM_Y_ADDR);
    volatile float *t = (volatile float *)(uintptr_t)RAM_TABLE_ADDR;

    /* 1. table lookup + clamp to [0, 84]. */
    float v = sh_3dlookup_type8(vis_desc(), x, y);
    v = clampf_rom(v, 0.0f, ROM_CLAMP_HI);
    t[0] = v;

    /* 2. table index; stock cal byte ROM[0x73F68] == 1 -> idx 0.  The dead
     *    path below (ROM[0x73F68] == 0) clamps to min(r, 12) — see header. */
    uint8_t idx;
    if (ROM_CMODE != 0u) {
        idx = 0u;
    } else {
        float d = RAM_F32(RAM_DP_IN_ADDR) * ROM_DP_SCALE * 0.125f
                  - ROM_DP_OFFSET;
        if (0.0f > d) d = 0.0f;                    /* fcmp/gt fr3(0),fr4(d)   */
        uint8_t r = float_to_index_rom(d, 1.0f, 0.0f);
        idx = (uint8_t)(r > 12u ? 12u : r);        /* min(r,12): cmp/gt+bf/s  */
    }
    RAM_U8(RAM_IDX_ADDR) = idx;

    /* 3. table[13] = table[idx]  (reads the just-written index byte). */
    t[13] = t[idx];

    /* 4. rolling shift: cell k <- old cell k-1 for k = 12..1 (loop @0x237E2). */
    for (int k = 12; k >= 1; k--)
        t[k] = t[k - 1];
}
