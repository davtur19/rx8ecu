/*
 * complement_shift_u16_2430_match.c — BYTE-PERFECT match for ROM 0x2430 (16 bytes).
 *
 * ROM:
 *   extu.w r4,r3 / shll16 r3 / not r4,r2 / extu.w r2,r2 / mov r3,r4
 *   / add r2,r4 / rts / mov r4,r0
 * Semantics: ((uint32)a << 16) + (uint16)~a
 *
 * Recipe (verified byte-identical, 16/16):
 *   xgcc -B ... -m2e -O1 -fomit-frame-pointer
 *
 * Why the explicit `extu.w` inline asm:
 *   gcc 3.4.6 assumes a HImode parameter register is already zero-extended,
 *   so `(unsigned)av` for `uint16_t av` becomes a plain `mov r4,r3` instead
 *   of the ROM's `extu.w r4,r3`.  The empty-asm barrier + `register uint16_t
 *   av` trick (used by the 8-bit sibling encode_2420) does NOT work here for
 *   the same reason.  The inline `extu.w %1,%0` expresses exactly the widening
 *   the target requires; everything else is plain C with scheduling barriers.
 */
#include <stdint.h>

unsigned complement_shift_u16(uint16_t a)
{
    register uint16_t av __asm__("r4") = a;
    register unsigned hi __asm__("r3");
    __asm__ __volatile__("extu.w %1,%0" : "=r"(hi) : "r"(av));
    hi <<= 16;
    register unsigned lo __asm__("r2") = (unsigned)(uint16_t)~av;
    register unsigned sum __asm__("r4");
    sum = hi + lo;
    __asm__ __volatile__("" : : "r"(sum));
    return sum;
}
