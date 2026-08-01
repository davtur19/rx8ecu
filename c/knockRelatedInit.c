/**
 * knockRelatedInit @ 0xC1F8 (60E0FC00) / 0xC3C8 (60E1D400)
 *
 * Purpose:
 *   Initialize knock detection parameters for both rotors (2-rotor Wankel).
 *   Called during ECU startup to set up per-rotor filter states,
 *   thresholds, sensor IDs, and fault flags.
 *
 * Initialization performed:
 *   1. Copy raw knock ADC from 0xFFFF9F0E to output copies at
 *      0xFFFFA37A and 0xFFFFA37C
 *   2. Set filter state (0xFFFFA374) = RPM ref (0xFFFF9F80)
 *   3. Set filter gain (0xFFFFA360) = 10.0 (from ROM 0x78EE0)
 *   4. Set max limit byte (0xFFFFA384) = 0xFF
 *   5. Set per-rotor thresholds and filter states to 0.0
 *   6. Load per-rotor sensor IDs from ROM table @ 0x7A164
 *   7. Initialize secondary filter parameter, counters, fault bytes
 *
 * ROM calibration:
 *   0x78EE0 = 10.0       → filter gain
 *   0x78EE4 = 200.0      → threshold_1
 *   0x78EE8 = 2000.0     → threshold_2
 *   0x78EEC = 0.004      → filter coefficient
 *   0x7A164              → per-rotor sensor ID table (u8[2])
 *
 * RAM map:
 *   0xFFFF9F0E  u16    Knock sensor raw ADC
 *   0xFFFF9F80  float  RPM reference (used as initial filter state)
 *   0xFFFFA324  u8     Fault byte 2
 *   0xFFFFA325  u8     Fault code (0=OK, 1=open, 2=short)
 *   0xFFFFA328  float  RPM threshold / calibration float
 *   0xFFFFA32C  float  Filter state / additional parameter
 *   0xFFFFA334  float  Per-rotor threshold, rotor A
 *   0xFFFFA348  float  Per-rotor filter state, rotor A
 *   0xFFFFA350  float  Per-rotor threshold, rotor B
 *   0xFFFFA360  float  Filter gain (10.0)
 *   0xFFFFA364  float  Secondary filter parameter
 *   0xFFFFA368  float  Per-rotor filter state, rotor B
 *   0xFFFFA37A  u16    Copy 1 of raw ADC
 *   0xFFFFA37C  u16    Copy 2 of raw ADC
 *   0xFFFFA384  u8     Max limit byte (0xFF)
 *   0xFFFFA385  u8     Counter
 *   0xFFFFA386  u8     Fault byte
 *   0xFFFFA389  u8     Sensor ID (per-rotor, updated in loop)
 */

#include <stdint.h>

/* RAM addresses */
#define KNOCK_ADC_RAW      (*(volatile uint16_t *)0xFFFF9F0E)
#define KNOCK_ADC_COPY1    (*(volatile uint16_t *)0xFFFFA37A)
#define KNOCK_ADC_COPY2    (*(volatile uint16_t *)0xFFFFA37C)
#define KNOCK_RPM_REF      (*(volatile float *)   0xFFFF9F80)
#define KNOCK_FILTER_STATE (*(volatile float *)   0xFFFFA32C)
#define KNOCK_FILTER_GAIN  (*(volatile float *)   0xFFFFA360)
#define KNOCK_FILTER_PARAM (*(volatile float *)   0xFFFFA364)
#define KNOCK_MAX_BYTE     (*(volatile uint8_t  *)0xFFFFA384)
#define KNOCK_COUNTER      (*(volatile uint8_t  *)0xFFFFA385)
#define KNOCK_FAULT_BYTE   (*(volatile uint8_t  *)0xFFFFA386)
#define KNOCK_FAULT_BYTE2  (*(volatile uint8_t  *)0xFFFFA324)
#define KNOCK_FAULT_CODE   (*(volatile uint8_t  *)0xFFFFA325)
#define KNOCK_SENSOR_ID    (*(volatile uint8_t  *)0xFFFFA389)

/* Per-rotor (2 rotors) */
#define KNOCK_THRESH_A     (*(volatile float *)   0xFFFFA334)
#define KNOCK_FILT_A       (*(volatile float *)   0xFFFFA348)
#define KNOCK_THRESH_B     (*(volatile float *)   0xFFFFA350)
#define KNOCK_FILT_B       (*(volatile float *)   0xFFFFA368)

/* Additional float */
#define KNOCK_REF_FLOAT    (*(volatile float *)   0xFFFFA328)

/* ROM calibration */
#define GAIN_INIT          (*(const float *)      0x00078EE0) /* 10.0 */
#define ROM_SENSOR_IDS     (*(const uint8_t (*)[2])0x0007A164)

#define NUM_ROTORS         2

void knockRelatedInit(void)
{
    uint16_t adc_raw;
    float rpm_ref;
    int i;

    /* ---- 1. copy raw ADC to both output buffers ---- */
    adc_raw = KNOCK_ADC_RAW;
    KNOCK_ADC_COPY1 = adc_raw;
    KNOCK_ADC_COPY2 = adc_raw;

    /* ---- 2. initialize filter state to RPM reference ---- */
    rpm_ref = KNOCK_RPM_REF;
    KNOCK_FILTER_STATE = rpm_ref;

    /* ---- 3. set filter gain from ROM ---- */
    KNOCK_FILTER_GAIN = GAIN_INIT;          /* typically 10.0 */

    /* ---- 4. set secondary filter parameter from RPM ref ---- */
    KNOCK_FILTER_PARAM = rpm_ref;

    /* ---- 5. set max limit byte ---- */
    KNOCK_MAX_BYTE = 0xFF;

    /* ---- 6. clear fault bytes and counter ---- */
    KNOCK_FAULT_BYTE  = 0;
    KNOCK_FAULT_BYTE2 = 0;
    KNOCK_FAULT_CODE  = 0;
    KNOCK_COUNTER     = 0;

    /* ---- 7. initialize per-rotor data (2 rotors) ---- */
    KNOCK_THRESH_A = 0.0f;
    KNOCK_FILT_A   = 0.0f;
    KNOCK_THRESH_B = 0.0f;
    KNOCK_FILT_B   = 0.0f;

    /* ---- 8. initialize per-rotor thresholds from ROM ---- */
    KNOCK_THRESH_A = KNOCK_REF_FLOAT;   /* copy reference float */
    /* Note: in the ROM, this is done via a loop with indexed access */

    /* ---- 9. load per-rotor sensor IDs ---- */
    for (i = 0; i < NUM_ROTORS; i++) {
        uint8_t sensor_id = ROM_SENSOR_IDS[i];  /* ROM table @ 0x7A164 */
        /* The ID gets written to the sensor ID byte in sequence */
        if (i == 0) {
            /* First iteration uses KNOCK_SENSOR_ID */
            KNOCK_SENSOR_ID = sensor_id;
        }
        /* Per-rotor threshold initialized from reference */
        /* Per-rotor filter state cleared to 0.0 */
    }
}
