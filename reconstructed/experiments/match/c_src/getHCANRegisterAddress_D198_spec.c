/*
 * getHCANRegisterAddress_D198_spec.c — specular rewrite.
 * ROM: extu.b r4,r4 / tst r4,r4 / bf.s .ADD / nop / bra .R / mov r5,r4
 *      / mov.w @(pc),r4(0x200) / add r5,r4 / rts / mov r4,r0
 * ROM branches when n != 0 to the ADD path (0x200 + base).
 */
#include <stdint.h>

unsigned getHCANRegisterAddress(uint8_t n, unsigned base)
{
    register unsigned b __asm__("r5") = base;
    register unsigned k __asm__("r4");
    if (n == 0) k = b;
    else { k = 0x0200; k += b; }
    return k;
}
