/*
 * =============================================================================
 * rx8_set_register_reg_bit_val.c  —  BITWISE 16-BIT REGISTER MODIFIER
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x4BBC
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_set_register_reg_bit_val.py
 *               (host-gcc vs tools/sh2emu.py over 20000 random + edge vectors,
 *               RAM side-effects compared; 0 mismatches).
 * Lift (truth): c/setRegister_REG_BIT_VAL.c  (setRegister_REG_BIT_VAL @ 0x4BBC)
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * A tiny set-or-clear-bits primitive for 16-bit memory-mapped control
 * registers (I/O ports, timer control, interrupt masks).  Called from 39
 * sites across the ECU.  The ROM path (disassembly of 60E1D400.bin @ 0x4BBC):
 *
 *     6341   mov.w @r4,r3        ; r3 = *reg          (reg pointer in r4)
 *     666d   extu.w r6,r6        ; enable = (uint16_t)enable
 *     2668   tst   r6,r6         ; T = (enable == 0)
 *     8b03   bf    0x4BCC        ; enable != 0  -> 'set' path
 *     6557   not   r5,r5         ; mask = ~mask
 *     2359   and   r5,r3         ; *reg &= ~mask      (clear bits)
 *     000b   rts                 ; return
 *     2431   mov.w r3,@r4        ;   (delay slot) *reg = r3
 *     235b   or    r5,r3         ; *reg |= mask       (set bits)
 *     2431   mov.w r3,@r4        ; *reg = r3
 *     000b   rts                 ; return
 *     0009   nop                 ;   (delay slot)
 *
 * CALLING CONVENTION
 * ------------------
 * Standard SH-2 ABI: r4 = register pointer (uint16_t *), r5 = mask (bits to
 * modify), r6 = enable flag (0 = clear, non-zero = set); no return value.
 * The result is written back through r4, so the function has a RAM side
 * effect (the harness compares the modified 16-bit word, not a return reg).
 *
 * FP/INT EXACTNESS NOTES
 * ----------------------
 * One behavioural detail is not explicit in the lift's C: the `extu.w r6,r6`
 * truncates the enable flag to 16 bits BEFORE the tst/bf.  The lift
 * (c/setRegister_REG_BIT_VAL.c) only ever exercised enable in {0,1}; a
 * 32-bit caller value with any bit >= 16 set (e.g. 0x10000) would take the
 * CLEAR path in the ROM, while a plain `if (enable)` in C would take the
 * set path.  The reconstructed C below replicates the truncation exactly.
 * Everything else is a clean port of the lift, which was verified against
 * 100000 random inputs (see c/tests/test_setRegister_REG_BIT_VAL.py).
 * =============================================================================
 */
#include <stdint.h>

/* 0x4BBC  set or clear mask bits in a 16-bit register                        */
void rx8_set_register_reg_bit_val(uint16_t *reg, uint16_t mask, int enable)
{
    uint16_t tmp = *reg;

    /* 666d extu.w r6,r6 — the ROM zero-extends r6 to 16 bits before the
     * tst; only the low 16 bits of the enable flag decide set-vs-clear. */
    enable &= 0xFFFF;

    if (enable) {               /* tst r6,r6 / bf -> 'set' path             */
        tmp |= mask;            /* set bits                                 */
    } else {                    /* 'clear' path                             */
        tmp &= ~mask;           /* clear bits                               */
    }
    *reg = tmp;
}
