/* calc_intake_pressure_pid_output_1252C.c
 *
 * ROM: 60E1D400  |  Address: 0x1252C  |  Size: 174 bytes  |  VERIFIED vs ROM emulator
 *
 * Intake manifold pressure PID output calculation (closed-loop).
 *
 * This function is the *output stage* of the intake-pressure PID: it does NOT
 * compute a Kp/Ki/Kd term.  Instead it selects one of three correction
 * references based on engine operating mode and clamps it to a calibrated
 * window, producing the final "PID output" written to RAM 0xFFFFA63C.
 *
 * Exact behavior (from disassembly, every branch verified):
 *
 *   rpm    = RAM[0xFFFFB5B8]            (engine speed, float)
 *   target = RAM[0xFFFFA790]            (intake pressure target, float)
 *   error  = RAM[0xFFFFBCE4]            (intake pressure error, float)
 *
 *   r1 = complement_shift_u32(target, 0.0, 1e-5)  -> 1 if |target| > 1e-5
 *   r2 = complement_shift_u32(error,  0.0, 1e-5)  -> 1 if |error|  > 1e-5
 *
 *   if (RAM[0xFFFFAADA] == 1          &&   // closed-loop active
 *       r1 == 0                       &&   // |target| within deadband of 0
 *       rpm < 2000.0                  &&   // below idle threshold (cal 0x12608)
 *       RAM[0xFFFFCE58] == 1)               // idle/overrun condition flag
 *       correction = *(float*)0x6E3D8;      // = -5.0  (fixed kPa correction)
 *   else if (RAM[0xFFFFBC36] == 0     &&   // fuel cut NOT active
 *            RAM[0xFFFFA9B8] > 0.0    &&   // lambda status positive
 *            (*(uint8_t*)0x6E3D4 == 0 || r2 == 0))   // cal enable == 0 or |error| tiny
 *       correction = RAM[0xFFFFA9A8];      // alternate reference (RAM)
 *   else
 *       correction = RAM[0xFFFFA640];      // default reference (RAM)
 *
 *   RAM[0xFFFFA63C] = clamp(correction, RAM[0xFFFFA658], 65.0)
 *   // clamp via fpu_compare_and_select @0x2404 = max(lo, min(val, hi))
 *
 * Notes on the helpers:
 *  - complement_shift_u32 @ 0x2440 (verified separately, 710 tests):
 *      returns 1 if |threshold - value| > adjustment
 *  - fpu_compare_and_select @ 0x2404:
 *      if fr4 <= fr5 -> fr5 ; else if fr6 > fr4 -> fr4 ; else fr6
 *      i.e. clamp(fr4, fr5, fr6)
 *
 * The three references are all pressures in kPa (MAP-domain):
 *  - -5.0  fixed value (ROM 0x6E3D8): used during closed-loop idle
 *  - RAM[0xFFFFA9A8]: alternate reference, used in the normal cruise path
 *  - RAM[0xFFFFA640]: default (open-loop / fuel-cut / lambda-fault) reference
 * The clamp window [RAM[0xFFFFA658], 65.0] bounds the correction the rest of
 * the intake-pressure subsystem may apply.
 */

#include <stdint.h>

/* ---- RAM map (all addresses verified against literal pool) ---- */
#define RAM_ENGINE_RPM           (*(volatile float   *)0xFFFFB5B8)
#define RAM_IP_TARGET            (*(volatile float   *)0xFFFFA790)
#define RAM_IP_ERROR             (*(volatile float   *)0xFFFFBCE4)
#define RAM_CLOSED_LOOP_ACTIVE   (*(volatile uint8_t *)0xFFFFAADA)
#define RAM_IP_IDLE_FLAG         (*(volatile uint8_t *)0xFFFFCE58)
#define RAM_FUEL_CUT_ACTIVE      (*(volatile uint8_t *)0xFFFFBC36)
#define RAM_LAMBDA_STATUS        (*(volatile float   *)0xFFFFA9B8)
#define RAM_IP_ALT_REF           (*(volatile float   *)0xFFFFA9A8)
#define RAM_IP_DEFAULT_REF       (*(volatile float   *)0xFFFFA640)
#define RAM_IP_CLAMP_LOW         (*(volatile float   *)0xFFFFA658)
#define RAM_IP_PID_OUTPUT        (*(volatile float   *)0xFFFFA63C)

/* ---- Calibration constants ---- */
#define CAL_IP_RPM_THRESHOLD     (*(const float *)0x00012608)   /* 2000.0 */
#define CAL_IP_DEADBAND          (*(const float *)0x00012600)   /* 1e-5   */
#define CAL_IP_CORRECTION        (*(const float *)0x0006E3D8)   /* -5.0   */
#define CAL_IP_CLAMP_HIGH        (*(const float *)0x0006E3F0)   /* 65.0   */
#define CAL_IP_ENABLE            (*(const uint8_t *)0x0006E3D4) /* 0      */

/* ---- External helpers (in ROM, both verified separately) ---- */
extern uint32_t complement_shift_u32(float threshold, float value, float adjustment);
/* @0x2440: 1 if |threshold - value| > adjustment */
extern float fpu_compare_and_select(float val, float lo, float hi);
/* @0x2404: clamp(val, lo, hi) */

void calc_intake_pressure_pid_output_1252C(void)
{
    float   rpm, target, error;
    uint32_t r1, r2;
    float   correction;

    rpm    = RAM_ENGINE_RPM;
    target = RAM_IP_TARGET;
    error  = RAM_IP_ERROR;

    /* |target| > deadband -> 1  (i.e. 1 means "target is non-zero") */
    r1 = complement_shift_u32(target, 0.0f, CAL_IP_DEADBAND);
    /* |error| > deadband -> 1 */
    r2 = complement_shift_u32(error, 0.0f, CAL_IP_DEADBAND);

    if (RAM_CLOSED_LOOP_ACTIVE == 1 &&
        r1 == 0 &&
        rpm < CAL_IP_RPM_THRESHOLD &&
        RAM_IP_IDLE_FLAG == 1) {
        correction = CAL_IP_CORRECTION;              /* -5.0 */
    } else if (RAM_FUEL_CUT_ACTIVE == 0 &&
               RAM_LAMBDA_STATUS > 0.0f &&
               (CAL_IP_ENABLE == 0 || r2 == 0)) {
        correction = RAM_IP_ALT_REF;                 /* RAM[0xA9A8] */
    } else {
        correction = RAM_IP_DEFAULT_REF;             /* RAM[0xA640] */
    }

    /* clamp(correction, [RAM_IP_CLAMP_LOW, 65.0]) */
    RAM_IP_PID_OUTPUT = fpu_compare_and_select(correction,
                                               RAM_IP_CLAMP_LOW,
                                               CAL_IP_CLAMP_HIGH);
}
