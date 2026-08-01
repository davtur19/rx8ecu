/**
 * limitKnockRetardMax_ConditonalRPM @ 0x13AE4 (60E0FC00)
 *
 * Purpose:
 *   Limit the maximum knock retard based on RPM and engine operating
 *   conditions. Uses 2D table lookup (RPM vs load) to determine the
 *   allowable retard limit, with conditional selection based on a
 *   fault/status flag.
 *
 * Logic:
 *   1. Load a status/counter byte from RAM flag byte
 *   2. If flag == 1, check a secondary sensor byte; if sensor >= threshold,
 *      select retard table A, else select table B
 *   3. If flag == 0 and certain conditions met, select table B
 *   4. Call TwoDLookup with the selected table to get retard limit
 *   5. Post-process the result (e.g., sqrt or gain scaling)
 *   6. Return the final retard limit as float
 *
 * ROM calibration:
 *   0x000693CC — Retard limit table A (2D, RPM vs load)
 *   0x000693B8 — Retard limit table B (2D, RPM vs load)
 *   0x00078544 — Intermediate threshold table (u8)
 *   0x00078584 — Gain/scaling factor table
 *
 * RAM:
 *   0xFFFFB594  u16   RPM or load threshold reference
 *   0xFFFFBB25  u8    Fault/status flag byte
 *   0xFFFFB580  u8    Sensor byte for conditional check
 *   0xFFFFBC75  u8    Secondary sensor/status byte
 *
 * Calls:
 *   TwoDLookup  @ 0x2068 — 2D table interpolation
 *   sqrt        @ 0x2404 — floating-point square root
 *
 * Returns:
 *   fr0: float — maximum allowed knock retard (degrees or relative)
 */

#include <stdint.h>

#define FLAG_BYTE        (*(volatile uint8_t  *)0xFFFFBB25)
#define SENSOR_BYTE      (*(volatile uint8_t  *)0xFFFFB580)
#define SEC_BYTE         (*(volatile uint8_t  *)0xFFFFBC75)
#define REF_VALUE        (*(volatile uint16_t *)0xFFFFB594)

#define TABLE_A          (*(const uint8_t (*)[1])0x000693CC)
#define TABLE_B          (*(const uint8_t (*)[1])0x000693B8)
#define THRESH_TABLE     (*(const uint8_t (*)[1])0x00078544)
#define GAIN_TABLE       (*(const uint8_t (*)[1])0x00078584)

extern float TwoDLookup(const void* table, float rpm, float load);
extern float sqrt_float(float x);

float limitKnockRetardMax_ConditionalRPM(void)
{
    uint8_t flag   = FLAG_BYTE;
    uint8_t sensor = SENSOR_BYTE;
    const void* table;
    float result;
    float rpm_ref = (float)REF_VALUE;
    float gain;

    if (flag == 1) {
        /* Check secondary sensor byte against threshold */
        uint8_t sec = SEC_BYTE;
        if (sec >= sensor) {
            table = (const void*)&TABLE_A;
        } else {
            table = (const void*)&TABLE_B;
        }
    } else {
        /* flag == 0: additional conditions */
        if (sensor == 0) {
            table = (const void*)&TABLE_B;
        } else {
            table = (const void*)&TABLE_A;
        }
    }

    /* Perform 2D table lookup (RPM vs load) */
    result = TwoDLookup(table, rpm_ref, (float)sensor);

    /* Apply sqrt scaling */
    result = sqrt_float(result);

    return result;
}
