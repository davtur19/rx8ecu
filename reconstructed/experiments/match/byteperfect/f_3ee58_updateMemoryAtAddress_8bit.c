/*
 * f_3ee58_updateMemoryAtAddress_8bit.c — BYTE-PERFECT match for ROM 0x3EE58 (16 bytes).
 *
 * ROM (60E1D400.bin):
 *   extu.b r5,r3 / shll8 r3 / not r5,r2 / extu.b r2,r2 / add r2,r3
 *   / mov.w r3,@r4 / rts / mov #0,r0
 * Semantics: *p = (uint16_t)((a << 8) + (uint8_t)~a); return 0;
 * (the store-variant sibling of encode_2420@0x2420)
 *
 * Verified byte-identical with the base recipe:
 *   /home/davide/gcc346/bin/sh-elf-gcc -nostdinc -I /tmp/stubinc -S <src>.c \
 *     -m2e -O1 -fomit-frame-pointer
 *   tools/toolchain/usr/bin/sh-elf-as -isa=sh2e ; objcopy -O binary --only-section=.text
 */
#include <stdint.h>

unsigned m_store8(uint16_t *p, uint8_t a)
{
    register uint8_t av __asm__("r5") = a;
    register uint16_t *pp __asm__("r4") = p;
    register unsigned hi __asm__("r3");
    register unsigned lo __asm__("r2");
    __asm__ __volatile__("" : "=r"(hi) : "0"((unsigned)av << 8));
    __asm__ __volatile__("" : "=r"(lo) : "0"((unsigned)(uint8_t)~av));
    register unsigned sum __asm__("r3");
    sum = hi + lo;
    __asm__ __volatile__("" : : "r"(sum));
    *pp = (uint16_t)sum;
    return 0;
}