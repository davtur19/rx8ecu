/* finalTrailingTimingStuff_0x132CA.c
 *
 * ROM: 60E0FC00 | Address: 0x132CA | Size: 0x9E (158) bytes per CSV range
 * 0x132CA..0x13368.  Code runs to the `rts` @0x13322 (delay nop @0x13324);
 * the literal pool @0x1332A..0x13366 is shared with the leading twin
 * finalLeadingTimingStuff (0x1326E) and the next function (FUN_00013368,
 * an unrelated table walker) starts exactly at the CSV end 0x13368.
 *
 * ENTRY VERIFICATION: 0x132CA matches the symbols CSV row (0x0132CA,0x013368,
 * finalTrailingTimingStuff?,ghidra-hand).  Valid entry: opens straight with a
 * mov.l literal load; the preceding twin finalLeadingTimingStuff ends with
 * `rts` @0x132C6 + nop @0x132C8, so there is no fall-through into us; no
 * incoming branches into the middle.  Called via the function-pointer slot
 * @0x144E4 of the engineControlCalculateTiming dispatcher (0x141FC) dispatch
 * table — the slot immediately AFTER the leading twin's slot @0x144E0
 * (0x0001326E).  The ROM literal @0x144E4 is the ONLY 32-bit reference to
 * 0x132CA in the binary.  The CSV address IS the real entry point.
 *
 * SEMANTICS (instruction-for-instruction, see disasm): final trailing-timing
 * per-rotor value writer, gated by calibration flag u8@ROM 0x6E0F1:
 *   if flag == 0:   f32@0xFFFFA6E8 = f32@0xFFFFA634   (copy the trailing-
 *                   timing derate base; A634 is the DSC-trailing derate output
 *                   of calculateDSCTrailingTimingDerate 0x12294, verified)
 *   if flag == 1:   f32@0xFFFFA6DC = f32@A6E8 + f32@A6F4 + f32@A6FC
 *                   f32@0xFFFFA6E0 = f32@A6E8 + f32@A6F8 + f32@A700
 *   if flag == 2:   f32@0xFFFFA6DC = f32@ROM 0x0006E100   (0.0f in this ROM)
 *                   f32@0xFFFFA6E0 = f32@ROM 0x0006E104   (0.0f in this ROM)
 * The flag byte is re-read from ROM between the copy block and the
 * value-selection block (both reads are @0x6E0F1, so the same value in a
 * single call).  r0 at return holds (flag & 0xFF) on every path (the extu.b
 * of the reloaded flag byte).  A6DC/A6E0 are the per-rotor (rotor1/rotor2)
 * final trailing timing values; A6E8 is the trailing per-rotor base; A6F4/
 * A6F8 and A6FC/A700 are rotor-specific and shared correction addends.
 *
 * TWIN COMPARISON vs finalLeadingTimingStuff (0x1326E) — the code shape is
 * identical (same 0x58-byte skeleton, same branch topology).  Exact
 * differences (verified byte-by-byte from disassembly):
 *   leading 0x1326E                  trailing 0x132CA
 *   flag byte      u8@ROM 0x6E0F0     u8@ROM 0x6E0F1    (adjacent cal bytes)
 *   base copy      f32@A62C -> A6E4   f32@A634 -> A6E8  (+8 / +4 vs leading)
 *   rotor1 out     f32@A6D4           f32@A6DC          (+8)
 *   rotor2 out     f32@A6D8           f32@A6E0          (+8)
 *   rotor1 adds    f32@A6EC, A6FC     f32@A6F4, A6FC    (first +8, shared)
 *   rotor2 adds    f32@A6F0, A700     f32@A6F8, A700    (first +8, shared)
 *   const path     f32@ROM 0x6E0F8/   f32@ROM 0x6E100/
 *                  0x6E0FC            0x6E104           (all 0.0f in this ROM)
 * The draft lift c/finalLeadingTimingStuff__1326e.c (gen_c_lift_v3) agrees
 * with this transcription of the shared skeleton; it was NOT copied — the
 * trailing body was transcribed from the actual disassembly above.
 *
 * Range  : 0x132CA .. 0x13368
 * Literal pool (values verified against roms/stock/60E0FC00.bin; mov.w values
 * sign-extend to 0xFFFFxxxx):
 *   0x1333A 0xA6E8   (mov.w -> f32 output/base @0xFFFFA6E8)
 *   0x1333C 0xA634   (mov.w -> f32 base copy source @0xFFFFA634)
 *   0x1333E 0xA6DC   (mov.w -> f32 rotor1 output @0xFFFFA6DC)
 *   0x13340 0xA6F4   (mov.w -> f32 rotor1 addend 1 @0xFFFFA6F4)
 *   0x13342 0xA6F8   (mov.w -> f32 rotor2 addend 1 @0xFFFFA6F8)
 *   0x13344 0xA6E0   (mov.w -> f32 rotor2 output @0xFFFFA6E0)
 *   (0x13332 0xA6FC and 0x13336 0xA700 are shared addends, also used by the
 *    leading twin; the 0x1332A..0x13366 pool block is shared between twins)
 *   0x1335C 0x0006E0F1 (mov.l -> u8 flag byte @ROM 0x6E0F1)
 *   0x13360 0x0006E100 (mov.l -> f32 rotor1 const @ROM 0x6E100, 0.0f)
 *   0x13364 0x0006E104 (mov.l -> f32 rotor2 const @ROM 0x6E104, 0.0f)
 * RAM r/w: reads 0xFFFFA634 (x1), 0xFFFFA6E8 (x2), 0xFFFFA6F4, 0xFFFFA6F8,
 * 0xFFFFA6FC, 0xFFFFA700; writes 0xFFFFA6E8, 0xFFFFA6DC, 0xFFFFA6E0.
 * ROM read: flag byte 0x6E0F1 (x2) + the two const floats 0x6E100/0x6E104.
 * Sub-calls: none.  Stack: none.
 * VERIFIED against the SH-2 emulator (tools/sh2emu.py, 60E0FC00.bin) in
 * c/tests/test_finalTrailingTimingStuff_0x132CA.py — 0 mismatches over 5 seeds
 * x 100000 iterations on the stock ROM (flag==0 copy path), plus patched-ROM
 * phases (flag byte @0x6E0F1 forced to 1 and 2) covering the compute and
 * const paths (byte-exact full post-call RAM overlay + r0).
 */
#include <stdint.h>

/* ---- RAM globals (mov.w literals sign-extend to 0xFFFFxxxx; f32 access) ---- */
#define IN_BASE_A634 (*(volatile float *)0xFFFFA634)  /* trailing derate base  */
#define BASE_A6E8    (*(volatile float *)0xFFFFA6E8)  /* per-rotor base/output */
#define OUT_R1_A6DC  (*(volatile float *)0xFFFFA6DC)  /* rotor 1 final trailing */
#define OUT_R2_A6E0  (*(volatile float *)0xFFFFA6E0)  /* rotor 2 final trailing */
#define ADD_R1_A6F4  (*(volatile float *)0xFFFFA6F4)  /* rotor 1 addend 1       */
#define ADD_R2_A6F8  (*(volatile float *)0xFFFFA6F8)  /* rotor 2 addend 1       */
#define ADD_S_A6FC   (*(volatile float *)0xFFFFA6FC)  /* shared addend 1        */
#define ADD_S_A700   (*(volatile float *)0xFFFFA700)  /* shared addend 2        */

/* ---- ROM calibration constants ---- */
#define FLAG_6E0F1   (*(const uint8_t *)0x0006E0F1)   /* mode flag byte        */
#define CONST_R1_6E100 (*(const float *)0x0006E100)   /* 0.0f in this ROM      */
#define CONST_R2_6E104 (*(const float *)0x0006E104)   /* 0.0f in this ROM      */

void finalTrailingTimingStuff_0x132CA(void)
{
    if (FLAG_6E0F1 == 0) {
        /* copy path (flag clear): the trailing derate base becomes the
         * per-rotor base; A634 = output of calculateDSCTrailingTimingDerate */
        BASE_A6E8 = IN_BASE_A634;
    }

    if (FLAG_6E0F1 == 1) {
        /* compute path: base + rotor-specific + shared correction addends */
        OUT_R1_A6DC = (BASE_A6E8 + ADD_R1_A6F4) + ADD_S_A6FC;
        OUT_R2_A6E0 = (BASE_A6E8 + ADD_R2_A6F8) + ADD_S_A700;
    } else if (FLAG_6E0F1 == 2) {
        /* const path: hard calibration values (0.0f in this ROM) */
        OUT_R1_A6DC = CONST_R1_6E100;
        OUT_R2_A6E0 = CONST_R2_6E104;
    }
}