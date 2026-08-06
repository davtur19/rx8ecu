/* setPerRotorTimingValuesTrailing_0x1470A.c
 *
 * ROM: 60E0FC00 | Address: 0x1470A | Size: 0x62 (98) bytes per CSV range
 * 0x1470A..0x1476C.  Code ends at the `rts` @0x1473C (delay nop @0x1473E);
 * the literal pool @0x14740..0x1476A is shared with the twin
 * setPerRotorTimingValuesLeading (0x146D4) and the next function (a byte-flag
 * writer, opens `mov.w 0x147E2,r3 ; 0xA79C`) starts exactly at the CSV end
 * 0x1476C.
 *
 * ENTRY VERIFICATION: 0x1470A matches the symbols CSV row (0x01470A,0x01476C,
 * setPerRotorTimingValuesTrailing,ghidra-hand).  Valid entry: opens straight
 * with two mov.w literal loads; the preceding twin setPerRotorTimingValuesLeading
 * ends with `rts` @0x14706 + nop @0x14708, so there is no fall-through into us;
 * no incoming branches into the middle.  Called via the function-pointer slot
 * @0x144EC of the engineControlCalculateTiming dispatcher (0x141FC) dispatch
 * table — the slot immediately AFTER the leading twin's slot @0x144E8
 * (0x000146D4).  The ROM literal @0x144EC is the ONLY 32-bit reference to
 * 0x1470A in the binary.  The CSV address IS the real entry point.
 *
 * SEMANTICS (instruction-for-instruction, see disasm):
 *   if u8@ROM 0x0006E0F1 == 0:            (tst r3,r3 ; bf/s -> fallback)
 *       f32@0xFFFFA794 = f32@0xFFFFA634 + f32@ROM 0x000753E4   (0.0)
 *       f32@0xFFFFA798 = f32@0xFFFFA634 + f32@ROM 0x000753E8   (0.0)
 *   else:                                 (flag != 0 -> direct copy path)
 *       f32@0xFFFFA794 = f32@0xFFFFA6DC
 *       f32@0xFFFFA798 = f32@0xFFFFA6E0
 * The two "add" constants are calibration offsets; in this ROM both are 0.0f,
 * so the add-path is an identity copy of the per-rotor trailing base value.
 * No stack frame, no sub-calls, no PR use; r0 is never touched (returns the
 * caller's r0).  The per-rotor trailing values feed the trailing-timing
 * derate/retard chain (A794/A798 are the trailing siblings of the leading
 * outputs A78C/A790).
 *
 * TWIN COMPARISON vs setPerRotorTimingValuesLeading (0x146D4) — the code
 * shape is identical (same 0x34-byte skeleton, same branch topology).  Exact
 * differences (verified byte-by-byte):
 *   leading 0x146D4                  trailing 0x1470A
 *   outputs        f32@A78C / A790   f32@A794 / A798   (+4 vs leading)
 *   base input     f32@A62C          f32@A634          (+8 vs leading)
 *   fallback copy  f32@A6D4 / A6D8   f32@A6DC / A6E0   (+8 vs leading)
 *   enable flag    u8@ROM 0x6E0F0    u8@ROM 0x6E0F1    (adjacent cal bytes)
 *   add constants  f32@ROM 0x753DC / 0x753E0   f32@ROM 0x753E4 / 0x753E8
 *                  (all four are 0.0f in this ROM)
 * The draft lift c/setPerRotorTimingValuesLeading_146d4.c (gen_c_lift_v3)
 * agrees with this transcription of the shared skeleton; it was NOT copied —
 * the trailing body was transcribed from the actual disassembly above.
 *
 * Range  : 0x1470A .. 0x1476C
 * Literal pool (values verified against roms/stock/60E0FC00.bin):
 *   0x1474A 0xA798   (mov.w -> f32 output @0xFFFFA798)
 *   0x1474C 0xA794   (mov.w -> f32 output @0xFFFFA794)
 *   0x1474E 0xA634   (mov.w -> f32 base input @0xFFFFA634)
 *   0x14750 0xA6DC   (mov.w -> f32 fallback source 1 @0xFFFFA6DC)
 *   0x14752 0xA6E0   (mov.w -> f32 fallback source 2 @0xFFFFA6E0)
 *   0x14760 0x0006E0F1 (mov.l -> u8 enable flag @ROM 0x6E0F1)
 *   0x14764 0x000753E4 (mov.l -> f32 add constant @ROM 0x753E4)
 *   0x14768 0x000753E8 (mov.l -> f32 add constant @ROM 0x753E8)
 * RAM r/w: reads 0xFFFFA634 (x2), 0xFFFFA6DC, 0xFFFFA6E0; writes
 * 0xFFFFA794, 0xFFFFA798.  ROM read: flag byte 0x6E0F1 + the two add floats.
 * Sub-calls: none.  Stack: none.
 * VERIFIED against the SH-2 emulator (tools/sh2emu.py, 60E0FC00.bin) in
 * c/tests/test_setPerRotorTimingValuesTrailing_0x1470A.py — 0 mismatches over
 * 5 seeds x 100000 iterations on the stock ROM (flag==0 add-path), plus a
 * patched-ROM phase (flag byte @0x6E0F1 forced to 1) covering the fallback
 * copy path (byte-exact full post-call RAM overlay + r0).
 */
#include <stdint.h>

/* ---- RAM globals (mov.w literals sign-extend to 0xFFFFxxxx; f32 access) ---- */
#define IN_BASE_A634 (*(volatile float *)0xFFFFA634)  /* per-rotor trailing base */
#define IN_FB_A6DC   (*(volatile float *)0xFFFFA6DC)  /* fallback copy source 1  */
#define IN_FB_A6E0   (*(volatile float *)0xFFFFA6E0)  /* fallback copy source 2  */
#define OUT_A794     (*(volatile float *)0xFFFFA794)  /* trailing output 1        */
#define OUT_A798     (*(volatile float *)0xFFFFA798)  /* trailing output 2        */

/* ---- ROM calibration constants ---- */
#define FLAG_6E0F1   (*(const uint8_t *)0x0006E0F1)   /* trailing enable flag    */
#define ADD_C1_753E4 (*(const float *)0x000753E4)     /* 0.0f in this ROM        */
#define ADD_C2_753E8 (*(const float *)0x000753E8)     /* 0.0f in this ROM        */

void setPerRotorTimingValuesTrailing_0x1470A(void)
{
    if (FLAG_6E0F1 == 0) {
        /* add-path (flag clear): f32@A634 reloaded for each fadd */
        OUT_A794 = IN_BASE_A634 + ADD_C1_753E4;
        OUT_A798 = IN_BASE_A634 + ADD_C2_753E8;
    } else {
        /* fallback: direct copy of the trailing-sensor pair */
        OUT_A794 = IN_FB_A6DC;
        OUT_A798 = IN_FB_A6E0;
    }
}
