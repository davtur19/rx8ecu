/*
 * add16bitSaturate_reg — variant for the GCC 3.4.6 sweep (see scripts/sweep_gcc346.py).
 *
 * Same semantics as add16bitSaturate.c but:
 *   - `max` is a VARIABLE (avoids the `sum >= 0xFFFF -> sum > 0xFFFE` fold
 *     that both GCC 14 and GCC 3.4.6 apply to the inline constant; the ROM
 *     uses `cmp/hs` against a single 0xFFFF literal);
 *   - `sum` and `max` are pinned to r4/r5 with the `register ... __asm__`
 *     extension to reproduce the ROM's register allocation (sum stays in r4,
 *     the constant lives in r5, clamp = `mov r5,r4`);
 *   - the return type is `unsigned` so the epilogue is `mov r4,r0` (no
 *     `extu.w r4,r0`), exactly like the ROM.
 *
 * With  -m2e -O1 -fomit-frame-pointer  this compiles byte-identically to
 * ROM 0x2460 (24 bytes): 644d 655d 345c d503 3452 8f01 0009 6453 000b 6043
 * + pool 0000ffff.  Verified by scripts/sweep_gcc346.py.
 */
#include <stdint.h>

unsigned add16bitSaturate(uint16_t add1, uint16_t add2)
{
    register unsigned sum __asm__("r4") = (unsigned)add1 + (unsigned)add2;
    register unsigned max __asm__("r5") = 0xFFFF;
    if (sum >= max) sum = max;
    return sum;
}
