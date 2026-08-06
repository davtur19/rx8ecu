/* write_knock_detected_flag_0x128C4.c
 *
 * ROM: 60E1D400 | Address: 0x128C4 | Size: 0x3A (58) bytes per CSV range
 * 0x128C4..0x128FE.  29 code instrs (0x128C4..0x128FC, rts+delay at
 * 0x128FA/0x128FC) with an interleaved mov.w literal pool @0x12990..0x1299C
 * and mov.l literals @0x129BC/0x129C0 shared with the neighbouring functions
 * (inside calc_combustion_chamber_temp 0x12938's pool region).
 *
 * Entry  : 0x128C4 — matches the symbols CSV row.  Valid standalone prologue
 *           (fmov.s fr12,@-r15 ; sts.l pr,@-r15), rts+delay at 0x128FA/0x128FC.
 *           The ONLY ROM reference to 0x128C4 is the function-pointer slot
 *           @0x14844 inside the dispatcher engineControlCalculateTiming
 *           (0x14584) literal pool — dispatch slot for write_knock_detected_flag
 *           (c/engineControlCalculateTiming.c line 264).  No code branches
 *           into the body (the function is a straight line), so the CSV
 *           address IS the real entry point.
 * Range  : 0x128C4 .. 0x128FE  (next function write_rotor_A_knock_flag
 *           @0x128FE starts right at the CSV end)
 *
 * Literal pool (interleaved, shared): 0x12990=0xA6AC, 0x12992=0xA734,
 *           0x12994=0xCA10, 0x12996=0xA760, 0x12998=0xA5E4, 0x1299A=0xB2F8,
 *           0x1299C=0xA670 (mov.w RAM addrs, sign-extended to 0xFFFFxxxx),
 *           0x129BC -> 0x23E4 (float-max leaf: fr0 = (fr4>fr5) ? fr4 : fr5),
 *           0x129C0 = 0xFFFFA654 (f32 output).
 *
 * Semantics (instruction-for-instruction, see disasm):
 *   fr12 = (f32@0xFFFFA734 - f32@0xFFFFA6AC);              ; fsub fr3,fr2
 *   fr12 = fr12 - max_0x23E4(f32@0xFFFFA760, f32@0xFFFFCA10);  ; jsr @0x23E4
 *   fr12 = fr12 + f32@0xFFFFA5E4;                          ; fadd fr3,fr12
 *   fr12 = fr12 + f32@0xFFFFB2F8;                          ; fadd fr2,fr12
 *   fr12 = fr12 - f32@0xFFFFA670;                          ; fsub fr1,fr12
 *   f32@0xFFFFA654 = fr12;                                 ; fmov.s fr12,@r3
 *
 *   A pure FP accumulate — every step is single-precision rounded (ts),
 *   exactly in the order above (left-associative in C).  The rotor-A / rotor-B
 *   mirror write_rotor_A_knock_flag_0x128FE uses the identical shape on
 *   the A6B0/A738/CA14/A764/A5E8/B2FC/A674/A664 register set.
 *
 * VERIFIED against the SH-2 emulator (tools/sh2emu.py) in
 * c/tests/test_write_knock_detected_flag_0x128C4.py — 0 mismatches over 5 seeds
 * x default iterations (full post-call RAM overlay, byte-exact).
 */

#include <stdint.h>

/* 0x23E4 — float max leaf (pure FPU): returns fr0 = (fr4 > fr5) ? fr4 : fr5
 *   (SH-2 fcmp/gt clears T on NaN, so a NaN first operand loses and the leaf
 *   returns the second operand). */
extern float max_0x23E4(float a, float b);

/* ---- RAM globals (mov.w literals sign-extend to 0xFFFFxxxx) ---- */
#define T_A6AC   (*(volatile float *)0xFFFFA6AC)  /* f32 input A */
#define T_A734   (*(volatile float *)0xFFFFA734)  /* f32 input B */
#define T_CA10   (*(volatile float *)0xFFFFCA10)  /* f32 knock-control output */
#define T_A760   (*(volatile float *)0xFFFFA760)  /* f32 knock delta */
#define T_A5E4   (*(volatile float *)0xFFFFA5E4)  /* f32 additive term */
#define T_B2F8   (*(volatile float *)0xFFFFB2F8)  /* f32 additive term */
#define T_A670   (*(volatile float *)0xFFFFA670)  /* f32 subtractive term */
#define OUT_A654 (*(volatile float *)0xFFFFA654)  /* f32 output (knock-detect) */

void write_knock_detected_flag_0x128C4(void)
{
    float fr12;

    fr12 = T_A734 - T_A6AC;                              /* fsub fr3,fr2 @0x128D2 */
    fr12 = fr12 - max_0x23E4(T_A760, T_CA10);            /* jsr @0x128DC, fsub @0x128E2 */
    fr12 = fr12 + T_A5E4;                                /* fadd fr3,fr12 @0x128EA */
    fr12 = fr12 + T_B2F8;                                /* fadd fr2,fr12 @0x128EE */
    fr12 = fr12 - T_A670;                                /* fsub fr1,fr12 @0x128F4 */
    OUT_A654 = fr12;                                     /* fmov.s fr12,@r3 @0x128F6 */
}
