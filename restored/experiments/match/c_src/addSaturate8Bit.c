/*
 * addSaturate8Bit — idiomatic C for ROM 0x2478 (22 bytes).
 *
 * ROM disassembly (see rom_hex/addSaturate8Bit_2478.txt):
 *   extu.b r4,r4      ; (uint8)add1
 *   extu.b r5,r5      ; (uint8)add2
 *   add    r5,r4
 *   extu.w r4,r3      ; sum zero-extended to 16 bits (value 0..510)
 *   mov.w  @(pc),r5   ; 0x00FF        (literal, 16-bit load)
 *   cmp/ge r5,r3      ; T = (sum >= 255)   SIGNED compare
 *   bf/s   .ret
 *   nop
 *   mov    r5,r4      ; clamp to 255
 * .ret: rts
 *   mov    r4,r0
 *
 * Note: cmp/ge (signed) rather than cmp/hs (unsigned) implies the compiler
 * knew the value was non-negative (extu.w) and used the signed compare;
 * the `mov.w @(pc)` load is what SH-2 GCC emits for a 16-bit constant that
 * does not fit in `mov #imm` (255 > 127).
 */
#include <stdint.h>

uint8_t addSaturate8Bit(uint8_t add1, uint8_t add2)
{
    unsigned sum = (unsigned)add1 + (unsigned)add2;
    return sum >= 255u ? (uint8_t)255u : (uint8_t)sum;
}
