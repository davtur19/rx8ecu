/*
 * charging_status_59C24_branch.c — best-effort branch variant for ROM 0x59C24.
 *
 * ROM:
 *   extu.b r5,r5 / tst r5,r5 / bf.s .L / nop / bra .R / mov #0,r4
 *   / mov #1,r4 / rts / mov r4,r0
 *
 * Best result with GCC 3.4.6 (structural match, 50% byte / branch polarity
 * and registers correct):
 *   xgcc -B ... -m2e -O1 -fomit-frame-pointer -fno-if-conversion
 *        -fno-if-conversion2 [-fno-delayed-branch]
 *
 * The two -fno-if-conversion flags disable the `movt`/`negc` boolean
 * idioms; the explicit if/else on a single pinned r4 with one return keeps
 * the branch structure.  gcc 3.4.6 still differs from the ROM in ONE
 * structural point: it fills the conditional-branch delay slot with the
 * `bra` (branch-in-delay-slot) instead of `bf.s` + explicit `nop`; no
 * 3.4.6 flag reproduces the ROM's scheduling here.
 */
#include <stdint.h>

unsigned charging_status(uint8_t a, uint8_t b)
{
    register uint8_t v __asm__("r5") = b;
    register unsigned r __asm__("r4");
    if (v == 0) r = 0; else r = 1;
    return r;
}
