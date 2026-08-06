/* getEngineLimitTimingDerates_0x12CE8.c
 *
 * ROM: 60E0FC00 | Address: 0x12CE8 | Size: 0x48 (72) bytes per CSV range
 * 0x12CE8..0x12D30.  Code runs to the `rts` @0x12D00 (delay fmov.s fr0,@r3
 * @0x12D02, the trailing store); the literal pool fills 0x12D04..0x12D2E, and
 * the next function engineConditionDetectForTimingModification (0x12D30)
 * starts exactly at the CSV end.  The CSV range is CORRECT (code+pool to
 * 0x12D2E, next function exactly at 0x12D30) — no correction needed.
 *
 * ENTRY VERIFICATION: 0x12CE8 matches the symbols CSV start.  Valid entry:
 * opens straight with a mov.l literal load.  The preceding somethingEngine
 * LoadCalc (0x12BD6) ends with `rts` @0x12CE0 (delay @0x12CE2), so there is
 * no fall-through into us; no incoming branches into the body.  Called via
 * the function-pointer slot @0x14444 of the engineControlCalculateTiming
 * dispatcher (0x141FC) dispatch table.  The ROM literal @0x14444 is the ONLY
 * 32-bit reference to 0x12CE8 in the binary.  The CSV address IS the real
 * entry point.
 *
 * SEMANTICS (instruction-for-instruction, see disasm): a small single-rotation
 * derate-scale getter-writing pair.  It reads two limit-timing derate floats
 * and stores them, each scaled by one shared calibration factor (a ROM float
 * constant read through r4 = 0x0007266C, value 1.0 in this stock image):
 *
 *   factor = f32@0x0007266C                       ; ROM constant (1.0f stock)
 *   DERATE_LEAD = *(volatile float*)0xFFFFA674    ; limit lead derate input
 *   DERATE_TRAIL= *(volatile float*)0xFFFFA678    ; limit trail derate input
 *   OUT_A660 = factor * DERATE_LEAD               ; mov right-hand chain, store A660
 *   OUT_A664 = factor * DERATE_TRAIL              ; fmul in r-return, store A664 (delay)
 *
 * Actual instruction order (see disasm):
 *   fr2 = f32@0x0007266C              (fmov.s @r4,fr2 ; r4=0x0007266C)
 *   fr3 = f32@0xFFFFA674              (fmov.s @r3,fr3)
 *   mov.w r2 = 0xFFFFA660 (sign-ext)  (r2 = 0xA660)
 *   fmul fr3,fr2  -> fr2 = factor * A674
 *   mov.l r1 = 0xFFFFA678
 *   fmov.s fr2,@r2                    -> f32@A660 = fr2
 *   fr1 = f32@0xFFFFA678              (fmov.s @r1,fr1)
 *   fr0 = f32@0x0007266C              (fmov.s @r4,fr0)
 *   mov.w r3 = 0xFFFFA664             (r3 = 0xA664)
 *   fmul fr1,fr0  -> fr0 = factor * A678
 *   rts
 *   fmov.s fr0,@r3  (delay)           -> f32@A664 = fr0
 *
 * Return value / register contract:
 *   r0 on return = 0 — no integer register is touched (all work is float).
 *   fr0 = f32@A664 = factor * A678 (float return, unused).
 * Two RAM float writes: A660, A664.  No stack frame, no sub-calls.
 *
 * NaN / inf semantics: exact single-precision fmul (round-to-nearest via the
 * emulator's ts()).  A NaN factor or NaN derate propagates through fmul.
 * With the stock factor = 1.0 this is an identity scale; the code is written
 * to preserve the multiplication so it stays exact for any factor.
 *
 * VERIFIED against the SH-2 emulator (tools/sh2emu.py, 60E0FC00.bin) in
 * c/tests/test_getEngineLimitTimingDerates_0x12CE8.py — 0 mismatches over
 * 5 seeds x 100000 iterations (byte-exact full post-call RAM overlay + r0).
 */
#include <stdint.h>

/* ---- RAM float globals (mov.w/mov.l sign-extension to 0xFFFFxxxx) ---- */
#define IN_A674   (*(volatile float *)0xFFFFA674)   /* limit lead derate   */
#define IN_A678   (*(volatile float *)0xFFFFA678)   /* limit trail derate  */
#define OUT_A660  (*(volatile float *)0xFFFFA660)   /* scaled lead out     */
#define OUT_A664  (*(volatile float *)0xFFFFA664)   /* scaled trail out    */

void getEngineLimitTimingDerates_0x12CE8(void)
{
    volatile float *factor_ptr = (volatile float *)0x0007266C;  /* ROM const 1.0 */

    float factor = *factor_ptr;    /* fmov.s @r4, fr2 ; mov.l r4 = 0x0007266C */
    float d = factor * IN_A674;    /* fr2 = factor * f32@A674                 */
    OUT_A660 = d;                  /* fmov.s fr2,@r2  (r2 = A660)             */

    OUT_A664 = factor * IN_A678;   /* fmul fr1,fr0 -> fr0 ; fmov.s fr0,@r3 */
}