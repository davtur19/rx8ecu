/*
 * getEngineOnTimeForOilMetering.c  —  RX-8 ECU oil-metering engine-on timer
 *
 * Address: 0x00E492  |  Size: 34 bytes
 *
 * Accumulates the total engine running time used for oil metering
 * calculations.  The OMP (Oil Metering Pump) needs to know how long
 * the engine has been running to adjust the premix/oil injection rate.
 *
 * Algorithm:
 *   1. Check engine-running flag at 0xA428
 *   2. If flag == 1:
 *      - Call accumulator at 0x2460 with (timer_val, 1)
 *      - Update storage with new accumulated value
 *   3. Return
 *
 * Verified against ROM: c/tests/test_getEngineOnTimeForOilMetering.py
 */
#include <stdint.h>

extern uint16_t timer_accumulator_function(uint16_t current, uint8_t mode);

/* 0x00E492 — accumulate engine-on time for oil metering */
void getEngineOnTimeForOilMetering(void)
{
    volatile uint8_t  *engine_flag  = (volatile uint8_t  *)0x0000A428;
    volatile uint16_t *on_timer     = (volatile uint16_t *)0x0000A422;

    if (*engine_flag == 1) {
        uint16_t new_val = timer_accumulator_function(*on_timer, 1);
        *on_timer = new_val;
    }
}
