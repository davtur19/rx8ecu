/*
 * obd_service_handler_67154_m1.c — -m1 -fno-if-conversion variant for ROM
 * 0x67154 (18 B).  Documents the best 3.4.6 result for this boolean.
 *
 * ROM:
 *   extu.b r4,r0 / tst #31,r0 / bf.s .L / nop / bra .R / mov #0,r4
 *   / mov #1,r4 / rts / mov r4,r0
 *
 * Best result (66.7% = 12/18, first diff +0x01):
 *   xgcc -B ... -m1 -O1 -fomit-frame-pointer -fno-if-conversion
 *        -fno-if-conversion2
 *   mov r4,r0 / and #31,r0 / tst r0,r0 / bf .c / bra .e / mov #0,r4
 *   / mov #1,r4 / rts / mov r4,r0
 *
 * Residual structural divergences (no 3.4.6 flag / C rewrite fixes them):
 *   1. `mov r4,r0` instead of `extu.b r4,r0` (gcc keeps QImode param as-is);
 *   2. `and #31,r0; tst r0,r0` instead of the single `tst #31,r0` — GCC 3.4.6
 *      has NO `tst #imm` pattern in sh.md (only register tst);
 *   3. `bf` (no delay) vs ROM `bf.s`+`nop` (delay-slot scheduling).
 */
#include <stdint.h>

unsigned obd_service_handler_67154(uint8_t a)
{
    register unsigned r __asm__("r4");
    if ((a & 31) == 0) r = 0; else r = 1;
    return r;
}
