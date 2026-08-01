/*
 * getHCANRegisterAddress_D198 — ROM 0xD198 (20 B body; pool @0xD1BA non-contiguous).
 *   extu.b r4,r4 / tst r4,r4 / bf/s .L / nop / bra .R / mov r5,r4
 *   / mov.w @(pc),r4   ; 0x0200
 *   / add r5,r4 / rts / mov r4,r0
 * Semantics:  n != 0 ? base + 0x0200 : base
 */
#include <stdint.h>

unsigned getHCANRegisterAddress(uint8_t n, unsigned base)
{
    register unsigned b __asm__("r5") = base;
    register unsigned k __asm__("r4");
    if (n != 0) k = 0x0200 + b; else k = b;
    return k;
}
