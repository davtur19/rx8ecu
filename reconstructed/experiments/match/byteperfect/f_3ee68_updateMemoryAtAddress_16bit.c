/*
 * f_3ee68_updateMemoryAtAddress_16bit.c — BYTE-PERFECT match for ROM 0x3EE68 (16 bytes).
 *
 * ROM (60E1D400.bin):
 *   extu.w r5,r3 / shll16 r3 / not r5,r2 / extu.w r2,r2 / add r2,r3
 *   / mov.l r3,@r4 / rts / mov #0,r0
 * Semantics: *p = (uint32_t)((a << 16) + (uint16_t)~a); return 0;
 * (the store-variant sibling of complement_shift_u16@0x2430)
 *
 * Why the explicit `extu.w` inline asm: gcc 3.4.6 assumes a HImode parameter
 * register is already zero-extended, so `(unsigned)av` would be a plain `mov`
 * instead of the ROM's `extu.w r5,r3` (same asymmetry as complement_shift_u16).
 *
 * Verified byte-identical with the base recipe (-m2e -O1 -fomit-frame-pointer).
 */
#include <stdint.h>

unsigned m_store16(uint32_t *p, uint16_t a)
{
    register uint16_t av __asm__("r5") = a;
    register uint32_t *pp __asm__("r4") = p;
    register unsigned hi __asm__("r3");
    __asm__ __volatile__("extu.w %1,%0" : "=r"(hi) : "r"(av));
    hi <<= 16;
    register unsigned lo __asm__("r2") = (unsigned)(uint16_t)~av;
    register unsigned sum __asm__("r3");
    sum = hi + lo;
    __asm__ __volatile__("" : : "r"(sum));
    *pp = sum;
    return 0;
}