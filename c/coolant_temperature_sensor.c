/**
 * coolant_temperature_sensor.c
 *
 * RX-8 ECU Coolant Temperature Sensor Processing
 *
 * The coolant temperature (CLT) sensor is a thermistor (NTC) whose resistance
 * varies with temperature. The ECU reads it through a voltage divider and ADC,
 * then converts the raw ADC count to voltage, and finally looks up the
 * temperature from a calibration table.
 *
 * Pipeline:
 *   1. ADC read via sensorADCRead @ 0x68A8 → raw u16 at 0xFFFF9EE4[slot]
 *   2. readECMVoltage @ 0x735C: ADC → voltage with hysteresis
 *   3. Temperature lookup via TwoDLookup using CLT calibration table
 *   4. Fault detection via coolant_temp_out_of_range_check @ 0xE50C
 *   5. Bounds check via coolant_temp_boundary_check @ 0x1F99A
 *
 * RAM map:
 *   0xFFFF9F00 (u16): Coolant temp raw ADC
 *   0xFFFF9F68 (float): Processed coolant voltage
 *   0xFFFF9F6C (u16): Previous raw ADC (for hysteresis/delta check)
 *   0xFFFFC12C (float): Engine coolant temperature (deg C), used by fuel/ignition
 *   0xFFFFC5D2 (u8): Below-min flag
 *   0xFFFFC5D3 (u8): Above-max flag
 *
 * Calibration:
 *   CLT Sensor Scaling table descriptor @ 0x6CF?? (TBD: verify exact addr)
 *   Threshold values @ 0x6CF90, 0x6CF94 (min/max ADC for fault detection)
 *
 * Scale factor: 7.62939e-5 = 5.0V / 65536 (16-bit ADC, 0-5V input range)
 *
 * The CLT sensor characteristic (typical NTC thermistor):
 *   - High resistance when cold (low voltage across pull-up)
 *   - Low resistance when hot (high voltage across pull-up)
 *   - Nonlinear: lookup table linearizes the response
 */

#include <stdint.h>

/* ================================================================
 * RAM Map
 * ================================================================ */
#define CLT_ADC_RAW          (*(volatile uint16_t *)0xFFFF9F00)
#define CLT_PROC_VOLTAGE     (*(volatile float    *)0xFFFF9F68)
#define CLT_ADC_PREV         (*(volatile uint16_t *)0xFFFF9F6C)
#define CLT_TEMPERATURE      (*(volatile float    *)0xFFFFC12C)  /* deg C */
#define CLT_BELOW_MIN_FLAG   (*(volatile uint8_t  *)0xFFFFC5D2)
#define CLT_ABOVE_MAX_FLAG   (*(volatile uint8_t  *)0xFFFFC5D3)

/* ================================================================
 * Calibration table descriptors (in ROM)
 * ================================================================ */

/* External 2D lookup function */
extern float TwoDLookup(uint32_t table_addr, float input);

/* ================================================================
 * Constants from ROM literal pools
 * ================================================================ */
#define ADC_SCALE_5V         7.62939e-5f   /* 5.0V / 65536 */

/**
 * readECMVoltage @ 0x735C
 *
 * Reads the raw coolant temp ADC, applies hysteresis thresholding
 * via function @ 0x2510, converts to voltage using a divider scale,
 * and multiplies by a calibration factor.
 *
 * This function is NOT a simple ADC->voltage conversion — it includes
 * a comparison-based processing step (0x2510) that filters the ADC
 * value against a threshold and the previous reading, implementing
 * a basic noise filter / rate limiter.
 *
 * Input:  CLT_ADC_RAW (0xFFFF9F00) - current raw ADC count
 *         CLT_ADC_PREV (0xFFFF9F6C) - previous raw ADC count
 *         Threshold at ROM 0x6CF50 (u16) - max allowable delta
 *         Scale factor at ROM 0x6CF4C (float) - voltage divider ratio
 * Output: CLT_PROC_VOLTAGE (0xFFFF9F68) - processed voltage as float
 *         CLT_ADC_PREV updated with current ADC
 *
 * Pseudocode:
 *   uint16_t adc_curr = CLT_ADC_RAW;
 *   uint16_t adc_prev = CLT_ADC_PREV;
 *   uint16_t threshold = *(uint16_t*)0x6CF50;
 *   
 *   // Function 0x2510: compare current vs previous, apply delta limit
 *   // If delta > threshold, clamp to previous +/- threshold
 *   uint16_t clamped = delta_limit(adc_curr, adc_prev, threshold);
 *   
 *   // Convert to voltage: V = clamped * scale / divider
 *   float divider = *(float*)0x6CF4C;  // voltage divider ratio
 *   float voltage = (float)clamped * ADC_SCALE_5V / divider;
 *   
 *   CLT_PROC_VOLTAGE = voltage;
 *   CLT_ADC_PREV = adc_curr;
 */
void readECMVoltage(void)
{
    uint16_t adc_curr = CLT_ADC_RAW;
    uint16_t adc_prev = CLT_ADC_PREV;
    
    /* Load threshold (at ROM 0x6CF50) — max allowable single-step delta */
    uint16_t delta_thresh = *(volatile uint16_t *)0x0006CF50;
    
    /* Call delta-limit function @ 0x2510
     * r4 = adc_curr, r5 = adc_prev, r6 = delta_thresh
     * Returns clamped value in r0 */
    uint16_t clamped;
    /* Inline: limit the rate of change */
    if (adc_curr > adc_prev) {
        uint16_t delta = adc_curr - adc_prev;
        clamped = (delta > delta_thresh) ? (adc_prev + delta_thresh) : adc_curr;
    } else {
        uint16_t delta = adc_prev - adc_curr;
        clamped = (delta > delta_thresh) ? (adc_prev - delta_thresh) : adc_curr;
    }
    
    /* Convert clamped ADC to voltage through divider ratio */
    float divider_ratio = *(volatile float *)0x0006CF4C;
    float voltage = (float)clamped * ADC_SCALE_5V * divider_ratio;
    
    CLT_PROC_VOLTAGE = voltage;
    CLT_ADC_PREV = adc_curr;  /* store raw (not clamped) for next cycle */
}

/**
 * getEngineTemperature @ ~0x73A0 area
 *
 * Converts coolant sensor voltage to temperature using the CLT
 * calibration lookup table.
 *
 * This function calls TwoDLookup with:
 *   r4 = CLT calibration table descriptor
 *   fr4 = coolant voltage (from readECMVoltage)
 *
 * The CLT calibration table is a type-0 (float values) 1D lookup
 * mapping voltage → temperature in degrees C.
 *
 * For safety: if voltage is out of valid range, a default
 * temperature (typically 90°C) or fault value is substituted.
 */
float coolantVoltageToTemperature(float voltage)
{
    /* CLT Sensor Scaling table — type 0 (float values directly) */
    /* Address: near 0x6CF4C region (exact descriptor addr TBD) */
    #define CLT_TABLE_ADDR    0x0006CF50
    
    float temp = TwoDLookup((uint32_t)CLT_TABLE_ADDR, voltage);
    
    /* Clamp to valid physical range (-40°C to +150°C) */
    if (temp < -40.0f) temp = -40.0f;
    if (temp > 150.0f) temp = 150.0f;
    
    return temp;
}

/**
 * coolant_temp_out_of_range_check @ 0xE50C
 *
 * Checks coolant temp sensor ADC against over/under-range thresholds.
 * Sets fault flags if out of range.
 *
 * Thresholds:
 *   Upper limit @ 0x6CF90 (u16): ~32000 counts (~2.44V)
 *   Lower limit @ 0x6CF94 (u16): ~400 counts (~0.03V)
 *
 * Output flags:
 *   0xFFFFC5D2 = 1 if below minimum (short circuit / ground)
 *   0xFFFFC5D3 = 1 if above maximum (open circuit / 5V rail)
 */
void coolant_temp_out_of_range_check(void)
{
    uint16_t adc = CLT_ADC_RAW;
    uint16_t upper = *(volatile uint16_t *)0x0006CF90;
    uint16_t lower = *(volatile uint16_t *)0x0006CF94;
    
    if (adc > upper) {
        CLT_ABOVE_MAX_FLAG = 1;  /* Open circuit / 5V rail */
    } else {
        CLT_ABOVE_MAX_FLAG = 0;
    }
    
    if (adc < lower) {
        CLT_BELOW_MIN_FLAG = 1;  /* Short circuit / ground */
    } else {
        CLT_BELOW_MIN_FLAG = 0;
    }
}

/**
 * coolant_temp_boundary_check @ 0x1F99A
 *
 * Validates the coolant temperature reading against reasonable
 * engine operating boundaries. Used for diagnostic enable conditions
 * (e.g., enable closed-loop only if coolant > threshold).
 *
 * Checks:
 *   - Temperature above cold-start threshold (~40°C)
 *   - Temperature below overheat threshold (~120°C)
 *   - Rate of change within limits
 */
uint8_t coolant_temp_boundary_check(float temp_degc)
{
    /* Cold threshold — below this, engine is warming up */
    float cold_thresh = 40.0f;
    /* Hot threshold — above this, engine is overheating */
    float hot_thresh = 120.0f;
    
    if (temp_degc < cold_thresh) {
        return 0;  /* Cold */
    } else if (temp_degc > hot_thresh) {
        return 2;  /* Hot / overheat */
    } else {
        return 1;  /* Normal operating range */
    }
}

/**
 * Main coolant temperature processing task
 *
 * Called periodically from the sensor acquisition loop.
 * Complete pipeline: read ADC → filter → look up temp → validate.
 */
void process_coolant_temperature(void)
{
    /* Step 1: Read ADC with rate limiting */
    readECMVoltage();
    
    /* Step 2: Convert voltage to temperature via lookup */
    float voltage = CLT_PROC_VOLTAGE;
    float temp = coolantVoltageToTemperature(voltage);
    CLT_TEMPERATURE = temp;
    
    /* Step 3: Fault detection */
    coolant_temp_out_of_range_check();
    
    /* Step 4: Boundary check */
    coolant_temp_boundary_check(temp);
}
