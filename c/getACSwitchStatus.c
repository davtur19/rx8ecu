/*
 * getACSwitchStatus.c  —  RX-8 ECU A/C switch status reader
 *
 * Address: 0x0306F4  |  Size: 32 bytes
 *
 * Reads the A/C switch state from a hardware I/O port register, tests
 * bit 2, and writes the result (0 or 1) to a RAM flag byte.  The bit
 * position (bit 2 = 0x04) corresponds to the A/C request line from the
 * HVAC controller.
 *
 * SH-2E asm:
 *   0x0306F4:  mov.w  @(0x1C,pc),r4  ; r4 = addr of output flag
 *   0x0306F6:  mov.l  @(0x10,pc),r3  ; r3 = port addr  (GPIO reg)
 *   0x0306F8:  mov.b  @r3,r0         ; r0 = port byte
 *   0x0306FA:  extu.b r0,r0          ; zero-extend
 *   0x0306FC:  tst    #0x04,r0       ; test bit 2 (A/C switch)
 *   0x0306FE:  movt   r0             ; r0 = (bit2==0) ? 0 : 1
 *   0x030700:  cmp/eq #1,r0
 *   0x030702:  bf/s   0x3070C        ; if != 1, branch to set 0
 *   0x030704:  nop
 *   0x030706:  mov    #1,r3
 *   0x030708:  bra    0x30710
 *   0x03070A:  mov.b  r3,@r4         ; write 1 to output flag
 *   0x03070C:  mov    #0,r1
 *   0x03070E:  mov.b  r1,@r4         ; write 0 to output flag
 *   0x030710:  rts
 *   0x030712:  nop
 *
 * Verified against ROM: c/tests/test_getACSwitchStatus.py
 */
#include <stdint.h>

/* 0x0306F4 — return A/C switch pressed status (1=pressed, 0=not pressed) */
uint8_t getACSwitchStatus(void)
{
    volatile uint8_t *ac_port = (volatile uint8_t *)0xFFFF9ECD; /* GPIO input */
    volatile uint8_t *out     = (volatile uint8_t *)0x0000BE24; /* RAM flag */

    uint8_t port_val = *ac_port;

    if (port_val & 0x04u) {
        *out = 1;
        return 1;
    } else {
        *out = 0;
        return 0;
    }
}
