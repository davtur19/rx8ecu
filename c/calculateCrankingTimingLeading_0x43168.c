/* calculateCrankingTimingLeading_0x43168.c
 *
 * ROM: 60E0FC00 | Address: 0x43168 | Size: 0x7E (126) bytes per CSV range
 * 0x43168..0x431E6.  Code runs to the `rts` @0x431E2 (delay mov.l @r15+,r14
 * @0x431E4); the trailing twin calculateCrankingTimingTrailing starts at the
 * CSV end 0x431E6.  The CSV range is CORRECT (function code to 0x431E4, next
 * function exactly at 0x431E6) - no phantom rows.  The shared mov.w/mov.l
 * literal pool @0x43250..0x43284 for this (leading) twin and @0x43288..0x432AE
 * for the trailing twin are PHYSICALLY inside the trailing CSV range
 * (0x431E6..0x432B0) because the two twins share them - the same documented
 * pattern as calculateLeadingTimingBase_0x11F78 (pool @0x12092..0x120EC).
 *
 * ENTRY VERIFICATION: 0x43168 matches the symbols CSV start.  Valid entry:
 * opens with the standard prologue (`mov.l r14,@-r15 ; mov.l r13,@-r15 ;
 * mov.l r12,@-r15 ; sts.l pr,@-r15`).  The preceding function
 * throttleLiftInitStuff (0x04315C) ends rts @0x43166 - no fall-through into
 * us.  Called via the function-pointer slot @0x1444C of the
 * engineControlCalculateTiming dispatcher (0x141FC) dispatch table; the
 * trailing twin slot @0x14450 sits right next to it.  The ROM literal @0x1444C
 * is the ONLY 32-bit reference to 0x43168 in the binary.  The CSV address IS
 * the real entry point.
 *
 * SEMANTICS (instruction-for-instruction, see disasm): cranking-timing driver
 * for one rotor (LEADING).  Gated by two flag bytes; when active it computes a
 * temp-indexed advance value via TwoDLookup and publishes it to the final
 * f32@FFFFC99C (a u8 "state latch" @FFFFC9AC and the working f32@FFFFC9A4 are
 * also written every active pass).  Structure:
 *
 *   if u8@FFFFAAC6 == 1 AND u8@FFFFB588 == 1:      // engine + crank gate
 *       twoD = TwoDLookup(desc 0x699CC, x=f32@FFFFA9FC)    // u8 temp map *0.5 -50
 *       TMP C = twoD                       // f32@FFFFC9A4 working
 *       if u8@FFFFC9AC == 0:               // "state NOT yet latched" path
 *           // upper const @0x79794 (= +1.0) > 0.0 is ALWAYS true, so the
 *           // min/ratio step always runs (the branch is dead):
 *           c = minValue_0x23F4(+1.0, +1.0)          // -> 1.0
 *           FIN = ratio_0x3E0AC(twoD, c)             // twoD / 1.0 (0x3E0AC)
 *       else:                             // "state latched" path
 *           FIN = filters0_0x23B0(twoD, FIN, 1.0, 1.0e-5)   // (0x23B0)
 *                        // blend w/ weight 1.0, max-delta 1.0e-5 -> passthrough
 *       u8@FFFFC9AC = u8@FFFFB588          // re-latch state (= 1)
 *   else:                                  // gate open, no crank
 *       TMP = 0.0 ; FIN = 0.0            // zero both
 *       u8@FFFFC9AC = u8@FFFFB588
 *
 * NOTE: both helper branches end up publishing FIN = twoD for typical inputs,
 * but the float paths differ (division by 1.0 on the "state==0" path vs a
 * 1.0e-5-delta-filtered passthrough on the latched path) and the NaN handling
 * of the two leaves differs, so the sub-calls MUST be made in the emulator; the
 * reference model mirrors this via the helper-leaves technique (test file).
 *
 * LITERAL POOL (values verified against roms/stock/60E0FC00.bin; shared with the
 * trailing twin):
 *   0x43250 0xC99C     (mov.w -> f32 final output @FFFFC99C, leading)
 *   0x43254 0xB588     (mov.w -> u8 gate @FFFFB588)
 *   0x43256 0xAAC6     (mov.w -> u8 gateway @FFFFAAC6)
 *   0x43258 0xA9FC     (mov.w -> f32 temp input @FFFFA9FC)
 *   0x4325C 0xC9A4     (mov.l -> f32 working temp @FFFFC9A4)
 *   0x43264 0x000699CC (mov.l -> TwoDLookup desc, 9-pt u8 temp map)
 *   0x43268 0x00002068 (mov.l -> TwoDLookup helper @0x2068)
 *   0x4326C 0xFFFFC9AC (mov.l -> u8 state @FFFFC9AC)
 *   0x43270 0x00079794 (mov.l -> f32 +1.0, "state==0" min upper)
 *   0x43274 0x000023F4 (mov.l -> minValue helper @0x23F4)
 *   0x43278 0x0003E0AC (mov.l -> ratio helper @0x3E0AC)
 *   0x4327C 1.0e-5     (mova inline f32, filter max delta)
 *   0x43280 0x00079798 (mov.l -> f32 +1.0, filter weight)
 *   0x43284 0x000023B0 (mov.l -> filters helper @0x23B0)
 * RAM r/w: reads AAC6, B588, A9FC, C9AC(prev); writes C9A4, C99C, C9AC + stack.
 * ROM read: descriptor @0x699C (axis @0x797A4, values @0x797C8) and the f32
 *   consts @0x79794/0x79798/@0x4327C.
 * Sub-calls: TwoDLookup @0x2068 (x1); then one of {minValue @0x23F4 + ratio
 *   @0x3E0AC} or filters @0x23B0, chosen by u8@C9AC.
 * r0 on return: equals 0x00079794 ("state==0" path), (bits of f32@C99C &
 *   0x7F800000) on the latched path, or the failing gate byte & 0xFF on the
 *   early-exit path - carried byte-exact by the emulator comparison.
 * TWIN (structural): calculateCrankingTimingTrailing @0x431E6. Differences ONLY:
 *   outputs f32@C9A8 (temp) & f32@C9A0 (final), state u8@FFFFC9AD, desc 0x699E0,
 *   f32 consts 0x79794->0x7979C, 0x79798->0x797A0 (all = +1.0; 0x699E0 is a flat
 *   map vs the leading's shaped temp map). Same skeleton, same helpers/pool.
 *
 * VERIFIED against the SH-2 emulator (tools/sh2emu.py, roms/stock/60E0FC00.bin)
 * in c/tests/test_calculatecrankingTimingLeading_0x43168.py - 0 mismatches over
 * 5 seeds x 100000 iterations (byte-exact full post-call RAM overlay + r0).
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
#define ST_C9AC   (*(volatile uint8_t *)0xFFFFC9AC)  /* u8 state latch  r+w      */
#define TMP_C9A4  (*(volatile float  *)0xFFFFC9A4)   /* f32 working advance r+w  */
#define FIN_C99C  (*(volatile float  *)0xFFFFC99C)   /* f32 final advance  r+w   */

/* ---- ROM calibration constants ---- */
#define ROM_P_79794 (*(const float *)0x00079794)   /* f32 +1.0, state==0 min upper */
#define ROM_P_79798 (*(const float *)0x00079798)   /* f32 +1.0, filter weight      */
#define ROM_D_4327C (*(const float *)0x0004327C)   /* f32 1.0e-5, filter max delta */

#define DESC_699CC ((const Map1D *)0x000699CC)     /* 9-pt u8 temp map */

/* ---- verified ROM leaves ---- */
extern float TwoDLookup(const Map1D *m, float x);              /* 0x2068 */
extern float minValue(float a, float b);                       /* 0x23F4 */
extern float ratio(float num, float den);                      /* 0x3E0AC */
extern float filters(float neu, float old, float w, float d);  /* 0x23B0 */

void calculateCrankingTimingLeading_0x43168(void)
{
    float twoD;
    if (G_AAC6 == 1 && GATE_B588 == 1) {          /* cmp/eq #1 x2 ; bf/s x2   */
        twoD = TwoDLookup(DESC_699CC, TEMP_A9FC); /* jsr 0x2068 @0x43190      */
        TMP_C9A4 = twoD;
        if (ST_C9AC == 0) {                       /* tst ; bf/s @0x4319C      */
            float c = minValue(ROM_P_79794, 1.0f);/* jsr @0x23F4 @0x431AE     */
            FIN_C99C = ratio(twoD, c);            /* jsr @0x3E0AC @0x431B6    */
        } else {
            FIN_C99C = filters(twoD, FIN_C99C,
                               ROM_P_79798, ROM_D_4327C); /* jsr @0x23B0     */
        }
        ST_C9AC = GATE_B588;                      /* mov.b r12,@r2 @0x431DA  */
    } else {
        TMP_C9A4 = 0.0f;                          /* fldi0 ; fmov.s @r14      */
        FIN_C99C = 0.0f;                          /* fmov.s fr4,@r13 @0x431D6 */
        ST_C9AC = GATE_B588;
    }
}