/**
 * iat_sensor.c
 *
 * RX-8 ECU Intake Air Temperature (IAT) Sensor Processing
 *
 * The IAT sensor is a thermistor whose resistance varies with temperature.
 * The ECU reads ADC voltage, converts to temperature via a calibration table.
 *
 * Primary function: iat_sensor_3C214 @ 0x3C214
 *   - Reads raw ADC from RAM
 *   - Compares against a threshold value at 0x7A9A8 (stored as first byte)
 *   - Sets status flags at 0xFFFFC5EC-0xFFFFC5F6 based on out-of-range checks
 *
 * RAM map:
 *   0xFFFFC5EC (u8): IAT sensor threshold compare flag
 *   0xFFFFC5F4 (u8): IAT over-temperature flag (hot)
 *   0xFFFFC5F5 (u8): IAT sensor fault flag (out of range high)
 *   0xFFFFC5F6 (u8): IAT sensor fault flag (out of range low)
 *   0xFFFFC5ED (u8): IAT sensor secondary threshold compare
 *   0xFFFFC5EE (u8): IAT sensor tertiary threshold compare
 *   0xFFFFC5F8 (u8): IAT status register (bitfield)
 *
 * Calibration: IAT table descriptor @ 0x7A9A8
 *   - First byte: threshold/cutoff value for comparison
 *   - Subsequent bytes: calibration parameters
 *
 * ADC-to-voltage scale: 7.62939e-5 (5V/65536)
 *
 * Typical IAT sensor characteristic (NTC):
 *   - ~2.5kΩ at 25°C → ~2.5V at ADC (with pull-up)
 *   - ~300Ω at 100°C → ~0.5V at ADC
 *   - ~10kΩ at -20°C → ~4.0V at ADC
 */

#include <stdint.h>

/* ================================================================
 * RAM Map
 * ================================================================ */
#define IAT_STATUS_FLAGS     (*(volatile uint8_t *)0xFFFFC5EC)   /* bitfield */
#define IAT_OVER_TEMP_FLAG   (*(volatile uint8_t *)0xFFFFC5F4)   /* 1=over temp */
#define IAT_RANGE_HIGH_FLAG  (*(volatile uint8_t *)0xFFFFC5F5)   /* 1=above max */
#define IAT_RANGE_LOW_FLAG   (*(volatile uint8_t *)0xFFFFC5F6)   /* 1=below min */
#define IAT_STATUS_BYTE      (*(volatile uint8_t *)0xFFFFC5F8)   /* combined status */

/* IAT processed temperature value */
#define IAT_TEMPERATURE      (*(volatile float    *)0xFFFFC5F0)   /* deg C */

/* Calibration table address in ROM */
#define IAT_CAL_TABLE_ADDR   0x0007A9A8

/* External 2D lookup function */
extern float TwoDLookup(uint32_t table_addr, float input);

/* IAT threshold comparison constant (first byte at 0x7A9A8) */
static uint8_t get_iat_threshold(void)
{
    return *(volatile uint8_t *)IAT_CAL_TABLE_ADDR;
}

/**
 * iat_sensor_3C214 @ 0x3C214
 *
 * Main IAT sensor processing function. Reads the IAT ADC value,
 * compares against calibration thresholds, and sets status flags.
 *
 * The calibration table at 0x7A9A8 provides:
 *   - Byte 0: Comparison threshold (used to detect open/short circuits)
 *   - Additional data for temperature lookup
 *
 * Flow:
 *   1. Load threshold value from calibration table byte 0
 *   2. Read IAT ADC value from sensor input
 *   3. Compare and set over-temp flag (0xFFFFC5F4)
 *   4. Compare and set range-high flag (0xFFFFC5F5)
 *   5. Compare and set range-low flag (0xFFFFC5F6)
 *   6. Update status byte (0xFFFFC5F8)
 *
 * Returns: status code
 */
uint8_t iat_sensor_3C214(void)
{
    uint8_t threshold = get_iat_threshold();  /* from cal table byte 0 */
    uint16_t iat_adc;  /* from sensor ADC input */
    uint8_t over_temp = 0;
    uint8_t range_high = 0;
    uint8_t range_low = 0;
    
    /* Read IAT ADC from RAM */
    iat_adc = *(volatile uint16_t *)0xFFFF9EE6;
    
    /* Convert ADC to temperature via lookup table */
    float voltage = (float)iat_adc * 7.62939e-5f;
    float temp = TwoDLookup(IAT_CAL_TABLE_ADDR, voltage);
    IAT_TEMPERATURE = temp;
    
    /* Out-of-range checks using threshold */
    /* Compare ADC value against calibration threshold */
    if (iat_adc > (uint16_t)threshold * 256) {
        over_temp = 1;
    }
    
    if (iat_adc > *(volatile uint16_t *)0x0006D462) {
        range_high = 1;  /* ADC above max limit */
    }
    
    if (iat_adc < *(volatile uint16_t *)0x0006D464) {
        range_low = 1;   /* ADC below min limit */
    }
    
    /* Set status flags */
    IAT_OVER_TEMP_FLAG = over_temp;
    IAT_RANGE_HIGH_FLAG = range_high;
    IAT_RANGE_LOW_FLAG = range_low;
    
    /* Combined status byte */
    IAT_STATUS_BYTE = (over_temp << 2) | (range_high << 1) | range_low;
    
    /* Store intermediate comparison results */
    IAT_STATUS_FLAGS = (iat_adc > threshold) ? 1 : 0;
    
    return IAT_STATUS_BYTE;
}

/**
 * Convert IAT voltage to temperature using the calibration lookup.
 *
 * Uses the standard TwoDLookup mechanism which:
 *   1. Reads the 20-byte table descriptor
 *   2. Performs binary search on axis breakpoints
 *   3. Linearly interpolates output values
 *
 * @param voltage  IAT sensor voltage (0-5V)
 * @return temperature in degrees C
 */
float iatVoltageToTemperature(float voltage)
{
    return TwoDLookup(IAT_CAL_TABLE_ADDR, voltage);
}
