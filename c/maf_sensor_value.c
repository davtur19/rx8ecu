/**
 * getMAFSensorValue @ 0x745C
 * 
 * Purpose: Read MAF sensor raw ADC, scale to voltage, apply 2D calibration
 * lookup to get air flow in g/s, validate against bounds.
 * 
 * RAM:
 *   0xFFFF9EEA (u16):   MAF sensor raw ADC value
 *   0xFFFF9F78 (float): Processed MAF value (g/s)
 *   0xFFFF9F7C (u8):    MAF status flag (0=OK, 1=high, 2=low)
 * 
 * Calibration:
 *   MAF Scaling @ 0x6FBD8 — 2D lookup table: voltage → air flow (g/s)
 * 
 * Scale factor: 7.62939e-5 = 5.0V / 65536 (16-bit ADC to voltage)
 */

#include <stdint.h>

#define MAF_ADC_ADDR       (volatile uint16_t*)0xFFFF9EEA
#define MAF_VALUE_ADDR     (volatile float*)   0xFFFF9F78
#define MAF_STATUS_ADDR    (volatile uint8_t*) 0xFFFF9F7C

#define MAF_SCALE_FACTOR   7.62939e-5f  /* 5.0V / 65536 */

/* Calibration lookup table address for MAF Scaling */
#define MAF_CAL_TABLE_ADDR 0x006FBD8

/* External 2D lookup function */
extern float TwoDLookup(uint32_t table_addr, float input);

void getMAFSensorValue(void)
{
    uint16_t maf_adc_raw = *MAF_ADC_ADDR;

    /* Convert 16-bit ADC count to voltage (0–5V range) */
    float maf_voltage = (float)maf_adc_raw * MAF_SCALE_FACTOR;

    /* Apply 2D calibration lookup (voltage → mass air flow in g/s) */
    float maf_flow = TwoDLookup(MAF_CAL_TABLE_ADDR, maf_voltage);

    *MAF_VALUE_ADDR = maf_flow;

    /* Bounds checking — raw-ADC plausibility limits, VERIFIED by disasm of
     * 0x745C (literal pool): mov.l 0x074C8,r1 -> u16@0x6CF02 (upper = 0xFAE1
     * = 64225) and mov.l 0x074CC,r0 -> u16@0x6CF04 (lower = 0x0AC0 = 2752),
     * both read with mov.w / extu.w then cmp/ge against the raw ADC.
     * (The old 0x6D402/0x6D404 were wrong — that region is a float literal
     * pool: 0x6D402=0x0000, 0x6D404=0x3F80.)  Status mapping per the disasm
     * (T=raw>=thr): raw>=upper -> 1 (high), raw>=lower -> 0 (normal),
     * else -> 2 (low).  Pinned by test_getMAFSensorValue_745C.py and
     * test_maf_limits.py (differential vs sh2emu, 0 mismatches). */
    uint16_t upper_limit = *(uint16_t*)0x006CF02;
    uint16_t lower_limit = *(uint16_t*)0x006CF04;

    uint8_t status;
    if (maf_adc_raw >= upper_limit) {
        status = 1;  /* Over-range high */
    } else if (maf_adc_raw >= lower_limit) {
        status = 0;  /* Normal range */
    } else {
        status = 2;  /* Over-range low */
    }

    *MAF_STATUS_ADDR = status;
}
