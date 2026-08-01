/**
 * getKnockSensorADC @ 0xC3CE
 * 
 * Purpose: Read knock sensor ADC, copy to output buffer, apply first-order
 * low-pass filter, convert back to uint16, and validate against RPM thresholds.
 * 
 * RAM map (knock sensor state):
 *   0xFFFF9F0E (u16):   Knock sensor raw ADC (input, from ADC buffer)
 *   0xFFFFA37E (u16):   Copy 1 of raw ADC
 *   0xFFFFA37C (u16):   Copy 2 of raw ADC
 *   0xFFFFA328 (float): Reference value (RPM or threshold)
 *   0xFFFFA360 (float): Filter gain (typically 10.0)
 *   0xFFFFA364 (float): Secondary filter parameter
 *   0xFFFFA384 (u8):    Output limit byte (0xFF = unlimited)
 *   0xFFFFA385 (u8):    Counter
 *   0xFFFFA386 (u8):    Fault byte
 *   0xFFFFA324 (u8):    Fault byte 2
 *   0xFFFFA32C (float): Filter state
 *   0xFFFFA348 (float): Per-rotor filter state (rotor A)
 *   0xFFFFA350 (float): Per-rotor threshold (rotor B)
 *   0xFFFFA334 (float): Per-rotor threshold (rotor A)
 *   0xFFFFA368 (float): Per-rotor filter state (rotor B)
 *   0xFFFFA389 (u8):    Sensor ID (per-rotor selector)
 * 
 * Calibration constants:
 *   0x0007A178 (u16):   0x005E = 94  (sensor cal constant 1)
 *   0x0007A17A (u16):   0x00C1 = 193 (sensor cal constant 2)
 *   0x0007A1A4 (float): 3.6875       (sensor calibration parameter)
 *   0x0007A1D0 (float): 64.0         (sensor threshold)
 *   0x41200000 (float): 10.0         (filter gain, encoded)
 */

#include <stdint.h>

/* RAM addresses */
#define KNOCK_ADC_RAW        (volatile uint16_t*)0xFFFF9F0E
#define KNOCK_ADC_COPY1      (volatile uint16_t*)0xFFFFA37E
#define KNOCK_ADC_COPY2      (volatile uint16_t*)0xFFFFA37C
#define KNOCK_REF_FLOAT      (volatile float*)   0xFFFFA328
#define KNOCK_FILTER_GAIN    (volatile float*)   0xFFFFA360
#define KNOCK_FILTER_STATE   (volatile float*)   0xFFFFA32C
#define KNOCK_FILTER_PARAM2  (volatile float*)   0xFFFFA364
#define KNOCK_MAX_BYTE       (volatile uint8_t*) 0xFFFFA384
#define KNOCK_FAULT_BYTE     (volatile uint8_t*) 0xFFFFA386
#define KNOCK_FAULT_BYTE2    (volatile uint8_t*) 0xFFFFA324
#define KNOCK_COUNTER        (volatile uint8_t*) 0xFFFFA385

/* External filter function: firstOrderFilter(sig, prev, gain, min_ff) */
extern float firstOrderFilter(float new_sample, float prev_out, float gain, float min_ff);

void getKnockSensorADC(void)
{
    uint16_t adc_raw = *KNOCK_ADC_RAW;
    float ref_val = *KNOCK_REF_FLOAT;

    /* Copy raw ADC to output buffers */
    *KNOCK_ADC_COPY1 = adc_raw;
    *KNOCK_ADC_COPY2 = adc_raw;

    /* Apply first-order low-pass filter */
    float adc_float = (float)adc_raw;
    float prev_state = *KNOCK_FILTER_STATE;
    float gain = *KNOCK_FILTER_GAIN;  /* typically 10.0 */

    float filtered = firstOrderFilter(adc_float, prev_state, gain, 0.0f);
    *KNOCK_FILTER_STATE = filtered;

    /* Convert filtered float back to uint16 */
    uint16_t filtered_int = (uint16_t)filtered;

    /* Store converted value */
    *KNOCK_ADC_COPY2 = filtered_int;

    /* RPM-gated fault detection */
    /* (threshold comparisons based on ref_val vs ROM constants) */
    if (ref_val > *(float*)0x0007A1A4) {
        *KNOCK_FAULT_BYTE = 1;  /* Fault: above threshold */
    } else if (ref_val <= *(float*)0x0007A1D0) {
        *KNOCK_FAULT_BYTE = 0;  /* OK */
    }
}
