/* output_spark2_0x8E20.c
 *
 * ROM: 60E1D400  |  Address: 0x8E20  |  Size: 0x40 bytes (0x8E20..0x8E60)
 *       next function ignitionTimingHardwareTimerSomething @0x8E60; literal
 *       pool @0x8EB8..0x8EC0 shared with outputSpark1 (0x8DE6).
 *       VERIFIED vs ROM emulator (0 mismatches,
 *       c/tests/test_output_spark2_0x8E20.py, 500000 random inputs).
 *
 * CSV/xmap name: "outputSpark2" (symbols/symbols_60E1D400_merged.csv,
 * ghidra-hand-xmap; IDA-ai name "sensor_interp_dispatch_B" — wrong).  The pair
 * outputSpark1(0x8DE6)/outputSpark2(0x8E20) are the two spark-event output
 * routines (lead = outputSpark1, trail = outputSpark2) driven by the
 * engine-cycle coil/duty dispatcher @0x10F84/0x10FF0 (call sites 0x11050 ->
 * outputSpark2 for event mode byte == 1, 0x11076 -> outputSpark1 for mode
 * byte == 0).  Both write a f32 spark value + mode byte into the per-channel
 * event table at 0xFFFFA0D8 (stride 8) and then call the shared arming helper
 * "ignitonSomethingCalc" @0x91FE.
 *
 * Semantics (execution order):
 *   1. saved_sr = getSR(16)          // raise IPL / save old SR mask (0x3920)
 *   2. ch = (u8*)(0xFFFFA0D8 + index*8)
 *   3. ONLY IF ch[4] == 2  (channel already armed/enabled):
 *        *(f32*)ch = value           // spark event value (fr4)
 *        ch[6]    = 0                // clear fired flag
 *        ignitonSomethingCalc(index) // 0x91FE: wrap angle, arm compare timer
 *      (when ch[4] != 2 the channel is left untouched: no write, no 0x91FE call)
 *   4. setSR(saved_sr)               // restore SR (0x3934), tail call
 *
 * Differences vs outputSpark1 @0x8DE6 (the direct lead sibling):
 *   * 0x8DE6 writes the event table UNCONDITIONALLY: value -> ch, ch[5] = 0
 *     (clear armed flag), ch[4] = 2 (arm the channel).  0x8E20 GATES the whole
 *     write on ch[4] == 2 — a trail event only fires on a channel that the
 *     lead side already armed — and then clears ch[6] (fired flag), NOT ch[5],
 *     leaving ch[4]/ch[5] untouched.
 *   * Both wrap in getSR(16)/setSR(saved_sr) and both tail-call the SAME
 *     arming helper 0x91FE (60E1D400's equivalent of 60E0FC00's 0x91C6).
 *
 * The dispatcher computes the fr4 spark value from the split block
 * (A9A0/A9A4/A9A8/A9AC written by calc_spark_lead_trail_split_19220) — the
 * A9A0..A9AC addresses have NO absolute reference anywhere in 60E1D400, so the
 * split values reach the dispatcher indirectly; 0x8E20 itself reads ONLY the
 * channel enable byte ch[4] (plus whatever 0x91FE reads internally).
 *
 * Inputs (args): r4 index (u8 channel 0..7), fr4 value (f32, degrees).
 * Inputs (RAM reads, mostly inside 0x91FE): ch[4] (u8 enable gate), table
 *   0xFFFFA0D8+idx*8, 0xFFFFA0FC (f32 wrap base), 0xFFFFA0F8 (f32 scratch),
 *   0xFFFFA0C4 (u32 pointer table), 0xFFFFA0D4 (u16), 0xFFFFA100 (u32
 *   deg->count divisor), 0xFFFFA104 (u16), per-channel descriptor table @0xDAB4
 *   (stride 24) + its pointed targets.
 * Outputs (RAM writes): on the armed path the table slot value/ch[6] + whatever
 *   0x91FE/0x9478/0xAA74 write (all verified via full-RAM comparison vs the
 *   ROM emulator).  getSR(16)/setSR touch only the Status Register.
 *
 * Naming note: "outputSpark2" (xmap) matches the observed TRAIL-spark channel
 * output driver; the IDA-ai name "sensor_interp_dispatch_B" is not supported
 * by the code (no interpolation / dispatch dispatch).  CSV names left
 * untouched per repo rules.
 */
#include <stdint.h>

#define RAM_TABLE      ((volatile uint8_t *)0xFFFFA0D8)  /* per-channel table, stride 8 */

/* ---- verified/lifted leaves ---- */
extern uint32_t getSR(uint32_t requested_sr);            /* 0x3920 (c/getSR.c) */
extern void     setSR(uint32_t sr_value);                /* 0x3934 (c/setSR.c) */

/* 0x91FE — "ignitonSomethingCalc": spark-angle wrap + compare-timer arming.
 * Not lifted as a standalone C function; executed in the ROM emulator by the
 * test harness (cpu2.call pattern) and its RAM effects merged. */
extern void ignitonSomethingCalc_0x91FE(uint32_t index);

void output_spark2_0x8E20(uint8_t index, float value)
{
    uint32_t saved_sr = getSR(16);                       /* 0x3920, r4=16 */
    volatile uint8_t *ch = RAM_TABLE + (uint32_t)index * 8u;

    if (ch[4] == 2) {                    /* mov.b @(4,r1),r0; extu; cmp/eq #2; bf/s 0x8E56 */
        *(volatile float *)ch = value;   /* fmov.s fr3,@r1  — spark event value */
        ch[6] = 0;                       /* mov #0,@(6,r1)  — clear fired flag   */
        ignitonSomethingCalc_0x91FE(index);              /* bsr 0x91FE            */
    }

    setSR(saved_sr);                                     /* jmp 0x3934 (tail) */
}
