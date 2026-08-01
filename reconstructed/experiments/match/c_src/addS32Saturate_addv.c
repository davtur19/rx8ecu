/*
 * addS32Saturate_addv — variant for the GCC 3.4.6 sweep (see scripts/sweep_gcc346.py).
 *
 * Tests whether forcing the SH `addv` (signed-overflow add) via inline asm
 * makes GCC 3.4.6 emit the ROM's structure at 0x2304:
 *     addv r4,r5 / bf/s .ret / mov r5,r0 / mov.l @(pc),r0 / cmp/pz r5
 *     / mov #0,r5 / addc r5,r0 / rts / nop
 *
 * GCC 3.4.6 has NO pure-C construct that emits `addv` (no
 * __builtin_add_overflow; -ftrapv calls a library routine; the 64-bit
 * formulation expands to 64-bit add/compare).  Even with the inline asm the
 * surrounding code differs structurally: gcc materialises the T flag with
 * `movt` and `tst` instead of branching on it directly (`bf/s`), and adds the
 * constant with `subc/sub` instead of the ROM's `mov #0,r5; addc r5,r0`.
 */
#include <stdint.h>

int32_t addS32Saturate(int32_t a, int32_t b)
{
    int32_t s = a;
    unsigned t;
    __asm__ __volatile__("addv %1,%0\n\tmovt %2" : "+r"(s), "=r"(t) : "r"(b) : "t");
    if (t) return s >= 0 ? 0x7FFFFFFF : (int32_t)0x80000000;
    return s;
}
