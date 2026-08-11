/* ROM: 60E1D400 | Address: 0x2420 | Size: 16 bytes | STATUS: FIXED (byte-identical)
 * FIX (was DRAFT: returned r0=0, missed the rts + delay-slot `mov r4,r0`):
 *   - function must RETURN r4 (not the uninitialized r0);
 *   - param is uint8_t: the (unsigned)av widening forces `extu.b r4,r3`
 *     (GCC 3.4.6 assumes HImode params already zero-extended but NOT QImode);
 *   - the two empty asm-volatile barriers stop CSE of the two `av` reads and
 *     stop gcc folding the final add onto r0;
 *   - `sum` pinned to r4 with a barrier -> epilogue `rts; mov r4,r0`.
 *
 * ROM asm (verified vs 60E1D400.bin @0x2420, byte-identical in 60E0FC00 too):
 *   extu.b r4,r3 / shll8 r3 / not r4,r2 / extu.b r2,r2 / mov r3,r4
 *   / add r2,r4 / rts / mov r4,r0
 * Semantics: ((uint32_t)a << 8) + (uint8_t)~a        (add==or: ~a&0xFF has no high bits)
 *
 * Recipe (verified byte-identical 16/16 with GCC 3.4.6 via tools/toolchain wrapper):
 *   sh-elf-gcc-3.4.6 -m2e -O1 -fomit-frame-pointer
 */
#include <stdint.h>

unsigned math_complement_2420_2420(uint8_t a)
{
    register uint8_t av __asm__("r4") = a;
    register unsigned hi __asm__("r3");
    register unsigned lo __asm__("r2");
    __asm__ __volatile__("" : "=r"(hi) : "0"((unsigned)av << 8));
    __asm__ __volatile__("" : "=r"(lo) : "0"((unsigned)(uint8_t)~av));
    register unsigned sum __asm__("r4");
    sum = hi + lo;
    __asm__ __volatile__("" : : "r"(sum));
    return sum;
}