/* calc_rotor_sync_idle_gate_B_0x12840.c
 *
 * ROM: 60E0FC00 | Address: 0x12840 | Size: 0xC4 (196) bytes per CSV range
 * 0x12840..0x12904.  Leaf — no prologue (no register push), no sub-calls
 * (the bsr/bra-looking words @0x128B8..0x128BE are the interleaved mov.w /
 * mov.l literal pool, not code).  Code runs to `rts` @0x12900 (delay
 * mov.b r5,@r2 @0x12902); the next function 0x12904 starts exactly at the
 * CSV end with a `mov.l r14,@-r15` prologue.  CSV range CORRECT, no phantom
 * rows; 0x128B8..0x128F2 literal pool sits inside the range.
 *
 * ENTRY VERIFICATION: 0x12840 matches the CSV start.  Valid leaf entry: the
 * ONLY 32-bit ROM reference to 0x12840 is the function-pointer slot @0x14440
 * in the engineControlCalculateTiming dispatcher (0x141FC) literal pool
 * (callgraph: 0x141FC -> 0x12840).  The preceding function 0x127E8 ends
 * rts+delay @0x1283C/0x1283E, so there is no fall-through into our body.
 * CSV address IS the real entry point.
 *
 * NAME VERDICT (source was ida-ai-xmap, flagged DUBIOUS): KEEP
 * `calc_rotor_sync_idle_gate_B`.  Byte-for-byte this is the FC00-bank build
 * of the SAME rotor-sync idle/anti-stall gate that the E1D400 twin
 * @0x12BC8 implements (c/calc_rotor_sync_idle_gate_B.c, previously VERIFIED):
 * identical residual gate + threshold structure, identical calibration
 * constants 40.0 R@0x72638 and 2000.0 @0x7263C (E1D400 keeps them at
 * 0x72BC4/0x72BC8), identical rotor-select + per-rotor status latch
 * (FC00: rotor_A u8@A444, rotor_B u8@A445, gate flag out u8@A680, prev-RPM
 * sample f32@A684; E1D400: A444/A445, flag u8@A690, prev f32@A694).  The
 * only cross-bank differences are the RAM cell addresses of the enable/
 * active/rotor-select bytes.  The DUBIOUS tag came purely from the cross-bank
 * ida-ai-xmap provenance, not from semantics — the verified behaviour
 * confirms the name is correct for this bank.
 *
 * SEMANTICS (instruction-for-instruction, see disasm):
 *   rotor_a = u8@FFFFA444;  rotor_b = u8@FFFFA445     (per-rotor status)
 *   rpm     = f32@FFFFB594; prev    = f32@FFFFA684    (latched last call)
 *   drop    = prev - rpm                              (fsub in the bt/s delay
 *                                                      slot @0x1285C — ALWAYS runs)
 *   gate u8@FFFFA680 = 1 iff ALL of:
 *     (u8@FFFFB580 == 1 || u8@FFFFC94C == 1)   - idle/closed-loop enable
 *     u8@FFFFAAC6 == 1                          - idle gate active
 *     (u8@FFFFA693 == 1 && rotor_a == 0) ||     - rotor-select: gate armed for
 *     (u8@FFFFA694 == 1 && rotor_b == 0)         the rotor not currently running
 *     drop >= 40.0                              - RPM fell >= 40 (0x72638 = 40.0)
 *     rpm  <= 2000.0                            - engine at low speed (0x7263C)
 *   else gate = 0.
 *   Always, after the branches: f32@FFFFA684 = rpm (store current as the
 *   "previous" sample for next call); u8@FFFFA693 = rotor_a; u8@FFFFA694 =
 *   rotor_b (latch the freshly-read per-rotor status bytes).
 *
 *   Downstream idle-control code uses the gate to hold idle speed against an
 *   RPM droop (anti-stall) while decelerating toward idle.
 *
 * RAM r/w: reads A444, A445, B594(f32), A684(f32), B580, C94C, AAC6, A693,
 * A694; writes A680, A684(f32), A693, A694.  Reads ROM f32 constants
 * @0x00072638 (40.0) and @0x0007263C (2000.0).
 *
 * VERIFIED against the SH-2 emulator (tools/sh2emu.py,
 * roms/stock/60E0FC00.bin) in c/tests/test_calc_rotor_sync_idle_gate_B_0x12840.py
 * - 0 mismatches over 5 seeds x 100000 iterations (byte-exact full post-call
 * RAM overlay + r0).
 */
#include <stdint.h>

/* ---- RAM globals (mov.w literals sign-extend to 0xFFFFxxxx) ---- */
#define RA_444 (*(volatile uint8_t *)0xFFFFA444)  /* u8 rotor A status            */
#define RB_445 (*(volatile uint8_t *)0xFFFFA445)  /* u8 rotor B status            */
#define RPM_B594 (*(volatile float   *)0xFFFFB594) /* f32 engine speed            */
#define PREV_A684 (*(volatile float *)0xFFFFA684) /* f32 previous RPM sample      */
#define GATE_A680 (*(volatile uint8_t *)0xFFFFA680) /* u8 idle anti-stall gate out */
#define ENA1_B580 (*(volatile uint8_t *)0xFFFFB580) /* u8 enable source A         */
#define ENA2_C94C (*(volatile uint8_t *)0xFFFFC94C) /* u8 enable source B         */
#define ACT_AAC6  (*(volatile uint8_t *)0xFFFFAAC6) /* u8 idle-gate-active gate   */
#define SEL_A693  (*(volatile uint8_t *)0xFFFFA693) /* u8 rotor-select / latch A  */
#define SEL_B694  (*(volatile uint8_t *)0xFFFFA694) /* u8 rotor-select / latch B  */

/* ---- Calibration constants (read-only ROM f32) ---- */
#define CAL_DROP (*(const float *)0x00072638)  /* 40.0  min RPM drop to arm gate */
#define CAL_RPM  (*(const float *)0x0007263C)  /* 2000.0 max RPM for low speed   */

void calc_rotor_sync_idle_gate_B_0x12840(void)
{
    uint8_t rotor_a = RA_444;
    uint8_t rotor_b = RB_445;
    float   rpm     = RPM_B594;
    float   prev    = PREV_A684;
    float   drop    = prev - rpm;             /* fsub in delay slot, always runs */
    uint8_t out     = 0;

    if ((ENA1_B580 == 1 || ENA2_C94C == 1) &&/* (B580==1) || (C94C==1)          */
        ACT_AAC6 == 1 &&                      /* AAC6 == 1                        */
        ((SEL_A693 == 1 && rotor_a == 0) ||   /* rotor A not running armed        */
         (SEL_B694 == 1 && rotor_b == 0)) &&  /*     ... or rotor B               */
        !(CAL_DROP > drop) &&                 /* drop >= 40.0 (fcmp/gt bt fail)   */
        !(rpm > CAL_RPM)) {                   /* rpm <= 2000.0                    */
        out = 1;
    }

    GATE_A680 = out;
    PREV_A684 = rpm;                          /* store sample as "prev" next call */
    SEL_A693  = rotor_a;                      /* latch per-rotor status bytes     */
    SEL_B694  = rotor_b;
}