/*
 * complement_shift_u16.c  —  RX-8 PCM value/complement pack for 16-bit (0x2430)
 *
 * Packs a 16-bit value together with its ones' complement into a 32-bit word.
 * This is the 16-bit sibling of encode() (0x2420, 8-bit) and sits in the
 * redundant-storage family (value + ~value) used to detect memory corruption
 * in calibration tables and safety-critical variables.
 *
 * SH-2E asm:
 *   0x2430:  extu.w  r4,r3       ; val  = r4 & 0xFFFF        (16-bit)
 *   0x2432:  shll16  r3          ; val  = val << 16          (shift to upper half)
 *   0x2434:  not     r4,r2       ; comp = ~r4                (bitwise complement)
 *   0x2436:  extu.w  r2,r2       ; comp = comp & 0xFFFF
 *   0x2438:  mov     r3,r4       ;
 *   0x243A:  add     r2,r4       ; r4   = val + comp
 *   0x243C:  rts                 ; return r0 = r4
 *   0x243E:  mov     r4,r0       ;
 *
 * C equivalent: ((uint32_t)(val & 0xFFFF) << 16) | (uint32_t)(~val & 0xFFFF)
 * (ADD is equivalent to OR here because comp has zeros in the upper 16 bits.)
 *
 * Track A: verified behavior-equivalent to emulated ROM over
 * 100000 random uint16_t inputs.  Test: c/tests/test_complement_shift_u16.py.
 */
#include <stdint.h>

/* 0x2430  pack a 16-bit value with its complement into a 32-bit word          */
uint32_t complement_shift_u16(uint16_t val)
{
    uint32_t shifted = (uint32_t)(val) << 16;
    uint32_t comp    = (uint32_t)(~val) & 0xFFFFu;
    return shifted | comp;
}
