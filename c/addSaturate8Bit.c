/*
 * addSaturate8Bit  —  RX-8 PCM helper @ ROM 0x2478
 *
 * Function name from the hand-annotated Ghidra RE by equinox311 (program 60E0FC00).
 * Byte-identical helper across the family (matched into 60E1D400 by content
 * signature).
 *
 * Original SH-2 (big-endian):
 *     extu.b r4,r4          ; add1 = (uint8)add1
 *     extu.b r5,r5          ; add2 = (uint8)add2
 *     add    r5,r4          ; r4 = add1 + add2        (0..510)
 *     extu.w r4,r3          ; r3 = r4
 *     mov.w  @(pc),r5       ; r5 = 255                (literal @0x248E == 0x00FF)
 *     cmp/ge r5,r3          ; T  = (r3 >= 255)        (signed; r3 is small +ve)
 *     bf/s   .ret           ; if !T skip clamp (delay: nop)
 *     nop
 *     mov    r5,r4          ; r4 = 255                (clamp)
 * .ret:
 *     rts
 *     mov    r4,r0          ; return r4
 *
 * Semantics: saturating unsigned 8-bit add — min(add1 + add2, 255).
 *
 * Track A: verified behavior-equivalent to the emulated ROM (tools/sh2emu.py) over
 * 100k random inputs — see c/tests/verify_emu.py.
 */
#include <stdint.h>

uint8_t addSaturate8Bit(uint8_t add1, uint8_t add2)
{
    unsigned sum = (unsigned)add1 + (unsigned)add2;
    return sum >= 255u ? (uint8_t)255u : (uint8_t)sum;
}
