/* getEngineSpeedRateOfChange_0x429BC.c
 *
 * ROM: 60E0FC00 | Address: 0x429BC | Size: 0x32 (50) bytes per CSV range
 * 0x429BC..0x429EE.  Standalone prologue (sts.l pr,@-r15) @0x429BC, rts+delay
 * @0x429EA/0x429EC, epilogue lds.l pr @0x429E8.  Sub-calls: jsr 0x2068 (the
 * 1D u8-interp lookup) and jsr 0x23E4 (float max clamp).  The code/mov.l
 * literal pool @0x42A40..0x42A7C sits immediately after the rts, inside the
 * same 50-byte window.  The next function 0x429EE starts exactly at the CSV
 * end.  CSV range CORRECT, no phantom rows.
 *
 * ENTRY VERIFICATION: 0x429BC matches the CSV entry.  Valid entry: the ONLY
 * 32-bit ROM reference to 0x429BC is the function-pointer slot @0x14488 in
 * the engineControlCalculateTiming dispatcher (0x141FC) literal pool
 * (callgraph: 0x141FC -> 0x429BC getEngineSpeedRateOfChange).  Preceding
 * function ends rts+delay @0x42994; no fall-through.  CSV address IS the real
 * entry point.
 *
 * SEMANTICS: produces the engine speed rate-of-change sample that the
 * sibling filterEngineSpeedRateOfChange (0x429EE, verified) consumes as its
 * "current raw rate" (f32@FFFFC8F4).  Flow:
 *
 *   1A  1D u8 lookup (jsr 0x2068 -> 0x26B0 handler) over table 0x69BC8
 *       (X axis = f32@FFFFC8C928 engine RPM) returns an interpolated scalar
 *       fr0 (single precision, A=0.1/B=0.0 scale on a u8 y-byte over the RPM
 *       axis [1..6]; the held value is 25/25/25/25/25/25 so this is a flat
 *       2.5 scalar in practice).
 *   delta = f32@FFFFC8FC - f32@FFFFC8F8   (both raw RPM inputs, fsub)
 *   num   = lerp * delta                  (fm = single-precision)
 *   rate  = num / f32@FFFFC910            (fdiv; the normaliser)
 *   out   = fmax(rate, 0.0)               (jsr 233E4 = float max; SH-2
 *             fcmp/gt picks rate when rate > 0.0 else 0.0, incl. -0.0 and
 *             NaN -> 0.0)
 *   f32@FFFFC8F4 = out
 *
 * r0 on return = the u8 byte the 1D lookup read at its final index (the
 * upper neighbour when the fraction is non-zero).  For this table the y
 * bytes are all 25, so r0 is always 25.
 *
 * RAM r/w: reads C928(f32), C8F8(f32), C8FC(f32), C910(f32); writes C8F4(f32).
 *
 * VERIFIED against the SH-2 emulator (tools/sh2emu.py,
 * roms/stock/60E0FC00.bin) in c/tests/test_getEngineSpeedRateOfChange_0x429BC.py
 * - 0 mismatches over 5 seeds x 100000 iterations (byte-exact full post-call
 * RAM overlay + r0).
 */
#include <stdint.h>
#include <math.h>

/* ---- RAM globals (mov.w literals sign-extend to 0xFFFFxxxx) ---- */
#define RPM_C928 (*(volatile float*)0xFFFFC928)   /* f32 engine RPM (X input)   */
#define A_C8F8   (*(volatile float*)0xFFFFC8F8)   /* f32 raw RPM A              */
#define B_C8FC   (*(volatile float*)0xFFFFC8FC)   /* f32 raw RPM B              */
#define SCALE_C910 (*(volatile float*)0xFFFFC910) /* f32 normaliser (divisor)   */
#define OUT_C8F4 (*(volatile float*)0xFFFFC8F4)   /* f32 output rate-of-change  */

/* ---- ROM table data (verified against roms/stock/60E0FC00.bin) ---- */
/* 1D u8 table 0x69BC8: X axis [1..6] = RPM (v/v), y bytes, A/B 0.1/0.0. */
static const float   AX[6]   = {1.0f, 2.0f, 3.0f, 4.0f, 5.0f, 6.0f};
static const uint8_t Y[6]    = {25, 25, 25, 25, 25, 25};
static const float   SCL_A   = 0.1f;
static const float   SCL_B   = 0.0f;

/* ---- axis lookup (mirror of 0x2624) ---- */
static void lookup_index(const float* xp, int cnt, float x, int* idx, float* frac)
{
    int i = cnt - 1;
    *frac = 0.0f;
    if (!(xp[i] > x)) { *idx = cnt - 1; return; }
    if (cnt == 1) { *idx = 0; return; }
    i -= 1;
    for (;;) {
        if (!(xp[i] > x)) { *idx = i; break; }
        if (i == 0) { *idx = 0; return; }
        i -= 1;
    }
    *frac = (x - xp[*idx]) / (xp[*idx + 1] - xp[*idx]);
}

/* ---- 1D u8 interp (mirror of 0x2068/0x26B0) over table 0x69BC8 ---- */
static float lerp1d(float x)
{
    int   idx;
    float frac;
    lookup_index(AX, 6, x, &idx, &frac);
    float v = (float)Y[idx];
    if (frac != 0.0f)
        v = (float)((double)frac * ((double)Y[idx + 1] - (double)v) + (double)v);
    return (float)((double)v * (double)SCL_A + (double)SCL_B);
}

void getEngineSpeedRateOfChange_0x429BC(void)
{
    float rpm   = RPM_C928;
    float a     = A_C8F8;
    float b     = B_C8FC;
    float scale = SCALE_C910;

    float lerp = lerp1d(rpm);              /* 1D u8 lookup (jsr 0x2068)     */
    float delta = b - a;                   /* fsub                         */
    float num   = lerp * delta;             /* fmul                         */
    float rate  = num / scale;               /* fdiv                         */

    /* jsr 0x23E4 = float fmax(rate, 0.0); fcmp/gt keeps rate only when
       rate > 0.0, so <=0, -0.0 and NaN all resolve to 0.0 */
    float out = (rate > 0.0f) ? rate : 0.0f;

    OUT_C8F4 = out;
}