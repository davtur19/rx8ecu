/* calculateLeadingDerateRetard_0x1253C.c
 *
 * ROM: 60E0FC00 | Address: 0x1253C | Size: 0x3A (58) bytes per CSV range
 * 0x1253C..0x12576.  Code runs to the `rts` @0x12572 (delay fmov.s @r15+,fr12
 * @0x12574); the trailing twin calculateTrailingDerateRetard starts at the CSV
 * end 0x12576.  The CSV range is CORRECT (code to 0x12574, next function
 * exactly at 0x12576) — no correction needed.
 *
 * ENTRY VERIFICATION: 0x1253C matches the symbols CSV start.  Valid entry:
 * opens with the standard prologue (`fmov.s fr12,@-r15 ; sts.l pr,@-r15`).
 * The preceding function calculateTrailingTimingBaseFinal (0x12456) ends with
 * `rts` @0x12538 (delay mov.l @r15+,r14 @0x1253A), so there is no fall-through
 * into us; no incoming branches into the middle (a whole-ROM scan of branch
 * targets into 0x1253C..0x12576 found none — the only brute hits were in the
 * data pool @0x1172A/@0x1173E, which decode as bra-like opcodes).  Called via
 * the function-pointer slot @0x144BC of the engineControlCalculateTiming
 * dispatcher (0x141FC) dispatch table (immediately after defaultTimingMinMax
 * @0x144B8 and before calculateLeadingTimingBaseFinal @0x144C0).  The ROM
 * literal @0x144BC is the ONLY 32-bit reference to 0x1253C in the binary.
 * The CSV address IS the real entry point.
 *
 * SEMANTICS (instruction-for-instruction, see disasm): the leading-timing
 * derate-retard writer — structural twin of calculateTrailingDerateRetard
 * (0x12576, byte-identical skeleton with +4-shifted RAM addresses).  It
 * computes (single-precision at every step, per the SH-2E fadd/fsub):
 *
 *   x  = f32@A724 - f32@A69C                   ; fsub fr3,fr2 (delay)
 *   x  = x - saturateLow_0x23E4(f32@A750, f32@C8A0)   ; jsr @0x23E4 (leaf)
 *   x  = x + f32@A5E4                          ; fadd fr3,fr12
 *   x  = x + f32@B2E4                          ; fadd fr2,fr12
 *   x  = x - f32@A660                          ; fsub fr1,fr12
 *   f32@A644 = x
 *
 * Where saturateLow @0x23E4 = (fr4 > fr5) ? fr4 : fr5 (max; NaN sig -> lower,
 * because fcmp/gt clears T on NaN so the bf path yields fr5).  r0 is not
 * touched by this function or by the 0x23E4 leaf, so r0 on return is the
 * value it held at entry (0 in the isolated-call harness).
 *
 * NaN semantics (matches the emulator byte-for-byte): each fadd/fsub rounds
 * to single precision; a NaN input propagates through the chain with the
 * usual fcmp behavior in the leaf (NaN sig -> returns C8A0 reference).  All
 * stack usage is the 0xFFFFDF00 window (fr12 + PR saves, 2 words).
 *
 * LITERAL POOL (values verified against roms/stock/60E0FC00.bin):
 *   mov.w 0x12608=0xA69C, 0x1260A=0xA724, 0x1260C=0xC8A0, 0x1260E=0xA750,
 *   0x12610=0xA5E4, 0x12612=0xB2E4, 0x12614=0xA660 (own; shared with the
 *   trailing twin's mov.w pool @0x12616..0x12622)
 *   mov.l 0x12634=0x000023E4 (saturateLow, shared with the trailing twin),
 *   0x12638=0xFFFFA644 (output)
 * RAM r/w: reads A69C, A724, C8A0, A750, A5E4, B2E4, A660; writes A644.
 * ROM read: the literal pool above.  No RAM sub-call beyond saturateLow @0x23E4
 * (x1, verified in c/math_primitives.c).
 * Sub-calls: saturateLow @0x23E4 (x1).  SH-2E conv: float args fr4/fr5, float
 * result fr0; the leaf never writes r0.
 *
 * VERIFIED against the SH-2 emulator (tools/sh2emu.py, 60E0FC00.bin) in
 * c/tests/test_calculateLeadingDerateRetard_0x1253C.py — 0 mismatches over
 * 5 seeds x 100000 iterations (byte-exact full post-call RAM overlay + r0).
 */
#include <stdint.h>
#include <math.h>

/* ---- RAM globals (mov.w literals sign-extend to 0xFFFFxxxx) ---- */
#define RAM_A69C  (*(volatile float *)0xFFFFA69C)  /* f32 diff minuend base   */
#define RAM_A724  (*(volatile float *)0xFFFFA724)  /* f32 diff minuend        */
#define RAM_C8A0  (*(volatile float *)0xFFFFC8A0)  /* f32 leaf lower/limit    */
#define RAM_A750  (*(volatile float *)0xFFFFA750)  /* f32 leaf sig            */
#define RAM_A5E4  (*(volatile float *)0xFFFFA5E4)  /* f32 addend 1            */
#define RAM_B2E4  (*(volatile float *)0xFFFFB2E4)  /* f32 addend 2            */
#define RAM_A660  (*(volatile float *)0xFFFFA660)  /* f32 subtrahend          */
#define OUT_A644  (*(volatile float *)0xFFFFA644)  /* f32 leading derate-ret  */

/* ---- External helper (in ROM, verified separately) ---- */
extern float saturateLow(float sig, float lower);  /* @0x23E4 max(sig, lower); NaN sig -> lower */

void calculateLeadingDerateRetard_0x1253C(void)
{
    float x;

    /* x = f32@A724 - f32@A69C   (fsub fr3,fr2 ; fr2=A724, fr3=A69C) */
    x = RAM_A724 - RAM_A69C;

    /* x -= saturateLow(f32@A750, f32@C8A0)  (jsr @0x23E4 -> fr0, fsub fr0,fr12) */
    x = x - saturateLow(RAM_A750, RAM_C8A0);

    /* x += f32@A5E4 ; x += f32@B2E4 ; x -= f32@A660 */
    x = x + RAM_A5E4;
    x = x + RAM_B2E4;
    x = x - RAM_A660;

    /* publish f32@A644 */
    OUT_A644 = x;
}