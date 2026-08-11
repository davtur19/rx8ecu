/* ROM: 60E1D400 | Address: 0x2430 | Size: 16 bytes | STATUS: FIXED (byte-identical)
 * FIX (was DRAFT: returned r0=0, missed the rts + delay-slot `mov r4,r0`):
 *   - function must RETURN r4 (not the uninitialized r0);
 *   - GCC 3.4.6 assumes a HImode param register is already zero-extended, so
 *     `(unsigned)av` for uint16_t av would become `mov r4,r3` instead of the
 *     ROM's `extu.w r4,r3` — the inline `extu.w %1,%0` expresses exactly the
 *     widening the target requires (the empty-asm barrier + register trick of
 *     the 8-bit sibling encode_2420 does NOT work here);
 *   - `sum` pinned to r4 with a barrier -> epilogue `rts; mov r4,r0`.
 *
 * ROM asm (verified vs 60E1D400.bin @0x2430, byte-identical in 60E0FC00 too):
 *   extu.w r4,r3 / shll16 r3 / not r4,r2 / extu.w r2,r2 / mov r3,r4
 *   / add r2,r4 / rts / mov r4,r0
 * Semantics: ((uint32_t)a << 16) + (uint16_t)~a      (add==or: ~a&0xFFFF has no high bits)
 *
 * Recipe (verified byte-identical 16/16 with GCC 3.4.6 via tools/toolchain wrapper):
 *   sh-elf-gcc-3.4.6 -m2e -O1 -fomit-frame-pointer
 */
#include <stdint.h>

unsigned math_complement_2430_2430(uint16_t a)
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