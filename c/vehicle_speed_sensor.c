/**
 * vehicle_speed_sensor.c
 *
 * RX-8 ECU Vehicle Speed Sensor (VSS) Processing
 *
 * The VSS signal comes from the transmission output shaft speed sensor.
 * It produces a square wave whose frequency is proportional to vehicle speed.
 * The ECU measures pulse period and converts to km/h.
 *
 * Primary function: calc_vehicle_speed_filter @ 0x133F8
 *
 * Processing pipeline:
 *   1. Raw pulse period measured by MTU (pulse timer unit)
 *   2. Convert period to raw speed (km/h)
 *   3. Apply first-order IIR filter with rate limiting
 *   4. Store filtered speed for use by fuel/ignition/cruise control
 *
 * RAM map (verified from disassembly):
 *   0xFFFFA6AC (float): Current raw speed (km/h)
 *   0xFFFFA6B0 (float): Previous filtered speed (km/h) — used by TPS filter too
 *   0xFFFFA6BC (float): Filter coefficient (time constant)
 *   0xFFFFA6C0 (float): Rate limit (max acceleration/deceleration)
 *   0xFFFFA6CC (float): Filter state / temp storage
 *   0xFFFFA6D0 (float): Filter state / temp storage
 *   0xFFFFA6D4 (float): Filter minimum change deadband
 *   0xFFFFA6D8 (float): Previous filter output
 *   0xFFFFA6B9 (u8): Speed sensor status / fault flags
 *
 * Calibration constants:
 *   Filter coefficient @ 0x6D470 (float): First-order filter factor (0-1)
 *   Rate limit @ 0x6D474 (float): Max speed change per cycle (km/h)
 *   Min change @ 0x6D478 (float): Deadband below which output is held
 *
 * Filter function @ 0x23DC:
 *   - Performs abs(diff), min/max operations
 *   - Used for rate limiting and deadband processing
 */

#include <stdint.h>
#include <math.h>

/* ================================================================
 * RAM Map
 * ================================================================ */
#define VSS_RAW_SPEED        (*(volatile float    *)0xFFFFA6AC)
#define VSS_FILTERED_SPEED   (*(volatile float    *)0xFFFFA6B0)   /* output */
#define VSS_FILTER_COEFF     (*(volatile float    *)0xFFFFA6BC)
#define VSS_RATE_LIMIT       (*(volatile float    *)0xFFFFA6C0)
#define VSS_FILTER_STATE1    (*(volatile float    *)0xFFFFA6CC)
#define VSS_FILTER_STATE2    (*(volatile float    *)0xFFFFA6D0)
#define VSS_MIN_DEADBAND     (*(volatile float    *)0xFFFFA6D4)
#define VSS_PREV_OUTPUT      (*(volatile float    *)0xFFFFA6D8)
#define VSS_STATUS           (*(volatile uint8_t  *)0xFFFFA6B9)

/* External helpers */
extern float firstOrderFilter(float sig, float sigprev, float ff, float min);

/**
 * speed_filter_minmax @ 0x23DC
 *
 * Building-block function used by the speed filter.
 * Performs min/max/abs operations that support the rate-limiting
 * and deadband logic.
 *
 * Called with:
 *   fr4 = value A
 *   fr5 = value B
 *   Returns min(A, B) or max(A, B) or abs(A-B) depending on entry point
 *
 * Entry points:
 *   0x23DC: fr0 = |fr4 - fr5| (abs difference)
 *   0x23E4: fr0 = max(|fr4-fr5|, fr5)  (max of diff and threshold)
 *   0x23F4: fr0 = max(fr4, fr5) / min(fr4, fr5)
 */
float speed_abs_diff(float a, float b)
{
    return fabsf(a - b);
}

float speed_max_diff_or_thresh(float a, float b)
{
    float diff = fabsf(a - b);
    return (diff > b) ? diff : b;   /* max(|a-b|, b) */
}

float speed_min_or_max(float a, float b)
{
    return (a > b) ? a : b;   /* max(a, b) */
}

/**
 * calc_vehicle_speed_filter @ 0x133F8
 *
 * Main vehicle speed filtering function.
 *
 * Algorithm:
 *   1. Read raw speed from pulse measurement (0xFFFFA6AC)
 *   2. Load previous filtered speed (0xFFFFA6B0)
 *   3. Compute rate of change: delta = raw - previous
 *   4. Apply rate limit: clamp delta to ±VSS_RATE_LIMIT
 *   5. Apply first-order IIR filter using VSS_FILTER_COEFF
 *   6. Apply deadband: if |change| < VSS_MIN_DEADBAND, hold previous value
 *   7. Store filtered result and update state
 *
 * This runs at ~100Hz (every 10ms) in the main control loop.
 * The filter provides smooth speed readings for:
 *   - Fuel injection calculations
 *   - Ignition timing adjustments
 *   - Cruise control operation
 *   - OBD-II speed reporting
 */
void calc_vehicle_speed_filter(void)
{
    float raw = VSS_RAW_SPEED;
    float prev = VSS_FILTERED_SPEED;
    float ff = VSS_FILTER_COEFF;       /* first-order filter factor */
    float rate_limit = VSS_RATE_LIMIT;
    float min_change = VSS_MIN_DEADBAND;
    
    /* Compute raw delta from previous output */
    float delta = raw - prev;
    
    /* Apply rate limiting (max acceleration/deceleration) */
    if (delta > rate_limit) {
        delta = rate_limit;
    } else if (delta < -rate_limit) {
        delta = -rate_limit;
    }
    
    /* Apply rate-limited raw value */
    float rate_limited_raw = prev + delta;
    
    /* Apply first-order IIR filter */
    float filtered = firstOrderFilter(rate_limited_raw, prev, ff, min_change);
    
    /* Deadband: if change is below threshold, hold previous */
    if (fabsf(filtered - prev) < min_change) {
        filtered = prev;
    }
    
    /* Store filtered result */
    VSS_FILTERED_SPEED = filtered;
    VSS_PREV_OUTPUT = prev;  /* save for next cycle */
    
    /* Update status (zero-speed detection) */
    if (filtered < 0.5f) {
        VSS_STATUS = 0;  /* Vehicle stopped */
    } else {
        VSS_STATUS = 1;  /* Vehicle moving */
    }
}

/**
 * getVehicleSpeed
 *
 * Returns the current filtered vehicle speed in km/h.
 * Used by cruise control, fuel cut, and OBD-II functions.
 *
 * @return Vehicle speed in km/h
 */
float getVehicleSpeed(void)
{
    return VSS_FILTERED_SPEED;
}

/**
 * getVehicleSpeedMPH
 *
 * Convenience function returning speed in MPH.
 *
 * @return Vehicle speed in MPH
 */
float getVehicleSpeedMPH(void)
{
    return VSS_FILTERED_SPEED * 0.621371f;
}
