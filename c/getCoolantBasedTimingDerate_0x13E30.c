/* getCoolantBasedTimingDerate_0x13E30.c
 *
 * ROM: 60E0FC00.bin | Address: 0x13E30 | Range 0x013E30..0x013E98 (CSV)
 *
 * ENTRY VERIFICATION: 0x13E30 IS the real entry.  Opens with the standard
 * prologue (fmov.s fr15/fr14/fr13,@-r15 ; sts.l pr,@-r15) and runs to `rts`
 * @0x13E94 (delay fmov.s @r15+,fr15 @0x13E96).  The preceding function
 * debounceThrottleRate (0x13E04) ends rts, so no fall-through.  The ONLY
 * 32-bit ROM reference to 0x13E30 is the function-pointer slot @0x14438 of the
 * engineControlCalculateTiming dispatcher (0x141FC) dispatch table
 * (0x14404..0x14458) — real dispatch slot.  The CSV range end 0x13E98 is the
 * start of the cataloged sub-function floatArrayToByteArrayLookup1 @0x13E98
 * (separate CSV row), so the range is CORRECT (same boundary pattern as
 * defaultTimingMinMax_0x125B0) — no correction needed.
 *
 * SEMANTICS: publishes the coolant-based per-side (leading/trailing) timing
 * derate cells that the derate-min/max dispatcher layer reads later.  It
 * resolves a coolant-vs-calibration ratio x clamped to [0,1] and scales the
 * two coolant lookups:
 *
 *   v  = f32_to_float_0x2500((float)byte@A758)   // source byte -> f32
 *   c1 = floatArrayToByteArrayLookup1_0x13E98(v) // coolant lookup 1 (fm float)
 *   c2 = floatArrayToByteArrayLookup2_0x13F60(v) // coolant lookup 2
 *   f32@A76C = c1 ; f32@A77(?= c2               // intermediate write-throughs
 *
 *   num = f32@A9F8 - f32@0x000727E4
 *   den = f32@0x000727E8 - f32@0x000727E4
 *   x   = clamp_0x2404( guarded_div_0x3E0AC(num,den), 0.0f, 1.0f )
 *   f32@A750 = x * c1      ; /* leading coolant timing derate */
 *   f32@A754 = x * c2      ; /* trailing coolant timing derate */
 *
 * Sub-calls (each is a real ROM function executed by this lift's test):
 *   0x2500 f32_to_byte: (float)byte  = fr4*byte + fr5 with fr4=1,fr5=0
 *   0x13E98 floatArrayToByteArrayLookup1(x) — coolant derate lookup -> f32
 *        (also writes its index byte @A774)
 *   0x13F60 floatArrayToByteArrayLookup2(x) — trailing-twin of 0x13E98 -> f32
 *        (also writes its index byte @A775)
 *   0x3E0AC guarded_div(num,den): num/den ; if den==0 -> 0.0 (0/0) else the
 *        FLT_MAX sentinel +/- (non-zero/0); exact bytes of the ROM diverge
 *   0x2404 clamp(x,lo,hi): min(max(x,lo),hi), NaN -> lo
 *
 * Verified byte-exact against tools/sh2emu.py + the real 60E0FC00.bin in
 * c/tests/test_getCoolantBasedTimingDerate_0x13E30.py — 0 mismatches over
 * 5 seeds x 100000 (full post-call RAM overlay, task-stack window skipped).
 */
#include <stdint.h>

/* ---- RAM cells (mov.l literals, 0xFFFFxxxx) ---- */
#define RAM_A758 (*(volatile uint8_t *)0xFFFFA758)
#define RAM_A9FC (*(volatile float  *)0xFFFFA9FC)
#define RAM_A76C (*(volatile float  *)0xFFFFA76C)
#define RAM_A770 (*(volatile float  *)0xFFFFA770)
#define OUT_A750 (*(volatile float  *)0xFFFFA750)
#define OUT_A754 (*(volatile float  *)0xFFFFA754)
#define OUT_A774 (*(volatile uint8_t *)0xFFFFA774) /* lookup1 index */
#define OUT_A775 (*(volatile uint8_t *)0xFFFFA775) /* lookup2 index */

/* ROM calibration constants (values in roms/stock/60E0FC00.bin) */
#define CAL_727E4 (*(const float *)0x000727E4)
#define CAL_727E8 (*(const float *)0x000727E8)

extern float f32_to_byte_0x2500(uint8_t byte, float scale, float add);
extern float lookup1_0x13E98(float value);
extern float lookup2_0x13F60(float value);
extern float guarded_div_0x3E0AC(float num, float den);
extern float clamp_0x2404(float x, float lo, float hi);

void getCoolantBasedTimingDerate_0x13E30(void)
{
    float v  = f32_to_byte_0x2500(RAM_A758, 1.0f, 0.0f);
    float c1 = lookup1_0x13E98(v);
    float c2 = lookup2_0x13F60(v);

    RAM_A76C = c1;
    RAM_A770 = c2;

    float num = RAM_A9FC - CAL_727E4;
    float den = CAL_727E8 - CAL_727E4;
    float x   = clamp_0x2404(guarded_div_0x3E0AC(num, den), 0.0f, 1.0f);

    OUT_A750 = x * c1;   /* leading  coolant timing derate */
    OUT_A754 = x * c2;   /* trailing coolant timing derate */
}