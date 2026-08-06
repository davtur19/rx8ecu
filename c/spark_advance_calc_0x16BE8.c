/* spark_advance_calc_0x16BE8.c
 *
 * ROM: 60E1D400 | Address: 0x16BE8 | Size: 0xA2 (162) bytes per CSV range
 * 0x16BE8..0x16C8A.  81 code instrs (0x16BE8..0x16C88, rts+delay) + mov.w
 * literal pool @0x16C8A..0x16C98 and mov.l literal pool @0x16C9C..0x16CB8
 * (both interleaved after the code, inside the caller's pool region).
 *
 * Entry  : 0x16BE8 — matches the symbols CSV row.  Valid standalone prologue
 *           (mov.l r14,@-r15 ; mov.l r13,@-r15 ; sts.l pr,@-r15), rts+delay at
 *           0x16C86/0x16C88.  The ONLY ROM reference to 0x16BE8 is the
 *           function-pointer slot @0x16B80 inside engine_control_main_loop
 *           (0x16AA8) dispatch table 0x16B64..0x16BD0 — call site
 *           0x16AC4/0x16AC6 (`mov.l @0x16B80,r2 ; jsr @r2`).  No code branches
 *           into the body from mid-function, so the CSV address IS the real
 *           entry point.
 * Range  : 0x16BE8 .. 0x16C8A  (literal pool follows; next named function
 *           init_string_buffer_copy @0x16CBC)
 *
 * Literal pool (interleaved): 0x16C9C -> 0x2068 (TwoDLookup leaf),
 *           0x16CA0 = 0xFFFFA8E0 (f32 result/prev), 0x16CA4..0x16CB8 = the six
 *           TwoDLookup descriptors: 0x69BC0, 0x69BD4, 0x69BE8, 0x69BFC,
 *           0x69C10, 0x69C24.
 *
 * Semantics (instruction-for-instruction, see disasm):
 *   if (u8@0xFFFFBDD5 == 0) { f32@0xFFFFA8DC = 0.0f; return; }   ; gate + store0
 *   x = f32@0xFFFFAE54;                    ; fr4 (delay slot, all paths)
 *   s = u8@0xFFFFBE24;                     ; r4 descriptor selector (delay slot)
 *   if (u8@0xFFFFB5A4 == 1 || u8@0xFFFFB5AC == 0) {            ; 0x16C10 / 0x16C1A
 *       f32@0xFFFFA8E0 = two_d_lookup_0x2068((s==0) ? 0x69BC0 : 0x69BD4, x);
 *   } else if (u8@0xFFFFB5B0 == 1) {                            ; 0x16C3C
 *       f32@0xFFFFA8E0 = two_d_lookup_0x2068((s==0) ? 0x69BE8 : 0x69BFC, x);
 *   } else if (u8@0xFFFFB5AE == 1) {                            ; 0x16C60
 *       f32@0xFFFFA8E0 = two_d_lookup_0x2068((s==0) ? 0x69C10 : 0x69C24, x);
 *   }
 *   f32@0xFFFFA8DC = f32@0xFFFFA8E0;      ; epilogue reload-copy (0x16C7C)
 *
 *   When no selector fires, f32@0xFFFFA8E0 keeps its pre-call value and is
 *   copied through to the output untouched.
 *
 *   Six 1-D maps (c/2DLookup.c layout), all count=6, type=8 (u16 cells),
 *   axis [-20,0,20,40,60,80] (0x6E4A4..0x6E558), scale=0.001, offset=0.0:
 *     0x69BC0 cells 25 25 25 35 35 35  |  0x69BD4 cells 30 30 30 40 40 40
 *     0x69BE8 cells 55 55 55 60 60 60  |  0x69BFC cells 60 60 60 65 65 65
 *     0x69C10 cells 55 55 55 60 60 60  |  0x69C24 cells 60 60 60 65 65 65
 *
 *   A spark-advance selector: BDD5 enables the calc, B5A4/B5AC/B5B0/B5AE pick
 *   the map family, BE24 picks the exact table inside the family, and the
 *   temperature input f32@0xFFFFAE54 indexes the axis.
 *
 * VERIFIED against the SH-2 emulator (tools/sh2emu.py) in
 * c/tests/test_spark_advance_calc_0x16BE8.py — 0 mismatches over 5 seeds
 * x default iterations (full post-call RAM overlay, byte-exact).
 */

#include <stdint.h>

/* 0x2068 — TwoDLookup (verified primitive, see c/2DLookup.c):
 *   r4 = descriptor ptr, fr4 = x.  returns fr0 = piecewise-linear interp of the
 *   typed cells, scale*interp+offset applied for non-zero cell type. */
extern float two_d_lookup_0x2068(uint32_t desc, float x);

/* ---- RAM globals (mov.w literals sign-extend to 0xFFFFxxxx) ---- */
#define GATE_BDD5 (*(volatile uint8_t *)0xFFFFBDD5)  /* u8 calc-enable gate (==0 -> store 0) */
#define SEL_BE24  (*(volatile uint8_t *)0xFFFFBE24)  /* u8 map selector 0/1 */
#define SW_B5A4   (*(volatile uint8_t *)0xFFFFB5A4)  /* u8 branch switch A (==1) */
#define SW_B5AC   (*(volatile uint8_t *)0xFFFFB5AC)  /* u8 branch switch A' (==0) */
#define SW_B5B0   (*(volatile uint8_t *)0xFFFFB5B0)  /* u8 branch switch B (==1) */
#define SW_B5AE   (*(volatile uint8_t *)0xFFFFB5AE)  /* u8 branch switch C (==1) */
#define T_AE54    (*(volatile float   *)0xFFFFAE54)  /* f32 lookup input (temp) */
#define R_A8E0    (*(volatile float   *)0xFFFFA8E0)  /* f32 lookup result / prev */
#define OUT_A8DC  (*(volatile float   *)0xFFFFA8DC)  /* f32 output (copy of A8E0) */

/* ROM constants: the six TwoDLookup descriptors @0x69BC0/0x69BD4/0x69BE8/
 * 0x69BFC/0x69C10/0x69C24 (count=6, type=8 u16 cells, scale=0.001, offset=0). */
#define MAP_A0 (uint32_t)0x00069BC0
#define MAP_A1 (uint32_t)0x00069BD4
#define MAP_B0 (uint32_t)0x00069BE8
#define MAP_B1 (uint32_t)0x00069BFC
#define MAP_C0 (uint32_t)0x00069C10
#define MAP_C1 (uint32_t)0x00069C24

void spark_advance_calc_0x16BE8(void)
{
    if (GATE_BDD5 == 0) {              /* tst r2,r2 ; bf/s 0x16C02 — store0 path */
        OUT_A8DC = 0.0f;               /* fldi0 fr3 ; mov.w 0xA8DC,r0 ; fmov.s fr3,@r0 */
        return;
    }

    float   x = T_AE54;                /* fmov.s @r2,fr4 (delay of first bt/s, all paths) */
    uint8_t s = SEL_BE24;              /* mov.b @r3,r4 (delay of gate bf/s, all paths) */

    if (SW_B5A4 == 1 || SW_B5AC == 0) {              /* 0x16C10 bt/s | 0x16C1A bf/s */
        R_A8E0 = two_d_lookup_0x2068(s == 0 ? MAP_A0 : MAP_A1, x);   /* jsr @0x16C2E */
    } else if (SW_B5B0 == 1) {                       /* 0x16C3C cmp/eq */
        R_A8E0 = two_d_lookup_0x2068(s == 0 ? MAP_B0 : MAP_B1, x);   /* jsr @0x16C52 */
    } else if (SW_B5AE == 1) {                       /* 0x16C60 cmp/eq */
        R_A8E0 = two_d_lookup_0x2068(s == 0 ? MAP_C0 : MAP_C1, x);   /* jsr @0x16C76 */
    }
    /* no selector fired -> R_A8E0 keeps its pre-call value */

    OUT_A8DC = R_A8E0;                 /* fmov.s @r14,fr3 ; fmov.s fr3,@r3 (reload-copy) */
}
