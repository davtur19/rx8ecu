/*
 * f_2034_checksum_complement_add.c — BYTE-PERFECT match for ROM 0x2034 (14 bytes).
 *
 * ROM (60E1D400.bin):
 *   mov.l @r4,r3 / mov r3,r0 / shlr16 r3 / not r0,r0 / sub r3,r0
 *   / rts / extu.w r0,r0
 * Semantics: x = *p; return (uint16_t)(~x - (x >> 16));
 *
 * The two register pins (x in r3, a copy in r0) are required: without them
 * gcc picks r1 for the load and emits `not` before the shift, breaking the
 * byte order. With the pins + base recipe (-m2e -O1 -fomit-frame-pointer)
 * the output is byte-identical (14/14) including the `rts; extu.w r0,r0`
 * delay-slot epilogue.
 */
#include <stdint.h>

uint16_t m_checksum(uint32_t *p)
{
    register uint32_t x __asm__("r3") = *p;
    register uint32_t a __asm__("r0") = x;
    register uint32_t hi __asm__("r3");
    hi = x >> 16;
    register uint32_t lo __asm__("r0") = ~a;
    lo -= hi;
    return (uint16_t)lo;
}