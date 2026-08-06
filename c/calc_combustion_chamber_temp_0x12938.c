/* calc_combustion_chamber_temp_0x12938.c
 *
 * ROM: 60E1D400 | Address: 0x12938 | Size: 0x110 (272) bytes per CSV range
 * 0x12938..0x12A48.  79 code instrs (0x12938..0x12A46, rts+delay at
 * 0x12A44/0x12A46) + interleaved mov.w literal pool @0x12984..0x129AA
 * (jumped over by bra 0x12980@0x1297E, bra 0x129E8@0x129D8/0x129E0, bra
 * 0x12A3A@0x12A08/0x12A20, bra 0x12A38@0x12A30, bra 0x12A08@0x129FE/0x12A00,
 * bra 0x12A04@0x129F6, bra 0x12A0C@0x129F2, bra 0x12A24@0x12A10/0x12A18,
 * bra 0x12A34@0x12A2A) and mov.l literals @0x129C8..0x12AEC (read by mov.l
 * at 0x1294C/0x12972/0x12974/0x129D8/0x129E8/0x129EA/0x129FE/0x12A04/
 * 0x12A1C/0x12A2E/0x12A34).
 *
 * Entry  : 0x12938 — matches the symbols CSV row.  Valid standalone prologue
 *           (mov.l r14,@-r15 ; fmov.s fr15,@-r15 ; fmov.s fr14,@-r15 ;
 *            fmov.s fr13,@-r15 ; sts.l pr,@-r15), rts+delay at 0x12A44/0x12A46.
 *           The ONLY ROM reference to 0x12938 is the function-pointer slot
 *           @0x14840 inside the dispatcher engineControlCalculateTiming
 *           (0x14584) literal pool — dispatch slot for
 *           calc_combustion_chamber_temp (c/engineControlCalculateTiming.c
 *           line 263).  No code branches into the body from mid-function
 *           (all static branch targets found inside [0x12938,0x12A48) are
 *           intra-function or pool-data false positives), so the CSV address
 *           IS the real entry point.
 * Range  : 0x12938 .. 0x12A48  (next function calc_rotor_B_knock_flag @0x12A48
 *           starts right at the CSV end)
 *
 * Literal pool:
 *   0x12994=0xCA10, 0x12996=0xA760, 0x1299C=0xA670, 0x129AC=0xC12C
 *           (mov.w RAM addrs, sign-extended to 0xFFFFxxxx)
 *   0x129C8 -> 0x2440          (window-out leaf: r0=1 if fr4 outside
 *                                [fr5-fr6, fr5+fr6])
 *   0x129CC f32 9.9999997e-06  (window epsilon, loaded via mova @0x12944)
 *   0x129D0 0xFFFFA66E         (u8 knock flag, written)
 *   0x129D4 f32 0.5            (ROM 0x0006E404 — hysteresis high threshold)
 *   0x12AD4 f32 0.05           (ROM 0x0006E408 — hysteresis band width)
 *   0x12AD8 0xFFFFA658         (f32 output — combustion chamber temp)
 *   0x12AC8 0xFFFFAADA         (u8 rotor-B enable gate (==1))
 *   0x12ADC f32 -25.0          (ROM 0x0006E3E4)
 *   0x12AE0 f32 -20.0          (ROM 0x0006E3FC)
 *   0x12AE4 f32 -58.5          (ROM 0x0006E3E8)
 *   0x12AE8 f32 -58.5          (ROM 0x0006E3EC)
 *   0x12AEC f32 -20.0          (ROM 0x0006E400)
 *
 * Semantics (instruction-for-instruction, see disasm):
 *   fr15 = f32@0xFFFFC12C;             ; loaded early (0x12950)
 *   w1 = window_out_0x2440(f32@A760, 0, eps);   ; 3x window-out on the knock
 *   w2 = window_out_0x2440(f32@A670, 0, eps);   ;   sensor deltas
 *   w3 = window_out_0x2440(f32@CA10, 0, eps);
 *   u8@0xFFFFA66E = (fr15 > 0.5f) ? 1        ; fcmp/gt fr4,fr15 -> T=(fr15>0.5)
 *                 : (fr15 > 0.45f) ? (unchanged)   ; band: flag retains value
 *                 : 0;                              ; NaN lands here (both T=0)
 *   if (u8@0xFFFFAADA == 1)                    ; rotor-B enable gate
 *       f32@0xFFFFA658 = (w2 == 0) ? -25.0f : -20.0f;
 *   else if (w3 == 0 && w1 == 0)
 *       f32@0xFFFFA658 = -58.5f;
 *   else
 *       f32@0xFFFFA658 = (u8@0xFFFFA66E == 1) ? -58.5f : -20.0f;
 *
 *   Structure is IDENTICAL to calc_rotor_B_knock_flag_0x12A48 (same window
 *   leaves, same hysteresis ladder, same gate/select shape) — only the RAM
 *   addresses (window inputs A760/A670/CA10, flag A66E, output A658) and the
 *   output constants (-25/-20/-58.5/-58.5/-20) differ.  The result is
 *   written into f32@0xFFFFA658, the same "chamber temp" area the spark
 *   advance code (0x162E4/0x16BE8) consumes — hence the ida-ai name
 *   calc_combustion_chamber_temp.
 *
 *   NaN semantics (matches the emulator byte-for-byte):
 *     fcmp/gt clears T on NaN.  The first check is a `bf/s` (branch on T==0),
 *     so NaN C12C skips the store-1; the second is a `bt/s` (branch on T==1),
 *     so NaN C12C also fails it and the flag is stored 0.  The window leaf
 *     0x2440 is pure fcmp — NaN inputs read as "inside the window" (w=0).
 *
 * VERIFIED against the SH-2 emulator (tools/sh2emu.py) in
 * c/tests/test_calc_combustion_chamber_temp_0x12938.py — 0 mismatches over
 * 5 seeds x default iterations (full post-call RAM overlay, byte-exact).
 */

#include <stdint.h>

/* 0x2440 — window-out leaf (pure FPU): returns r0 = 1 if fr4 is outside
 *   [fr5-fr6, fr5+fr6] (i.e. (fr5-fr6) > fr4 || fr4 > (fr5+fr6)), else 0.
 *   NOTE the SH-2 fcmp/gt NaN rule: a NaN fr4 makes both comparisons false,
 *   so NaN inputs read as "inside the window" (r0 = 0). */
extern int window_out_0x2440(float v, float c, float eps);

/* ---- RAM globals (mov.w literals sign-extend to 0xFFFFxxxx) ---- */
#define T_C12C   (*(volatile float   *)0xFFFFC12C)  /* f32 hysteresis input */
#define T_A760   (*(volatile float   *)0xFFFFA760)  /* f32 chamber temp delta 1 */
#define T_A670   (*(volatile float   *)0xFFFFA670)  /* f32 chamber temp delta 2 */
#define T_CA10   (*(volatile float   *)0xFFFFCA10)  /* f32 knock-control output */
#define G_AADA   (*(volatile uint8_t *)0xFFFFAADA)  /* u8 rotor-B enable (==1) */
#define FLAG     (*(volatile uint8_t *)0xFFFFA66E)  /* u8 knock flag (read+write) */
#define OUT_A658 (*(volatile float   *)0xFFFFA658)  /* f32 combustion chamber temp */

/* ROM constants */
#define EPS      (*(volatile float   *)0x000129CC)  /* f32 1e-5 (window eps) */
#define ROM_F050 (*(volatile float   *)0x0006E404)  /* f32 0.5 (high threshold) */
#define ROM_F005 (*(volatile float   *)0x0006E408)  /* f32 0.05 (band width) */
#define ROM_M25  (*(volatile float   *)0x0006E3E4)  /* f32 -25.0 */
#define ROM_M20a (*(volatile float   *)0x0006E3FC)  /* f32 -20.0 */
#define ROM_M585 (*(volatile float   *)0x0006E3E8)  /* f32 -58.5 */
#define ROM_M585b(*(volatile float   *)0x0006E3EC)  /* f32 -58.5 */
#define ROM_M20b (*(volatile float   *)0x0006E400)  /* f32 -20.0 */

void calc_combustion_chamber_temp_0x12938(void)
{
    float   fr15 = T_C12C;        /* fmov.s @r3,fr15 @0x12950 */
    int     w1 = window_out_0x2440(T_A760, 0.0f, EPS);   /* jsr @0x12956 */
    int     w2 = window_out_0x2440(T_A670, 0.0f, EPS);   /* jsr @0x12962 */
    int     w3 = window_out_0x2440(T_CA10, 0.0f, EPS);   /* jsr @0x1296E, r6=w3 */
    float   half_band = ROM_F050 - ROM_F005;   /* fsub fr3,fr4 @0x129DC -> 0.45f */

    /* 0x12976..0x129E6: the flag hysteresis (fcmp/gt fr4,fr15 = fr15>fr4).
     *   T=(fr15>0.5)  -> store 1 ; bf/s 0x129D8 on T==0 (NaN falls to 2nd check)
     *   T=(fr15>0.45) -> unchanged (bt/s 0x129E8 skips the store-0)
     *   else          -> store 0 (NaN C12C lands here: both fcms give T=0) */
    if (fr15 > ROM_F050) {
        FLAG = 1;                 /* mov.b r1,@r5 (bra delay @0x12982) */
    } else if (fr15 > half_band) {
        /* bt/s 0x129E8 taken — flag byte keeps its pre-call value */
    } else {
        FLAG = 0;                 /* mov.b r0,@r5 @0x129E6 */
    }

    /* 0x129E8..0x12A38: pick the output amount into f32@A658. */
    if (G_AADA == 1) {            /* cmp/eq #1,r0 ; bf/s 0x12A0C */
        if (w2 == 0) {            /* mov.b @(0x04,r15),r0 ; tst ; bf/s 0x12A04 */
            OUT_A658 = ROM_M25;   /* fmov.s @r2,fr3 @0x12A02 (delay of bra) */
        } else {
            OUT_A658 = ROM_M20a;  /* fmov.s @r1,fr3 @0x12A06 */
        }
    } else if (w3 == 0 && w1 == 0) {          /* extu.b r6 ; tst ; bf/s x2 @0x12A10/0x12A18 */
        OUT_A658 = ROM_M585;      /* fmov.s @r3,fr3 @0x12A1E (delay of bra) */
    } else {
        if (FLAG == 1) {          /* mov.b @r5,r0 ; cmp/eq #1 ; bf/s 0x12A34 */
            OUT_A658 = ROM_M585b; /* fmov.s @r3,fr3 @0x12A32 (delay of bra) */
        } else {
            OUT_A658 = ROM_M20b;  /* fmov.s @r2,fr3 @0x12A36 */
        }
    }
}
