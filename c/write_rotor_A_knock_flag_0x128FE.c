/* write_rotor_A_knock_flag_0x128FE.c
 *
 * ROM: 60E1D400 | Address: 0x128FE | Size: 0x3A (58) bytes per CSV range
 * 0x128FE..0x12938.  29 code instrs (0x128FE..0x12936, rts+delay at
 * 0x12934/0x12936) with an interleaved mov.w literal pool @0x12990..0x129AA
 * and mov.l literals @0x129BC/0x129C4 shared with the neighbouring functions
 * (inside calc_combustion_chamber_temp 0x12938's pool region).
 *
 * Entry  : 0x128FE — matches the symbols CSV row.  Valid standalone prologue
 *           (fmov.s fr12,@-r15 ; sts.l pr,@-r15), rts+delay at 0x12934/0x12936.
 *           The ONLY ROM reference to 0x128FE is the function-pointer slot
 *           @0x14858 inside the dispatcher engineControlCalculateTiming
 *           (0x14584) literal pool — dispatch slot for write_rotor_A_knock_flag
 *           (c/engineControlCalculateTiming.c line 269).  No code branches
 *           into the body (the function is a straight line), so the CSV
 *           address IS the real entry point.
 * Range  : 0x128FE .. 0x12938  (next function calc_combustion_chamber_temp
 *           @0x12938 starts right at the CSV end)
 *
 * Literal pool (interleaved, shared): 0x1299E=0xA6B0, 0x129A0=0xA738,
 *           0x129A2=0xCA14, 0x129A4=0xA764, 0x129A6=0xA5E8, 0x129A8=0xB2FC,
 *           0x129AA=0xA674 (mov.w RAM addrs, sign-extended to 0xFFFFxxxx),
 *           0x129BC -> 0x23E4 (float-max leaf: fr0 = (fr4>fr5) ? fr4 : fr5),
 *           0x129C4 = 0xFFFFA664 (f32 output).
 *
 * Semantics (instruction-for-instruction, see disasm):
 *   fr12 = (f32@0xFFFFA738 - f32@0xFFFFA6B0);              ; fsub fr3,fr2
 *   fr12 = fr12 - max_0x23E4(f32@0xFFFFA764, f32@0xFFFFCA14);  ; jsr @0x23E4
 *   fr12 = fr12 + f32@0xFFFFA5E8;                          ; fadd fr3,fr12
 *   fr12 = fr12 + f32@0xFFFFB2FC;                          ; fadd fr2,fr12
 *   fr12 = fr12 - f32@0xFFFFA674;                          ; fsub fr1,fr12
 *   f32@0xFFFFA664 = fr12;                                 ; fmov.s fr12,@r3
 *
 *   A pure FP accumulate — every step is single-precision rounded (ts),
 *   exactly in the order above (left-associative in C).
 *
 * VERIFIED against the SH-2 emulator (tools/sh2emu.py) in
 * c/tests/test_write_rotor_A_knock_flag_0x128FE.py — 0 mismatches over 5 seeds
 * x default iterations (full post-call RAM overlay, byte-exact).
 */

#include <stdint.h>

/* 0x23E4 — float max leaf (pure FPU): returns fr0 = (fr4 > fr5) ? fr4 : fr5
 *   (SH-2 fcmp/gt clears T on NaN, so a NaN first operand loses and the leaf
 *   returns the second operand). */
extern float max_0x23E4(float a, float b);

/* ---- RAM globals (mov.w literals sign-extend to 0xFFFFxxxx) ---- */
#define T_A6B0   (*(volatile float *)0xFFFFA6B0)  /* f32 input A */
#define T_A738   (*(volatile float *)0xFFFFA738)  /* f32 input B */
#define T_CA14   (*(volatile float *)0xFFFFCA14)  /* f32 knock-control output */
#define T_A764   (*(volatile float *)0xFFFFA764)  /* f32 rotor-B knock delta */
#define T_A5E8   (*(volatile float *)0xFFFFA5E8)  /* f32 additive term */
#define T_B2FC   (*(volatile float *)0xFFFFB2FC)  /* f32 additive term */
#define T_A674   (*(volatile float *)0xFFFFA674)  /* f32 subtractive term */
#define OUT_A664 (*(volatile float *)0xFFFFA664)  /* f32 output (rotor A flag) */

void write_rotor_A_knock_flag_0x128FE(void)
{
    float fr12;

    fr12 = T_A738 - T_A6B0;                              /* fsub fr3,fr2 @0x1290E */
    fr12 = fr12 - max_0x23E4(T_A764, T_CA14);            /* jsr @0x12916, fsub @0x1291A */
    fr12 = fr12 + T_A5E8;                                /* fadd fr3,fr12 @0x12922 */
    fr12 = fr12 + T_B2FC;                                /* fadd fr2,fr12 @0x1292A */
    fr12 = fr12 - T_A674;                                /* fsub fr1,fr12 @0x1292E */
    OUT_A664 = fr12;                                     /* fmov.s fr12,@r3 @0x12930 */
}
