/* calc_ignition_all_rotors_13C2C.c
 *
 * ROM: 60E1D400  |  Address: 0x13C2C  |  Size: 208 bytes
 *
 * Main ignition timing correction calculation.
 * Called by engineControlCalculateTiming (0x14584) once per scheduler tick.
 *
 * Computes the combined ignition timing correction based on:
 *   - Engine speed (RPM)
 *   - Knock sensor status
 *   - Coolant temperature
 *   - 1-D calibration table lookup
 *
 * The resulting corrections are added to the base ignition timing and written
 * to per-rotor output registers.
 *
 * BEHAVIORAL RECONSTRUCTION, emulator-verified against the ROM bytes:
 *
 *   The ROM keeps two distinct quantities across the whole function:
 *     fr15 = "correction"   -> feeds 0x13E6C, whose result is stored at A744
 *     fr4  = "clamp input"  -> feeds 0x13ED2 (saturate to [-10.0, 0.0]),
 *                              whose result is stored back at A73C
 *
 *   Knock-active path (byte@C0C7 >= byte@0x7983B):
 *     the 2.5 deg max knock retard is subtracted from the CLAMP INPUT
 *     (fr4 = fr6 - 2.5, where fr6 = f32@A73C) -- NOT from the correction,
 *     and the comparison is between two BYTES, not a float RPM.
 *
 *   ECT block (byte@C0C4 == 1):
 *     OVERWRITES the correction with previous_timing - 1.0
 *     (delay slot `fmov fr5,fr15` then `fsub 1.0`); it does NOT accumulate.
 *     Both corr_enable branches use 1.0 (0x79880 and 0x79888 are both 1.0f).
 *
 *   Final dispatch (0x13CCE):
 *     A73C = 0x13ED2(fr4)                    clamp to [-10.0, 0.0]
 *     A744 = 0x13E6C(correction)             saturate(correction, table(RPM), 0.0)
 *     A734 = A738 = 0x13EE6(A744 + A73C)     saturate(sum, t1(RPM), t2(RPM))
 *     A75C = ign_enable_byte (r14)
 *
 * The three helper subroutines (0x13ED2, 0x13E6C, 0x13EE6) are implemented
 * below as static functions with their ROM behavior; 0x2068 (generic 1-D table
 * lookup) remains extern (shared with calc_adaptive_fuel_trim.c).
 */

#include <stdint.h>

/* ========================================================================
 * RAM address map (on-chip SH-2E RAM, 0xFFFFA700–0xFFFFA7FF)
 * ======================================================================== */

#define RAM_ENGINE_SPEED       (*(volatile float *)0xFFFFA73C)   /* fr6 input; reused to store 0x13ED2 clamp result */
#define RAM_IGNITION_ENABLE    (*(volatile uint8_t *)0xFFFFA740) /* ignition enable byte (r14) */
#define RAM_IGNITION_TIMING    (*(volatile float *)0xFFFFA744)   /* main ign timing output (fr5/previous_timing input) */
#define RAM_KNOCK_SENSOR_FAULT (*(volatile uint8_t *)0xFFFFA748) /* knock sensor fault status */
#define RAM_KNOCK_DETECTED     (*(volatile uint8_t *)0xFFFFA749) /* knock detected flag */
#define RAM_KNOCK_SCRATCH      (*(volatile float *)0xFFFFA74C)   /* intermediate storage */
#define RAM_KNOCK_ACTIVE       (*(volatile uint8_t *)0xFFFFA75C) /* knock control active byte */
#define RAM_RPM_ALT            (*(volatile float *)0xFFFFB5B8)   /* alternate RPM read */
#define RAM_ECT_STATUS         (*(volatile uint8_t *)0xFFFFC0C4) /* coolant temp status */
#define RAM_ECT_CORR_ENABLE    (*(volatile uint8_t *)0xFFFFC0C5) /* ECT correction enable */
#define RAM_KNOCK_COUNTER      (*(volatile uint8_t *)0xFFFFC0C7) /* knock counter byte (0x13C96 compare) */
#define RAM_IGN_TIMING_LEAD    (*(volatile float *)0xFFFFA734)   /* leading-rotor timing output (0x13EE6 result) */
#define RAM_IGN_TIMING_TRL     (*(volatile float *)0xFFFFA738)   /* trailing-rotor timing output (0x13EE6 result) */
#define RAM_LKUP1_SCRATCH      (*(volatile float *)0xFFFFA750)   /* 0x13EE6 lookup 1 result scratch */
#define RAM_LKUP2_SCRATCH      (*(volatile float *)0xFFFFA754)   /* 0x13EE6 lookup 2 result scratch */
#define RAM_STATUS_B5A4        (*(volatile uint8_t *)0xFFFFB5A4) /* 0x13E6C table-select status byte */
#define RAM_STATUS_BB55        (*(volatile uint8_t *)0xFFFFBB55) /* 0x13E6C table-select status byte */
#define RAM_STATUS_BCA9        (*(volatile uint8_t *)0xFFFFBCA9) /* 0x13E6C table-select status byte */

/* ========================================================================
 * Calibration ROM constants
 * ======================================================================== */

#define CAL_ZERO               (*(const float *)0x0007987C)      /* 0.0f */
#define CAL_KNOCK_RETARD_MAX   (*(const float *)0x00079890)     /* 2.5f — max knock retard */
#define CAL_CORR_DEFAULT_1     (*(const float *)0x00079880)     /* 1.0f */
#define CAL_CORR_DEFAULT_2     (*(const float *)0x00079888)     /* 1.0f */
#define CAL_KNOCK_THRESH_BYTE  (*(const uint8_t *)0x0007983B)   /* byte threshold for knock counter (== 1) */
#define CAL_13ED2_LOWER        (*(const float *)0x0007989C)     /* -10.0f — 0x13ED2 saturate lower bound */
#define CAL_13ED2_UPPER        (*(const float *)0x000798A0)     /* 0.0f   — 0x13ED2 saturate upper bound */
#define CAL_13E6C_UPPER        (*(const float *)0x00079878)     /* 0.0f   — 0x13E6C saturate upper bound */
#define CAL_13E6C_THRESH       (*(const uint8_t *)0x00079838)   /* 5 — 0x13E6C table-select threshold */
#define CAL_TABLE_1D_DESC      ((const uint8_t *)0x0006B68C)    /* 1D lookup descriptor (detected==0 path) */
#define CAL_13E6C_TABLE_A      ((const uint8_t *)0x0006B678)    /* 0x13E6C table A (4-pt u8) */
#define CAL_13E6C_TABLE_B      ((const uint8_t *)0x0006B664)    /* 0x13E6C table B (5-pt u8) */
#define CAL_13EE6_TABLE_1      ((const uint8_t *)0x0006B6A0)    /* 0x13EE6 lookup 1 (12-pt u8) */
#define CAL_13EE6_TABLE_2      ((const uint8_t *)0x0006B6B4)    /* 0x13EE6 lookup 2 (12-pt u8) */

/* ========================================================================
 * Table descriptor for 1D lookup (function at 0x2068)
 *
 * Layout:
 *   +0: u16  count     — number of X-axis breakpoints
 *   +2: u8   type      — cell type (0=float, 4=u8, 8=u16, 12=s8, 16=s16)
 *   +3: u8   pad
 *   +4: f32* axis_x    — pointer to X-axis array
 *   +8: void* values   — pointer to Y values
 *   +12: f32 scale     — only if type != 0: result = interp * scale + offset
 *   +16: f32 offset
 * ======================================================================== */
typedef struct {
    uint16_t     count;
    uint8_t      type;
    uint8_t      _pad;
    const float *axis_x;
    const void  *values;
    /* scale and offset follow only if type != 0 */
} Table1D;

/* 1D table lookup @ 0x2068.  r4=descriptor, fr4=x, returns fr0 */
extern float table1D_lookup(const Table1D *desc, float x);

/* ========================================================================
 * Helper 0x13ED2 — clamp input to [-10.0, 0.0]
 *
 * ROM: fr6 = f32@0x798A0 (0.0 upper), fr5 = f32@0x7989C (-10.0 lower),
 *      jsr 0x2404 (saturate: sig=fr4, lower=fr5, upper=fr6).
 * Returns fr0 = clamp(fr4, -10.0, 0.0).
 * ======================================================================== */
static float clamp_correction_0x13ED2(float v)
{
    float lower = CAL_13ED2_LOWER;   /* -10.0 */
    float upper = CAL_13ED2_UPPER;   /* 0.0 */
    if (v < lower) return lower;
    if (v > upper) return upper;
    return v;
}

/* ========================================================================
 * Helper 0x13E6C — final correction clamp: saturate(correction, table(RPM), 0.0)
 *
 * ROM table selection (reads status bytes; see 0x13E76..0x13EB6):
 *   if   byte@B5A4 == 1  &&  byte@BCA9 >= byte@0x79838 (5)  -> table 0x6B678
 *   else if byte@B5A4 != 0                                  -> table 0x6B664
 *   else (byte@B5A4 == 0): byte@BB55 > 5 or byte@BB55 == 0  -> table 0x6B664
 *                          otherwise                        -> table 0x6B678
 * Then: lower = table1D_lookup(table, RPM@B5B8), upper = f32@0x79878 (0.0),
 *       return saturate(correction, lower, upper).
 * ======================================================================== */
static const Table1D *select_13E6C_table(void)
{
    uint8_t status = RAM_STATUS_B5A4;      /* 0xFFFFB5A4 */
    uint8_t bca9   = RAM_STATUS_BCA9;      /* 0xFFFFBCA9 */
    uint8_t bb55   = RAM_STATUS_BB55;      /* 0xFFFFBB55 */
    uint8_t thr    = CAL_13E6C_THRESH;     /* 5 */
    if (status == 1 && bca9 >= thr)
        return (const Table1D *)CAL_13E6C_TABLE_A;
    if (status != 0)
        return (const Table1D *)CAL_13E6C_TABLE_B;
    if (bb55 > thr || bb55 == 0)
        return (const Table1D *)CAL_13E6C_TABLE_B;
    return (const Table1D *)CAL_13E6C_TABLE_A;
}

static float correction_final_clamp_0x13E6C(float correction)
{
    float rpm   = RAM_RPM_ALT;                          /* 0xFFFFB5B8 */
    float lower = table1D_lookup(select_13E6C_table(), rpm);
    float upper = CAL_13E6C_UPPER;                      /* 0.0f @0x79878 */
    if (correction < lower) return lower;
    if (correction > upper) return upper;
    return correction;
}

/* ========================================================================
 * Helper 0x13EE6 — rotor output clamp: saturate(v, t1(RPM), t2(RPM))
 *
 * ROM: lookup1 = table1D_lookup(0x6B6A0, RPM) -> RAM_A750
 *      lookup2 = table1D_lookup(0x6B6B4, RPM) -> RAM_A754
 *      return saturate(v, lookup1, lookup2)  (fr5=lookup1 lower, fr6=lookup2 upper)
 * The caller passes v = A744_result + A73C (delay slot `fadd fr3,fr4`).
 * ======================================================================== */
static float rotor_output_clamp_0x13EE6(float v)
{
    float rpm   = RAM_RPM_ALT;                          /* 0xFFFFB5B8 */
    float lower = table1D_lookup((const Table1D *)CAL_13EE6_TABLE_1, rpm);
    float upper = table1D_lookup((const Table1D *)CAL_13EE6_TABLE_2, rpm);
    RAM_LKUP1_SCRATCH = lower;                          /* 0xFFFFA750 */
    RAM_LKUP2_SCRATCH = upper;                          /* 0xFFFFA754 */
    if (v < lower) return lower;
    if (v > upper) return upper;
    return v;
}

/* ========================================================================
 * calc_ignition_all_rotors_13C2C
 *
 * Computes the ignition timing correction for all rotors.
 *
 * Pseudocode summary (register-level, mirrors the ROM exactly):
 *   1. Load previous timing (fr5/A744), clamp input (fr6/A73C), enable byte
 *      (r14/A740), knock sensor fault (r2/A748).  fr15 = fr5, fr4 = fr6.
 *   2. If knock sensor NOT faulted: correction = 0, clamp input = 0.
 *   3. If faulted:
 *        a. knock_detected == 0: correction = table1D_lookup(0x6B68C, RPM),
 *           A74C = correction, clamp input = 0.
 *        b. knock_detected != 0, knock_active == 0:
 *              ign_enable == 1 -> correction = 0, clamp input = 0
 *              ign_enable != 1 -> keep fr15/fr4 (prev_timing / A73C)
 *        c. knock_detected != 0, knock_active != 0:
 *              ign_enable != 1 -> keep fr15/fr4 (prev_timing / A73C)
 *              ign_enable == 1 -> clamp input = A73C - 2.5  (if byte@C0C7
 *                                 >= byte@0x7983B) else A73C
 *              ECT byte@C0C4 == 1 -> OVERWRITE correction = prev_timing - 1.0
 *   4. Final dispatch: A73C = clamp(fr4); A744 = 0x13E6C(correction);
 *      A734 = A738 = 0x13EE6(A744 + A73C); A75C = ign_enable_byte.
 * ======================================================================== */
void calc_ignition_all_rotors_13C2C(void)
{
    float previous_timing;          /* fr5  = f32@A744 */
    float engine_speed;             /* fr6  = f32@A73C */
    uint8_t ign_enable_byte;        /* r14  = u8@A740  */
    uint8_t knock_sensor_fault;     /* r2   = u8@A748  */
    float clamp_input;              /* fr4  (0x13ED2 argument) */
    float correction;               /* fr15 (0x13E6C argument) */
    float final_timing;             /* A744 value (0x13E6C result) */
    float clamp_result;             /* A73C value (0x13ED2 result) */
    float rotor_timing;             /* A734/A738 value (0x13EE6 result) */

    /* ---- Phase 1: Load inputs (0x13C38..0x13C4A) ---- */
    previous_timing   = RAM_IGNITION_TIMING;      /* fr5 */
    engine_speed      = RAM_ENGINE_SPEED;         /* fr6 */
    ign_enable_byte   = RAM_IGNITION_ENABLE;      /* r14 */
    knock_sensor_fault = RAM_KNOCK_SENSOR_FAULT;  /* r2  */
    correction  = previous_timing;                /* fr15 = fr5 (0x13C3E) */
    clamp_input = engine_speed;                   /* fr4  = fr6 (0x13C46) */

    /* ---- Phase 2: Knock sensor path selection (0x13C4C..0x13C8E) ---- */
    if (knock_sensor_fault == 0) {
        /* 0x13C4E not taken: bra 0x13C8A (delay fmov fr14,fr15) then
         * 0x13C8A bra 0x13CCE (delay fmov fr14,fr4) with fr14 = 0.0 (fldi0). */
        correction  = CAL_ZERO;
        clamp_input = CAL_ZERO;
    } else {
        /* ---- 0x13C56: faulted ---- */
        uint8_t knock_detected = RAM_KNOCK_DETECTED;  /* 0xFFFFA749 */

        if (knock_detected == 0) {
            /* ---- 0x13C60: light-retard path: RPM-based table lookup ---- */
            float rpm = RAM_RPM_ALT;              /* 0xFFFFB5B8 */
            correction = table1D_lookup((const Table1D *)CAL_TABLE_1D_DESC, rpm);
            RAM_KNOCK_SCRATCH = correction;       /* 0xFFFFA74C */
            clamp_input = CAL_ZERO;               /* fr4 = fr14 = 0.0 */
        } else {
            /* ---- 0x13C74: knock detected ---- */
            uint8_t knock_active = RAM_KNOCK_ACTIVE;  /* 0xFFFFA75C */

            if (knock_active == 0) {
                /* 0x13C7E: no knock control active */
                if (ign_enable_byte == 1) {
                    correction  = CAL_ZERO;       /* fr15 = f32@0x7987C = 0.0 */
                    clamp_input = CAL_ZERO;       /* fr4 = fr14 = 0.0 */
                }
                /* else: bf 0x13CCE keeps fr15=previous_timing, fr4=A73C */
            } else {
                /* ---- 0x13C8E: knock control active ---- */
                if (ign_enable_byte == 1) {
                    /* 0x13C96: byte threshold check (BYTE vs BYTE) */
                    uint8_t knock_counter = RAM_KNOCK_COUNTER;      /* 0xFFFFC0C7 */
                    uint8_t threshold     = CAL_KNOCK_THRESH_BYTE;  /* 0x7983B == 1 */
                    if (knock_counter >= threshold) {
                        /* 0x13CA4: fr4 = fr6 - 2.5  (2.5 subtracted from
                         * CLAMP INPUT = A73C value, NOT from the correction) */
                        clamp_input = engine_speed - CAL_KNOCK_RETARD_MAX;
                    } else {
                        /* 0x13CA0 not taken: fr4 stays = fr6 = A73C */
                        clamp_input = engine_speed;
                    }

                    /* 0x13CAC: ECT block — OVERWRITES correction */
                    if (RAM_ECT_STATUS == 1) {     /* 0xFFFFC0C4 */
                        /* 0x13CB8: both corr_enable branches set fr3 = 1.0
                         * (0x79880 when byte@C0C5==0, 0x79888 when !=0)
                         * after fr15 = previous_timing (fmov fr5,fr15). */
                        (void)RAM_ECT_CORR_ENABLE; /* 0xFFFFC0C5 — both branches use 1.0 */
                        correction = previous_timing - CAL_CORR_DEFAULT_1;
                    }
                    /* else: fr15 stays = previous_timing */
                }
                /* else: bf 0x13CCE keeps fr15=previous_timing, fr4=A73C */
            }
        }
    }

    /* ---- Phase 3: Final dispatch (0x13CCE..0x13CEC) ---- */

    /* bsr 0x13ED2: A73C = clamp(fr4, -10.0, 0.0) */
    clamp_result = clamp_correction_0x13ED2(clamp_input);
    RAM_ENGINE_SPEED = clamp_result;               /* 0xFFFFA73C */

    /* bsr 0x13E6C(fr4 = fr15): A744 = saturate(correction, table(RPM), 0.0) */
    final_timing = correction_final_clamp_0x13E6C(correction);
    RAM_IGNITION_TIMING = final_timing;            /* 0xFFFFA744 */

    /* bsr 0x13EE6(fr4 = fadd fr3,fr4 = A744 + A73C):
     * A734 = A738 = saturate(sum, t1(RPM), t2(RPM)) */
    rotor_timing = rotor_output_clamp_0x13EE6(final_timing + clamp_result);
    RAM_IGN_TIMING_LEAD = rotor_timing;            /* 0xFFFFA734 */
    RAM_IGN_TIMING_TRL  = rotor_timing;            /* 0xFFFFA738 */

    /* 0x13CEA: A75C = ign_enable_byte (r14) */
    RAM_KNOCK_ACTIVE = ign_enable_byte;
}

/* ========================================================================
 * NOTES:
 *
 * 1. The function at 0x2068 (labeled "fpu_multiply_accumulate" in IDA) is
 *    actually a generic 1D table interpolator.  The descriptor at 0x6B68C
 *    defines a 5-point RPM -> ignition correction table with u8 cells,
 *    scale=0.5, offset=-64.  Effective values:
 *      RPM < 2000: clamped to -10.0°
 *      RPM 2000-5000: -10.0° (retard)
 *      RPM > 5000: 0.0°
 *
 * 2. The constant 2.5° at 0x79890 is the maximum knock retard.  In the
 *    knock-active path it is subtracted from the CLAMP INPUT (fr4 = fr6 -
 *    2.5, fr6 being the f32@A73C value), and the result is clamped to
 *    [-10.0, 0.0] by 0x13ED2 before being stored back to A73C.  It never
 *    directly becomes the "correction" value.
 *
 * 3. The ECT block (0x13CAC..0x13CCC) OVERWRITES the correction with
 *    previous_timing - 1.0 when byte@C0C4 == 1.  Both corr_enable branches
 *    (byte@C0C5 == 0 / != 0) subtract the same 1.0 (constants at 0x79880
 *    and 0x79888 are both 1.0f), so corr_enable has no effect on the value.
 *
 * 4. Helper semantics (each emulator-verified against the ROM):
 *      0x13ED2 = saturate(v, -10.0, 0.0)   via 0x2404
 *      0x13E6C = saturate(correction, table_select(RPM), 0.0)
 *      0x13EE6 = saturate(v, t1(0x6B6A0,RPM), t2(0x6B6B4,RPM)), also stores
 *                lookups to A750/A754
 *
 * 5. Naming: the earlier reconstruction labeled these helpers
 *    "compare_select_two_float_values" (0x13ED2), "calc_fuel_pump_control_output"
 *    (0x13E6C) and "calc_fuel_pressure_load_compensation" (0x13EE6); those
 *    names are misleading (they are clamps around 1-D RPM lookups, shared
 *    with calc_fuel_injection_all_rotors at 0x13D3C).
 * ======================================================================== */
