/*
 * least_square_0x5687A.c  —  RX-8 PCM least-square check byte (0x05687A)
 *
 * Compares a byte-wide calibration/status value against a stored
 * reference byte at 0xFFFFD20B.  Returns 0 if equal, 1 if different.
 * This is used as a "least-square validity" check — a simple equality
 * test of a stored sentinel byte.
 *
 * SH-2E asm:
 *   0x05687A: extu.b  r4,r4            ; val = r4 & 0xFF
 *   0x05687C: mov.l   @(0x40,pc),r2    ; r2 = &DAT_ffffd20b
 *   0x05687E: mov.b   @r2,r3           ; r3 = *r2
 *   0x056880: extu.b  r3,r3            ; ref = r3 & 0xFF
 *   0x056882: cmp/eq  r4,r3            ; T = (val == ref)
 *   0x056884: bf/s    diff
 *   0x056886: nop
 *   0x056888: bra     ret
 *   0x05688A: mov     #0x00,r4         ; return 0  (same)
 * diff:
 *   0x05688C: mov     #0x01,r4         ; return 1  (different)
 * ret:
 *   0x05688E: rts
 *   0x056890: mov     r4,r0
 *
 * C equivalent:
 *   uint8_t ref = *(volatile uint8_t *)0xFFFFD20B;
 *   return (val != ref) ? 1 : 0;
 *
 * Track A: verified behavior-equivalent to emulated ROM over
 * all 256 possible input bytes.
 */
#include <stdint.h>

#define REF_ADDR    0xFFFFD20Bu

/* 0x05687A  Returns 1 if param_1 differs from the stored reference byte */
uint32_t least_square_0x5687A(uint8_t val)
{
    volatile uint8_t *ref_ptr = (volatile uint8_t *)REF_ADDR;
    uint8_t ref = *ref_ptr;
    return (val != ref) ? 1u : 0u;
}
