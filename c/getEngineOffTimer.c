/*
 * getEngineOffTimer.c  —  RX-8 ECU engine-off elapsed time reader
 *
 * Address: 0x03279E  |  Size: 40 bytes
 *
 * Reads and updates a timer that tracks how long the engine has been off.
 * If the engine is running (flag == 1), calls a timer-continue function
 * that adds the elapsed delta to the accumulator.  If the engine is off,
 * resets the accumulator to zero.
 *
 * Algorithm:
 *   1. Read engine-running flag at 0xA41C
 *   2. If flag == 1:
 *      - Call accumulator function at 0x2460 with (timer_val, 1)
 *      - Store returned updated timer value
 *   3. If flag != 1:
 *      - Write 0 to the timer word
 *   4. Return
 *
 * The "1" parameter likely means "continue summing" (vs "reset").
 *
 * Verified against ROM: c/tests/test_getEngineOffTimer.py
 */
#include <stdint.h>

extern uint16_t timer_accumulator_function(uint16_t current, uint8_t mode);

/* 0x03279E — get/set engine-off elapsed time counter */
void getEngineOffTimer(void)
{
    volatile uint8_t  *engine_run_flag = (volatile uint8_t  *)0x0000A41C;
    volatile uint16_t *off_timer       = (volatile uint16_t *)0xFFFFBFD6;

    if (*engine_run_flag == 1) {
        uint16_t new_val = timer_accumulator_function(*off_timer, 1);
        *off_timer = new_val;
    } else {
        *off_timer = 0;
    }
}
