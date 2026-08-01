/*
 * add16bitSaturate — idiomatic C for ROM 0x2460 (24 bytes).
 *
 * ROM disassembly (see rom_hex/add16bitSaturate_2460.txt):
 *   extu.w r4,r4      ; (uint16)add1
 *   extu.w r5,r5      ; (uint16)add2
 *   add    r5,r4
 *   mov.l  @(pc),r5   ; 0x0000FFFF   (literal pool)
 *   cmp/hs r5,r4      ; T = (sum >= 0xFFFF)  unsigned
 *   bf/s   .ret
 *   nop
 *   mov    r5,r4      ; clamp to 0xFFFF
 * .ret: rts
 *   mov    r4,r0
 *
 * The `extu.w` zero-extensions and the mov.l literal load are exactly the
 * codegen a SH-2 GCC emits for unsigned-short operands compared against a
 * constant that does not fit in `mov #imm`/`mov.w` (0xFFFF > 32767).
 */
#include <stdint.h>

uint16_t add16bitSaturate(uint16_t add1, uint16_t add2)
{
    unsigned sum = (unsigned)add1 + (unsigned)add2;
    return sum >= 0xFFFFu ? (uint16_t)0xFFFFu : (uint16_t)sum;
}
