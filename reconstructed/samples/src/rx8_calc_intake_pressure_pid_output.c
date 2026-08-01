/*
 * =============================================================================
 * rx8_calc_intake_pressure_pid_output.c  —  INTAKE-PRESSURE PID OUTPUT STAGE
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x1252C  (174 bytes, 0x1252C..0x125DA)
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_calc_intake_pressure_pid_output.py
 *               (host-gcc vs tools/sh2emu.py over edge + random vectors;
 *               bit-exact float output at RAM[0xFFFFA63C], 0 mismatches).
 * Lift (truth): c/calc_intake_pressure_pid_output_1252C.c (same address, listed
 *               in c/verified_addrs.txt) — re-verified instruction-for-instruction
 *               against the 60E1D400.bin disassembly during this lift; no
 *               discrepancy found.
 *
 * WHAT THE FUNCTION DOES
 * ----------------------
 * This is the *output stage* of the intake-manifold-pressure PID: it does NOT
 * compute a Kp/Ki/Kd term.  It selects one of three correction references based
 * on the engine operating mode and clamps it to a calibrated window, writing the
 * final "PID output" to RAM 0xFFFFA63C:
 *
 *     rpm    = RAM[0xFFFFB5B8]            (engine speed, float)
 *     target = RAM[0xFFFFA790]            (intake pressure target, float)
 *     error  = RAM[0xFFFFBCE4]            (intake pressure error, float)
 *
 *     r1 = deadband(target, 0.0, cal 0x12600)   -> 1 if target < -1e-5 or > +1e-5
 *     r2 = deadband(error,  0.0, cal 0x12600)   -> 1 if error  < -1e-5 or > +1e-5
 *
 *     if (RAM[0xFFFFAADA] == 1          &&   // closed-loop active
 *         r1 == 0                       &&   // |target| within the deadband
 *         rpm < 2000.0                  &&   // below idle threshold (cal 0x12608)
 *         RAM[0xFFFFCE58] == 1)               // idle/overrun condition flag
 *         correction = *(float*)0x6E3D8;      // = -5.0 fixed kPa correction
 *     else if (RAM[0xFFFFBC36] == 0     &&   // fuel cut NOT active
 *              RAM[0xFFFFA9B8] > 0.0    &&   // lambda status positive
 *              (*(uint8_t*)0x6E3D4 == 0 || r2 == 0))   // cal enable==0 or |error| tiny
 *         correction = RAM[0xFFFFA9A8];      // alternate reference (RAM)
 *     else
 *         correction = RAM[0xFFFFA640];      // default reference (RAM)
 *
 *     RAM[0xFFFFA63C] = clamp(correction, RAM[0xFFFFA658], 65.0)   (cal 0x6E3F0)
 *
 * The three references are all pressures in kPa (MAP-domain): -5.0 during
 * closed-loop idle, RAM[0xFFFFA9A8] in the normal cruise path, RAM[0xFFFFA640]
 * in the open-loop / fuel-cut / lambda-fault path.  The clamp window
 * [RAM[0xFFFFA658], 65.0] bounds the correction the rest of the intake-pressure
 * subsystem may apply.
 *
 * CALLING CONVENTION / CALLEES
 * ----------------------------
 * The ROM entry @0x1252C is a void function with NO ABI return value; its whole
 * effect is the RAM write above.  It internally jsr's TWO non-ABI leaves that the
 * emulator executes from the REAL ROM bytes:
 *
 *   - complement_shift_u32  @0x2440  (fr4=threshold, fr5=value, fr6=adjustment;
 *     returns r0).  Inlined here as rx8_deadband_2440().
 *   - fpu_compare_and_select @0x2404  (fr4=val, fr5=lo, fr6=hi; returns fr0).
 *     Inlined here as rx8_clamp_2404().
 *
 * Both are tiny, separately-verified leaves (c/complement_shift_u32.c and the
 * 0x2404 clamp used by c/calc_intake_pressure_pid_output_1252C.c) and are inlined
 * as static helpers so this sample stays self-contained (the oracle build links
 * only this file + its oracle).
 *
 * FP EXACTNESS
 * ------------
 * This function performs NO FP arithmetic of its own — the correction value is a
 * bit-exact copy of one of the five inputs (-5.0, alt_ref, default_ref, clamp_lo,
 * 65.0).  The only arithmetic in the whole call tree lives in the 0x2440 deadband
 * leaf, which emits exactly two single-precision ops, `value - adjustment` (fsub)
 * and `value + adjustment` (fadd), each a single IEEE-754 rounding; since the ROM
 * calls it with value = 0.0 and the calibrated adjustment 1e-5 these are exact
 * constants, so no fmaf()/rounding work is needed.  The two fcmp/gt branches are
 * ordinary IEEE `>` — with NaN operands both sides read unordered, i.e. the
 * condition is false and the target counts as "inside the deadband", exactly like
 * C's `>`.
 * =============================================================================
 */
#include <stdint.h>
#include "rx8_samples.h"

/* ---- RAM map (all addresses verified against the 0x125DA literal pool) ---- */
#define RAM_ENGINE_RPM           (*(volatile float   *)0xFFFFB5B8u)
#define RAM_IP_TARGET            (*(volatile float   *)0xFFFFA790u)
#define RAM_IP_ERROR             (*(volatile float   *)0xFFFFBCE4u)
#define RAM_CLOSED_LOOP_ACTIVE   (*(volatile uint8_t *)0xFFFFAADAu)
#define RAM_IP_IDLE_FLAG         (*(volatile uint8_t *)0xFFFFCE58u)
#define RAM_FUEL_CUT_ACTIVE      (*(volatile uint8_t *)0xFFFFBC36u)
#define RAM_LAMBDA_STATUS        (*(volatile float   *)0xFFFFA9B8u)
#define RAM_IP_ALT_REF           (*(volatile float   *)0xFFFFA9A8u)
#define RAM_IP_DEFAULT_REF       (*(volatile float   *)0xFFFFA640u)
#define RAM_IP_CLAMP_LOW         (*(volatile float   *)0xFFFFA658u)
#define RAM_IP_PID_OUTPUT        (*(volatile float   *)0xFFFFA63Cu)

/* ---- Calibration constants (real ROM values; the harness seeds these pages
 *      with the stock 60E1D400.bin bytes so both sides read identical data) ---- */
#define CAL_IP_RPM_THRESHOLD     (*(const float *)0x00012608u)   /* 2000.0   */
#define CAL_IP_DEADBAND          (*(const float *)0x00012600u)   /* 1e-5     */
#define CAL_IP_CORRECTION        (*(const float *)0x0006E3D8u)   /* -5.0     */
#define CAL_IP_CLAMP_HIGH        (*(const float *)0x0006E3F0u)   /* 65.0     */
#define CAL_IP_ENABLE            (*(const uint8_t *)0x0006E3D4u) /* 0        */

/* 0x2440 — deadband / range-violation test (leaf called twice via jsr).
 *
 * ROM:
 *     fmov  fr5,fr3       ; fr3 = value
 *     fsub  fr6,fr3       ; fr3 = value - adjustment
 *     fcmp/gt fr4,fr3     ; T = (value - adjustment > threshold)
 *     bt    outside
 *     fmov  fr5,fr3       ; fr3 = value
 *     fadd  fr6,fr3       ; fr3 = value + adjustment
 *     fcmp/gt fr3,fr4     ; T = (threshold > value + adjustment)
 *     bt    outside
 *     rts / mov #0,r4 -> r0
 * outside: mov #1,r4 -> r0
 *
 * Returns 1 when the threshold lies strictly outside the open interval
 * (value - adjustment, value + adjustment), else 0.  With value = 0.0 and a
 * NaN threshold both fcmp/gt report unordered (T = 0), so a NaN yields 0 —
 * exactly like the C `>` below. */
static uint32_t rx8_deadband_2440(float threshold, float value, float adjustment)
{
    if (value - adjustment > threshold) {
        return 1u;
    }
    if (threshold > value + adjustment) {
        return 1u;
    }
    return 0u;
}

/* 0x2404 — fpu_compare_and_select (clamp leaf, called once via jsr).
 *
 * ROM:
 *     fcmp/gt fr5,fr4     ; T = (val > lo)
 *     bt     0x240E
 *     bra    0x241A / fmov fr5,fr7   ; val <= lo  -> result = lo
 *     fcmp/gt fr4,fr6     ; T = (hi > val)
 *     bt     0x2418 / fmov fr4,fr7   ; hi  > val  -> result = val
 *     bra    0x241A / fmov fr6,fr7   ; val >= hi  -> result = hi
 *     rts    / fmov fr7,fr0
 *
 * I.e. clamp(val, lo, hi); with a NaN `val` both fcmp/gt are unordered so the
 * result is `lo`, matching the C comparisons below. */
static float rx8_clamp_2404(float val, float lo, float hi)
{
    if (val > lo) {
        if (hi > val) {
            return val;
        }
        return hi;
    }
    return lo;
}

/* 0x1252C — intake-pressure PID output stage (void; result is the RAM write). */
void rx8_calc_intake_pressure_pid_output(void)
{
    float    rpm, target, error;
    uint32_t r1, r2;
    float    correction;

    rpm    = RAM_ENGINE_RPM;
    target = RAM_IP_TARGET;
    error  = RAM_IP_ERROR;

    /* 1 if the target/error left the calibrated deadband around 0.0. */
    r1 = rx8_deadband_2440(target, 0.0f, CAL_IP_DEADBAND);
    r2 = rx8_deadband_2440(error,  0.0f, CAL_IP_DEADBAND);

    if (RAM_CLOSED_LOOP_ACTIVE == 1 &&
        r1 == 0 &&
        rpm < CAL_IP_RPM_THRESHOLD &&
        RAM_IP_IDLE_FLAG == 1) {
        correction = CAL_IP_CORRECTION;                 /* -5.0 */
    } else if (RAM_FUEL_CUT_ACTIVE == 0 &&
               RAM_LAMBDA_STATUS > 0.0f &&
               (CAL_IP_ENABLE == 0 || r2 == 0)) {
        correction = RAM_IP_ALT_REF;                    /* RAM[0xA9A8] */
    } else {
        correction = RAM_IP_DEFAULT_REF;                /* RAM[0xA640] */
    }

    /* clamp(correction, [RAM[0xFFFFA658], 65.0]) via leaf 0x2404. */
    RAM_IP_PID_OUTPUT = rx8_clamp_2404(correction,
                                       RAM_IP_CLAMP_LOW,
                                       CAL_IP_CLAMP_HIGH);
}
