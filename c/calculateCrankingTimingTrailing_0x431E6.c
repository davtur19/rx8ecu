/* calculateCrankingTimingTrailing_0x431E6.c
 *
 * ROM: 60E0FC00 | Address: 0x431E6 | Size: 0xCA (202) bytes per CSV range
 * 0x431E6..0x432B0.  Code runs to the `rts` @0x432A8 (delay mov.l @r15+,r14
 * @0x432AA); the next function apvVoltageRange starts at the CSV end 0x432B0.
 * The CSV range is CORRECT (code to 0x432AA, pool to 0x432AE, next function at
 * 0x432B0) - no phantom rows.  This function OWNS the shared twin literal pool
 * @0x43250..0x432AE (the leading twin's mov.l entries @0x4325C..0x43284 live
 * inside this range too - shared, same pattern as calculateLeadingTimingBase
 * @0x11F78 vs its twin @0x1202A).
 *
 * ENTRY VERIFICATION: 0x431E6 matches the symbols CSV start.  Valid entry:
 * opens with the standard prologue (`mov.l r14,@-r15 ; mov.l r13,@-r15 ;
 * mov.l r12,@-r15 ; sts.l pr,@-r15`).  The preceding function
 * calculateCrankingTimingLeading (0x43168) ends rts @0x431E2 (delay @0x431E4)
 * - no fall-through into us.  Called via the function-pointer slot @0x14450 of
 * the engineControlCalculateTiming dispatcher (0x141FC) dispatch table,
 * immediately after the leading twin's slot @0x1444C.  The ROM literal @0x14450
 * is the ONLY 32-bit reference to 0x431E6 in the binary.  The CSV address IS
 * the real entry point.
 *
 * SEMANTICS: exact structural twin of calculateCrankingTimingLeading (0x43168)
 * for the other rotor (TRAILING).  Same gating, same helper schedule, same
 * latched-state logic - ONLY these constants differ (all verified against
 * roms/stock/60E0FC00.bin):
 *   f32 working temp @FFFFC9A8   (leading: @FFFFC9A4)
 *   f32 final output @FFFFC9A0   (leading: @FFFFC99C)
 *   u8 state latch  @FFFFC9AD    (leading: @FFFFC9AC)
 *   TwoDLookup desc 0x699E0      (leading: 0x699CC; both 9-pt u8 temp maps
 *                                  scale 0.5 offset -50; 0x699E0 is the FLAT
 *                                  map - cells all 100/110 - vs the leading's
 *                                  shaped map)
 *   f32 consts @0x7979C/+1.0 (min upper), @0x797A0/+1.0 (filter weight)
 *                                  (leading: @0x79794 / @0x79798)
 *   Same shared inline pool @0x4327C (1.0e-5 filter max delta), same helpers
 *   TwoDLookup @0x2068, minValue @0x23F4, ratio @0x3E0AC, filters @0x23B0.
 * r0 on return: 0x0007979C ("state==0" path), (bits of f32@C9A0 & 0x7F800000)
 *   on the latched path, or the failing gate byte & 0xFF on early exit.
 *
 * VERIFIED against the SH-2 emulator (tools/sh2emu.py, roms/stock/60E0FC00.bin)
 * in c/tests/test_calculateCrankingTimingTrailing_0x431E6.py - 0 mismatches
 * over 5 seeds x 100000 iterations (byte-exact full post-call RAM overlay + r0).
 */
#include <stdint.h>
#include <math.h>

/* ---- 1-D lookup descriptor (20 bytes, big-endian SH-2E; see c/2DLookup.c) ---- */
typedef struct {
    uint16_t     count;    /* +0 */
    uint8_t      type;     /* +2 */
    uint8_t      _pad;     /* +3 */
    const float *axis;     /* +4 */
    const void  *values;   /* +8 */
    float        scale;    /* +12 */
    float        offset;   /* +16 */
} Map1D;

/* ---- RAM globals (mov.w literals sign-extend to 0xFFFFxxxx) ---- */
#define GATE_B588 (*(volatile uint8_t *)0xFFFFB588)  /* u8 crank gate (==1)     */
#define G_AAC6    (*(volatile uint8_t *)0xFFFFAAC6)  /* u8 gateway    (==1)     */
#define TEMP_A9FC (*(volatile float  *)0xFFFFA9FC)   /* f32 temp x input        */
#define ST_C9AD   (*(volatile uint8_t *)0xFFFFC9AD)  /* u8 state latch  r+w      */
#define TMP_C9A8  (*(volatile float  *)0xFFFFC9A8)   /* f32 working advance r+w  */
#define FIN_C9A0  (*(volatile float  *)0xFFFFC9A0)   /* f32 final advance  r+w   */

/* ---- ROM calibration constants ---- */
#define ROM_P_7979C (*(const float *)0x0007979C)   /* f32 +1.0, state==0 min upper */
#define ROM_P_797A0 (*(const float *)0x000797A0)   /* f32 +1.0, filter weight      */
#define ROM_D_4327C (*(const float *)0x0004327C)   /* f32 1.0e-5, filter max delta */

#define DESC_699E0 ((const Map1D *)0x000699E0)     /* 9-pt u8 flat temp map */

/* ---- verified ROM leaves ---- */
extern float TwoDLookup(const Map1D *m, float x);              /* 0x2068 */
extern float minValue(float a, float b);                       /* 0x23F4 */
extern float ratio(float num, float den);                      /* 0x3E0AC */
extern float filters(float neu, float old, float w, float d);  /* 0x23B0 */

void calculateCrankingTimingTrailing_0x431E6(void)
{
    float twoD;
    if (G_AAC6 == 1 && GATE_B588 == 1) {          /* cmp/eq #1 x2 ; bf/s x2   */
        twoD = TwoDLookup(DESC_699E0, TEMP_A9FC); /* jsr 0x2068 @0x4320E      */
        TMP_C9A8 = twoD;
        if (ST_C9AD == 0) {                       /* tst ; bf/s @0x4321A      */
            float c = minValue(ROM_P_7979C, 1.0f);/* jsr @0x23F4 @0x4322C     */
            FIN_C9A0 = ratio(twoD, c);            /* jsr @0x3E0AC @0x43234    */
        } else {
            FIN_C9A0 = filters(twoD, FIN_C9A0,
                               ROM_P_797A0, ROM_D_4327C); /* jsr @0x23B0   */
        }
        ST_C9AD = GATE_B588;                      /* mov.b r12,@r2 @0x432A0  */
    } else {
        TMP_C9A8 = 0.0f;                          /* fldi0 ; fmov.s @r14      */
        FIN_C9A0 = 0.0f;                          /* fmov.s fr4,@r13 @0x4329C */
        ST_C9AD = GATE_B588;
    }
}