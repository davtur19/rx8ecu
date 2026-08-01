/*
 * getHCANRegisterAddress.c  —  RX-8 ECU HCAN register address calculator
 *
 * Address: 0x00D198  |  Size: 20 bytes
 *
 * Given a channel index (r4) and a base address (r5), returns either the
 * base address (for channel 0) or base + 0x200 (for non-zero channels).
 * The 0x200 stride is the register bank size for each HCAN channel in the
 * SH-2E's on-chip CAN controller.
 *
 * SH-2E asm:
 *   0x00D198:  extu.b  r4,r4        ; index = r4 & 0xFF
 *   0x00D19A:  tst     r4,r4        ; if index == 0
 *   0x00D19C:  bf/s    0x0D1A4      ;   → skip (non-zero)
 *   0x00D19E:  nop
 *   0x00D1A0:  bra     0x0D1A8      ; return base (r5)
 *   0x00D1A2:  mov     r5,r4        ; [delay] r4 = base
 *   0x00D1A4:  mov.w   @(0x12,pc),r4 ; r4 = 0x0200 (channel offset)
 *   0x00D1A6:  add     r5,r4        ; r4 = base + 0x200
 *   0x00D1A8:  rts
 *   0x00D1AA:  mov     r4,r0        ; [delay] return r4
 *
 * Called during CAN controller init to compute register block addresses
 * for each CAN channel.
 *
 * Verified against ROM: c/tests/test_getHCANRegisterAddress.py
 */
#include <stdint.h>

/* 0x00D198 — return HCAN register address for channel `idx` at `base` */
uint32_t getHCANRegisterAddress(uint32_t base, uint8_t idx)
{
    if (idx == 0) {
        return base;
    } else {
        return base + 0x200u;  /* per-channel register stride */
    }
}
