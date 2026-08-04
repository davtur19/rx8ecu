/* output_spark_0x8DE6.c
 *
 * ROM: 60E1D400  |  Address: 0x8DE6  |  Size: 0x3A bytes (0x8DE6..0x8E20)
 *       next function outputSpark2 @0x8E20; literal pool @0x8EB8..0x8EC3 (words
 *       L_008eb8/0x8ebc/0x8ec0) shared with outputSpark2 and
 *       ignitionTimingHardwareTimerSomething.  VERIFIED vs ROM emulator
 *       (0 mismatches, c/tests/test_output_spark_0x8DE6.py, 500000 random
 *       inputs).
 *
 * CSV / merged-xmap name: "outputSpark1" (symbols/symbols_60E1D400_merged.csv,
 * ghidra-hand-xmap).  This is the per-rotor-A (LEAD) spark-event output
 * routine, byte-for-byte identical to outputSpark1 @0x8DAE in ROM 60E0FC00
 * (the sibling lift c/output_spark_0x8DAE.c) — same opcodes, same literals
 * (table 0xFFFFA0D8, getSR 0x3920, setSR 0x3934); the two ROM images differ
 * only in the base address of this code block and in the address of the shared
 * arming helper (0x91FE here vs 0x91C6 there).  outputSpark2 @0x8E20 is the
 * TRAIL-spark sibling that only fires when the channel is already armed
 * (byte4==2).
 *
 * Semantics (execution order):
 *   1. saved_sr = getSR(16)          // raise IPL / save old SR mask (0x3920)
 *   2. ch = (u8*)(0xFFFFA0D8 + index*8)
 *        *(f32*)ch = value           // spark event value (fr4)
 *        ch[5]    = 0                // clear armed/fired flag
 *        ch[4]    = 2                // lead-spark output-enable byte
 *   3. ignitonSomethingCalc(index)   // 0x91FE: wrap angle, arm compare timer
 *   4. setSR(saved_sr)               // restore SR (0x3934)
 *
 * 0x91FE (un-lifted) is the 60E1D400 instance of "ignitonSomethingCalc" (the
 * 60E0FC00 helper is @0x91C6): it wraps the just-stored value as a spark-advance
 * angle (base offset f32@0xFFFFA0FC, wrap range [-90..720]/[630..-720]), writes
 * the wrapped result to f32@0xFFFFA0F8, and — when the computed timer count is
 * in range — arms the output-compare channel via the per-channel retrigger
 * helper @0xAA74 (descriptor table @0xDAB4; the 60E0FC00 numbers are 0x9440 /
 * 0xD81C) which also sets ch[5]=1, ch[6]=0.  getSR(16)/setSR only touch the
 * Status Register (no RAM side effects).
 *
 * Caller / ignition-output path: called (via literal 0x8DE6) from the
 * per-rotor ignition output dispatcher "FUN_0x10DC8+ / resetFunc?"-family
 * routine at ~0x11056..0x11140 (the 60E0FC00 "setEngineCycle?" @0x10D82 chain;
 * coil/duty dispatcher 0x10F84/0x10FF0 in the other ROM's numbering).  That
 * caller computes the spark value passed in fr4 by scaling a dwell-derived
 * count by 1/65536 and drawing the per-rotor LEAD/TRAIL timing from the
 * block-0x19220 outputs f32@0xFFFFA9A0/A9A4/A9A8/A9AC, and stays in step with
 * outputSpark2 (0x8E20) via the channel state byte @(3,ch): state 1 ->
 * outputSpark2 (0x8E20), state 0 -> outputSpark1 (0x8DE6).  (Disasm at
 * 0x11024-0x1102C: cmp/eq #1 -> bt/s 0x11034 -> jsr 0x8E20; cmp/eq #0 ->
 * bt/s 0x1105A -> jsr 0x8DE6.)  Dwell time A0D4/A0D6 is consumed
 * inside the ignitonSomethingCalc / retrigger chain (reads 0xFFFFA0D4).
 *
 * Inputs (args): r4 index (u8 channel 0..7), fr4 value (f32, degrees).
 * Inputs (RAM reads, mostly inside 0x91FE): table 0xFFFFA0D8+idx*8,
 *   0xFFFFA0FC (f32 wrap base), 0xFFFFA0F8 (f32 scratch), 0xFFFFA0C4+idx*8
 *   (u32 pointer), 0xFFFFA0D4 (u16), 0xFFFFA100 (u32 deg->count divisor).
 * Outputs (RAM writes): table slot value/bytes + whatever 0x91FE/0xAA74/A8A4
 *   write (all verified via full-RAM comparison vs the ROM emulator).
 *
 * Naming note: "outputSpark1" is a workable name, but as a semantic proposal
 * this routine is the LEAD-spark channel output driver (per-rotor-A leading
 * plugs); outputSpark2 @0x8E20 is the TRAIL-spark sibling.  Both are scheduled
 * by the ignition-output dispatcher and arm through ignitonSomethingCalc
 * @0x91FE.  CSV names left untouched per repo rules.
 */
#include <stdint.h>

#define RAM_TABLE      ((volatile uint8_t *)0xFFFFA0D8)  /* per-channel table, stride 8 */

/* ---- verified/lifted leaves ---- */
extern uint32_t getSR(uint32_t requested_sr);            /* 0x3920 (c/getSR.c) */
extern void     setSR(uint32_t sr_value);                /* 0x3934 (c/setSR.c) */

/* 0x91FE — "ignitonSomethingCalc" (60E1D400; the 60E0FC00 helper is @0x91C6):
 * spark-angle wrap + compare-timer arming.  Not lifted as a standalone C
 * function; executed in the ROM emulator by the test harness (cpu2.call
 * pattern) and its RAM effects merged. */
extern void ignitonSomethingCalc_0x91FE(uint32_t index);

void output_spark_0x8DE6(uint8_t index, float value)
{
    uint32_t saved_sr = getSR(16);                       /* 0x3920, r4=16 */
    volatile uint8_t *ch = RAM_TABLE + (uint32_t)index * 8u;

    *(volatile float *)ch = value;   /* fmov.s fr3,@r4  — spark event value */
    ch[5] = 0;                       /* mov #0,@(5,r4)  — clear armed flag  */
    ch[4] = 2;                       /* mov #2,@(4,r4)  — lead enable byte  */

    ignitonSomethingCalc_0x91FE(index);                  /* bsr 0x91FE       */

    setSR(saved_sr);                                     /* jmp 0x3934 (tail) */
}