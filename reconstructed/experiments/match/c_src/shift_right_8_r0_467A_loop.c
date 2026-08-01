/*
 * shift_right_8_r0_467A_loop.c — unrolled-shift variant for ROM 0x467A (18 B).
 *
 * ROM:
 *   shar r0 x7 / rts / shar r0   (8x shar r0; arithmetic >> 8 on r0)
 *
 * The ROM is an 8x-unrolled `shar r0` fragment that expects the operand
 * already in r0 (leaf/trampoline fragment).  A normal C function receives
 * the argument in r4, so a single `mov r4,r0` prefix is unavoidable and
 * shifts the whole body by 2 bytes (first byte-diff at +0x00).
 *
 * With  -m2e -O1 -fomit-frame-pointer -funroll-all-loops  (or -funroll-loops
 * / -O2) gcc 3.4.6 emits EXACTLY the ROM's body:
 *   mov r4,r0 / shar r0 x7 / rts / shar r0
 * i.e. the 8 shar instructions + `rts; shar r0` are reproduced; only the
 * ABI-required `mov r4,r0` prologue differs (structural, not flag-fixable).
 */
#include <stdint.h>

int shift_right_8_r0(int a)
{
    register int v __asm__("r0") = a;
    int i;
    for (i = 0; i < 8; i++) v >>= 1;
    return v;
}
