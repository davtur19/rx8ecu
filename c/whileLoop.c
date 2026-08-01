/*
 * whileLoop.c  —  RX-8 ECU infinite wait-loop / trap handler
 *
 * Address: 0x00A0CE  |  Size: 14 bytes
 *
 * An infinite-loop function used as a trap for unrecoverable error states,
 * watchdog timeouts, or assertion failures.  The SH-2E code performs:
 *
 *   0x00A0CE:  unknown  0x0002       ; (likely data or padding)
 *   0x00A0D0:  mov.w  @(0x18,pc),r3  ; r3 = 0xFF0F  (mask)
 *   0x00A0D2:  and    r3,r0          ; apply mask to r0
 *   0x00A0D4:  unknown  0xCBF0       ; (GBR-relative or custom)
 *   0x00A0D6:  unknown  0x400E       ; (SH-2E reserved or custom)
 *   0x00A0D8:  bra    0x0A0D8        ; infinite loop (while(1))
 *   0x00A0DA:  nop                   ; delay slot
 *
 * The initial instructions likely mask/clear some state before entering
 * the infinite loop.  The BRA to itself is the definitive infinite loop.
 *
 * Verified against ROM: c/tests/test_whileLoop.py
 */
#include <stdint.h>

/* 0x00A0CE — trap/halt; never returns */
void whileLoop(void)
{
    /* Hardware-triggered infinite loop — equivalent to the BRA at 0x0A0D8.
     * In the actual ECU this is entered after a fatal error such as
     * stack corruption, invalid interrupt, or unexpected trap. */
    while (1) {
        /* burn CPU — watchdog will eventually reset the ECU */
        __asm__ volatile ("nop");
    }
}
