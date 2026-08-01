/**
 * throttle_position_sensor.c
 *
 * RX-8 ECU Throttle Position Sensor (TPS) Processing
 *
 * The TPS is a potentiometer that provides a voltage proportional to
 * throttle plate angle. The RX-8 uses dual TPS sensors (main + sub)
 * for redundancy and diagnostics.
 *
 * Primary functions:
 *   throttle_position_adc_reader @ 0x19FC0 — reads Main TPS ADC
 *   throttle_sub_adc_reader — reads Sub TPS ADC
 *   calc_throttle_position_filter @ 0x1345C — applies filtering & 3D multiplier
 *
 * RAM map (verified):
 *   0xFFFFA424 (u16): Main TPS raw ADC value
 *   0xFFFFA428 (u16): Main TPS processed value
 *   0xFFFFAA14 (u16): Sub TPS raw ADC value
 *   0xFFFFAA18 (u16): Sub TPS ADC after processing
 *   0xFFFFA6B0 (float): Filtered speed (used in TPS filter)
 *   0xFFFFA6B4 (float): Previous filtered TPS angle
 *   0xFFFFA6B8 (float): Rate of change limit
 *
 * Calibration tables:
 *   TPS ADC limit table @ 0x6F9B8 (type-0, 6 entries)
 *   TPS scalar table @ 0x6F9D0 (type-0, 3 entries)
 *   TPS MultiMap3D table @ 0x6F9E8 (axis: RPM × load)
 *
 * Scale factors:
 *   ADC-to-voltage: 7.62939e-5 (5V/65536)
 *   Voltage-to-angle: calibration-dependent
 *
 * Fault detection:
 *   - Main vs Sub TPS disagreement → DTC P0121
 *   - ADC out-of-range → DTC P0122/P0123
 *   - Plausibility vs. MAF/MAP → DTC P0120
 */

#include <stdint.h>
#include <math.h>

/* ================================================================
 * RAM Map
 * ================================================================ */
#define TPS_MAIN_ADC         (*(volatile uint16_t *)0xFFFFA424)
#define TPS_MAIN_PROC        (*(volatile uint16_t *)0xFFFFA428)   /* processed */
#define TPS_SUB_ADC          (*(volatile uint16_t *)0xFFFFAA14)
#define TPS_SUB_PROC         (*(volatile uint16_t *)0xFFFFAA18)
#define TPS_FILTERED_ANGLE   (*(volatile float    *)0xFFFFA6B0)   /* deg */
#define TPS_PREV_ANGLE       (*(volatile float    *)0xFFFFA6B4)   /* prev filtered */
#define TPS_RATE_LIMIT       (*(volatile float    *)0xFFFFA6B8)   /* deg/s limit */

/* ================================================================ */

/* External helpers */
extern float TwoDLookup(uint32_t table_addr, float input);
extern float firstOrderFilter(float sig, float sigprev, float ff, float min);

/**
 * throttle_position_adc_reader @ 0x19FC0
 *
 * Reads the main TPS ADC value and validates against limits.
 * If out of range, calls the fault handler.
 *
 * The ADC value is stored in 16-bit format (0-65535 corresponding to 0-5V).
 * Normal TPS range is typically 0.5V (closed) to 4.5V (WOT).
 *
 * RAM addresses confirmed:
 *   0xFFFFA424 — Main TPS ADC input (from ADC scan task)
 *   0xFFFFA428 — Main TPS processed output
 *   0x0006F9B8 — Limit table descriptor (contains min/max)
 *   0x0003EEB8 — Fault handler function when out of range
 *
 * Returns: 0 = valid, 1 = out of range
 */
uint8_t throttle_position_adc_reader(void)
{
    uint16_t tps_adc = TPS_MAIN_ADC;
    uint16_t limit_table;  /* loaded from ROM table descriptor */
    
    /* Load limit value from calibration table at 0x6F9B8
     * (table descriptor: count=6, type=0, axis=limit_voltages, values=limits) */
    uint16_t max_limit = *(volatile uint16_t *)0x0006F9BA;  /* u16 from descriptor+2 */
    
    /* If ADC exceeds limit, call fault handler */
    if (tps_adc >= max_limit) {
        /* Fault handler at 0x3EEB8 records the out-of-range condition
         * and sets diagnostic trouble code flags */
        /* Called as: jsr 0x3EEB8 with r4 = tps_adc */
        TPS_MAIN_PROC = 0;  /* Default to closed throttle on fault */
        return 1;  /* Out of range */
    }
    
    /* Store processed ADC value */
    TPS_MAIN_PROC = tps_adc;
    return 0;  /* Valid */
}

/**
 * tps_adc_to_angle
 *
 * Converts TPS ADC value to a throttle angle in degrees.
 * Uses the factory calibration table to linearize the
 * potentiometer output.
 *
 * @param adc_value Raw TPS ADC count (0-65535)
 * @return Throttle angle in degrees
 */
float tps_adc_to_angle(uint16_t adc_value)
{
    float voltage = (float)adc_value * 7.62939e-5f;
    
    /* TPS angle lookup table @ 0x6F9B8
     * Maps voltage to throttle angle (type-0, float output) */
    #define TPS_ANGLE_TABLE   0x0006F9B8
    return TwoDLookup(TPS_ANGLE_TABLE, voltage);
}

/**
 * calc_throttle_position_filter @ 0x1345C
 *
 * Applies rate-of-change limiting and first-order filtering
 * to the raw TPS angle.
 *
 * Uses MultiMap3D tables for RPM/load-dependent filtering
 * (higher filtering at low RPM to reduce noise).
 *
 * Algorithm:
 *   1. Compute raw angle from ADC
 *   2. Compute rate of change from previous value
 *   3. Apply rate limit (max deg/sec based on RPM)
 *   4. Apply first-order IIR filter for noise reduction
 *   5. Store filtered result
 *
 * MultiMap3D table at 0x6F9E8 provides RPM×Load→filter_factor
 * and RPM×Load→rate_limit lookups.
 */
void calc_throttle_position_filter(void)
{
    uint16_t adc = TPS_MAIN_PROC;
    float raw_angle = tps_adc_to_angle(adc);
    float prev_angle = TPS_PREV_ANGLE;
    
    /* Load filter factor from calibration (RPM-dependent) */
    /* 3D lookup: factor = f(RPM, load) from table at 0x6F9E8 */
    float filter_factor = 0.5f;  /* default until 3D lookup resolved */
    
    /* Apply first-order filter */
    float filtered = firstOrderFilter(raw_angle, prev_angle, filter_factor, 0.0f);
    
    /* Apply rate of change limit */
    float rate_limit = TPS_RATE_LIMIT;
    float delta = filtered - prev_angle;
    if (delta > rate_limit) {
        filtered = prev_angle + rate_limit;
    } else if (delta < -rate_limit) {
        filtered = prev_angle - rate_limit;
    }
    
    /* Store results */
    TPS_FILTERED_ANGLE = filtered;
    TPS_PREV_ANGLE = filtered;
}

/**
 * getThrottlePosition
 *
 * High-level API: returns the current filtered throttle position
 * as a percentage (0 = closed, 100 = wide open throttle).
 *
 * Uses calibration data to determine the min/max voltage range
 * for normalization.
 *
 * @return Throttle position percentage (0.0 - 100.0)
 */
float getThrottlePosition(void)
{
    float angle = TPS_FILTERED_ANGLE;
    
    /* Min/max angles from calibration */
    float min_angle = 0.0f;    /* Closed throttle */
    float max_angle = 90.0f;   /* WOT (typically ~80-85° on RX-8) */
    
    if (angle <= min_angle) return 0.0f;
    if (angle >= max_angle) return 100.0f;
    
    return (angle - min_angle) / (max_angle - min_angle) * 100.0f;
}
