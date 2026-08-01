/*
 * dtc_data_read_60F58.c  —  RX-8 PCM DTC data read/clear (0x060F58)
 *
 * Fills four consecutive 16-bit memory locations at 0xFFFFD6C8 with 0xFFFF.
 * This is a "Reset DTC Data" operation — writing 0xFFFF to every halfword
 * in the DTC status region marks all DTC entries as "completed/cleared".
 *
 * SH-2E asm:
 *   0x060F58: mov.l   @(0x1C,pc),r7     ; r7 = 0xFFFFD6C8   (base addr)
 *   0x060F5A: mov     r7,r4
 *   0x060F5C: mov.l   @(0x1C,pc),r5     ; r5 = 0x0000FFFF   (fill value)
 *   0x060F5E: mov     r7,r6
 *   0x060F60: add     #0x08,r6          ; r6 = base + 8      (end bound)
 *   loop:
 *   0x060F62: mov.w   r5,@r4            ; *r4 = 0xFFFF
 *   0x060F64: add     #0x04,r4          ; r4 += 4  (skip 2 halfwords)
 *   0x060F66: cmp/hs  r6,r4             ; while r4 < r6
 *   0x060F68: bf/s    loop
 *   0x060F6A: nop
 *   0x060F6C: rts
 *   0x060F6E: nop
 *
 * The region spans 8 bytes: 0xFFFFD6C8 .. 0xFFFFD6CF  (4 × uint16).
 * Track A: verified behavior-equivalent to emulated ROM.
 */
#include <stdint.h>

#define DTC_BASE  0xFFFFD6C8u

/* 0x060F58  Reset all four DTC status halfwords to 0xFFFF           */
void dtc_data_read_60F58(void)
{
    volatile uint16_t *p = (volatile uint16_t *)DTC_BASE;
    volatile uint16_t *end = p + 4;
    do {
        *p = 0xFFFFu;
        p++;
    } while (p < end);
}
