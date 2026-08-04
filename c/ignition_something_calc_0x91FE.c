/* ignition_something_calc_0x91FE.c
 *
 * ROM: 60E1D400  |  Address: 0x91FE  |  body 0x91FE..0x9320 entry + tail-arms
 *       0x9478/0x9320 (leaves).  VERIFIED vs ROM emulator (0 mismatches,
 *       c/tests/test_ignition_something_calc_0x91FE.py, 500000 random inputs
 *       across 5 seeds).
 *
 * CSV / merged-xmap name: "ignitonSomethingCalc" (sic, symbols/symbols_60E1D400_merged.csv,
 * ghidra-hand-xmap).  Semantic name: spark-angle wrap + compare-timer arming.
 * This is the 60E1D400 instance of the shared arming helper tail-called by both
 * outputSpark1 @0x8DE6 (c/output_spark_0x8DE6.c) and outputSpark2 @0x8E20
 * (c/output_spark2_0x8E20.c).  The 60E0FC00 sibling is @0x91C6 (same opcodes,
 * different base; literal-pool bytes obtained by decoding the ROM .bin because
 * the annotated .s renders the pools as spurious instructions).
 *
 * Semantics (execution order), with the literal-pool constants decoded from the
 * .bin:  L_0x9248=0xFFFFA0FC, L_0x9274=0xFFFFA0F8, L_0x924C=-90.0,
 * L_0x9250=720.0, L_0x9254=630.0, L_0x9258=-720.0, L_0x9310=30.0,
 * L_0x9318=60.0, L_0x9308=0xFFFFA0C4, L_0x930C=0xFFFFA0D4, L_0x9314=0xFFFFA100,
 * L_0x931C=0x0000DAB4.
 *
 *   1. base = f32@0xFFFFA0FC;  v = f32@(0xFFFFA0D8+idx*8) - base.
 *   2. wrap v into [-90, 630):
 *        v < -90 -> w = v + 720    |    -90 <= v < 630 -> w = v
 *        v >= 630 -> w = v - 720
 *      (NOTE: SH-2E fcmp/gt FRm,FRn = FRn > FRm; the disasm "fcmp/gt fr4,fr1"
 *       whose literal operands are FRm=fr4(v),FRn=fr1(-90) reverses the naive
 *       reading.  NaN takes the v >= 630 fallback -> w = NaN.)
 *      w is stored to f32@0xFFFFA0F8 (the wrapped-out scratch, then consumed by
 *      the arming leaves).
 *   3. If ch[5] == 0 (channel not already armed): compute a timer count
 *        fpul = 0xFFFFA0C4[idx] + u16@0xFFFFA0D4 * 16
 *        count = (float)s32(fpul) * 30.0 / (float)s32(u32@0xFFFFA100)
 *      and arm ONLY when (w - count) < 60.0 deg: call 0x9478 (pre-arm
 *      retrigger: writes desc[] compare values, calls 0xAA74, sets ch[5]=1,
 *      ch[6]=0) then tail-call 0x9320 (compare-timer arm/build).  Otherwise
 *      return with the channel untouched.
 *   4. If ch[5] != 0 (already armed): desc = u32@(0x0000DAB4 + idx*24); if the
 *      first word @desc == 0, disarm (ch[4]=0, ch[5]=0); else tail-call 0x9320.
 *
 *   The fdiv in step 3 divides by float(s32(u32@0xFFFFA100)); a divisor of 0
 *   raises a divide-by-zero on the real FPU (and ZeroDivisionError in the
 *   emulator), so the test harness seeds it non-zero.  The leaves 0x9478 and
 *   0x9320 are executed in the emulator by the harness (cpu2.call pattern) and
 *   their full-RAM effects merged, so this lift transcribes the entry wrap +
 *   dispatch + count/arm-decision logic and delegates the hardware arming to
 *   those verified tails (same approach as the 0x19220 split lift).
 *
 * Inputs (RAM reads): f32 @0xFFFFA0FC (wrap base), f32 @0xFFFFA0D8+idx*8
 *   (spark value), ch[5] (armed flag), u32 @0xFFFFA0C4+idx*4 (base pointer),
 *   u16 @0xFFFFA0D4 (dwell), u32 @0xFFFFA100 (deg->count divisor), descriptor
 *   u32@0x0000DAB4+idx*24 (+ pointed words).
 * Outputs (RAM writes): f32 @0xFFFFA0F8 (wrapped), ch[4]/ch[5] (disarm path),
 *   and everything the 0x9478 / 0x9320 leaves write (compare-timer descriptor
 *   words and the ch[5]/ch[6] flags) — all merged in the full-RAM diff.
 *   getSR(0x2054)/setSR(0x2064) touched by the leaves alter only SR.
 *
 * Naming note: "ignitonSomethingCalc" (xmap) matches this wrap+arm behavior;
 * the more descriptive name is "wrap_and_arm_compare_timer".  CSV names left
 * untouched per repo rules.
 */
#include <stdint.h>

#define RAM_TABLE   ((volatile uint8_t *)0xFFFFA0D8)  /* per-channel table, stride 8 */
#define F32_A0FC    (*(volatile float    *)0xFFFFA0FC) /* wrap base offset          */
#define F32_A0F8    (*(volatile float    *)0xFFFFA0F8) /* wrapped-out scratch       */
#define U32_A0C4    ((volatile uint32_t  *)0xFFFFA0C4) /* per-channel u32 base ptr  */
#define U16_A0D4    (*(volatile uint16_t  *)0xFFFFA0D4)/* dwell (u16)               */
#define U32_A100    (*(volatile uint32_t  *)0xFFFFA100)/* deg->count divisor (u32)  */
#define DESC_DAB4   ((volatile uint32_t  *)0x0000DAB4) /* per-channel descriptor    */

/* 0x9478 — pre-arm/set-output helper ("sensor_filter_apply" mislabel).  Writes
 * compare values via the descriptor's [4]/[8] pointers, calls the retrigger
 * 0xAA74 (stores r5's 0x3E80 into desc[0]'s target), then sets ch[5]=1, ch[6]=0. */
extern void retrigger_arm_prepare_0x9478(uint8_t index);

/* 0x9320 — compare-timer arm/build (save/touch SR via 0x2054/0x2064, computes
 * and writes the per-descriptor timer words + ch[6]/desc[8]). */
extern void compare_timer_arm_0x9320(uint8_t index);

void ignition_something_calc_0x91FE(uint8_t index)
{
    uint32_t          idx   = (uint32_t)index;
    volatile uint8_t *ch    = RAM_TABLE + idx * 8u;
    float             v, w, count;

    /* step 1-2: wrap the just-stored spark angle (value - base) into [-90,630) */
    v = (*(volatile float *)ch) - F32_A0FC;
    if (v < -90.0f) {
        w = v + 720.0f;
    } else if (v < 630.0f) {
        w = v;
    } else {
        w = v - 720.0f;
    }
    F32_A0F8 = w;                                  /* L_0x927A fmov.s fr2,@r4 */

    if (ch[5] == 0) {                              /* @(5,r6): armed flag clear */
        /* step 3: (w - count) < 60 -> arm  */
        uint32_t fpul  = U32_A0C4[idx] + (uint32_t)U16_A0D4 * 16u;
        float    fr3   = (float)(int32_t)fpul;     /* lds/float: s32 -> f32   */
        fr3            = fr3 * 30.0f;              /* L_0x9310                */
        float    fr1   = (float)(int32_t)U32_A100; /* L_0x9314 fdiv divisor   */
        count          = fr3 / fr1;
        if (w - count < 60.0f) {                   /* L_0x9318                */
            retrigger_arm_prepare_0x9478(index);
            compare_timer_arm_0x9320(index);
        }
    } else {
        /* step 4: already-armed channel — disarm if descriptor target is 0   */
        uint32_t desc = DESC_DAB4[idx * 24u / 4u];
        if (*(volatile uint16_t *)desc == 0) {
            ch[4] = 0;
            ch[5] = 0;
        } else {
            compare_timer_arm_0x9320(index);
        }
    }
}