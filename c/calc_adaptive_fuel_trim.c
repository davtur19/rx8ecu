/* calc_adaptive_fuel_trim.c
 *
 * ROM: 60E1D400  |  Address: 0x1379C  |  Size: 228 bytes
 *
 * Adaptive fuel trim calculation — the long-term fuel correction that
 * compensates for component wear, tolerances, and fuel quality.
 *
 * Called from engineControlCalculateTiming Phase 2 as the first subsystem
 * call after the SR barrier.
 *
 * Computes a trim multiplier based on:
 *   - O2 sensor / lambda feedback
 *   - Engine speed (RPM)
 *   - Load deviation from reference
 *   - Calibration tables (two variants, selected by condition flag)
 *
 * The trim is integrated over time (leaky integrator), clipped to safe
 * limits, and written to RAM for consumption by the injector pulse width
 * calculation.
 *
 * NOTE: This is a BEHAVIORAL reconstruction.  The ROM uses global RAM
 * addresses rather than parameters.  Some details of the enable logic
 * are inferred.
 */

#include <stdint.h>

/* ========================================================================
 * RAM variables (on-chip SH-2A RAM)
 * ======================================================================== */

#define RAM_ENGINE_RPM          (*(volatile float *)0xFFFFB5B8)   /* engine speed */
#define RAM_LAMBDA_FEEDBACK     (*(volatile float *)0xFFFFB5C4)   /* O2 sensor / lambda reading */
#define RAM_TRIM_TABLE_SELECT   (*(volatile uint8_t *)0xFFFFB5AC) /* 0=table1, else=table2 */
#define RAM_TRIM_ENABLE         (*(volatile uint8_t *)0xFFFFB5A4) /* adaptive trim enable flag */
#define RAM_ERROR_SIGNAL        (*(volatile float *)0xFFFFA728)   /* computed error (deviation) */
#define RAM_TRIM_OUTPUT         (*(volatile float *)0xFFFFA720)   /* final trim value (output) */
#define RAM_RPM_THRESH_STATUS   (*(volatile float *)0xFFFFA730)   /* RPM comparison result */
#define RAM_TRIM_OUT_LEADING    (*(volatile float *)0xFFFFA718)   /* leading edge fuel trim */
#define RAM_TRIM_OUT_TRAILING   (*(volatile float *)0xFFFFAADA)   /* trailing edge fuel trim */
#define RAM_ECT_STATUS          (*(volatile uint8_t *)0xFFFFC084) /* coolant temp status */

/* ========================================================================
 * Calibration ROM constants and tables
 * ======================================================================== */

/* RPM threshold for enabling adaptation */
#define CAL_RPM_THRESHOLD       (*(const float *)0x00072C60)      /* 1500.0 */

/* Integral gain per scheduler tick */
#define CAL_INTEGRAL_GAIN       (*(const float *)0x00072C64)      /* ~0.009766 (1/1024) */

/* Minimum error threshold (deadband) */
#define CAL_ERROR_DEADBAND      (*(const float *)0x00072C5C)      /* 0.0 */

/* Proportional gain / adaptation speed */
#define CAL_PROP_GAIN           (*(const float *)0x00072C68)      /* 0.6 */

/* Trim limits */
#define CAL_TRIM_LIMIT_NEG      (*(const float *)0x00072C6C)      /* -2.8 */
#define CAL_TRIM_LIMIT_POS      (*(const float *)0x00072C70)      /* 0.7 */

/* 1D table descriptors */
#define TABLE_TRIM_PRIMARY      ((const uint8_t *)0x0006A868)     /* Table 2D - 106_ */
#define TABLE_TRIM_SECONDARY    ((const uint8_t *)0x0006A87C)     /* Table 2D - 107_ */

/* ========================================================================
 * External helpers
 * ======================================================================== */

/* 1D table lookup @ 0x2068
 *   r4 = descriptor, fr4 = x input
 *   returns fr0 = interpolated value */
extern float table1D_lookup(const void *desc, float x);

/* fpu_compare_and_select @ 0x2404
 *   Compare two floats and select based on condition */
extern float fpu_compare_and_select(float a, float b, float c);

/* ========================================================================
 * calc_adaptive_fuel_trim
 *
 * Main adaptive fuel trim computation.
 *
 * Pseudocode:
 *   1. Read engine speed (RPM) and lambda feedback (O2 sensor)
 *   2. Compute deviation from reference (target lambda or RPM-based reference)
 *   3. Select trim table based on flag at RAM_TRIM_TABLE_SELECT
 *   4. Interpolate trim value from selected table
 *   5. Check enable conditions (coolant temp, RPM threshold)
 *   6. If enabled: accumulate trim with integral gain
 *   7. If disabled: zero out trim
 *   8. Clip trim to [-2.8, +0.7] range
 *   9. Write trim to output registers
 * ======================================================================== */
void calc_adaptive_fuel_trim(void)
{
    float engine_rpm;
    float lambda_feedback;
    float target_reference;
    float deviation;
    float trim_value;
    float trimmed;

    /* ---- Phase 1: Read inputs ---- */
    engine_rpm      = RAM_ENGINE_RPM;          /* fr15 = [0xFFFFB5B8] */
    lambda_feedback = RAM_LAMBDA_FEEDBACK;     /* fr14 = [0xFFFFB5C4] */

    /*
     * Compute deviation.
     * The ROM computes:  deviation = RPM - some_reference
     * The reference could be target lambda converted to RPM domain,
     * or it could be a load/RPM reference from another RAM location.
     *
     * For now: use lambda feedback directly as the error signal.
     * The actual formula may be: error = actual_lambda - target_lambda
     * where target comes from a map lookup not yet reversed.
     */
    {
        float reference;  /* fr3 in the ROM — loaded from RAM but address unknown */

        /* Placeholder: use the current trim output as reference */
        reference = RAM_TRIM_OUTPUT;

        deviation = engine_rpm - reference;   /* fr2 = fr15 - fr3 */
        RAM_ERROR_SIGNAL = deviation;          /* store to 0xFFFFA728 */
    }

    /* ---- Phase 2: Table selection and interpolation ---- */
    {
        const void *table_desc;
        uint8_t table_select = RAM_TRIM_TABLE_SELECT;  /* 0xFFFFB5AC */

        if (table_select == 0) {
            table_desc = TABLE_TRIM_PRIMARY;    /* 0x6A868 */
        } else {
            uint8_t trim_enable = RAM_TRIM_ENABLE;  /* 0xFFFFB5A4 */
            if (trim_enable == 0) {
                table_desc = TABLE_TRIM_PRIMARY;
            } else {
                table_desc = TABLE_TRIM_SECONDARY;  /* 0x6A87C */
            }
        }

        /* 1D lookup with deviation as input */
        trim_value = table1D_lookup(table_desc, deviation);
        RAM_TRIM_OUTPUT = trim_value;           /* store to 0xFFFFA720 */
    }

    /* ---- Phase 3: Enable conditions ---- */
    {
        uint8_t ect_status = RAM_ECT_STATUS;    /* 0xFFFFC084 — coolant temp */

        if (ect_status == 1) {                  /* engine warm (closed loop) */
            /* Check RPM threshold */
            float rpm_threshold = CAL_RPM_THRESHOLD;  /* 1500.0 */

            if (engine_rpm > rpm_threshold) {
                /*
                 * Adaptation is active.
                 * Apply integral gain to accumulate trim over time.
                 * The ROM uses an integrator with gain 0.009766 (~1/1024).
                 *
                 * trimmed = previous_trim + integral_gain * (new_trim - previous_trim)
                 * This is a first-order low-pass filter / leaky integrator.
                 */
                float previous_trim = RAM_TRIM_OUTPUT;
                float gain = CAL_INTEGRAL_GAIN;  /* 0.009766 */

                trimmed = previous_trim + gain * (trim_value - previous_trim);
            } else {
                /* RPM below threshold — zero out trim */
                trimmed = 0.0f;
            }
        } else {
            /* Engine cold — zero out trim */
            trimmed = 0.0f;
        }
    }

    /* ---- Phase 4: Limiting and output ---- */
    {
        float neg_limit = CAL_TRIM_LIMIT_NEG;   /* -2.8 */
        float pos_limit = CAL_TRIM_LIMIT_POS;   /* 0.7 */

        /* Clamp trim to [-2.8, +0.7] */
        if (trimmed < neg_limit) {
            trimmed = neg_limit;
        } else if (trimmed > pos_limit) {
            trimmed = pos_limit;
        }

        /* Write outputs */
        RAM_TRIM_OUT_LEADING = trimmed;         /* 0xFFFFA718 */
        /* Also written to 0xFFFFAADA (trailing) via a secondary path */
    }
}

/* ========================================================================
 * NOTES:
 *
 * 1. The two 1D tables both have 9 breakpoints from -100% to +100% load
 *    deviation.  Table 1 has symmetric limiting (rich on negative dev,
 *    lean on positive dev).  Table 2 is asymmetric (only rich corrections).
 *
 * 2. The raw u8 values center on 128 (= stoich, no correction).  The
 *    actual trim value is: trim = (raw_interp) * scale + offset, where
 *    scale and offset come from bytes 12-19 of the 1D descriptor.
 *
 * 3. The values 1500 RPM threshold, 0.6 gain, 0.7 trim limit, and -2.8
 *    trim limit are from ROM at 0x72C60-0x72C70.  These define the
 *    adaptation operating envelope.
 *
 * 4. The enable logic checks coolant temperature (0xFFFFC084) and RPM
 *    to determine if closed-loop adaptation should run.  This prevents
 *    adaptation during cold start and idle.
 *
 * 5. The exact error computation (subtracting a reference from RPM or
 *    lambda) is not fully resolved — the RAM location of the reference
 *    value is still unknown.  The placeholder uses the previous trim
 *    output.  Update when the reference location is identified.
 * ======================================================================== */
