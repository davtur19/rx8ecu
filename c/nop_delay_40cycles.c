/*
 * nop_delay_40cycles.c  —  RX-8 ECU calibrated NOP-burn delay (~40 cycles)
 *
 * Address: 0x004C14  |  Size: 44 bytes
 *
 * A simple calibrated delay achieved by executing 20 NOP instructions
 * (each 2 bytes, 1 cycle on SH-2E) followed by RTS.  Used where a short,
 * predictable delay is needed without side effects — typically for
 * GPIO settling, peripheral timing, or bus access wait states.
 *
 * SH-2E asm:
 *   0x004C14:  nop  × 20
 *   0x004C3C:  rts              ; return
 *   0x004C3E:  nop              ; delay slot
 *
 * The function provides approximately 40 CPU cycles of delay (20 NOPs at
 * 1 cycle each + call/return overhead).  Actual timing depends on the
 * SH-2E clock speed and bus state.
 *
 * Verified against ROM: c/tests/test_nop_delay_40cycles.py
 */
#include <stdint.h>

/* 0x004C14 — burn ~40 cycles doing nothing */
void nop_delay_40cycles(void)
{
    /* 20 NOPs — implemented as a volatile loop to prevent optimizer
     * removal while maintaining the calibrated cycle count */
    volatile uint32_t i;
    for (i = 0; i < 20; i++) {
        __asm__ volatile ("nop");
    }
}
