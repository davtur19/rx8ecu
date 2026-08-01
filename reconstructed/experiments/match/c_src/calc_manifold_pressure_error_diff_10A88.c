/*
 * calc_manifold_pressure_error_diff_10A88 — ROM 0x10A88 (22 B body; pools non-contig).
 *   mov.l @(pc),r2 ; 0xFFE20000 (=-1964032) / mov r5,r3 / sub r4,r3 / mov r3,r4
 *   / cmp/gt r2,r4 / bt/s .R / nop / mov.l @(pc),r1 ; 0x168 / add r1,r4 / rts / mov r4,r0
 * Semantics:  int d = b - a;  return d > C1 ? d : d + C2;
 *   C1 = 0xFFE20000 (-1964032), C2 = 0x168 (360).
 */
#include <stdint.h>

int calc_manifold_pressure_error_diff(int a, int b)
{
    register int d __asm__("r4");
    register int c1 __asm__("r2");
    register int c2 __asm__("r1");
    c1 = 0xFFE20000;  /* as int32 = -1964032 */
    c2 = 0x168;
    d = b - a;
    if (d > c1) return d;
    return d + c2;
}
