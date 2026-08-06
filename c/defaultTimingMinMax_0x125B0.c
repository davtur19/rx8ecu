/* defaultTimingMinMax_0x125B0.c
 *
 * ROM: 60E0FC00 | Address: 0x125B0 | Code 0x125B0..0x126BE, literal pool
 * shared with the trailing twin @0x126C0 over 0x12740..0x12766 (own pool
 * 0x12624..0x1264E).
 *
 * RANGE NOTE: the symbols CSV row (0x0125B0,0x0126C0,defaultTimingMinMax,
 * ghidra-hand) is CORRECT for the code: the function runs to the `rts` @0x126BC
 * (delay mov.l @r15+,r14 @0x126BE), and the trailing twin calculateTrailing-
 * OffThrottleRetard starts exactly at the CSV end 0x126C0.  The mov.l literal
 * pool at 0x1274C..0x12766 sits beyond the CSV end but belongs to the shared
 * pool block 0x12740..0x127CA owned by the trailing twin (same sharing pattern
 * as the calculateLeading/TrailingDerateRetard pair).  No phantom rows; no
 * correction needed.
 *
 * ENTRY VERIFICATION: 0x125B0 matches the symbols CSV start.  Valid entry: opens
 * with the standard prologue (mov.l r14,@-r15 ; three fmov.s fr N,@-r15 ;
 * sts.l pr,@-r15).  The preceding function calculateTrailingDerateRetard
 * (0x12576) ends with `rts` @0x125AC (delay fmov.s @r15+,fr12 @0x125AE), so no
 * fall-through into us; no incoming branches into the middle.  The ROM literal
 * @0x144B8 is the ONLY 32-bit reference to 0x125B0 in the binary — the
 * function-pointer slot of the engineControlCalculateTiming dispatcher (0x141FC)
 * dispatch table (immediately before calculateLeadingDerateRetard @0x144BC and
 * calculateLeadingTimingBaseFinal @0x144C0).  The CSV address IS the real entry.
 *
 * SEMANTICS (instruction-for-instruction, see disasm): the leading-side "default
 * timing min/max" derate writer — structural twin of the trailing function
 * calculateTrailingOffThrottleRetard @0x126C0 (byte-for-byte the same +4-shifted
 * skeleton).  It runs the isNotZero_wDivideByZeroProtect leaf @0x2440 three
 * times over a 1e-5 deadband, maintains a sticky off-throttle-style latch byte,
 * then publishes a default timing derate (one of -58.5/-25/-20):
 *
 *   s = isNotZero_0x2440(f32@A750, 0, 1e-5)    // |A750| > 1e-5 ?
 *   r = isNotZero_0x2440(f32@A660, 0, 1e-5)    // |A660| > 1e-5 ?
 *   t = isNotZero_0x2440(f32@C8A0, 0, 1e-5)    // |C8A0| > 1e-5 ?
 *
 *   // sticky latch u8@A65E, hysteresis on f32@C0D8 vs 0.5 / (0.5-0.05):
 *   if     f32@C0D8 >  0.5f :     u8@A65E = 1
 *   elif   f32@C0D8 >  0.5f-0.05: u8@A65E = <unchanged (sticky prior value)>
 *   else                          u8@A65E = 0
 *
 *   // default timing derate f32@A648:
 *   if     u8@AAC6 == 1:          f32@A648 = (r != 0) ? -20.0f : -25.0f
 *   elif   t == 0 && s == 0:      f32@A648 = -58.5f
 *   else:                         f32@A648 = (u8@A65E == 1) ? -58.5f : -20.0f
 *
 *   return r0: u8@AAC6==1 -> (r & 0xFF) ; else if t==0&&s==0 -> u8@AAC6 ;
 *              else -> u8@A65E (final latch value, 0/1 or sticky prior).
 *
 * NaN semantics (matches the emulator byte-for-byte): every fcmp/gt clears T on
 * NaN, so a NaN f32@C0D8 drives the latch to 0 and a NaN deadband input reads 0
 * (helper returns 0).  All stack usage is the 0xFFFFDEE4..0xFFFFDF00 window
 * (r14 + fr13/fr14/fr15 + PR saves + 8 scratch bytes) - inside the task-stack
 * inspection window skipped by the harness.
 *
 * LITERAL POOL (values verified against roms/stock/60E0FC00.bin):
 *   mov.w 0x12624=0xC0D8 (own), 0x1260E=0xA750, 0x12614=0xA660, 0x1260C=0xC8A0,
 *         0x12740=0xAAC6 (shared with twin)
 *   mov.l 0x12640=0x00002440 (isNotZero, own), 0x12648=0xFFFFA65E (latch byte),
 *         0x1264C=0x0006E0C4 (0.5f), 0x12750=0xFFFFA648 (output),
 *         0x12754=0x0006E0A4 (-25.0f), 0x12758=0x0006E0BC (-20.0f),
 *         0x1275C=0x0006E0A8 (-58.5f), 0x12760=0x0006E0AC (-58.5f),
 *         0x12764=0x0006E0C0 (-20.0f), 0x1274C=0x0006E0C8 (0.05f) (shared)
 *   mova 0x12644 = 1e-5f deadband (own; f2 uses its own @0x1276C)
 * RAM r/w: reads C0D8, A750, A660, C8A0, AAC6 (byte), A65E (byte, sticky prior);
 *          writes A65E (byte), A648 (f32).  No RAM sub-call beyond isNotZero
 *          @0x2440 (x3, verified separately in c/math_primitives.c + c/complement_
 *          shift_u32.c).  SH-2E conv: float args fr4/fr5/fr6, u32 result r0.
 *
 * VERIFIED against the SH-2 emulator (tools/sh2emu.py, 60E0FC00.bin) in
 * c/tests/test_defaultTimingMinMax_0x125B0.py — 0 mismatches over 5 seeds x
 * 100000 iterations (byte-exact full post-call RAM overlay + r0).
 */
#include <stdint.h>

/* ---- RAM globals (mov.w literals sign-extend to 0xFFFFxxxx) ---- */
#define RAM_C0D8 (*(volatile float  *)0xFFFFC0D8) /* latch input (throttle-like) */
#define RAM_A750 (*(volatile float  *)0xFFFFA750) /* deadband input 1 (leading)    */
#define RAM_A660 (*(volatile float  *)0xFFFFA660) /* deadband input 2              */
#define RAM_C8A0 (*(volatile float  *)0xFFFFC8A0) /* deadband input 3              */
#define RAM_AAC6 (*(volatile uint8_t *)0xFFFFAAC6) /* mode gate byte (==1)         */
#define RAM_A65E (*(volatile uint8_t *)0xFFFFA65E) /* sticky off-throttle latch   */
#define OUT_A648 (*(volatile float  *)0xFFFFA648) /* default timing derate output */

/* ---- ROM calibration constants (confirmed against roms/stock/60E0FC00.bin) ---- */
#define CAL_THRESH_HI   (*(const float *)0x0006E0C4) /* 0.5f   (latch set hi)     */
#define CAL_THRESH_DELTA (*(const float *)0x0006E0C8) /* 0.05f  (latch hysteresis) */
#define CAL_N25         (*(const float *)0x0006E0A4) /* -25.0f                   */
#define CAL_N20a        (*(const float *)0x0006E0BC) /* -20.0f                   */
#define CAL_N58_5a      (*(const float *)0x0006E0A8) /* -58.5f (min-default)      */
#define CAL_N58_5b      (*(const float *)0x0006E0AC) /* -58.5f (sticky-on default)*/
#define CAL_N20b        (*(const float *)0x0006E0C0) /* -20.0f (sticky-off default)*/
#define CAL_DEADBAND    (*(const float *)0x00012644) /* 1e-5f                    */

/* ---- External helper (in ROM, verified separately) ---- */
extern uint32_t complement_shift_u32(float value, float center, float tolerance);
/* @0x2440 (= isNotZero_wDivideByZeroProtect): 1 if |value - center| > tolerance */

int32_t defaultTimingMinMax_0x125B0(void)
{
    uint32_t s, r, t;

    s = complement_shift_u32(RAM_A750, 0.0f, CAL_DEADBAND);   /* |A750| > 1e-5 */
    r = complement_shift_u32(RAM_A660, 0.0f, CAL_DEADBAND);   /* |A660| > 1e-5 */
    t = complement_shift_u32(RAM_C8A0, 0.0f, CAL_DEADBAND);   /* |C8A0| > 1e-5 */

    /* sticky latch: hysteresis on f32@C0D8 vs 0.5 / 0.45 */
    if (RAM_C0D8 > CAL_THRESH_HI) {
        RAM_A65E = 1;
    } else if (RAM_C0D8 > (CAL_THRESH_HI - CAL_THRESH_DELTA)) {
        RAM_A65E = RAM_A65E;                 /* unchanged (sticky prior) */
    } else {
        RAM_A65E = 0;
    }

    /* default timing derate (min/max selection) */
    if (RAM_AAC6 == 1) {
        OUT_A648 = (r != 0) ? CAL_N20a : CAL_N25;
    } else if (t == 0 && s == 0) {
        OUT_A648 = CAL_N58_5a;
    } else {
        OUT_A648 = (RAM_A65E == 1) ? CAL_N58_5b : CAL_N20b;
    }

    /* return r0: (r&0xFF) if AAC6==1, else u8@AAC6 if t==0&&s==0, else the
     * final sticky byte u8@A65E (the emulator leaves it in r0). */
    if (RAM_AAC6 == 1) return (int32_t)(r & 0xFF);
    if (t == 0 && s == 0) return (int32_t)RAM_AAC6;
    return (int32_t)RAM_A65E;
}