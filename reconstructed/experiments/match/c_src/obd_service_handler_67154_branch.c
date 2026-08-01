/*
 * obd_service_handler_67154_branch.c — best-effort branch variant for ROM 0x67154.
 *
 * ROM:
 *   extu.b r4,r0 / tst #31,r0 / bf.s .L / nop / bra .R / mov #0,r4
 *   / mov #1,r4 / rts / mov r4,r0
 *
 * Best result with GCC 3.4.6 (66.7% byte; branch structure/registers match,
 * tail `bra;mov#0;mov#1;rts;mov r4,r0` byte-identical):
 *   xgcc -B ... -m2e -O1 -fomit-frame-pointer -fno-if-conversion
 *        -fno-if-conversion2
 *
 * Residual diffs vs ROM:
 *   1. `mov r4,r0 / and #31,r0 / tst r0,r0` instead of `extu.b r4,r0 /
 *      tst #31,r0` (gcc 3.4.6 materialises the AND instead of folding to
 *      the `tst #imm,r0` pattern that exists in sh.md but is never selected
 *      here);
 *   2. `bf`+`bra`-in-delay-slot vs `bf.s`+`nop` (same structural divergence
 *      as charging_status).
 */
#include <stdint.h>

unsigned obd_service_handler_67154(uint8_t a)
{
    register unsigned r __asm__("r4");
    if ((a & 31) == 0) r = 0; else r = 1;
    return r;
}
