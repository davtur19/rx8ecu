/* knock_control_calc_44824.c
 *
 * ROM: 60E1D400 | Address: 0x44824 | Size: 0x6A (106) bytes, 38 instrs.
 *
 * Entry  : 0x44824 — matches the symbols CSV row.  Valid standalone prologue
 *           (mov.l r14,@-r15 ; fmov.s fr15,@-r15 ; mov.w ... ; sts.l pr,@-r15),
 *           rts+delay at 0x4488A/0x4488C.  The ONLY ROM reference to 0x44824 is
 *           the function-pointer slot @0x1483C inside the dispatcher
 *           engineControlCalculateTiming (0x14584) literal pool — dispatch
 *           slot 61 of Phase 2 (c/engineControlCalculateTiming.c line 261).
 *           No code branches into the body from mid-function, so the CSV
 *           address IS the real entry point.
 * Range  : 0x44824 .. 0x4488E
 *
 * Literal pool (own + interleaved): 0x44926=0xCA10, 0x44928=0xCAB4,
 *           0x4492A=0xCAAF, 0x4492C=0xAA10, 0x4492E=0xB5B8, 0x44930=0xCA18,
 *           0x44932=0xCA14 (sign-extended RAM addrs via mov.w),
 *           0x44944=0x7B3DB, 0x44948=0x7B42C, 0x4494C=0x7B430,
 *           0x44950->0x2404, 0x44954=0x6BE74, 0x44958->0x2068, 0x4495C->0x23F4.
 *
 * Semantics (instruction-for-instruction, see disasm):
 *   fr15 = 0.0f (fldi0 in the first delay slot — runs on every path)
 *   if (u8@0xFFFFCAB4 != 1)                      goto store0;
 *   if (!(u8@0xFFFFCAAF > u8@0x0007B3DB))        goto store0;   ; cmp/hi (u)
 *   v  = (f32@0xFFFFAA10 - f32@0x0007B42C) * f32@0x0007B430;   ; fsub,fmul
 *   c  = clamp_0x2404(v, 0.0f, 1.0f);            ; fr5=0.0 (fldi0), fr6=1.0
 *   lk = two_d_lookup_0x2068(desc@0x0006BE74, f32@0xFFFFB5B8);
 *   m  = min_0x23F4(f32@0xFFFFCA18, lk);
 *   f32@0xFFFFCA10 = m * c;                      ; fmul fr15,fr4
 *   goto epilogue;
 * store0:
 *   f32@0xFFFFCA10 = fr15;                       ; 0.0
 * epilogue:
 *   f32@0xFFFFCA14 = f32@0xFFFFCA10;             ; reload, copy
 *
 *   TwoDLookup descriptor @0x0006BE74 (c/2DLookup.c layout): count=11,
 *   type=4 (u8 cells), axis 500..5500 step 500 @0x7B4AC, cells @0x7B4D8,
 *   scale=0.5, offset=0.0 — a knock/retard 1-D map on f32@0xFFFFB5B8.
 *
 * VERIFIED against the SH-2 emulator (tools/sh2emu.py) in
 * c/tests/test_knock_control_calc_44824.py — 0 mismatches over 5 seeds
 * x default iterations (full post-call RAM overlay, byte-exact).
 */

#include <stdint.h>

/* 0x2404 — FP clamp (verified leaf, pure FPU): returns fr4 clamped into
 *   [fr5, fr6]:  (fr4 > fr5) ? (fr6 > fr4 ? fr4 : fr6) : fr5. */
extern float clamp_0x2404(float v, float lo, float hi);

/* 0x2068 — TwoDLookup (verified primitive, see c/2DLookup.c).
 *   r4 = descriptor ptr, fr4 = x.  returns fr0 = piecewise-linear interp of
 *   the typed cells, scale*interp+offset applied for non-zero cell type. */
extern float two_d_lookup_0x2068(uint32_t desc, float x);

/* 0x23F4 — FP min (verified leaf, pure FPU): returns fr5 > fr4 ? fr4 : fr5. */
extern float min_0x23F4(float a, float b);

/* ---- RAM globals (16-bit literals sign-extend to 0xFFFFxxxx) ---- */
#define GATE_FLAG   (*(volatile uint8_t  *)0xFFFFCAB4)  /* enable gate (==1) */
#define KNK_RPM_B   (*(volatile uint8_t  *)0xFFFFCAAF)  /* u8 rpm/knock gate */
#define T_AA10      (*(volatile float    *)0xFFFFAA10)  /* f32 input (temp) */
#define RPM_B5B8    (*(volatile float    *)0xFFFFB5B8)  /* f32 lookup input */
#define LIM_CA18    (*(volatile float    *)0xFFFFCA18)  /* f32 min input */
#define OUT_CA10    (*(volatile float    *)0xFFFFCA10)  /* f32 output */
#define OUT_CA14    (*(volatile float    *)0xFFFFCA14)  /* f32 output (copy) */

/* ROM constants: 0x0007B3DB u8=1 (cmp/hi threshold), 0x0007B42C f32=-30.0,
 * 0x0007B430 f32=0.01, 0x0006BE74 = TwoDLookup descriptor. */
#define ROM_RPM_MIN (*(volatile uint8_t  *)0x0007B3DB)
#define ROM_T_BASE  (*(volatile float    *)0x0007B42C)
#define ROM_T_GAIN  (*(volatile float    *)0x0007B430)
#define KNK_MAP     (uint32_t)0x0006BE74

void knock_control_calc_44824(void)
{
    const float fr15 = 0.0f;   /* fldi0 in first delay slot (all paths) */

    if (GATE_FLAG != 1)        /* bf/s 0x4487E */
        goto store0;
    if (!(KNK_RPM_B > (uint8_t)ROM_RPM_MIN))  /* cmp/hi r0,r1 ; bf/s */
        goto store0;

    /* 0x44846..0x4487A: compute knock-correction factor */
    float fr2 = T_AA10 - ROM_T_BASE;             /* fsub fr3,fr2  */
    float v   = fr2 * ROM_T_GAIN;                /* fmul fr1,fr4  */
    float c   = clamp_0x2404(v, 0.0f, 1.0f);     /* jsr @0x2404   */
    float lk  = two_d_lookup_0x2068(KNK_MAP, RPM_B5B8); /* jsr @0x2068 */
    float m   = min_0x23F4(LIM_CA18, lk);        /* jsr @0x23F4   */
    OUT_CA10 = m * c;                            /* fmul fr15,fr4; store */
    goto epilogue;

store0:
    OUT_CA10 = fr15;                             /* fmov.s fr15,@r14 */

epilogue:
    OUT_CA14 = OUT_CA10;                         /* reload @r14 -> 0xFFFFCA14 */
}
