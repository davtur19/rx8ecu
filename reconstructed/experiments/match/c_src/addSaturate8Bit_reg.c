/*
 * addSaturate8Bit_reg — variant for the GCC 3.4.6 sweep (see scripts/sweep_gcc346.py).
 *
 * Aimed at ROM 0x2478 (extu.w inputs, signed cmp/ge, extra 16-bit truncation
 * before the compare).  Uses uint16_t params (extu.w zero-extension, like the
 * ROM), a `uint16_t sum` (forces the extra `extu.w` before the signed
 * compare), `max` as a variable (no `>= 255 -> > 254` fold), registers pinned
 * to r4/r5, and `unsigned` return (plain `mov r4,r0` epilogue).
 *
 * GCC 3.4.6 -m2e -O1 -fomit-frame-pointer is one instruction and a register
 * away from the ROM: gcc emits `extu.w r4,r1; cmp/ge r5,r1` (r1) and
 * `rts; extu.w r4,r0` where the ROM has `extu.w r4,r3; cmp/ge r5,r3` and
 * `rts; mov r4,r0`.
 */
#include <stdint.h>

unsigned addSaturate8Bit(uint16_t add1, uint16_t add2)
{
    register uint16_t sum __asm__("r4") = (uint16_t)(add1 + add2);
    register int max __asm__("r5") = 255;
    if ((int)sum >= max) sum = (uint16_t)max;
    return sum;
}
