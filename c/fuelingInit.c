/*
 * fuelingInit.c  —  RX-8 ECU fueling & crank system initialisation
 *
 * Address: 0x00753C  |  Size: 80 bytes
 *
 * Initialises the fuel injection system together with crank position
 * sensing.  Called as part of the engine start-up sequence.  Sets up
 * the timing hardware, clears state bytes, and initialises the crank
 * sensor before falling through to crank_output_update.
 *
 * Call tree:
 *   fuelingInit
 *     ├─ crank_timer_hw_reset (0x076DC)  — reset crank timer
 *     ├─ clear/set various RAM control bytes
 *     ├─ crank_vars_init (0x07748)       — initialise crank variables
 *     ├─ crank_mode_write (0x07C00)      — write crank mode byte
 *     ├─ crank_state_bytes_clear (0x07BA8) — clear state bytes
 *     ├─ crankSensorInit (0x07C30)       — init crank sensor
 *     ├─ crank_flags_enable (0x07ED8)    — enable crank flags
 *     ├─ crank_counters_reset (0x07FB4)  — reset crank counters
 *     └─ → crank_output_update (0x0808E) — fall-through (tail call)
 *
 * Verified against ROM: c/tests/test_fuelingInit.py
 */
#include <stdint.h>

/* External crank subsystem init functions */
extern void crank_timer_hw_reset(void);
extern void crank_vars_init(void);
extern void crank_mode_write(void);
extern void crank_state_bytes_clear(void);
extern void crankSensorInit(void);
extern void crank_flags_enable(void);
extern void crank_counters_reset(void);
extern void crank_output_update(void) __attribute__((noreturn));

/* 0x00753C — initialise fuel/crank subsystem */
void fuelingInit(void)
{
    volatile uint16_t *timing_ctrl = (volatile uint16_t *)0x0000F6EA;
    volatile uint8_t  *flag_a      = (volatile uint8_t  *)0xFFFF9FA3;
    volatile uint8_t  *flag_b      = (volatile uint8_t  *)0xFFFF9FA4;
    volatile uint8_t  *flag_c      = (volatile uint8_t  *)0xFFFF9FA5;
    volatile uint8_t  *flag_d      = (volatile uint8_t  *)0xFFFF9FC0;
    volatile uint8_t  *flag_e      = (volatile uint8_t  *)0xFFFF9FC4;
    volatile uint8_t  *flag_f      = (volatile uint8_t  *)0xFFFF9FA2;

    crank_timer_hw_reset();

    /* Clear/set timing control bits */
    *timing_ctrl &= 0xFFFB;   /* AND with ~0x0004 */

    /* Clear all state flags */
    *flag_a = 1;        /* set flag A */
    *flag_b = 0;        /* clear flag B */
    *flag_c = 0;        /* clear flag C */
    *flag_d = 0;        /* clear flag D */
    *flag_e = 0;        /* clear flag E */
    *flag_f = 0;        /* clear flag F */

    /* Crank subsystem init chain */
    crank_vars_init();
    crank_mode_write();
    crank_state_bytes_clear();

    /* Clear engine-run flag and init crank sensor */
    *(volatile uint8_t *)0xFFFF9F96 = 0;
    *(volatile uint8_t *)0xFFFF9FCB = 0;
    crankSensorInit();

    crank_flags_enable();
    crank_counters_reset();

    /* Tail-call: enable crank outputs */
    crank_output_update();
}
