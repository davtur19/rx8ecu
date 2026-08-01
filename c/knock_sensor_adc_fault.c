/**
 * knockSensorADCFault @ 0xC460
 * 
 * Purpose: Validate knock sensor ADC against open-circuit/short-circuit bounds.
 * 
 * RAM:
 *   0xFFFF9F0E (u16):   Knock sensor raw ADC value
 *   0xFFFFA325 (u8):    Fault code (0=OK, 1=open circuit, 2=short circuit)
 * 
 * ROM thresholds:
 *   0x0006CF7E (u16):   Max ADC threshold = 0xC831 = 51249 (~3.91V)
 *   0x0006CF7C (u16):   Min ADC threshold = 0x3EF9 = 16121 (~1.23V)
 * 
 * ADC reference: 5.0V, 16-bit resolution (0-65535)
 *   - 51249 counts ≈ 3.91V  — open circuit (sensor pulled to Vcc)
 *   - 16121 counts ≈ 1.23V  — short circuit (sensor pulled to ground)
 *   - In between: valid knock sensor signal range
 */

#include <stdint.h>

#define KNOCK_ADC_RAW_ADDR       (volatile uint16_t*)0xFFFF9F0E
#define KNOCK_FAULT_ADDR         (volatile uint8_t*) 0xFFFFA325

#define KNOCK_MAX_THRESHOLD_ADDR (uint16_t*)0x0006CF7E
#define KNOCK_MIN_THRESHOLD_ADDR (uint16_t*)0x0006CF7C

#define KNOCK_FAULT_OK      0
#define KNOCK_FAULT_OPEN    1
#define KNOCK_FAULT_SHORT   2

void knockSensorADCFault(void)
{
    uint16_t adc_value = *KNOCK_ADC_RAW_ADDR;
    uint16_t max_thresh = *KNOCK_MAX_THRESHOLD_ADDR;  /* 51249 (~3.91V) */
    uint16_t min_thresh = *KNOCK_MIN_THRESHOLD_ADDR;  /* 16121 (~1.23V) */
    uint8_t fault_code;

    if (adc_value >= max_thresh) {
        /* ADC near Vcc — sensor open circuit (disconnected) */
        fault_code = KNOCK_FAULT_OPEN;
    } else if (adc_value < min_thresh) {
        /* ADC near GND — sensor short circuit (shorted to ground) */
        fault_code = KNOCK_FAULT_SHORT;
    } else {
        /* ADC in valid operating range */
        fault_code = KNOCK_FAULT_OK;
    }

    *KNOCK_FAULT_ADDR = fault_code;
}
