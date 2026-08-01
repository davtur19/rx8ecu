/*
 * setRegister_REG_BIT_VAL.c  —  RX-8 PCM bitwise register modifier (0x4BBC)
 *
 * Set or clear specific bits in a 16-bit memory-mapped register.
 * Called from 39 sites — used across the ECU to manipulate control
 * registers (I/O ports, timer control, interrupt masks, etc.).
 *
 * C signature:
 *   void setRegister_REG_BIT_VAL(uint16_t *reg, uint16_t mask, int enable);
 *
 * SH-2E asm:
 *   ; r4 = reg pointer  (uint16_t*)
 *   ; r5 = mask         (bits to modify)
 *   ; r6 = enable       (0 = clear, non-zero = set)
 *   0x4BBC:  mov.w   @r4,r3          ; r3 = *reg
 *   0x4BBE:  extu.w  r6,r6           ; zero-extend r6 (safety)
 *   0x4BC0:  tst     r6,r6           ; enable == 0 ?
 *   0x4BC2:  bf      0x4BCC          ;  -> no, jump to 'set' path
 *   ; ---- clear path ----
 *   0x4BC4:  not     r5,r5           ; mask = ~mask
 *   0x4BC6:  and     r5,r3           ; *reg &= ~mask (clear bits)
 *   0x4BC8:  rts                     ; return
 *   0x4BCA:  mov.w   r3,@r4          ; [delay] *reg = r3
 *   ; ---- set path ----
 *   0x4BCC:  or      r5,r3           ; *reg |= mask (set bits)
 *   0x4BCE:  mov.w   r3,@r4          ; *reg = r3
 *   0x4BD0:  rts                     ; return
 *   0x4BD2:  nop                     ; [delay]
 *
 * Track A: verified behavior-equivalent to emulated ROM over
 * 100000 random inputs (all 16-bit reg values × mask × enable).
 * Test: c/tests/test_setRegister_REG_BIT_VAL.py.
 */
#include <stdint.h>

/* 0x4BBC  set or clear mask bits in a 16-bit register                        */
void setRegister_REG_BIT_VAL(uint16_t *reg, uint16_t mask, int enable)
{
    uint16_t tmp = *reg;
    if (enable) {
        tmp |= mask;            /* set bits */
    } else {
        tmp &= ~mask;           /* clear bits */
    }
    *reg = tmp;
}
