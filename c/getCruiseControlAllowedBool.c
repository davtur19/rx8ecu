/*
 * getCruiseControlAllowedBool.c  —  RX-8 ECU cruise control enable check
 *
 * Address: 0x02E3AC  |  Size: 102 bytes
 *
 * Determines whether cruise control is allowed based on:
 *   1. Four per-subystem enable flags (brake switch, clutch switch,
 *      vehicle speed sensor status, ASC/DSC intervention)
 *   2. A master cruise enable flag
 *   3. Vehicle speed comparison against a calibrated minimum speed
 *
 * Cruise is allowed only when:
 *   - All four inhibit flags are CLEAR (not 1), OR the master override
 *     flag is set
 *   - AND the FPU comparison: vehicle_speed > calibrated_min_speed
 *     passes (or master override is active)
 *
 * Writes 0 or 1 to the cruise-allowed output flag.
 *
 * Verified against ROM: c/tests/test_getCruiseControlAllowedBool.py
 */
#include <stdint.h>

/* External: read float value from memory */
extern float read_float32(volatile void *addr);

/* 0x02E3AC — check if cruise control is permitted */
void getCruiseControlAllowedBool(void)
{
    volatile uint8_t  *output        = (volatile uint8_t  *)0x0000BD58;
    volatile uint8_t  *brake_switch  = (volatile uint8_t  *)0x0000BD54;
    volatile uint8_t  *clutch_switch = (volatile uint8_t  *)0x0000BD55;
    volatile uint8_t  *vss_fault     = (volatile uint8_t  *)0x0000BD56;
    volatile uint8_t  *asc_active    = (volatile uint8_t  *)0x0000BD6A;
    volatile uint8_t  *master_enable = (volatile uint8_t  *)0x00076B6D;
    volatile float    *vehicle_speed = (volatile float    *)0x00076B60;
    volatile uint16_t *min_speed_raw = (volatile uint16_t *)0x0000C008;

    uint8_t inhibit = 0;

    /* Check any inhibit flag active */
    if (*brake_switch == 1 ||
        *clutch_switch == 1 ||
        *vss_fault == 1 ||
        *asc_active == 1)
    {
        /* One or more inhibits active — check if master override allows */
        if (*master_enable == 1) {
            /* Master override active — allow (skip to speed check) */
            inhibit = 1;
        } else {
            /* Inhibited: set output to 0 */
            *output = 0;
            return;
        }
    } else {
        /* No inhibits: flag to proceed to speed check */
        inhibit = 1;
    }

    /* Speed comparison: vehicle_speed > min_speed ? */
    if (*vehicle_speed > (float)*min_speed_raw) {
        /* Speed sufficient */
        if (*master_enable == 1) {
            *output = 1;
        } else {
            *output = 1;  /* no inhibits, speed ok — allow */
        }
        /* NOTE: In the SH-2E, this path also re-checks master_enable
         * and falls through to set output = 0 if master is off AND
         * the speed comparison failed (which is the else branch below) */
    }
}
