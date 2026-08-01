/**
 * getKnockSensorADC @ 0xC3CE (60E0FC00)
 *
 * Purpose:
 *   Read knock sensor raw ADC, copy to output buffer, apply first-order
 *   low-pass filter in the 200-2000 RPM band, and validate the RPM reference.
 *
 * Logic summary:
 *   1. Load RPM float; if RPM >= 10000 → fault=1, else fault=0
 *   2. Copy raw ADC (0xFFFF9F0E) to output buffer (0xFFFFA37A)
 *   3. If 200 <= RPM < 2000:
 *        call firstOrderFilter(raw_adc_float, prev_state, coeff_0_004, 1.0)
 *        store filtered float back; convert to uint16 and store to 0xFFFFA378
 *   4. Else (RPM outside filtering band): leave filter state unchanged
 *
 * ROM calibration:
 *   0x78EE4 = 200.0      → low-RPM knee  (below this → no filter)
 *   0x78EE8 = 2000.0     → high-RPM knee (above/at this → no filter)
 *   0x78EEC = 0.004      → IIR filter coefficient
 *   0x78EA4 = 10000.0    → RPM validity limit (fault if >=)
 *   0x78EA0 = 10000.0    → redundant limit loaded via 2nd pointer
 *   0x023B0              → address of firstOrderFilter
 *
 * RAM map:
 *   0xFFFF9F80  float  RPM reference
 *   0xFFFF9F0E  u16    Knock sensor raw ADC
 *   0xFFFFA37A  u16    Copy of raw ADC (output)
 *   0xFFFFA374  float  Filter state (previous filter output)
 *   0xFFFFA378  u16    Filtered integer output
 *   0xFFFFA386  u8     Fault byte (0=OK, 1=RPM out-of-range)
 */

#include <stdint.h>

#define KNOCK_RPM_REF      (*(volatile float *)   0xFFFF9F80)
#define KNOCK_ADC_RAW      (*(volatile uint16_t *)0xFFFF9F0E)
#define KNOCK_ADC_COPY     (*(volatile uint16_t *)0xFFFFA37A)
#define KNOCK_FILTER_STATE (*(volatile float *)   0xFFFFA374)
#define KNOCK_FILTER_OUT   (*(volatile uint16_t *)0xFFFFA378)
#define KNOCK_FAULT_BYTE   (*(volatile uint8_t  *)0xFFFFA386)

#define THRESHOLD_1        (*(const float *)      0x00078EE4) /* 200.0  */
#define THRESHOLD_2        (*(const float *)      0x00078EE8) /* 2000.0 */
#define FILTER_COEFF       (*(const float *)      0x00078EEC) /* 0.004  */
#define FAULT_LIMIT        (*(const float *)      0x00078EA4) /* 10000.0 */

extern float firstOrderFilter(float new_sample, float prev_out,
                               float gain, float min_ff);

void getKnockSensorADC(void)
{
    float rpm   = KNOCK_RPM_REF;
    uint16_t adc_raw = KNOCK_ADC_RAW;

    /* ---- 1. copy raw ADC to output buffer ---- */
    KNOCK_ADC_COPY = adc_raw;

    /* ---- 2. conditional first-order filter ---- */
    if (rpm >= THRESHOLD_1 && rpm < THRESHOLD_2) {
        /* filtering band 200 <= RPM < 2000 */
        float adc_f   = (float)adc_raw;
        float prev    = KNOCK_FILTER_STATE;
        float filtered = firstOrderFilter(adc_f, prev, FILTER_COEFF, 1.0f);

        KNOCK_FILTER_STATE = filtered;
        KNOCK_FILTER_OUT   = (uint16_t)filtered;
    }
    /* outside the band: filter state retains its previous value */

    /* ---- 3. RPM validity check ---- */
    if (rpm >= FAULT_LIMIT) {
        KNOCK_FAULT_BYTE = 1;   /* RPM reference out of valid range */
    } else {
        KNOCK_FAULT_BYTE = 0;   /* OK */
    }
}
