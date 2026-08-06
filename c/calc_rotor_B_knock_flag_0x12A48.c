/* calc_rotor_B_knock_flag_0x12A48.c
 *
 * ROM: 60E1D400 | Address: 0x12A48 | Size: 0x100 (256) bytes per CSV range
 * 0x12A48..0x12B48.  65 code instrs (0x12A48..0x12B46, rts+delay at
 * 0x12B44/0x12B46) + mov.w literal pool @0x12AC8..0x12B0A (jumped over by
 * bra 0x12AC4@0x12ABC / bra 0x12B3A@0x12B20/0x12B30/0x12B38) and trailing
 * mov.l literals @0x12B48..0x12B53 (read by mov.l at 0x12B1C/0x12B2E/0x12B34).
 *
 * Entry  : 0x12A48 — matches the symbols CSV row.  Valid standalone prologue
 *           (mov.l r14,@-r15 ; fmov.s fr15,@-r15 ; fmov.s fr14,@-r15 ;
 *            fmov.s fr13,@-r15 ; sts.l pr,@-r15), rts+delay at 0x12B44/0x12B46.
 *           The ONLY ROM reference to 0x12A48 is the function-pointer slot
 *           @0x14854 inside the dispatcher engineControlCalculateTiming
 *           (0x14584) literal pool — dispatch slot for calc_rotor_B_knock_flag
 *           (c/engineControlCalculateTiming.c line 268).  No code branches
 *           into the body from mid-function, so the CSV address IS the real
 *           entry point.
 * Range  : 0x12A48 .. 0x12B48  (next named function @0x12B54 after the
 *           trailing literal pool 0x12B48..0x12B53)
 *
 * Literal pool:
 *   0x12AC8=0xAADA, 0x12ACA=0xC12C, 0x12ACC=0xA764, 0x12ACE=0xA674,
 *           0x12AD0=0xCA14      (mov.w RAM addrs, sign-extended to 0xFFFFxxxx)
 *   0x12AF0 -> 0x2440          (window-out leaf: r0=1 if fr4 outside
 *                               [fr5-fr6, fr5+fr6])
 *   0x12AF4 f32 9.9999997e-06  (window epsilon, loaded via mova @0x12A54)
 *   0x12AF8 0xFFFFA66F         (u8 knock flag, written)
 *   0x12AFC f32 0.5            (ROM 0x0006E404 — hysteresis high threshold)
 *   0x12AD4 f32 0.05           (ROM 0x0006E408 — hysteresis band width)
 *   0x12B00 0xFFFFA668         (f32 output — knock-retard amount)
 *   0x12B04 f32 -25.0          (ROM 0x0006E418)
 *   0x12B08 f32 -20.0          (ROM 0x0006E428)
 *   0x12B48 f32 -69.2          (ROM 0x0006E41C)
 *   0x12B4C f32 -69.2          (ROM 0x0006E420)
 *   0x12B50 f32 -20.0          (ROM 0x0006E42C)
 *
 * Semantics (instruction-for-instruction, see disasm):
 *   fr15 = f32@0xFFFFC12C;             ; loaded early (0x12A60), used in both fcms
 *   w1 = window_out_0x2440(f32@A764, 0, eps);   ; 3x window-out on the knock
 *   w2 = window_out_0x2440(f32@A674, 0, eps);   ;   sensor deltas
 *   w3 = window_out_0x2440(f32@CA14, 0, eps);
 *   u8@0xFFFFA66F = (fr15 > 0.5f) ? 1        ; fcmp/gt fr4,fr15 -> T=(fr15>0.5)
 *                 : (fr15 > 0.45f) ? (unchanged)   ; band: flag retains value
 *                 : 0;                              ; NaN lands here (both T=0)
 *   if (u8@0xFFFFAADA == 1)                    ; rotor-B enable gate
 *       f32@0xFFFFA668 = (w2 == 0) ? -25.0f : -20.0f;
 *   else if (w3 == 0 && w1 == 0)
 *       f32@0xFFFFA668 = -69.2f;
 *   else
 *       f32@0xFFFFA668 = (u8@0xFFFFA66F == 1) ? -69.2f : -20.0f;
 *
 *   NaN semantics (matches the emulator byte-for-byte):
 *     fcmp/gt clears T on NaN.  The first check is a `bf/s` (branch on T==0),
 *     so NaN C12C skips the store-1; the second is a `bt/s` (branch on T==1),
 *     so NaN C12C also fails it and the flag is stored 0.  The window leaf
 *     0x2440 is pure fcmp — NaN inputs read as "inside the window" (w=0).
 *
 * VERIFIED against the SH-2 emulator (tools/sh2emu.py) in
 * c/tests/test_calc_rotor_B_knock_flag_0x12A48.py — 0 mismatches over 5 seeds
 * x default iterations (full post-call RAM overlay, byte-exact).
 */

#include <stdint.h>

/* 0x2440 — window-out leaf (pure FPU): returns r0 = 1 if fr4 is outside
 *   [fr5-fr6, fr5+fr6] (i.e. (fr5-fr6) > fr4 || fr4 > (fr5+fr6)), else 0.
 *   NOTE the SH-2 fcmp/gt NaN rule: a NaN fr4 makes both comparisons false,
 *   so NaN inputs read as "inside the window" (r0 = 0). */
extern int window_out_0x2440(float v, float c, float eps);

/* ---- RAM globals (mov.w literals sign-extend to 0xFFFFxxxx) ---- */
#define T_C12C   (*(volatile float   *)0xFFFFC12C)  /* f32 hysteresis input */
#define T_A764   (*(volatile float   *)0xFFFFA764)  /* f32 rotor-B knock delta 1 */
#define T_A674   (*(volatile float   *)0xFFFFA674)  /* f32 rotor-B knock delta 2 */
#define T_CA14   (*(volatile float   *)0xFFFFCA14)  /* f32 knock-control output */
#define G_AADA   (*(volatile uint8_t *)0xFFFFAADA)  /* u8 rotor-B enable (==1) */
#define FLAG     (*(volatile uint8_t *)0xFFFFA66F)  /* u8 knock flag (read+write) */
#define OUT_A668 (*(volatile float   *)0xFFFFA668)  /* f32 knock-retard output */

/* ROM constants */
#define EPS      (*(volatile float   *)0x00012AF4)  /* f32 1e-5 (window eps) */
#define ROM_F050 (*(volatile float   *)0x0006E404)  /* f32 0.5 (high threshold) */
#define ROM_F005 (*(volatile float   *)0x0006E408)  /* f32 0.05 (band width) */
#define ROM_M25  (*(volatile float   *)0x0006E418)  /* f32 -25.0 */
#define ROM_M20a (*(volatile float   *)0x0006E428)  /* f32 -20.0 */
#define ROM_M692 (*(volatile float   *)0x0006E41C)  /* f32 -69.2 */
#define ROM_M692b(*(volatile float   *)0x0006E420)  /* f32 -69.2 */
#define ROM_M20b (*(volatile float   *)0x0006E42C)  /* f32 -20.0 */

void calc_rotor_B_knock_flag_0x12A48(void)
{
    float   fr15 = T_C12C;        /* fmov.s @r3,fr15 @0x12A60 */
    int     w1 = window_out_0x2440(T_A764, 0.0f, EPS);   /* jsr @0x12A66 */
    int     w2 = window_out_0x2440(T_A674, 0.0f, EPS);   /* jsr @0x12A72 */
    int     w3 = window_out_0x2440(T_CA14, 0.0f, EPS);   /* jsr @0x12A7E, r6=w3 */
    float   half_band = ROM_F050 - ROM_F005;   /* fsub fr3,fr4 @0x12A98 -> 0.45f */

    /* 0x12A88..0x12AA2: the flag hysteresis (fcmp/gt fr4,fr15 = fr15>fr4).
     *   T=(fr15>0.5)  -> store 1 ; bf/s 0x12A94 on T==0 (NaN falls to 2nd check)
     *   T=(fr15>0.45) -> unchanged (bt/s 0x12AA4 skips the store-0)
     *   else          -> store 0 (NaN C12C lands here: both fcms give T=0) */
    if (fr15 > ROM_F050) {
        FLAG = 1;                 /* mov.b r1,@r5 (bra delay @0x12A92) */
    } else if (fr15 > half_band) {
        /* bt/s 0x12AA4 taken — flag byte keeps its pre-call value */
    } else {
        FLAG = 0;                 /* mov.b r0,@r5 @0x12AA2 */
    }

    /* 0x12AA4..0x12B38: pick the knock-retard amount into f32@A668. */
    if (G_AADA == 1) {            /* cmp/eq #1,r0 ; bf/s 0x12B0C */
        if (w2 == 0) {            /* mov.b @(4,r15),r0 ; tst ; bf/s 0x12AC0 */
            OUT_A668 = ROM_M25;   /* fmov.s @r2,fr3 @0x12ABE (delay of bra) */
        } else {
            OUT_A668 = ROM_M20a;  /* fmov.s @r1,fr3 @0x12AC2 */
        }
    } else if (w3 == 0 && w1 == 0) {          /* tst r6 ; bf/s x2 @0x12B10/0x12B18 */
        OUT_A668 = ROM_M692;      /* fmov.s @r3,fr3 @0x12B1E (delay of bra) */
    } else {
        if (FLAG == 1) {          /* mov.b @r5,r0 ; cmp/eq #1 ; bf/s 0x12B34 */
            OUT_A668 = ROM_M692b; /* fmov.s @r3,fr3 @0x12B32 (delay of bra) */
        } else {
            OUT_A668 = ROM_M20b;  /* fmov.s @r2,fr3 @0x12B36 */
        }
    }
}
