/*
 * crankSensorInit.c  —  RX-8 ECU crankshaft sensor initialization
 *
 * Address: 0x007C30  |  Size: 36 bytes
 *
 * Initializes crankshaft sensor state registers and optionally jumps
 * to crank_mode_switch if the engine is already in a running state.
 *
 * Algorithm:
 *   1. Write 0x00 to sensor control register A
 *   2. Write 0xFF to sensor control register B (all bits set/mask)
 *   3. Read engine running flag at 0xFFFF9F96
 *   4. If flag == 1: clear it and branch to crank_mode_switch (0x0768C)
 *   5. Return
 *
 * This is called during crank system init; if the engine is already
 * running (post-init reset), it transitions to the running mode state
 * machine immediately.
 *
 * Verified against ROM: c/tests/test_crankSensorInit.py
 */
#include <stdint.h>

/* External: crank mode switch at 0x0768C */
extern void crank_mode_switch(void);

/* 0x007C30 — initialise crank sensor state */
void crankSensorInit(void)
{
    volatile uint8_t *ctrl_reg_a  = (volatile uint8_t *)0xFFFF9FC9;
    volatile uint8_t *ctrl_reg_b  = (volatile uint8_t *)0xFFFF9FCA;
    volatile uint8_t *run_flag    = (volatile uint8_t *)0xFFFF9F96;

    *ctrl_reg_a = 0x00;
    *ctrl_reg_b = 0xFF;

    if (*run_flag == 1) {
        *run_flag = 0;
        crank_mode_switch(); /* transition to crank mode */
    }
}
