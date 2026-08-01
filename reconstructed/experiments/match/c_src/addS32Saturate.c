/*
 * addS32Saturate — idiomatic C for ROM 0x2304 (20 bytes).
 *
 * ROM disassembly (see rom_hex/addS32Saturate_2304.txt):
 *   addv   r4,r5         ; r5 = r4+r5; T = signed overflow
 *   bf/s   .ret          ; no overflow -> return wrapped sum
 *   mov    r5,r0         ;   (delay slot)
 *   mov.l  @(pc),r0      ; 0x7FFFFFFF
 *   cmp/pz r5            ; T = (wrapped sum >= 0)
 *   mov    #0,r5
 *   addc   r5,r0         ; r0 = 0x7FFFFFFF + T
 * .ret: rts
 *   nop
 *
 * KEY POINT for the match experiment: the ROM uses `addv`, the SH-2
 * signed-overflow-detect add.  Plain GCC for SH-2 only emits `addv` via
 * __builtin_add_overflow (GCC 5+) or -ftrapv; a 2002-era GCC does not emit
 * it for idiomatic saturating C.  This function is therefore expected to be
 * a NON-match for plain idiomatic C — likely hand-written asm or a vendor
 * intrinsic (see REPORT.md §5).
 */
#include <stdint.h>

int32_t addS32Saturate(int32_t a, int32_t b)
{
    int64_t s = (int64_t)a + (int64_t)b;
    if (s > 0x7FFFFFFF) return 0x7FFFFFFF;
    if (s < -0x80000000LL) return (int32_t)0x80000000;
    return (int32_t)s;
}
