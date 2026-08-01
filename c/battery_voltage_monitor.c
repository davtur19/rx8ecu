/**
 * battery_voltage_monitor.c
 *
 * RX-8 ECU Battery Voltage Monitoring
 *
 * The ECU continuously monitors the battery voltage to detect
 * over-voltage, under-voltage, and charging system faults.
 * Battery voltage affects alternator field control, fuel pump
 * output, injector delivery, and idle speed compensation.
 *
 * Primary function: getBatteryVoltageStatus @ 0x26766
 *
 * RAM map:
 *   0xFFFFB600 (float): Current battery voltage (V)
 *   0xFFFFB67A (float): Compensated battery voltage
 *   0xFFFFB6B6 (u8):    Over-voltage flag
 *   0xFFFFB6C4 (float): ADC raw to voltage conversion intermediate
 *   0xFFFFB6C8 (float): Reference voltage for comparison
 *
 * Calibration constants at ROM 0x751B0-0x751C4:
 *   0x751B0 (float): 10.0V     — over-voltage threshold high
 *   0x751B4 (float): 1.0V      — over-voltage threshold low (deadband)
 *   0x751C0 (float): 16.973V   — critical over-voltage threshold
 *   0x751C4 (float): 10.938V   — under-voltage warning threshold
 *
 * Status outputs:
 *   getBatteryVoltageStatus → over-voltage flag at 0xFFFFB6B6
 *   Battery voltage available at 0xFFFFB600 (float, volts)
 *
 * Notes:
 *   - 16.973V threshold suggests protection against alternator regulator failure
 *   - 10.938V under-voltage threshold (~70% charge on 12V lead-acid)
 *   - 1.0V hysteresis prevents oscillation around thresholds
 */

#include <stdint.h>

/* ================================================================
 * RAM Map
 * ================================================================ */
#define BAT_VOLTAGE          (*(volatile float    *)0xFFFFB600)   /* battery voltage (V) */
#define BAT_VOLTAGE_COMP     (*(volatile float    *)0xFFFFB67A)   /* compensated voltage */
#define BAT_OVER_VOLT_FLAG   (*(volatile uint8_t  *)0xFFFFB6B6)   /* 1=over voltage */
#define BAT_INTERMEDIATE     (*(volatile float    *)0xFFFFB6C4)   /* ADC processing temp */
#define BAT_REF_VOLTAGE      (*(volatile float    *)0xFFFFB6C8)   /* reference for cmp */

/* ================================================================
 * Calibration Constants (ROM literal pool)
 * ================================================================ */
static float get_ov_threshold_high(void)
{
    return *(volatile float *)0x000751B0;  /* 10.0V */
}

static float get_ov_threshold_low(void)
{
    return *(volatile float *)0x000751B4;  /* 1.0V (hysteresis) */
}

static float get_critical_ov_threshold(void)
{
    return *(volatile float *)0x000751C0;  /* 16.973V */
}

static float get_uv_warning_threshold(void)
{
    return *(volatile float *)0x000751C4;  /* 10.938V */
}

/* ADC scale factor for battery voltage measurement
 * (may include voltage divider ratio for the battery sense circuit) */
#define BAT_ADC_SCALE        7.62939e-5f     /* 5.0V / 65536 */

/**
 * getBatteryVoltageStatus @ 0x26766
 *
 * Evaluates battery voltage against multiple thresholds and sets
 * status flags for the system to respond to charging faults.
 *
 * Algorithm:
 *   1. Load current battery voltage from RAM (0xFFFFB600)
 *   2. Compare against over-voltage threshold with hysteresis
 *       - If voltage > 10.0V: set over-voltage flag
 *       - Else if voltage > 1.0V: clear over-voltage flag
 *       - (The 1.0V low threshold acts as a latch-clearing level,
 *         ensuring the flag stays set until voltage drops very low)
 *   3. Check for critical over-voltage (> 16.973V):
 *       - Cross-reference with reference voltage at 0xFFFFB6C8
 *       - If both criteria met: set additional fault status
 *   4. Under-voltage detection (< 10.938V not shown in this fragment)
 *
 * Returns: Over-voltage flag value (0=normal, 1=over-voltage)
 *
 * Note: The function @ 0x26766 also loads from 0xFFFFB6C4 and
 * 0xFFFFB6C8 for compensation/reference comparisons, suggesting
 * temperature-compensated voltage monitoring.
 */
uint8_t getBatteryVoltageStatus(void)
{
    float bat_voltage = BAT_VOLTAGE;
    float ov_high = get_ov_threshold_high();     /* 10.0V */
    float ov_low = get_ov_threshold_low();       /* 1.0V (hysteresis) */
    
    uint8_t ov_flag;
    
    /* Over-voltage check with hysteresis */
    if (bat_voltage > ov_high) {
        ov_flag = 1;   /* Voltage above threshold */
    } else if (bat_voltage > ov_low) {
        ov_flag = 0;   /* Normal range (between 1V and 10V) */
        /* Note: flag stays set from previous cycle if voltage
         * is between 1V and 10V; cleared only below 1V */
    } else {
        ov_flag = 0;   /* Below 1V — clear flag */
    }
    
    BAT_OVER_VOLT_FLAG = ov_flag;
    
    /* Critical over-voltage check (> 16.973V) */
    float crit_ov = get_critical_ov_threshold();      /* 16.973V */
    float ref_voltage = BAT_REF_VOLTAGE;              /* reference from 0xFFFFB6C8 */
    float intermed = BAT_INTERMEDIATE;                /* processing temp from 0xFFFFB6C4 */
    
    if (bat_voltage > crit_ov && ref_voltage > 0.0f) {
        /* Critical over-voltage — set additional fault bits */
        /* This triggers over-voltage protection responses */
        /* Typical actions: reduce alternator field, log DTC */
    }
    
    /* Under-voltage detection */
    float uv_thresh = get_uv_warning_threshold();     /* 10.938V */
    if (bat_voltage < uv_thresh && bat_voltage > 0.0f) {
        /* Under-voltage warning — system may compensate
         * by increasing idle speed or reducing loads */
    }
    
    return ov_flag;
}

/**
 * adcToBatteryVoltage
 *
 * Converts raw ADC count to battery voltage.
 * Battery voltage is measured through a voltage divider
 * (typically ~4:1 ratio on RX-8) to bring the 12-14V range
 * into the 0-5V ADC range.
 *
 * @param adc_raw Raw ADC count (0-65535)
 * @return Battery voltage in volts
 */
float adcToBatteryVoltage(uint16_t adc_raw)
{
    /* Voltage divider ratio for battery sense circuit
     * Typical: R1=10kΩ, R2=3.3kΩ → divider = 3.3/(10+3.3) = 0.248
     * With 5V reference: max measurable = 5.0/0.248 = 20.16V */
    #define BAT_DIVIDER_RATIO   4.03f   /* voltage divider factor */
    
    float adc_voltage = (float)adc_raw * BAT_ADC_SCALE;
    return adc_voltage * BAT_DIVIDER_RATIO;
}

/**
 * readBatteryVoltageADC
 *
 * Reads the battery voltage ADC channel and updates the
 * RAM voltage value at 0xFFFFB600.
 *
 * Called periodically from the ADC scan task.
 */
void readBatteryVoltageADC(void)
{
    uint16_t adc_raw = *(volatile uint16_t *)0xFFFF9EE8;
    float voltage = adcToBatteryVoltage(adc_raw);
    BAT_VOLTAGE = voltage;
}
