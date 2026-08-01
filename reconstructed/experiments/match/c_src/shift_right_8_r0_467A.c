/*
 * shift_right_8_r0_467A — ROM 0x467A (18 bytes, no pool).
 *   8x shar r0 ... rts; shar r0  →  arithmetic shift right by 8 of r0.
 * NB: arg comes in r0 (leaf fragment), not the usual r4 — we pin r0.
 * Semantics:  a >> 8 (arithmetic)
 */
#include <stdint.h>

int shift_right_8_r0(int a)
{
    register int v __asm__("r0") = a;
    v >>= 8;
    return v;
}
