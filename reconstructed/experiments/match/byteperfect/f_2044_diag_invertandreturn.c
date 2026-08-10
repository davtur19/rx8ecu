/*
 * f_2044_diag_invertandreturn.c — BYTE-PERFECT match for ROM 0x2044 (14 bytes).
 *
 * ROM (60E1D400.bin):
 *   mov.w @r4,r3 / mov r3,r0 / shlr8 r3 / not r0,r0 / sub r3,r0
 *   / rts / extu.b r0,r0
 * Semantics: x = *p; return (uint8_t)(~x - (x >> 8));
 *
 * Type trick: the load is done as `(int16_t)*(int16_t*)p` — a 16-bit load
 * sign-extends into r3 with no widen, exactly like the ROM's `mov.w @r4,r3`.
 * Declaring the loaded value as `uint16_t` would make gcc emit an extra
 * `extu.w r3,r3`. The register pins (x in r3, copy in r0) fix the `not`/shift
 * order so the bytes match (14/14) with the base recipe.
 */
#include <stdint.h>

uint8_t m_invert(uint16_t *p)
{
    register int x __asm__("r3") = (int16_t)*(int16_t *)p;
    register int a __asm__("r0") = x;
    register unsigned hi __asm__("r3");
    hi = ((unsigned)x) >> 8;
    register unsigned lo __asm__("r0") = ~((unsigned)a);
    lo -= hi;
    return (uint8_t)lo;
}