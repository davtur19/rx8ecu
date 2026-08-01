/*
 * alignment_boundary_validator_D90C — ROM 0xD90C (38 bytes, no pool).
 *   mov #3,r7 / mov r4,r3 / tst r7,r3 / bf/s L1 / mov #0,r6
 *   / cmp/hi r5,r4 / bt/s L1 / nop / mov r5,r0 / and r7,r0 / cmp/eq #3,r0
 *   / bt/s L2 / nop / cmp/eq r5,r4 / bt/s L2 / nop / L1: mov #1,r6
 *   / L2: rts / mov r6,r0
 * Semantics (a=r4, b=r5):
 *   if ((a&3)!=0) return 1;
 *   if (a > b)    return 1;
 *   if ((b&3)==3) return r6;   (r6 = 3rd arg! edge cases pass through)
 *   if (a == b)   return r6;
 *   return 1;
 * Approximated C used for the sweep — expected to be a NEAR-miss (r6 passthrough).
 */
#include <stdint.h>

unsigned alignment_boundary_validator(unsigned a, unsigned b, unsigned c)
{
    register unsigned v __asm__("r6") = c;
    if ((a & 3) != 0) return 1;
    if (a > b) return 1;
    if ((b & 3) == 3) return v;
    if (a == b) return v;
    return 1;
}
