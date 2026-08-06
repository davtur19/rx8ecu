/* spark_timing_boundary_limiter_0x162E4.c
 *
 * ROM: 60E1D400 | Address: 0x162E4 | Size: 0x182 (386) bytes per CSV range
 * 0x162E4..0x16466.  151 code instrs in two blocks
 * (0x162E4..0x163E6 + 0x1643C..0x16464) with an embedded literal pool
 * @0x163E8..0x1643A (jumped over by bra 0x163D2@0x163CC / bra 0x1643E@0x163E4)
 * and interleaved literals @0x16554/0x16558 (inside dual_rotor_sync_controller's
 * 0x16466.. range).
 *
 * Entry  : 0x162E4 — matches the symbols CSV row.  Valid standalone prologue
 *           (mov.l r14,@-r15 ; mov.l r13,@-r15 ; mov.l r12,@-r15 ;
 *            fmov.s fr15,@-r15 ; fmov.s fr14,@-r15 ; sts.l pr,@-r15),
 *           rts+delay at 0x16462/0x16464.  The ONLY ROM reference to 0x162E4 is
 *           the function-pointer slot @0x16BAC inside engine_control_main_loop
 *           (0x16AA8) dispatch table 0x16B64..0x16BD0 — call site
 *           0x16B06/0x16B08 (`mov.l @0x16BAC,r3 ; jsr @r3`).  No code branches
 *           into the body from mid-function, so the CSV address IS the real
 *           entry point.
 * Range  : 0x162E4 .. 0x16466  (next function dual_rotor_sync_controller
 *           @0x16466 starts right at the CSV end)
 *
 * Literal pool (own 0x163E8..0x1643A + interleaved 0x16554/0x16558):
 *   0x163E8..0x16406 mov.w RAM addrs (sign-extended to 0xFFFFxxxx):
 *           A7C4, A7C5, B5C0, A7BC, A848, A8DC, A8A0, AA10, AE54, A7B4, B360,
 *           A850, A84C, A7C7, CCD1
 *   0x16408 -> 0x23DC   float abs-diff leaf  fr0 = |fr4 - fr5|
 *   0x1640C f32 9.9999997e-06   (window epsilon for 0x2440)
 *   0x16410 -> 0x2440   window-out leaf: r0 = 1 if fr4 outside [fr5-fr6,fr5+fr6]
 *   0x16414 0xFFFFA8A2  u16 counter A (mov.l sign-extended RAM addr)
 *   0x16418 0x00076AEA  u16 312 (threshold for counters A/B)
 *   0x1641C 0xFFFFA8A4  u16 counter B
 *   0x16420 0x00076AEC  f32 80.0
 *   0x16424 0x00076AF0  f32 60.0
 *   0x16428 0x00076AF4  f32 37.0
 *   0x1642C 0x00076AF8  f32 0.035
 *   0x16430 0x00076AFC  f32 35.0
 *   0x16434 0x00076AE8  u8 0 (ROM enable flag)
 *   0x16438 -> 0x2460   u16 saturating-add leaf  r0 = min(u16(r4)+u16(r5),0xFFFF)
 *   0x16554 0xFFFFA8A4, 0x16558 -> 0x2460
 *
 * Semantics (instruction-for-instruction, see disasm):
 *   gate_a = u8@0xFFFFA7C4;   gate_b = u8@0xFFFFA7C5;
 *   fr15   = f32@0xFFFFA848;                        ; loaded early (0x16312)
 *   delta  = |f32@0xFFFFA7BC - f32@0xFFFFB5C0|;     ; 0x23DC (0x16304)
 *   wout   = (|f32@0xFFFFA8DC| > 1e-5f);            ; 0x2440(v=A8DC,c=0,e=1e-5)
 *   pass   = gate_a==1
 *          && u16@0xFFFFA8A2 >= 312
 *          && gate_b==0
 *          && u16@0xFFFFA8A4 >= 312
 *          && !(80.0f  > f32@0xFFFFAA10)            ; fcmp/gt fr2,fr3 (NaN passes)
 *          &&  (60.0f  > f32@0xFFFFAE54)            ; fcmp/gt fr2,fr3 (NaN fails)
 *          && !(delta  > 37.0f)                     ; fcmp/gt fr3,fr14
 *          && !wout
 *          && !(f32@0xFFFFA7B4 > 0.035f)            ; fcmp/gt fr3,fr2
 *          && !(f32@0xFFFFB360 > 35.0f)             ; fcmp/gt fr3,fr2
 *          &&  f32@0xFFFFA848 > f32@0xFFFFA850      ; fcmp/gt fr3,fr15
 *          &&  f32@0xFFFFA84C > f32@0xFFFFA848      ; fcmp/gt fr15,fr3
 *          && u8@0xFFFFA7C7 == 0
 *          && u8@0xFFFFCCD1 == 0
 *          && u8@0x00076AE8 == 0;                   ; ROM byte (always 0)
 *   u8@0xFFFFA8A0  = pass ? 1 : 0;                  ; mov.b r1/r14,@r6
 *   u16@0xFFFFA8A2 = (gate_a==1) ? satadd16(u16@A8A2,1) : 0;   ; 0x2460
 *   u16@0xFFFFA8A4 = (gate_b==0) ? satadd16(u16@A8A4,1) : 0;   ; 0x2460
 *
 *   NOTE the NaN asymmetry (matches the emulator byte-for-byte):
 *     fcmp/gt clears T on NaN, so a `bt/s` fail-check (needs T=1) PASSES
 *     through on NaN for the 80.0/AA10 gate, while the `bf/s` fail-checks
 *     (need T=0) FAIL on NaN for the 60.0/AE54 and the two ordering gates.
 *
 * VERIFIED against the SH-2 emulator (tools/sh2emu.py) in
 * c/tests/test_spark_timing_boundary_limiter_0x162E4.py — 0 mismatches over
 * 5 seeds x default iterations (full post-call RAM overlay, byte-exact).
 */

#include <stdint.h>

/* 0x23DC — float abs-diff leaf (pure FPU): fr0 = |fr4 - fr5|. */
extern float abs_diff_0x23DC(float a, float b);

/* 0x2440 — window-out leaf (pure FPU): returns r0 = 1 if fr4 is outside
 *   [fr5-fr6, fr5+fr6] (i.e. (fr5-fr6) > fr4 || fr4 > (fr5+fr6)), else 0. */
extern int window_out_0x2440(float v, float c, float eps);

/* 0x2460 — u16 saturating-add leaf (pure regs): returns min(u16(a)+u16(b), 0xFFFF). */
extern uint16_t satadd16_0x2460(uint16_t a, uint16_t b);

/* ---- RAM globals (mov.w literals sign-extend to 0xFFFFxxxx) ---- */
#define GATE_A   (*(volatile uint8_t  *)0xFFFFA7C4)  /* u8 enable gate A (==1) */
#define GATE_B   (*(volatile uint8_t  *)0xFFFFA7C5)  /* u8 enable gate B (==0) */
#define T_A7BC   (*(volatile float    *)0xFFFFA7BC)  /* f32 boundary A */
#define T_B5C0   (*(volatile float    *)0xFFFFB5C0)  /* f32 boundary B */
#define T_A848   (*(volatile float    *)0xFFFFA848)  /* f32 ordering middle (fr15) */
#define T_A850   (*(volatile float    *)0xFFFFA850)  /* f32 ordering low */
#define T_A84C   (*(volatile float    *)0xFFFFA84C)  /* f32 ordering high */
#define T_A8DC   (*(volatile float    *)0xFFFFA8DC)  /* f32 delta/zero gate */
#define CNT_A    (*(volatile uint16_t *)0xFFFFA8A2)  /* u16 counter A */
#define CNT_B    (*(volatile uint16_t *)0xFFFFA8A4)  /* u16 counter B */
#define OUT_A8A0 (*(volatile uint8_t  *)0xFFFFA8A0)  /* u8 pass/fail flag */
#define T_AA10   (*(volatile float    *)0xFFFFAA10)  /* f32 80.0-gate input */
#define T_AE54   (*(volatile float    *)0xFFFFAE54)  /* f32 60.0-gate input */
#define T_A7B4   (*(volatile float    *)0xFFFFA7B4)  /* f32 0.035-gate input */
#define T_B360   (*(volatile float    *)0xFFFFB360)  /* f32 35.0-gate input */
#define F_A7C7   (*(volatile uint8_t  *)0xFFFFA7C7)  /* u8 flag gate */
#define F_CCD1   (*(volatile uint8_t  *)0xFFFFCCD1)  /* u8 flag gate */

/* ROM constants */
#define ROM_THR  (*(volatile uint16_t *)0x00076AEA)  /* u16 312 */
#define ROM_EPS  (*(volatile float    *)0x0001640C)  /* f32 1e-5 */
#define ROM_F80  (*(volatile float    *)0x00076AEC)  /* f32 80.0 */
#define ROM_F60  (*(volatile float    *)0x00076AF0)  /* f32 60.0 */
#define ROM_F37  (*(volatile float    *)0x00076AF4)  /* f32 37.0 */
#define ROM_F035 (*(volatile float    *)0x00076AF8)  /* f32 0.035 */
#define ROM_F35  (*(volatile float    *)0x00076AFC)  /* f32 35.0 */
#define ROM_EN   (*(volatile uint8_t  *)0x00076AE8)  /* u8 0 (ROM enable) */

void spark_timing_boundary_limiter_0x162E4(void)
{
    uint8_t gate_a = GATE_A;          /* r4 (saved to stack, reloaded @0x16320) */
    uint8_t gate_b = GATE_B;          /* r13 */
    float   fr15   = T_A848;          /* fr15 loaded @0x16312 */
    float   delta  = abs_diff_0x23DC(T_A7BC, T_B5C0);   /* fr14 @0x1630E */
    int     wout   = window_out_0x2440(T_A8DC, 0.0f, ROM_EPS);  /* r5 @0x1631E */

    /* 0x16326..0x163C8: the boundary gate chain — every check is a
       `bt/s`/`bf/s 0x163D0` branch to the store-0 exit. */
    if (gate_a != 1)                  /* cmp/eq #1,r0 ; bf/s */
        goto fail;
    if (CNT_A < ROM_THR)              /* mov.w @A8A2 ; cmp/hs r1,r2 ; bf/s */
        goto fail;
    if (gate_b != 0)                  /* extu.b r13 ; tst ; bf/s */
        goto fail;
    if (CNT_B < ROM_THR)              /* mov.w @A8A4 ; cmp/hs r3,r2 ; bf/s */
        goto fail;
    if (ROM_F80 > T_AA10)             /* fcmp/gt fr2,fr3 ; bt/s (NaN passes) */
        goto fail;
    if (!(ROM_F60 > T_AE54))          /* fcmp/gt fr2,fr3 ; bf/s (NaN fails) */
        goto fail;
    if (delta > ROM_F37)              /* fcmp/gt fr3,fr14 ; bt/s */
        goto fail;
    if (wout)                         /* extu.b r5 ; tst ; bf/s */
        goto fail;
    if (T_A7B4 > ROM_F035)            /* fcmp/gt fr3,fr2 ; bt/s */
        goto fail;
    if (T_B360 > ROM_F35)             /* fcmp/gt fr3,fr2 ; bt/s */
        goto fail;
    if (!(fr15 > T_A850))             /* fcmp/gt fr3,fr15 ; bf/s */
        goto fail;
    if (!(T_A84C > fr15))             /* fcmp/gt fr15,fr3 ; bf/s */
        goto fail;
    if (F_A7C7 != 0)                  /* tst r3,r3 ; bf/s */
        goto fail;
    if (F_CCD1 != 0)                  /* tst r3,r3 ; bf/s */
        goto fail;
    if (ROM_EN != 0)                  /* tst r3,r3 ; bf/s (ROM byte, always 0) */
        goto fail;

    OUT_A8A0 = 1;                     /* mov #1,r1 ; bra 0x163D2 ; mov.b r1,@r6 */
    goto counters;

fail:
    OUT_A8A0 = 0;                     /* mov.b r14(0),@r6 @0x163D0 */

counters:
    /* 0x163D2..0x163E6 / 0x1643C: counter A — saturating inc while gate_a, else 0. */
    CNT_A = (gate_a == 1) ? satadd16_0x2460(CNT_A, 1) : 0;
    /* 0x1643E..0x16452 / 0x16454: counter B — saturating inc while gate_b, else 0. */
    CNT_B = (gate_b == 0) ? satadd16_0x2460(CNT_B, 1) : 0;
}
