/**
 * battery_voltage_monitor.c
 *
 * RX-8 ECU Battery Voltage / Charging-Fault Monitor
 *
 * Primary function: getBatteryVoltageStatus @ 0x26766
 * (ROM body 0x26766..0x2687E; the ROM routine is a void periodic task —
 * the host lift returns the stage-1 flag byte for convenience.)
 *
 * RAM map (verified by c/tests/test_battery_voltage_monitor_26766.py,
 * differential vs sh2emu, 0 mismatches):
 *   0xFFFFB600 (f32): battery voltage input (V)
 *   0xFFFFA428 (u8):  TPS / engine-state input byte
 *   0xFFFFB6C4 (f32): ADC-processing intermediate input
 *   0xFFFFB6C8 (f32): reference voltage input
 *   0xFFFFB6B6 (u8):  stage-1 charging-fault byte (in/out)
 *   0xFFFFB67A (u16): compensation word (in/out, NOT a float)
 *   0xFFFFB6AC (u16): counter A (in/out)
 *   0xFFFFB6AE (u16): counter B (in/out)
 *
 * Calibration constants (ROM literal pool, values read back from ROM):
 *   0x751B0 (f32): 10.0    — stage-1 high threshold
 *   0x751B4 (f32): 1.0     — stage-1 hysteresis delta (the 9.0 low edge
 *                   is computed at runtime as 10.0 - 1.0 by fsub)
 *   0x751C0 (f32): 16.9729 — stage-2 comparison constant
 *   0x751C4 (f32): 10.938  — stage-2 comparison constant
 *   0x751A2/0x751A4 (u16): 63  — counter comparison constants
 *   0x751A8 (u16): 312     — compensation-word reload value
 *
 * Status outputs:
 *   getBatteryVoltageStatus → stage-1 flag at 0xFFFFB6B6
 *   (0 = bat < 9.0, hold 9.0 <= bat < 10.0, 1 = bat >= 10.0 or NaN)
 */

#include <stdint.h>

/* ================================================================
 * RAM Map
 * ================================================================ */
#define BAT_VOLTAGE          (*(volatile float    *)0xFFFFB600)   /* battery voltage input (V) */
#define BAT_VOLTAGE_COMP     (*(volatile uint16_t *)0xFFFFB67A)   /* compensation word (u16, stage 2 — not lifted) */
#define BAT_OVER_VOLT_FLAG   (*(volatile uint8_t  *)0xFFFFB6B6)   /* 1=charging fault (stage 1) */
#define BAT_INTERMEDIATE     (*(volatile float    *)0xFFFFB6C4)   /* ADC intermediate input (stage 2 — not lifted) */
#define BAT_REF_VOLTAGE      (*(volatile float    *)0xFFFFB6C8)   /* reference voltage input (stage 2 — not lifted) */

/* ================================================================
 * Calibration Constants (ROM literal pool, values read back from ROM)
 * ================================================================ */
static float get_ov_threshold_high(void)
{
    return *(volatile float *)0x000751B0;  /* 10.0 */
}

static float get_ov_hysteresis_delta(void)
{
    return *(volatile float *)0x000751B4;  /* 1.0 hysteresis delta (not a threshold) */
}

/**
 * getBatteryVoltageStatus @ 0x26766 (stage 1 only)
 *
 * Stage-1 charging-fault byte with hold band, test-pinned by
 * c/tests/test_battery_voltage_monitor_26766.py (differential vs ROM,
 * 0 mismatches). The ROM compares with fcmp/gt (T=0 on NaN, as C `>`):
 *   - bat >= 10.0 (or NaN): flag = 1
 *   - bat < 9.0 (9.0 = 10.0 - 1.0 via runtime fsub): flag = 0
 *   - 9.0 <= bat < 10.0: flag holds its previous value (ROM skips the
 *     write; the lift models the hold by re-storing the old byte)
 *
 * Returns: stage-1 flag value (0=normal, 1=charging fault)
 */
uint8_t getBatteryVoltageStatus(void)
{
    float bat_voltage = BAT_VOLTAGE;
    float ov_high = get_ov_threshold_high();              /* 10.0 */
    float ov_low = ov_high - get_ov_hysteresis_delta();   /* 9.0 via runtime fsub */

    uint8_t ov_flag;

    /* Charging-fault check with 9-10V hold band (fcmp/gt semantics:
     * NaN fails both `>` tests, so NaN takes the fault branch). */
    if (!(ov_high > bat_voltage)) {
        ov_flag = 1;   /* bat >= 10.0 (or NaN) */
    } else if (ov_low > bat_voltage) {
        ov_flag = 0;   /* bat < 9.0 */
    } else {
        ov_flag = BAT_OVER_VOLT_FLAG;   /* 9.0 <= bat < 10.0: hold */
    }

    BAT_OVER_VOLT_FLAG = ov_flag;

    /* GAP — stages 2..4 of ROM 0x26766 (B67A compensation word reload/
     * decay gated on f32 @0x751C0=16.9729 / @0x751C4=10.938 plus the
     * A428 input byte and old B6B6/B6AC/B6AE; B6AC/B6AE saturating
     * counters via helper @0x2460) are not lifted here. Their behavior
     * lives only in c/tests/test_battery_voltage_monitor_26766.py
     * (differential vs ROM, 0 mismatches) — do not re-invent. */

    return ov_flag;
}

/* GAP — ADC-to-voltage conversion is not part of the ROM 0x26766 body
 * (the verified reconstruction notes adcToBatteryVoltage /
 * readBatteryVoltageADC are absent from this vector). No ADC source
 * address and no voltage-divider ratio are verified for this path, so
 * no invented BAT_DIVIDER_RATIO/divider math is kept here. */
