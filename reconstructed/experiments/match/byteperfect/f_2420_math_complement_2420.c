/*
 * encode_2420_match.c — BYTE-PERFECT match for ROM 0x2420 (16 bytes).
 *
 * ROM (see rom_hex/../disasm):
 *   extu.b r4,r3 / shll8 r3 / not r4,r2 / extu.b r2,r2 / mov r3,r4
 *   / add r2,r4 / rts / mov r4,r0
 * Semantics: ((uint32)a << 8) + (uint8)~a
 *
 * Recipe (verified byte-identical, 16/16):
 *   xgcc -B ... -m2e -O1 -fomit-frame-pointer
 *
 * Why it matches:
 *   - `hi`/`lo` pinned to r3/r2 (ROM allocation);
 *   - `av` (uint8) pinned to r4: the (unsigned)av cast forces `extu.b r4,r3`
 *     (gcc 3.4.6 assumes HImode params already zero-extended but NOT QImode,
 *     so the widening is emitted; this is the same asymmetry that makes the
 *     16-bit sibling `complement_shift_u16` need an explicit `extu.w` asm);
 *   - the two empty asm-volatile barriers stop gcc from CSE-ing the two reads
 *     of `av` into one register and stop it folding the final add onto r0;
 *   - `sum` pinned r4 with a barrier → epilogue `rts; mov r4,r0`.
 */
#include <stdint.h>

unsigned encode_2420(uint8_t a)
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
