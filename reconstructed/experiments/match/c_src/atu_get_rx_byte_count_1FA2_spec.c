/*
 * atu_get_rx_byte_count_1FA2_spec.c — specular rewrite of the selector.
 *
 * ROM 0x1FA2:
 *   extu.b r4,r4 / mov #32,r3 / cmp/ge r3,r4 / bt .ADD / bra .R / mov r5,r4
 *   / mov.w @(pc),r4(0x200) / add r5,r4 / rts / mov r4,r0
 *
 * Baseline gcc 3.4.6 (-m2e -O1 -fomit-frame-pointer) emitted `bf` (inverted
 * polarity) and `mov.w @(pc),r1; mov r5,r4; add r1,r4` (constant in r1).
 * This variant:
 *   - writes the else-branch first (k=b) and the then-branch as
 *     accumulator `k = 0x200; k += b;` so the constant lands directly in r4;
 *   - lets the compiler choose the branch polarity that falls into `bra`
 *     for the k=b path.
 */
#include <stdint.h>

unsigned atu_get_rx_byte_count(uint8_t n, unsigned base)
{
    register unsigned b __asm__("r5") = base;
    register unsigned c __asm__("r3") = 32;
    register unsigned k __asm__("r4");
    if ((int)n < (int)c) k = b;
    else { k = 0x0200; k += b; }
    return k;
}
