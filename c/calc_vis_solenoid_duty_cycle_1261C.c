/* calc_vis_solenoid_duty_cycle_1261C.c
 *
 * ROM: 60E1D400  |  Address: 0x1261C  |  Size: 174 bytes (0x1261C..0x126CA)
 *       VERIFIED vs ROM emulator (0 mismatches, c/tests/test_calc_vis_solenoid_duty_cycle_1261C.py).
 *
 * VIS solenoid duty-cycle output stage.  The IDA-ai name
 * "calc_vis_solenoid_duty_cycle_1261C" matches the structure: this is the
 * output stage that picks one of three duty-cycle references based on the
 * engine operating mode and clamps it to a calibrated window, producing the
 * PWM duty written to RAM 0xFFFFA644.  It is the direct sibling of
 * calc_intake_pressure_pid_output_1252C (0x1252C) — same branch skeleton,
 * different RAM offsets / constants (0x1252C writes A63C and reads A790,
 * A640, A658; this one writes A644 and reads A794, A648, A668, A9A4).
 *
 * Exact behavior (from disassembly, every branch verified):
 *
 *   rpm    = RAM[0xFFFFB5B8]            (engine speed, float)
 *   target = RAM[0xFFFFA794]            (control target, float)
 *   error  = RAM[0xFFFFBCE4]            (intake pressure error, float)
 *
 *   r1 = complement_shift_u32(target, 0.0, 1e-5)  -> 1 if |target| > 1e-5
 *   r2 = complement_shift_u32(error,  0.0, 1e-5)  -> 1 if |error|  > 1e-5
 *
 *   if (RAM[0xFFFFAADA] == 1          &&   // closed-loop active
 *       r1 == 0                       &&   // |target| within deadband of 0
 *       rpm < 2000.0                  &&   // below idle threshold (lit @0x1272C)
 *       RAM[0xFFFFCE58] == 1)               // idle/overrun condition flag
 *       duty = *(float*)0x6E40C;            // = 10.0  (fixed low-speed duty)
 *   else if (RAM[0xFFFFBC36] == 0     &&   // fuel cut NOT active
 *            RAM[0xFFFFA9B8] > 0.0    &&   // lambda/air-charge status positive
 *            (*(uint8_t*)0x6E3D5 == 0 || r2 == 0))   // cal enable == 0 or |error| tiny
 *       duty = RAM[0xFFFFA9A4];            // alternate reference (RAM)
 *   else
 *       duty = RAM[0xFFFFA648];            // default reference (RAM)
 *
 *   RAM[0xFFFFA644] = clamp(duty, RAM[0xFFFFA668], 65.0)
 *   // clamp via fpu_compare_and_select @0x2404 = max(lo, min(val, hi))
 *
 * Notes on the references:
 *  - RAM[0xFFFFA9A4] is written by calc_spark_lead_trail_split_19220 as
 *    max(lead + minSplit, trail + minSplit) — the spark lead/trail split
 *    (timing + min-split) is re-used here as the cruise-path duty reference.
 *  - RAM[0xFFFFA648] is the default (open-loop / fuel-cut / lambda-fault)
 *    reference; RAM[0xFFFFA668] is the clamp lower bound.
 *  - The clamp window [RAM[0xFFFFA668], 65.0] bounds the duty.
 *
 * Helpers (both verified separately):
 *  - complement_shift_u32 @ 0x2440: returns 1 if |threshold - value| > adjustment
 *  - fpu_compare_and_select  @ 0x2404: clamp(val, lo, hi)
 *
 * The function pushes/restores fr13..fr15 + pr and parks the first 0x2440
 * result on the task stack (0xFFFFDEE8) — inside the 0xFFFFDE00..0xFFFFDF00
 * region the test harness skips.
 *
 * Verified: 100000 random inputs x 5 seeds (500000 total) vs the ROM emulator,
 * 0 mismatches.
 */

#include <stdint.h>

/* ---- RAM map (all addresses verified against literal pool) ---- */
#define RAM_ENGINE_RPM           (*(volatile float   *)0xFFFFB5B8)
#define RAM_VIS_TARGET           (*(volatile float   *)0xFFFFA794)
#define RAM_IP_ERROR             (*(volatile float   *)0xFFFFBCE4)
#define RAM_CLOSED_LOOP_ACTIVE   (*(volatile uint8_t *)0xFFFFAADA)
#define RAM_IP_IDLE_FLAG         (*(volatile uint8_t *)0xFFFFCE58)
#define RAM_FUEL_CUT_ACTIVE      (*(volatile uint8_t *)0xFFFFBC36)
#define RAM_LAMBDA_STATUS        (*(volatile float   *)0xFFFFA9B8)
#define RAM_VIS_ALT_REF          (*(volatile float   *)0xFFFFA9A4)
#define RAM_VIS_DEFAULT_REF      (*(volatile float   *)0xFFFFA648)
#define RAM_VIS_CLAMP_LOW        (*(volatile float   *)0xFFFFA668)
#define RAM_VIS_DUTY_OUT         (*(volatile float   *)0xFFFFA644)

/* ---- Calibration constants ---- */
#define CAL_VIS_RPM_THRESHOLD    (*(const float *)0x0001272C)   /* 2000.0 */
#define CAL_VIS_DEADBAND         (*(const float *)0x00012724)   /* 1e-5   */
#define CAL_VIS_IDLE_DUTY        (*(const float *)0x0006E40C)   /* 10.0   */
#define CAL_VIS_CLAMP_HIGH       (*(const float *)0x0006E424)   /* 65.0   */
#define CAL_VIS_ENABLE           (*(const uint8_t *)0x0006E3D5) /* 0      */

/* ---- External helpers (in ROM, both verified separately) ---- */
extern uint32_t complement_shift_u32(float threshold, float value, float adjustment);
/* @0x2440: 1 if |threshold - value| > adjustment */
extern float fpu_compare_and_select(float val, float lo, float hi);
/* @0x2404: clamp(val, lo, hi) */

void calc_vis_solenoid_duty_cycle_1261C(void)
{
    float   rpm, target, error;
    uint32_t r1, r2;
    float   duty;

    rpm    = RAM_ENGINE_RPM;
    target = RAM_VIS_TARGET;
    error  = RAM_IP_ERROR;

    /* |target| > deadband -> 1  (i.e. 1 means "target is non-zero") */
    r1 = complement_shift_u32(target, 0.0f, CAL_VIS_DEADBAND);
    /* |error| > deadband -> 1 */
    r2 = complement_shift_u32(error, 0.0f, CAL_VIS_DEADBAND);

    if (RAM_CLOSED_LOOP_ACTIVE == 1 &&
        r1 == 0 &&
        rpm < CAL_VIS_RPM_THRESHOLD &&
        RAM_IP_IDLE_FLAG == 1) {
        duty = CAL_VIS_IDLE_DUTY;              /* 10.0 */
    } else if (RAM_FUEL_CUT_ACTIVE == 0 &&
               RAM_LAMBDA_STATUS > 0.0f &&
               (CAL_VIS_ENABLE == 0 || r2 == 0)) {
        duty = RAM_VIS_ALT_REF;                /* RAM[A9A4] — spark split + minSplit */
    } else {
        duty = RAM_VIS_DEFAULT_REF;            /* RAM[A648] */
    }

    /* clamp(duty, [RAM_VIS_CLAMP_LOW, 65.0]) */
    RAM_VIS_DUTY_OUT = fpu_compare_and_select(duty,
                                              RAM_VIS_CLAMP_LOW,
                                              CAL_VIS_CLAMP_HIGH);
}
