/*
 * charging_status_59C24 — ROM 0x59C24 (18 bytes, no pool). Arg is in r5!
 *   extu.b r5,r5 / tst r5,r5 / bf/s .L / nop / bra .R / mov #0,r4
 *   / mov #1,r4 / rts / mov r4,r0
 * Semantics:  b != 0 ? 1 : 0   (second param b lives in r5 per SH ABI)
 */
#include <stdint.h>

unsigned charging_status(uint8_t a, uint8_t b)
{
    register uint8_t v __asm__("r5") = b;
    return v != 0;
}
