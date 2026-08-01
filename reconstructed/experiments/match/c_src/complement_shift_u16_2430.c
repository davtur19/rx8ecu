/*
 * complement_shift_u16_2430 — variant pinning temporaries r3/r2, sum r4.
 * ROM: extu.w r4,r3 / shll16 r3 / not r4,r2 / extu.w r2,r2 / mov r3,r4
 *      / add r2,r4 / rts / mov r4,r0
 */
#include <stdint.h>

unsigned complement_shift_u16(uint16_t a)
{
    register unsigned hi __asm__("r3") = (unsigned)a << 16;
    register unsigned lo __asm__("r2") = (unsigned)(uint16_t)~a;
    register unsigned sum __asm__("r4") = hi + lo;
    return sum;
}
