/*
 * alignment_boundary_validator_D90C_r6.c — ROM 0xD90C (38 bytes).
 *
 * ROM:
 *   mov #3,r7 / mov r4,r3 / tst r7,r3 / bf.s L1 / mov #0,r6
 *   / cmp/hi r5,r4 / bt/s L1 / nop / mov r5,r0 / and r7,r0 / cmp/eq #3,r0
 *   / bt/s L2 / nop / cmp/eq r5,r4 / bt/s L2 / nop / L1: mov #1,r6
 *   / L2: rts / mov r6,r0
 *
 * This variant:
 *   - mask `m` pinned to r7 (register-register `tst r7,rn` instead of
 *     `and #3,r0; tst r0,r0`);
 *   - return value pinned to r6 (ROM accumulates 0/1 in r6 and returns
 *     `mov r6,r0`);
 *   - if/else-if chain so the branch polarities follow the ROM.
 */
#include <stdint.h>

unsigned alignment_boundary_validator(unsigned a, unsigned b, unsigned c)
{
    register unsigned m __asm__("r7") = 3;
    register unsigned v __asm__("r6") = c;
    register unsigned rv __asm__("r6");
    if ((a & m) != 0) rv = 1;
    else if (a > b) rv = 1;
    else if ((b & m) == m) rv = v;
    else if (a == b) rv = v;
    else rv = 1;
    return rv;
}
