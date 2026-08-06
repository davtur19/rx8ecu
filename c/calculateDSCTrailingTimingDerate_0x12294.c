/* calculateDSCTrailingTimingDerate_0x12294.c
 *
 * ROM: 60E0FC00 | Address: 0x12294 | Size: 0xAE (174) bytes actual code+pool
 *
 * RANGE NOTE (discrepancy, documented): the symbols CSV row for this function
 * is (0x012294,0x012326,calculateDSCTrailingTimingDerate?,ghidra-hand), and a
 * phantom "modifyTrailingTiming" row sits at (0x012326,0x012342).  The real
 * function does NOT end at 0x12326: the code runs to the `rts` @0x1233E
 * (delay pop of fr15 @0x12340) and its literal pool (the words @0x12384..0x12396
 * plus the dwords @0x1239C..0x123B8) is shared with the adjacent pool block;
 * the next function (calculateLeadingTimingDerateCompensated @0x12342) starts
 * exactly at 0x12342.  The 0x12326..0x1233E tail (jsr saturate + fmov.s store)
 * IS part of this function (verified by disassembly).  The phantom
 * "modifyTrailingTiming" row @0x012326 is spurious — that address is inside
 * this function.  The CSVs updated here therefore widen this row to
 * 0x012294..0x012342 and drop the phantom modifyTrailingTiming row
 * (structural twin of the 0x121A4 "modifyTiming" cleanup).
 *
 * ENTRY VERIFICATION: 0x12294 matches the CSV start.  Valid entry: opens with
 * the standard prologue (three fmov.s frN,@-r15 pushes + sts.l pr,@-r15);
 * the preceding function (DSC-leading twin @0x121A4) ends with `rts` @0x1224E
 * (delay pop @0x12240 + literal pool @0x12250..0x12292), so no fall-through
 * into us; no incoming branches into the middle.  Called via the function-
 * pointer slot @0x144DC of the engineControlCalculateTiming dispatcher
 * (0x141FC) dispatch table — the slot immediately AFTER the DSC-leading twin's
 * slot @0x144C8 (0x000121A4).  The ROM literal @0x144DC is the ONLY 32-bit
 * reference to 0x12294 in the binary.  The CSV address IS the real entry point.
 *
 * SEMANTICS (instruction-for-instruction, see disasm): trailing-timing DSC
 * (dynamic-stability-control) derate writer — different tail than its leading
 * twin (0x121A4): same branch topology, but the DSC-cut constant is +10.0
 * (not -5.0) and the output goes to f32@A634 (the trailing per-rotor base).
 * It computes:
 *
 *   s = complement_shift_u32(@A784, 0.0f, 1e-5f)   // call 1, low byte -> stack
 *   r = complement_shift_u32(@BCA8, 0.0f, 1e-5f)   // call 2, full r4
 *
 *   if u8@AAC6 == 1 && (s & 0xFF) == 0 &&
 *       2000.0 > f32@B594 && u8@CCE4 == 1:
 *       derate = 10.0                              // DSC cut (ROM 0x6E0CC)
 *   else if u8@BC02 == 0 && f32@A9A4 > 0.0f &&
 *           (u8@ROM 0x6E095 == 0 || (r & 0xFF) == 0):
 *       derate = f32@A
 *   else:
 *       derate = f32@A638
 *
 *   f32@0xFFFFA634 = saturate(derate, f32@A658, 65.0f)   // clamp @0x2404
 *
 * The 10.0 DSC-cut branch is gated on: byte AAC6 (==1), A784 within the 1e-5
 * deadband of 0 (the first guard's "zero" result), B594 below 2000.0 RPM,
 * and byte CCE4 (==1).  u8@ROM 0x6E095 is a calibration enable that is 0x00
 * in this ROM, so the middle branch always resolves to the f32@A990 reference;
 * the r4 guard is dead in practice but is transcribed for fidelity.  r0 on
 * return holds the last integer value the branch chain left in it: 0 on the
 * f32@A990 path, the masked CCE4 byte on the 10.0 path, else the masked AAC6
 * byte / the mova address 0x123A4 / the masked CCE4 byte depending on which
 * gate failed (see the test reference model).  All stack usage is the
 * 0xFFFFDEEC..0xFFFFDF00 window (fr13/fr14/fr15 + PR saves, one scratch byte).
 *
 * Range  : 0x12294 .. 0x12342 (code 0x12294..0x12340, literal pool 0x12384..0x123B8
 *         [shared tail block]; next function at 0x12342)
 * Literal pool (values verified against roms/stock/60E0FC00.bin; mov.w values
 * sign-extend to 0xFFFFxxxx):
 *   0x12384 0xB594   (mov.w -> f32 @0xFFFFB594, RPM-gate input)
 *   0x12386 0xA784   (mov.w -> f32 @0xFFFFA784, first deadband input)
 *   0x12388 0xBCA8   (mov.w -> f32 @0xFFFFBCA8, second deadband input)
 *   0x1238A 0xAAC6   (mov.w -> u8 @0xFFFFAAC6, gate byte 1)
 *   0x1238C 0xCCE4   (mov.w -> u8 @0xFFFFCCE4, gate byte 2)
 *   0x1238E 0xBC02   (mov.w -> u8 @0xFFFFBC02, middle-branch gate byte)
 *   0x12390 0xA9A4   (mov.w -> f32 @0xFFFFA9A4, middle-branch gate float)
 *   0x12392 0xA990   (mov.w -> f32 @0xFFFFA990, middle derate reference)
 *   0x12394 0xA638   (mov.w -> f32 @0xFFFFA638, default derate reference)
 *   0x12396 0xA634   (mov.w -> f32 output @0xFFFFA634)
 *   0x1239C 0x3727C5AC (mova/fmov.s -> 1e-5f deadband @ROM 0x1239C)
 *   0x123A0 0x00002440 (mov.l -> complement_shift_u32 @0x2440)
 *   0x123A4 0x44FA0000 (mova/fmov.s -> 2000.0f RPM gate @ROM 0x123A4)
 *   0x123A8 0x0006E0CC (mov.l -> f32 10.0f DSC cut @ROM 0x6E0CC)
 *   0x123AC 0x0006E095 (mov.l -> u8 cal enable @ROM 0x6E095, ==0)
 *   0x123B0 0x0006E0E4 (mov.l -> f32 65.0f clamp high @ROM 0x6E0E4)
 *   0x123B4 0xFFFFA658 (mov.l -> f32 @0xFFFFA658, clamp low)
 *   0x123B8 0x00002404 (mov.l -> saturate @0x2404)
 * RAM r/w: reads A784, BCA8, AAC6, B594, CCE4, BC02, A9A4, A990, A638, A658
 * (plus the 4-byte stack scratch); writes f32@A634 (plus the stack window).
 * ROM read: literals above incl. the deadband/2000/65/10 cal constants.
 * Sub-calls: complement_shift_u32 @0x2440 (x2, = isNotZero_wDivideByZero-
 *   Protect, verified in c/calc_intake_pressure_pid_output_0x1252C.c and
 *   c/lib/complement_shift_u32.c) and saturate @0x2404 (x1).  SH-2E convention:
 *   float args fr4/fr5/fr6, int result r0 (0/1) for 0x2440; float result fr0
 *   for 0x2404.
 * VERIFIED against the SH-2 emulator (tools/sh2emu.py, 60E0FC00.bin) in
 * c/tests/test_calculateDSCTrailingTimingDerate_0x12294.py — 0 mismatches over
 * 5 seeds x 100000 iterations (byte-exact full post-call RAM overlay + r0).
 */
#include <stdint.h>

/* ---- RAM globals (mov.w literals sign-extend to 0xFFFFxxxx) ---- */
#define RAM_A784  (*(volatile float *)0xFFFFA784)  /* deadband input 1        */
#define RAM_BCA8  (*(volatile float *)0xFFFFBCA8)  /* deadband input 2        */
#define RAM_AAC6  (*(volatile uint8_t *)0xFFFFAAC6)  /* gate byte 1 (==1)     */
#define RAM_B594  (*(volatile float *)0xFFFFB594)  /* RPM gate (< 2000)       */
#define RAM_CCE4  (*(volatile uint8_t *)0xFFFFCCE4)  /* gate byte 2 (==1)     */
#define RAM_BC02  (*(volatile uint8_t *)0xFFFFBC02)  /* middle gate byte (0)  */
#define RAM_A9A4  (*(volatile float *)0xFFFFA9A4)  /* middle gate float (>0) */
#define RAM_A990  (*(volatile float *)0xFFFFA990)  /* middle derate reference */
#define RAM_A638  (*(volatile float *)0xFFFFA638)  /* default derate reference */
#define RAM_A658  (*(volatile float *)0xFFFFA658)  /* clamp low               */
#define OUT_A634  (*(volatile float *)0xFFFFA634)  /* trailing-timing derate  */

/* ---- ROM calibration constants ---- */
#define CAL_DEADBAND_1E5 (*(const float *)0x0001239C)   /* 1e-5f     */
#define CAL_RPM_GATE_2K  (*(const float *)0x000123A4)   /* 2000.0f   */
#define CAL_ENABLE_6E095 (*(const uint8_t *)0x0006E095) /* 0x00      */
#define CAL_DSC_CUT_10   (*(const float *)0x0006E0CC)   /* 10.0f     */
#define CAL_CLAMP_HI_65  (*(const float *)0x0006E0E4)   /* 65.0f     */

/* ---- External helpers (in ROM, both verified separately) ---- */
extern uint32_t complement_shift_u32(float threshold, float value, float adjustment);
/* @0x2440 (= isNotZero_wDivideByZeroProtect): 1 if |threshold-value| > adjustment */
extern float fpu_compare_and_select(float val, float lo, float hi);
/* @0x2404: clamp(val, lo, hi) */

void calculateDSC_TrailingTimingDerate_0x12294(void)
{
    uint32_t s, r;
    float    derate;

    /* first guard: A784 must sit inside the 1e-5 deadband of 0.0 */
    s = complement_shift_u32(RAM_A784, 0.0f, CAL_DEADBAND_1E5);
    /* second guard result (only consumed via the dead cal-enable byte) */
    r = complement_shift_u32(RAM_BCA8, 0.0f, CAL_DEADBAND_1E5);

    if (RAM_AAC6 == 1 && (s & 0xFF) == 0 &&
        CAL_RPM_GATE_2K > RAM_B594 && RAM_CCE4 == 1) {
        derate = CAL_DSC_CUT_10;                    /* 10.0 (DSC cut) */
    } else if (RAM_BC02 == 0 && RAM_A9A4 > 0.0f &&
               (CAL_ENABLE_6E095 == 0 || (r & 0xFF) == 0)) {
        derate = RAM_A990;
    } else {
        derate = RAM_A638;
    }

    /* clamp the derate into [f32@A658, 65.0] and publish */
    OUT_A634 = fpu_compare_and_select(derate, RAM_A658, CAL_CLAMP_HI_65);
}