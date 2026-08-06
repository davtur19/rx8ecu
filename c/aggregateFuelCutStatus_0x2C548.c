/* aggregateFuelCutStatus_0x2C548.c
 *
 * ROM: 60E0FC00 | Address: 0x2C548 | Size: 0x88 (136) bytes per CSV range
 * 0x2C548..0x2C5D0.  Straight-line leaf (no prologue/epilogue, no sub-calls).
 * Code runs to the `rts` @0x2C5CC (delay nop @0x2C5CE); the interleaved
 * mov.w literal pool @0x2C590..0x2C596 and the mov.l literal @0x2C5C4 sit
 * inside the CSV range.  The CSV range is CORRECT (the preceding function
 * 0x02C4E6 ends rts @0x2C544 + delay nop @0x2C546, no fall-through; the next
 * function starts exactly at the CSV end 0x2C5D0, `sts.l pr,@-r15` prologue).
 * No phantom rows.
 *
 * ENTRY VERIFICATION: 0x2C548 matches the symbols CSV start.  Valid entry:
 * there is no prologue push (leaf with only one RAM store), and no code
 * branches into it from mid-function.  The ONLY 32-bit ROM reference to
 * 0x2C548 is the function-pointer slot @0x144FC inside the
 * engineControlCalculateTiming dispatcher (0x141FC) dispatch table literal
 * pool (same pool that carries calculateCrankingTimingLeading @0x1444C etc).
 * The preceding function's rts is two instructions before us, so there is no
 * fall-through into our body.  CSV address IS the real entry point.
 *
 * NAME NOTE: the ghidra-hand name was `checkFuelCutStatusForSomething` — the
 * trailing "ForSomething" was a placeholder.  Semantics resolve it: the
 * function OR-compounds four neighboring fuel-cut condition flags
 * (CC8A = `ram_cc8a` / fuel_cut_flag, CC8B = `fuel_cut_condition7_flag`,
 * plus the adjacent CC8C/CC8D which share the same 12-14 group) and latches
 * the resulting "any fuel-cut now active" status into u8@FFFFBC61.  Renamed
 * here to `aggregateFuelCutStatus`.  (The duplicate-draft scan already has a
 * tracked `calculateDriverConditions_43c4a` and many `*FuelCut*` siblings;
 * this is a NEW correct lift, not a copy of any Draft.)
 *
 * STRUCTURE (instruction-for-instruction, see disasm):
 *   out = u8@FFFFBC61
 *   if u8@FFFFCC8A == 1  -> out = 1   (bt/s 0x2C57A)
 *   elif u8@FFFFCC8B == 1 -> out = 1
 *   elif u8@FFFFCC8C == 1 -> out = 1
 *   elif u8@FFFFCC8D == 1 -> out = 1
 *   else                  -> out = 0   (bf/s 0x2C5C8)
 *   out is written via `mov.b r3,@r4` (r4 = &FFFFBC61); the else path writes
 *   r1=0.
 *   r0 on return = the extended value of the "deciding" flag byte: == 0x01 on
 *   every set path (the deciding flag is one of the four ==-1 inputs), or
 *   u8@FFFFCC8D & 0xFF on the clear path (the last byte compared).  Carried
 *   byte-exact by the emulator comparison.
 *
 * RAM r/w: reads U8 CC8A, CC8B, CC8C, CC8D (@FFFFCC8x); writes u8@FFFFBC61.
 * No ROM constants read, no sub-calls.
 *
 * VERIFIED against the SH-2 emulator (tools/sh2emu.py,
 * roms/stock/60E0FC00.bin) in c/tests/test_aggregateFuelCutStatus_0x2C548.py —
 * 0 mismatches over 5 seeds x 100000 iterations (byte-exact full post-call
 * RAM overlay + r0).
 */
#include <stdint.h>

/* ---- RAM globals (mov.w literals sign-extend to 0xFFFFxxxx) ---- */
#define FC0_CC8A (*(volatile uint8_t *)0xFFFFCC8A)  /* fuel_cut_flag            */
#define FC7_CC8B (*(volatile uint8_t *)0xFFFFCC8B)  /* fuel_cut_condition 7 flag */
#define FC_CC8C  (*(volatile uint8_t *)0xFFFFCC8C)  /* fuel-cut condition flag   */
#define FC_CC8D  (*(volatile uint8_t *)0xFFFFCC8D)  /* fuel-cut condition flag   */
#define STS_BC61 (*(volatile uint8_t *)0xFFFFBC61)  /* aggregate fuel-cut status */

void aggregateFuelCutStatus_0x2C548(void)
{
    if (FC0_CC8A == 1 || FC7_CC8B == 1 || FC_CC8C == 1 || FC_CC8D == 1)
        STS_BC61 = 1;
    else
        STS_BC61 = 0;
}