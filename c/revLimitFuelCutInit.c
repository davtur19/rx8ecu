/*
 * revLimitFuelCutInit.c  —  RX-8 ECU rev-limiter fuel cut initialisation
 *
 * Address: 0x00F0FC  |  Size: 30 bytes
 *
 * Initialises the rev-limiter fuel-cut counters to zero.
 * Only executes if the rev-limit-enabled flag is set (==1).
 *
 * Algorithm:
 *   1. Read rev-limit enable flag at global byte
 *   2. If flag == 1:
 *      - Clear two byte registers (counter hi/lo or per-rotor)
 *      - Clear a 16-bit accumulator register
 *   3. Return
 *
 * The flag is typically set by calibration or after the crank-to-run
 * transition is complete.
 *
 * Verified against ROM: c/tests/test_revLimitFuelCutInit.py
 */
#include <stdint.h>

/* 0x00F0FC — initialise rev-limit fuel cut counters */
void revLimitFuelCutInit(void)
{
    volatile uint8_t *enable_flag = (volatile uint8_t *)0xFFFF9F8C;
    volatile uint8_t *cnt_a       = (volatile uint8_t *)0x0000A4A4;
    volatile uint8_t *cnt_b       = (volatile uint8_t *)0x0000A4A5;
    volatile uint16_t *accum      = (volatile uint16_t *)0xFFFFA4A8;

    if (*enable_flag == 1) {
        *cnt_a  = 0;
        *cnt_b  = 0;
        *accum  = 0;
    }
}
