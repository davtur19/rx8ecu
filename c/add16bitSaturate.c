/*
 * add16bitSaturate  —  RX-8 PCM helper @ ROM 0x2460
 *
 * Function name from the hand-annotated Ghidra RE by equinox311 (program 60E0FC00):
 * `add16bitSaturate_ADD1_ADD2`. Byte-identical helper in 60E1D400, 60E0FC00, [REDACTED].
 *
 * Original SH-2 (big-endian):
 *     extu.w r4,r4          ; add1 = (uint16)add1   (arg0 in r4)
 *     extu.w r5,r5          ; add2 = (uint16)add2   (arg1 in r5)
 *     add    r5,r4          ; r4 = add1 + add2      (32-bit, no wrap in range)
 *     mov.l  @(pc),r5       ; r5 = 0x0000FFFF       (literal pool @0x2474)
 *     cmp/hs r5,r4          ; T  = (r4 >= 0xFFFF)   (unsigned)
 *     bf/s   .ret           ; if !T skip the clamp (delay slot: nop)
 *     nop
 *     mov    r5,r4          ; r4 = 0xFFFF           (clamp, when r4 >= 0xFFFF)
 * .ret:
 *     rts
 *     mov    r4,r0          ; return r4             (delay slot)
 *
 * Semantics: saturating unsigned 16-bit add — min(add1 + add2, 0xFFFF).
 *
 * Track A (functional decompilation): behavior-equivalent, not byte-identical.
 * Verified against an exact transcription of the instructions above — see
 * c/tests/test_add16bitSaturate.c (edges + 20M random, host-gcc).
 */
#include <stdint.h>

uint16_t add16bitSaturate(uint16_t add1, uint16_t add2)
{
    uint32_t sum = (uint32_t)add1 + (uint32_t)add2;
    return sum >= 0xFFFFu ? (uint16_t)0xFFFFu : (uint16_t)sum;
}
