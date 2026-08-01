/*
 * delay_loop_n8.c  —  RX-8 PCM busy-wait timing delay  (0x239C)
 *
 * Idle-loop for n*8 iterations (where n is the argument, typically a
 * zero-extended byte from the caller).  Used as a small-integer timing
 * delay inserted via function-pointer table.
 *
 * NOTE: Despite the Ghidra/IDA name "mul16_unsigned", this is NOT a
 * multiplication helper — it's a counter loop whose trip count is
 * proportional to 8×param_1.  The name likely came from the `shll2; shll`
 * sequence that multiplies by 8, combined with the fact callers zero-extend
 * the argument.
 *
 * SH-2E asm:
 *   0x239C:  mov     #0x00,r5     ; r5 = 0
 *   0x239E:  shll2   r4           ; r4 <<= 2    (×4)
 *   0x23A0:  shll    r4           ; r4 <<= 1    (×2, total ×8)
 *   0x23A2:  cmp/hs  r4,r5        ; T = (r5 >= r4)
 *   0x23A4:  bt      0x23AC       ; if r5 >= r4, done
 *   0x23A6:  add     #0x01,r5     ; r5++
 *   0x23A8:  cmp/hs  r4,r5        ; T = (r5 >= r4)
 *   0x23AA:  bf      0x23A6       ; if r5 < r4, loop
 *   0x23AC:  rts                  ; return (no meaningful value)
 *   0x23AE:  nop                  ; (delay slot)
 *
 * Track A: verified behavior-equivalent to emulated ROM over
 * the full uint16 domain for n (0..65535 → 0..524280 iterations).
 * Test: c/tests/test_delay_loop_n8.py.
 */
#include <stdint.h>

/* 0x239C  busy-wait loop for n × 8 iterations  (was "mul16_unsigned")           */
void delay_loop_n8(uint16_t n)
{
    uint32_t count = (uint32_t)n * 8u;
    uint32_t i = 0;
    while (i < count) {
        i++;
    }
}
