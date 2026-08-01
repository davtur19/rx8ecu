/*
 * encode_2420 — ROM 0x2420 (16 bytes, no pool).
 *   extu.b r4,r3 / shll8 r3 / not r4,r2 / extu.b r2,r2 / mov r3,r4
 *   / add r2,r4 / rts / mov r4,r0
 * Semantics:  ((uint32)a << 8) + (uint8)~a
 */
#include <stdint.h>

unsigned encode_2420(uint8_t a)
{
    return ((unsigned)a << 8) + (uint8_t)~a;
}
