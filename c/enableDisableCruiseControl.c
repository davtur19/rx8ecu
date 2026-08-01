/*
 * enableDisableCruiseControl.c  —  RX-8 ECU cruise control enable/disable
 *
 * Address: 0x00C2E6  |  Size: 54 bytes
 *
 * Enables or disables the cruise control system.  Takes a boolean
 * parameter (0=disable, 1=enable) and updates the cruise control
 * state variables accordingly.  Uses tail-call optimisation (jmp)
 * for the final dispatch to a cleanup/finalisation function.
 *
 * Algorithm:
 *   1. Call dispatch function at 0x3920 with r4=0x10 (lock/mutex?)
 *   2. Read current enable state at 0xFFFFA38C
 *   3. If input != current state:
 *      - Write 0xFF to cruise PWM duty init (all on)
 *      - Write 0x00 to two cruise control flags
 *      - Update state to new value
 *   4. Tail-call to cleanup at 0x3934 (via jmp @Rn)
 *
 * The 0xFF written to the PWM init register ensures the cruise
 * actuator starts from a known state when transitioning.
 *
 * Verified against ROM: c/tests/test_enableDisableCruiseControl.py
 */
#include <stdint.h>

/* External: dispatch and cleanup functions (indirect via 0x3920/0x3934) */
extern uint32_t dispatch_3920(uint32_t r4);
extern void     cleanup_3934(void) __attribute__((noreturn));

/* 0x00C2E6 — enable or disable cruise control */
void enableDisableCruiseControl(uint8_t enable)
{
    volatile uint8_t *cruise_state  = (volatile uint8_t *)0xFFFFA38C;
    volatile uint8_t *pwm_init      = (volatile uint8_t *)0xFFFFA384;
    volatile uint8_t *flag_a        = (volatile uint8_t *)0xFFFFA385;
    volatile uint8_t *flag_b        = (volatile uint8_t *)0xFFFFA324;

    dispatch_3920(0x10);

    if (*cruise_state != enable) {
        *pwm_init = 0xFF;   /* reset PWM actuator */
        *flag_a   = 0x00;   /* clear cruise flags */
        *flag_b   = 0x00;
        *cruise_state = enable;
    }

    /* tail-call to cleanup */
    cleanup_3934();
}
