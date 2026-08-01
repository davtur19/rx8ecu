/**
 * getBaroSensorVal @ 0xD144
 *
 * RX-8 ECU Barometric (Atmospheric) Pressure Sensor Processing
 *
 * The barometric pressure sensor (integrated into the ECU or MAF sensor)
 * measures absolute atmospheric pressure. It is read:
 *   - At key-on before engine start (for altitude compensation)
 *   - Periodically during steady-state operation (for adaptive updates)
 *
 * The baro reading is used for:
 *   - Air density compensation in fueling calculations
 *   - Boost control reference (on turbo models, NA Renesis uses it
 *     for altitude compensation of MAF-based fueling)
 *   - Atmospheric pressure for OBD-II monitor thresholds
 *
 * RAM map:
 *   0xFFFF9F18 (u16):   Barometric pressure sensor raw ADC
 *   0xFFFFA3DC (float): Normalized barometric pressure value
 *   0xFFFFC5D8 (float): Barometric pressure trim compensation
 *
 * Calibration:
 *   0x0007978C (float): Linearization gain
 *   0x00079790 (float): Linearization offset
 *   0x6D46C (u16):      Min threshold (0x0505 = 1285 counts)
 *   0x6D46E (u16):      Max threshold (0x0505 = 1285 counts)
 *
 * Barometric pressure trim: calc_barometric_pressure_trim @ 0x13F68
 *   - Applies correction based on baro reading
 *   - Trim floats at 0x72D4C-0x72D58: all = -0.02 (correction factor)
 *   - Used as multiplier in fuel/ignition calculations
 *
 * Scale factor: 7.62939e-5 = 5.0V / 65536 (16-bit ADC to voltage)
 *
 * Normal barometric pressure range:
 *   Sea level:   101.3 kPa  (14.7 psi)
 *   High altitude: ~60 kPa  (8.7 psi) at 4000m
 *   ADC range:    0-65535 (0-5V)
 */

#include <stdint.h>

/* ================================================================
 * RAM Map
 * ================================================================ */
#define BARO_ADC_RAW         (*(volatile uint16_t *)0xFFFF9F18)
#define BARO_NORMALIZED      (*(volatile float    *)0xFFFFA3DC)
#define BARO_TRIM_COMP       (*(volatile float    *)0xFFFFC5D8)

/* ================================================================
 * Calibration constants from ROM
 * ================================================================ */
static float get_baro_gain(void)
{
    return *(volatile float *)0x0007978C;
}

static float get_baro_offset(void)
{
    return *(volatile float *)0x00079790;
}

static uint16_t get_baro_min_threshold(void)
{
    return *(volatile uint16_t *)0x006D46C;   /* 0x0505 = 1285 */
}

static uint16_t get_baro_max_threshold(void)
{
    return *(volatile uint16_t *)0x006D46E;   /* 0x0505 = 1285 */
}

/* ================================================================ */

#define BARO_SCALE_FACTOR    7.62939e-5f

/**
 * fixedPointScaling
 *
 * Fixed-point scaling helper. Converts raw ADC to fixed-point
 * representation used by the baro linearization algorithm.
 *
 * @param adc_val Raw ADC count (0-65535)
 * @return Scaled fixed-point value
 */
static uint16_t fixedPointScaling(uint16_t adc_val)
{
    /* Implemented at ROM 0xD1BC:
     *   r0 = (adc_val * scale_factor) >> shift
     * Returns fixed-point intermediate for linearization */
    return adc_val;  /* placeholder: actual scaling TBD */
}

/**
 * fixedPointToFloat_16bit
 *
 * Converts fixed-point value to float with gain and offset.
 *
 * @param fixed_val Fixed-point value
 * @param mult      Multiplier (gain)
 * @param off       Offset
 * @return Floating-point result
 */
static float fixedPointToFloat_16bit(uint16_t fixed_val, float mult, float off)
{
    return off + mult * ((float)fixed_val * BARO_SCALE_FACTOR);
}

/**
 * getBaroSensorVal @ 0xD144
 *
 * Main barometric pressure sensor processing function.
 *
 * Pipeline:
 *   1. Read raw ADC from baro sensor (0xFFFF9F18)
 *   2. Apply fixed-point scaling (0xD1BC)
 *   3. Apply linearization: normalized = offset + gain * adc_voltage
 *   4. Store result at 0xFFFFA3DC
 *   5. Validate against min/max thresholds
 *   6. Return status code
 *
 * Thresholds at 0x6D46C/0x6D46E both = 0x0505 (1285).
 * This corresponds to ~0.098V ADC input:
 *   1285 * 5V / 65536 = 0.098V
 *
 * An ADC reading this low typically indicates:
 *   - Sensor disconnected (open circuit)
 *   - Sensor ground fault
 *
 * Returns: status code
 *   0 = Valid reading
 *   1 = Over-range high
 *   2 = Over-range low
 */
uint8_t getBaroSensorVal(void)
{
    uint16_t adc_raw = BARO_ADC_RAW;
    uint16_t min_thresh = get_baro_min_threshold();  /* 0x0505 = 1285 */
    uint16_t max_thresh = get_baro_max_threshold();  /* 0x0505 = 1285 */
    
    /* Fixed-point scaling */
    uint16_t scaled = fixedPointScaling(adc_raw);
    
    /* Convert to float with linearization */
    float gain = get_baro_gain();
    float offset = get_baro_offset();
    float normalized = fixedPointToFloat_16bit(scaled, gain, offset);
    
    BARO_NORMALIZED = normalized;
    
    /* Validate against range bounds */
    if (scaled > max_thresh) {
        return 1;  /* Over-range high */
    } else if (scaled >= min_thresh) {
        return 0;  /* Valid */
    } else {
        return 2;  /* Over-range low */
    }
}

/**
 * calc_barometric_pressure_trim @ 0x13F68
 *
 * Calculates barometric pressure trim compensation.
 *
 * Trim formula:
 *   trim = BARO_TRIM_FACTOR * (reference_pressure - measured_pressure)
 *
 * Where BARO_TRIM_FACTOR = -0.02 (from ROM literal pool at 0x72D4C-0x72D58)
 *
 * The trim is applied as a multiplier to:
 *   - Fuel injection base pulse width
 *   - Ignition timing advance
 *   - Idle air bypass
 *
 * Negative trim factor means the ECU reduces fuel/advance
 * when atmospheric pressure drops (high altitude).
 *
 * Returns: Barometric pressure trim value
 */
float calc_barometric_pressure_trim(void)
{
    #define BARO_TRIM_FACTOR  -0.02f   /* from 0x72D4C */
    #define BARO_REF_PRESSURE 101.325f /* sea level kPa */
    
    float baro_pressure = BARO_NORMALIZED;
    float trim = BARO_TRIM_FACTOR * (BARO_REF_PRESSURE - baro_pressure);
    
    BARO_TRIM_COMP = trim;
    return trim;
}

/**
 * getAtmosphericPressure
 *
 * Returns the current atmospheric pressure in kPa.
 * Normalized from the baro sensor ADC reading.
 *
 * @return Atmospheric pressure in kPa
 */
float getAtmosphericPressure(void)
{
    return BARO_NORMALIZED;
}

/**
 * getAltitudeCompensation
 *
 * Returns the altitude compensation factor based on barometric
 * pressure. Used to adjust fueling for altitude changes.
 *
 * @return Compensation factor (1.0 at sea level, < 1.0 at altitude)
 */
float getAltitudeCompensation(void)
{
    float baro_kpa = BARO_NORMALIZED;
    float sea_level_kpa = 101.325f;
    
    /* Simple density compensation based on ideal gas law */
    return baro_kpa / sea_level_kpa;
}
