/* throttleLiftoffRelated_0x425A2.c
 *
 * ROM: 60E0FC00 | Address: 0x425A2 | Size: 0x120 (288) bytes per CSV range
 * 0x425A2..0x426C2.  Standalone prologue (mov.l r14/r13/r12/r11/r10,@-r15 +
 * fmov fr15/fr14) @0x425A2, rts+delay @0x426BE/0x426C0, epilogue pops
 * @0x426B0..0x426C0.  Sub-calls: jsr 0x2500 (fma state, 5 instr), jsr 0x20DC
 * (the 2D-interp dispatcher), jsr 0x2068 (the 1D u8-interp lookup).  The
 * code/mov.w/mov.l literal pool @0x4263E..0x4267A sits inside the range.
 * The next function 0x426C4 starts exactly at the CSV end.  CSV range
 * CORRECT, no phantom rows.
 *
 * ENTRY VERIFICATION: 0x425A2 matches the CSV entry.  Valid entry: the ONLY
 * 32-bit ROM reference to 0x425A2 is the function-pointer slot @0x1446C in
 * the engineControlCalculateTiming dispatcher (0x141FC) literal pool
 * (callgraph: 0x141FC -> 0x425A2 throttleLiftoffRelated).  The preceding
 * function ends before 0x425A2 (its rts+delay is @0x42570/0x42572); no
 * fall-through.  CSV address IS the real entry point.
 *
 * SEMANTICS: per-cycle reaction to backing off the throttle.  It derives an
 * integer "liftoff state" (0..3) from the throttle-rate signal f32@FFFFC934
 * and a hard override byte @FFFFAAC6, pushes a copy of the engine RPM
 * f32@FFFFC928 to f32@FFFFC920 when a mode byte @FFFFC93E equals 2 (else
 * clears it), then writes two look-up results:
 *   f32@FFFFC918 = a 2D-interp over one of four throttle tables
 *                  (0x69BF0/0x69C0C/0x69C28/0x69C44, rowwise state 0..3, grid
 *                  u16 x 0.01), X axis = f32@FFFFC920, Y axis = state (float
 *                  int 0..3);
 *   f32@FFFFC91C = a 1D u8-interp over table 0x69BDC (X axis = f32@FFFFC928).
 * The four 2D tables are selected by two enable bytes @FFFFC94A / @FFFFC94D,
 * the RPM latch by @FFFFC93E (== 2); the state by AAC6 + threshold logic on
 * C934 (5.0 / 6.5 f32 mova literals @0x7A1AC / 0x7A1B0).
 *
 * State (mirrors the emulator byte-exactly):
 *   AAC6 == 1          -> state 0   (hard override clears)
 *   else if C934 > 5.0 -> state 2 if 6.5 > C934 else state 3
 *   else               -> state 1
 * (fcmp/gt FRn>FRm, so a NaN C934 falls through to state 1; 5.0<=C934 is in
 * the else branch.)
 *
 * Interpolation helpers (single precision, SH-2 rounding on every op):
 *   lookup_index(xp, x)  -> (idx, frac); x below the first axis point clamps
 *     to (0,0.0); above the last -> (cnt-1, 0.0).  frac =
 *     (x-xp[idx])/(xp[idx+1]-xp[idx]).
 *   2D: stride = cnt1*2; X-lerp along row iy over the u16 grid (only reads
 *     the idx+1 cell when frac != 0); then if the Y frac is non-zero X-lerp
 *     along row iy+1 and blend by the Y frac; out = (val*A + B).  All four
 *     tables share the same 7x4 grid data (verified).
 *   1D u8: bin by the axis, lerp between the two u8 y values (idx+1 read
 *     only when frac != 0); out = (val*A + B).
 *
 * RAM r/w: reads C934(f32), C94A(u8), C94D(u8), C928(f32), C93E(u8),
 * AAC6(u8); writes C93D(u8), C920(f32), C918(f32), C91C(f32).
 *
 * VERIFIED against the SH-2 emulator (tools/sh2emu.py,
 * roms/stock/60E0FC00.bin) in c/tests/test_throttleLiftoffRelated_0x425A2.py
 * - 0 mismatches over 5 seeds x 100000 iterations (byte-exact full post-call
 * RAM overlay + r0).
 */
#include <stdint.h>
#include <math.h>

/* ---- RAM globals (mov.w literals sign-extend to 0xFFFFxxxx) ---- */
#define RATE_C934 (*(volatile float*)0xFFFFC934)   /* f32 throttle rate (input) */
#define RPM_C928  (*(volatile float*)0xFFFFC928)   /* f32 engine RPM            */
#define EA_C94A   (*(volatile uint8_t*)0xFFFFC94A) /* u8 2D-table enable A       */
#define ED_C94D   (*(volatile uint8_t*)0xFFFFC94D) /* u8 2D-table enable B       */
#define AAC6      (*(volatile uint8_t*)0xFFFFAAC6) /* u8 hard override (state0)  */
#define ENA_C93E  (*(volatile uint8_t*)0xFFFFC93E) /* u8 RPM-copy enable (==2)   */
#define STATE_C93D (*(volatile uint8_t*)0xFFFFC93D)/* u8 liftoff state (output)  */
#define F920      (*(volatile float*)0xFFFFC920)   /* f32 RPM-X for 2D interp    */
#define F918      (*(volatile float*)0xFFFFC918)   /* f32 2D interp result       */
#define F91C      (*(volatile float*)0xFFFFC91C)   /* f32 1D interp result       */

/* ---- ROM table data (verified against roms/stock/60E0FC00.bin) ---- */
/* 1D u8 table 0x69BDC: X axis [1..6], y bytes, A/B scale 0.1/0.0. */
static const float   AX1D[6] = {1.0f, 2.0f, 3.0f, 4.0f, 5.0f, 6.0f};
static const uint8_t AY1D[6] = {3, 9, 6, 4, 4, 4};
static const float   SCL1D_A = 0.1f;
static const float   SCL1D_B = 0.0f;

/* 2D tables.  All four (0x69BF0/0x69C0C/0x69C28/0x69C44) share the same
 * 7x4 u16 grid (X axis [0..6], Y axis [0..3] = state rows, A=0.01/B=0.0). */
static const float    AX2D[7] = {0.0f, 1.0f, 2.0f, 3.0f, 4.0f, 5.0f, 6.0f};
static const float    AY2D[4] = {0.0f, 1.0f, 2.0f, 3.0f};
static const uint16_t G2D[4][7] = {
    {5000, 5000, 5000, 5000, 5000, 5000, 5000},
    {5000, 5000, 5000, 5000, 5000, 5000, 5000},
    {  10,   30,   30,   15,   12,    5,    5},
    {  10,   30,   30,   15,   12,    5,    5},
};
static const float SCL2D_A = 0.01f;
static const float SCL2D_B = 0.0f;

/* ---- axis lookup (mirror of 0x2624): returns idx + frac in single fp ---- */
static void lookup_index(const float* xp, int cnt, float x, int* idx, float* frac)
{
    int i = cnt - 1;
    *frac = 0.0f;
    if (!(xp[i] > x)) { *idx = cnt - 1; return; }      /* above last point   */
    if (cnt == 1) { *idx = 0; return; }
    i -= 1;
    for (;;) {
        if (!(xp[i] > x)) { *idx = i; break; }         /* xp[i] <= x          */
        if (i == 0) { *idx = 0; return; }              /* below first point   */
        i -= 1;
    }
    *frac = (x - xp[*idx]) / (xp[*idx + 1] - xp[*idx]);
}

/* ---- 2D u16 grid bilinear interp (mirror of 0x25F4/0x20DC) ---- */
/* Each lerp/lookup op mirrors SH-2 "op + fused fmac" = single rounding:
   fsub   -> d = (float)(b - a)
   fmac   -> acc = (float)((double)frac * (double)d + (double)v)   */
static float interp_u16(const uint16_t* row, int ix, float fx)
{
    float v = (float)row[ix];
    if (fx != 0.0f)
    {
        float d = (float)((int)row[ix + 1] - (int)row[ix]);       /* fsub   */
        v = (float)((double)fx * (double)d + (double)v);         /* fmac   */
    }
    return v;
}

static float interp2d(float x, float y)
{
    int   ix, iy;
    float fx, fy;
    lookup_index(AX2D, 7, x, &ix, &fx);
    lookup_index(AY2D, 4, y, &iy, &fy);

    /* X-lerp along row iy (idx+1 read only when fx != 0) */
    float v1 = interp_u16(G2D[iy], ix, fx);

    if (fy == 0.0f)
        return (float)((double)v1 * (double)SCL2D_A + (double)SCL2D_B);

    /* X-lerp along row iy+1, then blend by the Y fraction (fused) */
    float v2 = interp_u16(G2D[iy + 1], ix, fx);
    float d = (float)(v2 - v1);                                /* fsub   */
    float val = (float)((double)fy * (double)d + (double)v1);   /* fmac   */
    return (float)((double)val * (double)SCL2D_A + (double)SCL2D_B);
}

/* ---- 1D u8 interp (mirror of 0x2068/0x26B0) over table 0x69BDC ---- */
static float lerp1d(float x)
{
    int   idx;
    float frac;
    lookup_index(AX1D, 6, x, &idx, &frac);
    float v = (float)AY1D[idx];
    if (frac != 0.0f)
    {
        float d = (float)((int)AY1D[idx + 1] - (int)v);        /* fsub   */
        v = (float)((double)frac * (double)d + (double)v);     /* fmac   */
    }
    return (float)((double)v * (double)SCL1D_A + (double)SCL1D_B);
}

void throttleLiftoffRelated_0x425A2(void)
{
    float   rrate = RATE_C934;
    uint8_t ovr   = AAC6;
    uint8_t ena   = ENA_C93E;
    float   rpm   = RPM_C928;
    int     state;

    /* ---- state (u8@C93D): override or banded on rrate ---- */
    if (ovr == 1)
        state = 0;
    else if (rrate > 5.0f)
        state = (6.5f > rrate) ? 2 : 3;
    else
        state = 1;

    STATE_C93D = (uint8_t)state;

    /* ---- RPM-X copy / clear (mov.l @C920 with the C93E==2 check) ---- */
    if (ena == 2)
        F920 = rpm;
    else
        F920 = 0.0f;

    /* ---- 2D interp: X = f32@C920, Y = state (float 0..3).  The throttle
       map grid is identical across all four enable-bank tables. ---- */
    F918 = interp2d(F920, (float)state);

    /* ---- 1D u8 interp over 0x69BDC, X = f32(C928) ---- */
    F91C = lerp1d(rpm);
}