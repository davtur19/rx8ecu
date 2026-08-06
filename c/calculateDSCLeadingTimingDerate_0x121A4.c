/* calculateDSCLeadingTimingDerate_0x121A4.c
 *
 * ROM: 60E0FC00 | Address: 0x121A4 | Size: 0xAC (172) bytes actual code+pool
 *
 * RANGE NOTE (discrepancy, documented): the symbols CSV row for this function
 * is (0x0121A4,0x012236,calculateDSCLeadingTimingDerate?,ghidra-hand).  The
 * real function does NOT end at 0x12236: the code runs to the `rts` @0x1224E
 * (delay nop @0x12250) and its literal pool occupies 0x12252..0x12292; the
 * next function (the DSC-trailing twin, opens `fmov.s fr15,@-r15`) starts at
 * 0x12294.  The CSV "modifyTiming" row @0x12236 is spurious — that address is
 * inside this function (verified by disassembly: 0x12236..0x12250 is the
 * derate-clamp tail + epilogue).  The CSVs updated here therefore widen this
 * row to 0x0121A4..0x012294 and drop the phantom modifyTiming row.
 *
 * ENTRY VERIFICATION: 0x121A4 matches the CSV start.  Valid entry: opens with
 * the standard prologue (three fmov.s frN,@-r15 pushes + sts.l pr,@-r15);
 * the preceding function getInitalLeadingTrailingAdvance? (0x12192) ends with
 * `rts` @0x121A0 (delay nop @0x121A2), so no fall-through into us; no
 * incoming branches into the middle.  Called via the function-pointer slot
 * @0x144C8 of the engineControlCalculateTiming dispatcher (0x141FC) dispatch
 * table (same table family that holds setPerRotorTimingValuesLeading/Trailing
 * @0x144E8/0x144EC).  The ROM literal @0x144C8 is the ONLY 32-bit reference
 * to 0x121A4 in the binary.  The CSV address IS the real entry point.
 *
 * SEMANTICS (instruction-for-instruction, see disasm): the leading-timing
 * DSC (dynamic-stability-control) derate writer — structural twin of the
 * verified calc_intake_pressure_pid_output (0x1252C) and of the adjacent
 * calculateDSCTrailingTimingDerate? (0x12294, byte-for-byte the same skeleton
 * with +4-shifted RAM addresses).  It computes:
 *
 *   s = complement_shift_u32(@A780, 0.0f, 1e-5f)   // call 1, low byte -> stack
 *   r = complement_shift_u32(@BCA8, 0.0f, 1e-5f)   // call 2, full r4
 *
 *   if u8@AAC6 == 1 && (s & 0xFF) == 0 &&
 *       2000.0 > f32@B594 && u8@CCE4 == 1:
 *       derate = -5.0                              // DSC cut (ROM 0x6E098)
 *   else if u8@BC02 == 0 && f32@A9A4 > 0.0f &&
 *           (u8@ROM 0x6E094 == 0 || (r & 0xFF) == 0):
 *       derate = f32@A994
 *   else:
 *       derate = f32@A630
 *
 *   f32@0xFFFFA62C = saturate(derate, f32@A648, 65.0f)   // clamp @0x2404
 *
 * The -5.0 DSC-cut branch is gated on: byte AAC6 (==1), A780 within the 1e-5
 * deadband of 0 (the first guard's "zero" result), B594 below 2000.0 RPM,
 * and byte CCE4 (==1).  u8@ROM 0x6E094 is a calibration enable that is 0x00 in
 * this ROM, so the middle branch always resolves to the f32@A994 reference;
 * the r4 guard is dead in practice but is transcribed for fidelity.  r0 on
 * return holds the last integer value the branch chain left in it (see the
 * test reference model): 0 on the f32@A994 path, the masked CCE4 byte on the
 * -5.0 path, else the masked AAC6 byte / the mova address 0x12280 / the
 * masked CCE4 byte depending on which gate failed.  All stack usage is the
 * 0xFFFFDEEC..0xFFFFDF00 window (fr13/fr14/fr15 + PR saves, one scratch byte).
 *
 * Range  : 0x121A4 .. 0x12294 (code 0x121A4..0x12250, literal pool
 *           0x12252..0x12292; next function at 0x12294)
 * Literal pool (values verified against roms/stock/60E0FC00.bin):
 *   0x12252 0xB594   (mov.w -> f32 @0xFFFFB594, RPM-gate input)
 *   0x12254 0xA780   (mov.w -> f32 @0xFFFFA780, first deadband input)
 *   0x12256 0xBCA8   (mov.w -> f32 @0xFFFFBCA8, second deadband input)
 *   0x12258 0xAAC6   (mov.w -> u8 @0xFFFFAAC6, gate byte 1)
 *   0x1225A 0xCCE4   (mov.w -> u8 @0xFFFFCCE4, gate byte 2)
 *   0x1225C 0xBC02   (mov.w -> u8 @0xFFFFBC02, middle-branch gate byte)
 *   0x1225E 0xA9A4   (mov.w -> f32 @0xFFFFA9A4, middle-branch gate float)
 *   0x12260 0xA994   (mov.w -> f32 @0xFFFFA994, middle derate reference)
 *   0x12262 0xA630   (mov.w -> f32 @0xFFFFA630, default derate reference)
 *   0x12264 0xA62C   (mov.w -> f32 output @0xFFFFA62C)
 *   0x12268 0x0006E098 (mov.l -> f32 -5.0 DSC cut @ROM 0x6E098)
 *   0x12278 0x3727C5AC (mova/fmov.s -> 1e-5f deadband @ROM 0x12278)
 *   0x1227C 0x00002440 (mov.l -> complement_shift_u32 @0x2440)
 *   0x12280 0x44FA0000 (mova/fmov.s -> 2000.0f RPM gate @ROM 0x12280)
 *   0x12284 0x0006E094 (mov.l -> u8 cal enable @ROM 0x6E094, ==0)
 *   0x12288 0x0006E0B0 (mov.l -> f32 65.0f clamp high @ROM 0x6E0B0)
 *   0x1228C 0xFFFFA648 (mov.l -> f32 @0xFFFFA648, clamp low)
 *   0x12290 0x00002404 (mov.l -> saturate @0x2404)
 * RAM r/w: reads A780, BCA8, AAC6, B594, CCE4, BC02, A9A4, A994, A630, A648
 * (plus the 4-byte stack scratch); writes f32@A62C (plus the stack window).
 * ROM read: literals above incl. the deadband/2000/65/-5 cal constants.
 * Sub-calls: complement_shift_u32 @0x2440 (x2, = isNotZero_wDivideByZero-
 *   Protect, verified in c/math_primitives.c + c/complement_shift_u32.c) and
 *   saturate @0x2404 (x1).  SH-2E convention: float args fr4/fr5/fr6, int
 *   result r0 (0/1) for 0x2440; float result fr0 for 0x2404.
 * VERIFIED against the SH-2 emulator (tools/sh2emu.py, 60E0FC00.bin) in
 * c/tests/test_calculateDSCLeadingTimingDerate_0x121A4.py — 0 mismatches over
 * 5 seeds x 100000 iterations (byte-exact full post-call RAM overlay + r0).
 */
#include <stdint.h>

/* ---- RAM globals (mov.w literals sign-extend to 0xFFFFxxxx) ---- */
#define RAM_A780  (*(volatile float *)0xFFFFA780)  /* deadband input 1        */
#define RAM_BCA8  (*(volatile float *)0xFFFFBCA8)  /* deadband input 2        */
#define RAM_AAC6  (*(volatile uint8_t *)0xFFFFAAC6)  /* gate byte 1 (==1)     */
#define RAM_B594  (*(volatile float *)0xFFFFB594)  /* RPM gate (< 2000)       */
#define RAM_CCE4  (*(volatile uint8_t *)0xFFFFCCE4)  /* gate byte 2 (==1)     */
#define RAM_BC02  (*(volatile uint8_t *)0xFFFFBC02)  /* middle gate byte (0)  */
#define RAM_A9A4  (*(volatile float *)0xFFFFA9A4)  /* middle gate float (>0) */
#define RAM_A994  (*(volatile float *)0xFFFFA994)  /* middle derate reference */
#define RAM_A630  (*(volatile float *)0xFFFFA630)  /* default derate reference */
#define RAM_A648  (*(volatile float *)0xFFFFA648)  /* clamp low               */
#define OUT_A62C  (*(volatile float *)0xFFFFA62C)  /* leading-timing derate   */

/* ---- ROM calibration constants ---- */
#define CAL_DEADBAND_1E5 (*(const float *)0x00012278)   /* 1e-5f     */
#define CAL_RPM_GATE_2K  (*(const float *)0x00012280)   /* 2000.0f   */
#define CAL_ENABLE_6E094 (*(const uint8_t *)0x0006E094) /* 0x00      */
#define CAL_DSC_CUT_N5   (*(const float *)0x0006E098)   /* -5.0f     */
#define CAL_CLAMP_HI_65  (*(const float *)0x0006E0B0)   /* 65.0f     */

/* ---- External helpers (in ROM, both verified separately) ---- */
extern uint32_t complement_shift_u32(float threshold, float value, float adjustment);
/* @0x2440 (= isNotZero_wDivideByZeroProtect): 1 if |threshold-value| > adjustment */
extern float fpu_compare_and_select(float val, float lo, float hi);
/* @0x2404: clamp(val, lo, hi) */

void calculateDSCLeadingTimingDerate_0x121A4(void)
{
    uint32_t s, r;
    float    derate;

    /* first guard: A780 must sit inside the 1e-5 deadband of 0.0 */
    s = complement_shift_u32(RAM_A780, 0.0f, CAL_DEADBAND_1E5);
    /* second guard result (only consumed via the dead cal-enable byte) */
    r = complement_shift_u32(RAM_BCA8, 0.0f, CAL_DEADBAND_1E5);

    if (RAM_AAC6 == 1 && (s & 0xFF) == 0 &&
        CAL_RPM_GATE_2K > RAM_B594 && RAM_CCE4 == 1) {
        derate = CAL_DSC_CUT_N5;                    /* -5.0 (DSC cut) */
    } else if (RAM_BC02 == 0 && RAM_A9A4 > 0.0f &&
               (CAL_ENABLE_6E094 == 0 || (r & 0xFF) == 0)) {
        derate = RAM_A994;
    } else {
        derate = RAM_A630;
    }

    /* clamp the derate into [f32@A648, 65.0] and publish */
    OUT_A62C = fpu_compare_and_select(derate, RAM_A648, CAL_CLAMP_HI_65);
}
