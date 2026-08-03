/* calc_secondary_o2_trim_1321C.c
 *
 * ROM: 60E1D400  |  Address: 0x1321C  |  Size: 0x187 bytes (0x1321C..0x133A2,
 *                 rts @0x133A0; literal pools @0x13288..0x132BA and
 *                 @0x133A4..0x133F6 interleaved).
 *
 * Secondary O2 sensor trim calculator — closed-loop fuel-trim correction
 * derived from the secondary (rear) lambda sensor.  The body splits into two
 * stages: (1) a recursive "filter" stage that updates two persistent trim
 * words, and (2) a mode-select stage that copies one of three calibration-map
 * result pairs (or the filter words) into the two output trim words.
 *
 * SIGNATURE:  void calc_secondary_o2_trim_1321C(void)
 *   - no arguments, no meaningful return value (r0 not set on the exit path).
 *
 * STAGE 1 — filter update (0x13230..0x132DA).  RAM words:
 *   0xFFFFA6C4  f32  trim filter word A (in/out)
 *   0xFFFFA6C8  f32  trim filter word B (in/out)
 *   control:
 *   0xFFFFA6DF  u8   latch  (last-stage control snapshot, in/out)
 *   0xFFFFA428  u8   mode-0 flag (bootstrap/reset request)
 *   0xFFFFAADA  u8   gain-select flag (==1 selects gain pair @0x6F70C/0x6F710
 *                    else @0x6F714/0x6F718)
 *
 *   if (A6DF == 0 && A428 == 1):          (reset / first-sample path)
 *       A6C4 = TwoDLookup(0x6A000, f32@0xFFFFAA1C)
 *       A6C8 = TwoDLookup(0x6A014, f32@0xFFFFAA1C)
 *   else:                                  (recursive path)
 *       A6C4 = min(A6C4 + gainA, 0)       gainA = f32 ROM @0x6F70C / 0x6F714
 *       A6C8 = min(A6C8 + gainB, 0)       gainB = f32 ROM @0x6F710 / 0x6F718
 *   (0x23F4 = minValue(fr4, fr5): result = (0 > v) ? v : 0, i.e. negative
 *   values pass through and positive values are clamped to zero; NaN -> 0.)
 *   Both ROM gain constants are 0.0 in this binary, so the recursive path just
 *   clips the two filter words to <= 0.
 *
 * STAGE 2 — map / mode select (0x132DC..0x1337E).  Outputs:
 *   0xFFFFA6BC  f32  trim output A
 *   0xFFFFA6C0  f32  trim output B
 *   inputs (f32): 0xFFFFAA10 (x), 0xFFFFAD8C (y1), 0xFFFFC12C (y2)
 *   mode flags (u8): 0xFFFFA6B9, 0xFFFFA6B7, 0xFFFFA6B8
 *
 *   if (A6B9 == 1):       3-D maps  (all 1x1 -> exactly 0.0 in this ROM)
 *       A6BC = 3DL(0x6A028, x, y2) + 3DL(0x6A044, y1, y2)
 *       A6C0 = 3DL(0x6A060, x, y2) + 3DL(0x6A07C, y1, y2)
 *   else if (A6B7 == 1):  1-D maps  (the two 12-point secondary-O2 tables)
 *       A6BC = 1DL(0x69F60, x) + 1DL(0x69F74, y1)
 *       A6C0 = 1DL(0x69F88, x) + 1DL(0x69F9C, y1)
 *   else if (A6B8 == 1):  1-D maps  (all 1-point -> exactly 0.0)
 *       A6BC = 1DL(0x69FB0, x) + 1DL(0x69FC4, y1)
 *       A6C0 = 1DL(0x69FD8, x) + 1DL(0x69FEC, y1)
 *   else:                 pass-through
 *       A6BC = A6C4;  A6C0 = A6C8
 *
 *   finally (0x13388): A6DF = A428   (control latch, every call)
 *
 * CALIBRATION TABLES (ROM, type-4 = u8 cells, scale=0.5 offset=-50):
 *   0x69F60  count=12  axis @0x6F75C,  vals @0x6F78C  (secondary-O2 map A:
 *            breakpoints -15..40, values 100/160 -> trim 0% / +30%)
 *   0x69F88  count=12  axis @0x6F7A0,  vals @0x6F7D0  (secondary-O2 map B:
 *            breakpoints -15..40, values 100/110 -> trim 0% / +5%)
 *   all other maps are 1-point (axis -30.0, value u8 = 0x64 -> trim exactly
 *   0.0): 0x6A000, 0x6A014, 0x69F74, 0x69F9C, 0x69FB0, 0x69FC4, 0x69FD8,
 *   0x69FEC (1-D) and 0x6A028, 0x6A044, 0x6A060, 0x6A07C (2-D, 1x1).
 *
 * SEMANTICS (human):
 *   Recursive secondary-O2 trim accumulator: every call the two persistent
 *   trim words are nudged by a calibration gain and clipped at zero on the
 *   positive side (a leaky accumulator that only ever lowers/carries a
 *   negative trim; the stock gains are 0 so the words simply clip to <= 0).  A
 *   one-shot bootstrap path (control A428==1 with the latch A6DF clear)
 *   instead initializes both words from the calibration maps, then the stage-2
 *   mode selector publishes either the map-derived pair (A6B7 path = the real
 *   O2-voltage->trim maps; A6B9/A6B8 = zeroed/disabled) or the accumulated
 *   filter words (A6B7 clear) as the active secondary trim pair A6BC/A6C0.
 *   A6DF latches the current A428 value so the bootstrap runs exactly once
 *   (the following calls see A6DF != 0 and take the recursive path).
 *
 * Track A: verified against the emulated ROM bytes (tools/sh2emu.py) over a
 * structured mode sweep + 20000 seeded random vectors, 0 mismatches.  Test:
 * c/tests/test_calc_secondary_o2_trim_1321C.py.
 */
#include <stdint.h>
#include <math.h>

#define RAM8(addr)       (*(volatile uint8_t *)(uintptr_t)(addr))
#define RAMF32(addr)     (*(volatile float   *)(uintptr_t)(addr))
#define ROM8(addr)       (*(const  uint8_t *)(uintptr_t)(addr))
#define ROMU16(addr)     (*(const  uint16_t*)(uintptr_t)(addr))
#define ROMU32(addr)     (*(const  uint32_t*)(uintptr_t)(addr))
#define ROMF32(addr)     (*(const  float   *)(uintptr_t)(addr))

/* ---- RAM cells ---------------------------------------------------------- */
#define RAM_CTL_LATCH     RAM8(0xFFFFA6DF)   /* control latch (in/out) */
#define RAM_CTL_RESET     RAM8(0xFFFFA428)   /* bootstrap/mode-0 flag  */
#define RAM_CTL_GAINSEL   RAM8(0xFFFFAADA)   /* gain-pair selector     */
#define RAM_FILT_A        RAMF32(0xFFFFA6C4) /* trim filter word A     */
#define RAM_FILT_B        RAMF32(0xFFFFA6C8) /* trim filter word B     */
#define RAM_OUT_A         RAMF32(0xFFFFA6BC) /* trim output A          */
#define RAM_OUT_B         RAMF32(0xFFFFA6C0) /* trim output B          */
#define RAM_IN_X          RAMF32(0xFFFFAA10) /* primary input           */
#define RAM_IN_Y1         RAMF32(0xFFFFAD8C) /* secondary input #1      */
#define RAM_IN_Y2         RAMF32(0xFFFFC12C) /* secondary input #2      */
#define RAM_IN_X0         RAMF32(0xFFFFAA1C) /* bootstrap-map input     */
#define RAM_MODE_B9       RAM8(0xFFFFA6B9)   /* 3-D map mode flag       */
#define RAM_MODE_B7       RAM8(0xFFFFA6B7)   /* 1-D map mode flag       */
#define RAM_MODE_B8       RAM8(0xFFFFA6B8)   /* 1-D zero-map mode flag  */

/* ---- calibration (ROM) -------------------------------------------------- */
#define CAL_GAIN_A1       ROMF32(0x6F70C)    /* = 0.0 */
#define CAL_GAIN_B1       ROMF32(0x6F710)    /* = 0.0 */
#define CAL_GAIN_A2       ROMF32(0x6F714)    /* = 0.0 */
#define CAL_GAIN_B2       ROMF32(0x6F718)    /* = 0.0 */

/* --------------------------------------------------------------------------
 * 1-D calibration read — ROM primitive TwoDLookup @0x2068, type-4 (u8 cells)
 * with scale*interp+offset (scale=0.5, offset=-50).  Same math as the
 * verified c/2DLookup.c: axis search + u8 cell + fmac single-rounding
 * combine; the typed leaf @0x26B0 computes  v0 + t*(v1-v0) with fmaf, and the
 * wrapper computes  offset + scale*interp with a second fmaf.
 * ------------------------------------------------------------------------ */
static float lookup1d(const void *desc_ptr, float x)
{
    const uint8_t *d = (const uint8_t *)desc_ptr;
    int    n     = ((d[0] << 8) | d[1]);
    const float *axis  = (const float *)(uintptr_t)(((uint32_t)d[4] << 24) |
                                                   ((uint32_t)d[5] << 16) |
                                                   ((uint32_t)d[6] << 8) |
                                                    (uint32_t)d[7]);
    const uint8_t *vals = (const uint8_t *)(uintptr_t)(((uint32_t)d[8] << 24) |
                                                   ((uint32_t)d[9] << 16) |
                                                   ((uint32_t)d[10] << 8) |
                                                    (uint32_t)d[11]);
    float scale = *(const float *)(const void *)(d + 12);
    float off   = *(const float *)(const void *)(d + 16);
    int i;
    float t, v0, v1, interp;

    if (!(x < axis[n - 1]))        { i = n - 1; t = 0.0f; }
    else if (x < axis[0])          { i = 0;     t = 0.0f; }
    else {
        i = 0;
        while (i + 1 < n && !(axis[i] <= x && x < axis[i + 1])) i++;
        t = (x - axis[i]) / (axis[i + 1] - axis[i]);
    }
    v0 = (float)vals[i];
    v1 = (float)vals[i + 1 < n ? i + 1 : i];
    interp = fmaf(t, v1 - v0, v0);          /* leaf 0x26B0: fmac single round */
    return fmaf(scale, interp, off);        /* wrapper: off + scale*interp    */
}

/* --------------------------------------------------------------------------
 * 2-D calibration read — ROM primitive ThreeDLookup @0x20DC (type-4 u8 cells).
 * Same math as the verified c/3dLookup.c (both axis searches + u8 bilinear +
 * scale/offset).  All four maps used here are 1x1, so the result is exactly
 * 0.0, but the general path is kept for completeness.
 * ------------------------------------------------------------------------ */
static float lookup2d(const void *desc_ptr, float x, float y)
{
    const uint8_t *d = (const uint8_t *)desc_ptr;
    int cx = ((d[0] << 8) | d[1]);
    int cy = ((d[2] << 8) | d[3]);
    const float *axx = (const float *)(uintptr_t)(((uint32_t)d[4] << 24) |
                                                  ((uint32_t)d[5] << 16) |
                                                  ((uint32_t)d[6] << 8) |
                                                   (uint32_t)d[7]);
    const float *axy = (const float *)(uintptr_t)(((uint32_t)d[8] << 24) |
                                                  ((uint32_t)d[9] << 16) |
                                                  ((uint32_t)d[10] << 8) |
                                                   (uint32_t)d[11]);
    const uint8_t *vals = (const uint8_t *)(uintptr_t)(((uint32_t)d[12] << 24) |
                                                   ((uint32_t)d[13] << 16) |
                                                   ((uint32_t)d[14] << 8) |
                                                    (uint32_t)d[15]);
    float scale = *(const float *)(const void *)(d + 20);
    float off   = *(const float *)(const void *)(d + 24);
    int ix, iy, ix1, iy1;
    float tx, ty, c00, c10, c01, c11, row0, row1, interp;

    if (!(x < axx[cx - 1]))        { ix = cx - 1; tx = 0.0f; }
    else if (x < axx[0])           { ix = 0;     tx = 0.0f; }
    else {
        ix = 0;
        while (ix + 1 < cx && !(axx[ix] <= x && x < axx[ix + 1])) ix++;
        tx = (x - axx[ix]) / (axx[ix + 1] - axx[ix]);
    }
    if (!(y < axy[cy - 1]))        { iy = cy - 1; ty = 0.0f; }
    else if (y < axy[0])           { iy = 0;     ty = 0.0f; }
    else {
        iy = 0;
        while (iy + 1 < cy && !(axy[iy] <= y && y < axy[iy + 1])) iy++;
        ty = (y - axy[iy]) / (axy[iy + 1] - axy[iy]);
    }
    ix1 = ix + 1 < cx ? ix + 1 : ix;
    iy1 = iy + 1 < cy ? iy + 1 : iy;
    c00 = (float)vals[iy  * cx + ix];
    c10 = (float)vals[iy  * cx + ix1];
    c01 = (float)vals[iy1 * cx + ix];
    c11 = (float)vals[iy1 * cx + ix1];
    row0 = fmaf(tx, c10 - c00, c00);
    row1 = fmaf(tx, c11 - c01, c01);
    interp = fmaf(ty, row1 - row0, row0);
    return fmaf(scale, interp, off);
}

void calc_secondary_o2_trim_1321C(void)
{
    float filt_a = RAM_FILT_A;          /* fr4 = f32@A6C4 (delay-slot load) */
    float filt_b = RAM_FILT_B;
    float in_x   = RAM_IN_X;            /* fr15 */
    float in_y1  = RAM_IN_Y1;           /* fr14 */
    float in_y2  = RAM_IN_Y2;           /* fr13 */
    float in_x0  = RAM_IN_X0;           /* fr12 */
    uint8_t ctl  = RAM_CTL_RESET;       /* r11 = u8@A428 */
    uint8_t latch= RAM_CTL_LATCH;       /* u8@A6DF */
    float out_a, out_b;

    /* ---- stage 1: filter update ---------------------------------------- */
    if (latch == 0 && ctl == 1) {
        /* bootstrap: initialize both words from the 1-point maps (== 0.0) */
        filt_a = lookup1d((const void *)0x6A000, in_x0);
        filt_b = lookup1d((const void *)0x6A014, in_x0);
    } else {
        /* recursive leaky-accumulator path (gains are 0.0 in this ROM) */
        float ga = (RAM_CTL_GAINSEL == 1) ? CAL_GAIN_A1 : CAL_GAIN_A2;
        float gb = (RAM_CTL_GAINSEL == 1) ? CAL_GAIN_B1 : CAL_GAIN_B2;
        float va = ga + filt_a;         /* fadd fr3,fr4 (gain + old) */
        float vb = gb + filt_b;         /* fadd fr5,fr12 (gain + old) */
        /* 0x23F4 minValue: result = (0.0 > v) ? v : 0.0  (NaN clamps to 0) */
        filt_a = (0.0f > va) ? va : 0.0f;
        filt_b = (0.0f > vb) ? vb : 0.0f;
    }

    /* ---- stage 2: map / mode select ------------------------------------ */
    if (RAM_MODE_B9 == 1) {
        out_a = lookup2d((const void *)0x6A028, in_x, in_y2)
              + lookup2d((const void *)0x6A044, in_y1, in_y2);
        out_b = lookup2d((const void *)0x6A060, in_x, in_y2)
              + lookup2d((const void *)0x6A07C, in_y1, in_y2);
    } else if (RAM_MODE_B7 == 1) {
        out_a = lookup1d((const void *)0x69F60, in_x)
              + lookup1d((const void *)0x69F74, in_y1);
        out_b = lookup1d((const void *)0x69F88, in_x)
              + lookup1d((const void *)0x69F9C, in_y1);
    } else if (RAM_MODE_B8 == 1) {
        out_a = lookup1d((const void *)0x69FB0, in_x)
              + lookup1d((const void *)0x69FC4, in_y1);
        out_b = lookup1d((const void *)0x69FD8, in_x)
              + lookup1d((const void *)0x69FEC, in_y1);
    } else {
        out_a = filt_a;                 /* 0x13380: copy filter words */
        out_b = filt_b;                 /* 0x13384 */
    }

    RAM_OUT_A = out_a;                  /* fmov.s frX,@r13 */
    RAM_OUT_B = out_b;                  /* fmov.s frX,@r12 */
    RAM_CTL_LATCH = ctl;                /* 0x13388: A6DF = A428 (r11) */
}
