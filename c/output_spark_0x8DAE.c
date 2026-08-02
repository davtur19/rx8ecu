/* output_spark_0x8DAE.c
 *
 * ROM: 60E0FC00  |  Address: 0x8DAE  |  Size: 0x3A bytes (0x8DAE..0x8DE8)
 *       next function outputSpark2 @0x8DE8; literal pool @0x8E80..0x8E8B shared
 *       with outputSpark2.  VERIFIED vs ROM emulator (0 mismatches,
 *       c/tests/test_output_spark_0x8DAE.py, 500000 random inputs).
 *
 * CSV / xmap name: "outputSpark1" (symbols/symbols_60E0FC00.csv).  The pair
 * outputSpark1(0x8DAE)/outputSpark2(0x8DE8) are the two spark-event output
 * routines (lead = outputSpark1, trail = outputSpark2) driven by the
 * engine-cycle dispatcher "setEngineCycle?" @0x10D82 (callgraph: 0x10D82 ->
 * 0x8DAE and 0x10D82 -> 0x8DE8).  Both write a f32 spark value + mode byte
 * into the per-channel event table at 0xFFFFA0D8 (stride 8) and then call the
 * shared arming helper "ignitonSomethingCalc" @0x91C6.
 *
 * Semantics (execution order):
 *   1. saved_sr = getSR(16)          // raise IPL / save old SR mask (0x3920)
 *   2. ch = (u8*)(0xFFFFA0D8 + index*8)
 *        *(f32*)ch = value           // spark event value (fr4)
 *        ch[5]    = 0                // clear armed/fired flag
 *        ch[4]    = 2                // lead-spark output-enable byte
 *   3. ignitonSomethingCalc(index)   // 0x91C6: wrap angle, arm compare timer
 *   4. setSR(saved_sr)               // restore SR (0x3934)
 *
 * 0x91C6 (un-lifted) wraps the just-stored value as a spark-advance angle
 * (base offset f32@0xFFFFA0FC, wrap range [-90..720]/[630..-720]), writes the
 * wrapped result to f32@0xFFFFA0F8, and — when the computed timer count is in
 * range — arms the output-compare channel via the 0x9440 retrigger routine
 * (per-channel descriptor table @0xD81C) which also sets ch[5]=1, ch[6]=0.
 * getSR(16)/setSR only touch the Status Register (no RAM side effects).
 *
 * Inputs (args): r4 index (u8 channel 0..7), fr4 value (f32, degrees).
 * Inputs (RAM reads, mostly inside 0x91C6): table 0xFFFFA0D8+idx*8,
 *   0xFFFFA0FC (f32 wrap base), 0xFFFFA0F8 (f32 scratch), 0xFFFFA0C4+idx*8
 *   (u32 pointer), 0xFFFFA0D4 (u16), 0xFFFFA100 (u32 deg->count divisor).
 * Outputs (RAM writes): table slot value/bytes + whatever 0x91C6/0x9440/A8A4
 *   write (all verified via full-RAM comparison vs the ROM emulator).
 *
 * Naming note: "outputSpark1" is a workable name, but as a semantic proposal
 * this routine is the LEAD-spark channel output driver (per-rotor leading
 * plugs); outputSpark2 @0x8DE8 is the TRAIL-spark sibling that only fires when
 * the channel is already armed (byte4==2).  Both are scheduled by
 * setEngineCycle? @0x10D82 and arm through ignitonSomethingCalc @0x91C6, which
 * itself feeds ignitionDwellOutputInit's hardware chain (0x8F2A/0x8F62).  CSV
 * names left untouched per repo rules.
 */
#include <stdint.h>

#define RAM_TABLE      ((volatile uint8_t *)0xFFFFA0D8)  /* per-channel table, stride 8 */

/* ---- verified/lifted leaves ---- */
extern uint32_t getSR(uint32_t requested_sr);            /* 0x3920 (c/getSR.c) */
extern void     setSR(uint32_t sr_value);                /* 0x3934 (c/setSR.c) */

/* 0x91C6 — "ignitonSomethingCalc": spark-angle wrap + compare-timer arming.
 * Not lifted as a standalone C function; executed in the ROM emulator by the
 * test harness (cpu2.call pattern) and its RAM effects merged. */
extern void ignitonSomethingCalc_0x91C6(uint32_t index);

void output_spark_0x8DAE(uint8_t index, float value)
{
    uint32_t saved_sr = getSR(16);                       /* 0x3920, r4=16 */
    volatile uint8_t *ch = RAM_TABLE + (uint32_t)index * 8u;

    *(volatile float *)ch = value;   /* fmov.s fr3,@r4  — spark event value */
    ch[5] = 0;                       /* mov #0,@(5,r4)  — clear armed flag  */
    ch[4] = 2;                       /* mov #2,@(4,r4)  — lead enable byte  */

    ignitonSomethingCalc_0x91C6(index);                  /* bsr 0x91C6       */

    setSR(saved_sr);                                     /* jmp 0x3934 (tail) */
}
