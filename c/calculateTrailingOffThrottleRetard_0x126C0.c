/* calculateTrailingOffThrottleRetard_0x126C0.c
 *
 * ROM: 60E0FC00 | Address: 0x126C0 | Code 0x126C0..0x127BE, literal pool
 * 0x12740..0x127CA (shared block with the leading twin @0x125B0 over
 * 0x12740..0x12766).
 *
 * RANGE NOTE: the symbols CSV row (0x0126C0,0x0127CC,calculateTrailing-
 * OffThrottleRetard?,ghidra-hand) is CORRECT for the code: the function runs to
 * the `rts` @0x127BC (delay mov.l @r15+,r14 @0x127BE), the pool ends @0x127CA,
 * and the next function (FUN_000127cc) starts exactly at the CSV end 0x127CC.
 * No phantom rows; no correction needed.  The trailing "?" on the CSV name is
 * dropped: the semantics resolve it — trailing-side structural twin of
 * defaultTimingMinMax (leading, 0x125B0, +4-shifted RAM addresses), applying a
 * timing retard whose magnitude (-69.2/-25/-20) is gated by an off-throttle
 * hysteresis latch on f32@C0D8.
 *
 * ENTRY VERIFICATION: 0x126C0 matches the symbols CSV start.  Valid entry: opens
 * with the standard prologue (mov.l r14,@-r15 ; three fmov.s fr N,@-r15 ;
 * sts.l pr,@-r15).  The preceding function defaultTimingMinMax (0x125B0) ends
 * with `rts` @0x126BC (delay mov.l @r15+,r14 @0x126BE), so no fall-through into
 * us; no incoming branches into the middle.  The ROM literal @0x144CC is the
 * ONLY 32-bit reference to 0x126C0 in the binary — the function-pointer slot of
 * the engineControlCalculateTiming dispatcher (0x141FC) dispatch table
 * (immediately after calculateDSCLeadingTimingDerate @0x144C8 and before
 * calculateTrailingDerateRetard @0x144D0).  The CSV address IS the real entry.
 *
 * SEMANTICS (instruction-for-instruction, see disasm): the trailing-side
 * off-throttle retard writer — byte-for-byte the same skeleton as the leading
 * defaultTimingMinMax @0x125B0 with +4-shifted RAM addresses.  It runs the
 * isNotZero_wDivideByZeroProtect leaf @0x2440 three times over a 1e-5 deadband,
 * maintains a sticky off-throttle latch byte, then publishes a trailing timing
 * retard (one of -69.2/-25/-20):
 *
 *   s = isNotZero_0x2440(f32@A754, 0, 1e-5)    // |A754| > 1e-5 ?
 *   r = isNotZero_0x2440(f32@A664, 0, 1e-5)    // |A664| > 1e-5 ?
 *   t = isNotZero_0x2440(f32@C8A4, 0, 1e-5)    // |C8A4| > 1e-5 ?
 *
 *   // sticky off-throttle latch u8@A65F, hysteresis on f32@C0D8 vs 0.5/(0.5-0.05):
 *   if     f32@C0D8 >  0.5f :     u8@A65F = 1
 *   elif   f32@C0D8 >  0.5f-0.05: u8@A65F = <unchanged (sticky prior value)>
 *   else                          u8@A65F = 0
 *
 *   // trailing retard f32@A658:
 *   if     u8@AAC6 == 1:          f32@A658 = (r != 0) ? -20.0f : -25.0f
 *   elif   t == 0 && s == 0:      f32@A658 = -69.2f
 *   else:                         f32@A658 = (u8@A65F == 1) ? -69.2f : -20.0f
 *
 *   return r0: u8@AAC6==1 -> (r & 0xFF) ; else if t==0&&s==0 -> u8@AAC6 ;
 *              else -> u8@A65F (final latch value, 0/1 or sticky prior).
 *
 * NaN semantics (matches the emulator byte-for-byte): every fcmp/gt clears T on
 * NaN, so a NaN f32@C0D8 drives the latch to 0 and a NaN deadband input reads 0
 * (helper returns 0).  All stack usage is the 0xFFFFDEE4..0xFFFFDF00 window
 * (r14 + fr13/fr14/fr15 + PR saves + 8 scratch bytes) - inside the task-stack
 * inspection window skipped by the harness.
 *
 * LITERAL POOL (values verified against roms/stock/60E0FC00.bin):
 *   mov.w 0x12742=0xC0D8, 0x12744=0xA754, 0x12746=0xA664, 0x12748=0xC8A4,
 *         0x12740=0xAAC6 (shared with twin)
 *   mov.l 0x12768=0x00002440 (isNotZero), 0x12770=0xFFFFA65F (latch byte),
 *         0x12774=0x0006E0C4 (0.5f), 0x12778=0xFFFFA658 (output),
 *         0x1277C=0x0006E0D8 (-25.0f), 0x12780=0x0006E0E8 (-20.0f),
 *         0x127C0=0x0006E0DC (-69.2f), 0x127C4=0x0006E0E0 (-69.2f),
 *         0x127C8=0x0006E0EC (-20.0f), 0x1274C=0x0006E0C8 (0.05f) (shared)
 *   mova 0x1276C = 1e-5f deadband (own; f1 uses its own @0x12644)
 * RAM r/w: reads C0D8, A754, A664, C8A4, AAC6 (byte), A65F (byte, sticky prior);
 *          writes A65F (byte), A658 (f32).  No RAM sub-call beyond isNotZero
 *          @0x2440 (x3, verified separately in c/math_primitives.c + c/complement_
 *          shift_u32.c).  SH-2E conv: float args fr4/fr5/fr6, u32 result r0.
 *
 * VERIFIED against the SH-2 emulator (tools/sh2emu.py, 60E0FC00.bin) in
 * c/tests/test_calculateTrailingOffThrottleRetard_0x126C0.py — 0 mismatches over
 * 5 seeds x 100000 iterations (byte-exact full post-call RAM overlay + r0).
 */
#include <stdint.h>

/* ---- RAM globals (mov.w literals sign-extend to 0xFFFFxxxx) ---- */
#define RAM_C0D8 (*(volatile float  *)0xFFFFC0D8) /* latch input (throttle-like) */
#define RAM_A754 (*(volatile float  *)0xFFFFA754) /* deadband input 1 (trailing) */
#define RAM_A664 (*(volatile float  *)0xFFFFA664) /* deadband input 2            */
#define RAM_C8A4 (*(volatile float  *)0xFFFFC8A4) /* deadband input 3            */
#define RAM_AAC6 (*(volatile uint8_t *)0xFFFFAAC6) /* mode gate byte (==1)       */
#define RAM_A65F (*(volatile uint8_t *)0xFFFFA65F) /* sticky off-throttle latch */
#define OUT_A658 (*(volatile float  *)0xFFFFA658) /* trailing retard output      */

/* ---- ROM calibration constants (confirmed against roms/stock/60E0FC00.bin) ---- */
#define CAL_THRESH_HI   (*(const float *)0x0006E0C4) /* 0.5f   (latch set hi)     */
#define CAL_THRESH_DELTA (*(const float *)0x0006E0C8) /* 0.05f  (latch hysteresis) */
#define CAL_N25         (*(const float *)0x0006E0D8) /* -25.0f                   */
#define CAL_N20a        (*(const float *)0x0006E0E8) /* -20.0f                   */
#define CAL_N69_2a      (*(const float *)0x0006E0DC) /* -69.2f (min-retard)       */
#define CAL_N69_2b      (*(const float *)0x0006E0E0) /* -69.2f (sticky-on retard) */
#define CAL_N20b        (*(const float *)0x0006E0EC) /* -20.0f (sticky-off retard)*/
#define CAL_DEADBAND    (*(const float *)0x0001276C) /* 1e-5f                    */

/* ---- External helper (in ROM, verified separately) ---- */
extern uint32_t complement_shift_u32(float value, float center, float tolerance);
/* @0x2440 (= isNotZero_wDivideByZeroProtect): 1 if |value - center| > tolerance */

int32_t calculateTrailingOffThrottleRetard_0x126C0(void)
{
    uint32_t s, r, t;

    s = complement_shift_u32(RAM_A754, 0.0f, CAL_DEADBAND);   /* |A754| > 1e-5 */
    r = complement_shift_u32(RAM_A664, 0.0f, CAL_DEADBAND);   /* |A664| > 1e-5 */
    t = complement_shift_u32(RAM_C8A4, 0.0f, CAL_DEADBAND);   /* |C8A4| > 1e-5 */

    /* sticky off-throttle latch: hysteresis on f32@C0D8 vs 0.5 / 0.45 */
    if (RAM_C0D8 > CAL_THRESH_HI) {
        RAM_A65F = 1;
    } else if (RAM_C0D8 > (CAL_THRESH_HI - CAL_THRESH_DELTA)) {
        RAM_A65F = RAM_A65F;                 /* unchanged (sticky prior) */
    } else {
        RAM_A65F = 0;
    }

    /* trailing retard (min/max selection) */
    if (RAM_AAC6 == 1) {
        OUT_A658 = (r != 0) ? CAL_N20a : CAL_N25;
    } else if (t == 0 && s == 0) {
        OUT_A658 = CAL_N69_2a;
    } else {
        OUT_A658 = (RAM_A65F == 1) ? CAL_N69_2b : CAL_N20b;
    }

    /* return r0: (r&0xFF) if AAC6==1, else u8@AAC6 if t==0&&s==0, else the
     * final sticky byte u8@A65F (the emulator leaves it in r0). */
    if (RAM_AAC6 == 1) return (int32_t)(r & 0xFF);
    if (t == 0 && s == 0) return (int32_t)RAM_AAC6;
    return (int32_t)RAM_A65F;
}