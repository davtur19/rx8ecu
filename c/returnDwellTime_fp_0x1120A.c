/* returnDwellTime_fp_0x1120A.c
 *
 * ROM: 60E1D400  |  Address: 0x1120A  |  Size: 0xE bytes (0x1120A..0x11218)
 *       next function outputPerRotorIgnitionDwell @0x11218; literal pool
 *       @0x1125C (value 0xFFFFA0D4).
 *       VERIFIED vs ROM emulator (c/tests/test_returnDwellTime_fp_0x1120A.py).
 *
 * Tiny leaf: returns the already-computed ignition dwell value scaled by 16.
 *   r3 = literal 0xFFFFA0D4            (u16 RAM dwell value, written upstream)
 *   r4 = (u32)(*(volatile u16*)0xFFFFA0D4)   -- zero-extended
 *   r4 = r4 << 2;  r0 = r4 << 2         (two shll2 => *16)
 *
 * SOURCE OF THE VALUE: upstream (0x94C8 pipeline) writes the dwell period to
 * RAM u16 @0xFFFFA0D4 (and 0xFFFFA0D6).  This leaf only READS it, extends to
 * unsigned 32-bit and returns `value * 16` in r0.
 *
 * SEMANTICS: integer "fixed-point" scale, NOT a float.  Despite the "_fp"
 * suffix the code returns a plain u32 in r0 (no FPU instruction, no float
 * literal).  Unit: dwell time stored as u16, scaled *16.  No frequency is read
 * in this leaf — the coil-output dispatcher (FUN @0x11010, dispatch site
 * 0x110D8..0x110DC) adds this scaled result to outputPerRotorIgnitionDwell
 * (0x11218) before its own fixed-point math, so the *16 is a fixed-point to
 * ticks adjustment handled entirely by the caller.
 *
 * NOTE (docs cross-check): docs/notes/ECU.md lists 0xFFFFA0D4 as "ETB
 * commanded throttle angle".  The coil-ignition dispatcher here consumes
 * 0xFFFFA0D4 as an input to the dwell adder, which is inconsistent with that
 * label; the value read at 0x94C8..0x94F2 is written to 0xFFFFA0D4/0xFFFFA0D6
 * by an accumulator (saturating add with carry into A0D6), i.e. a running dwclks
 * period, supporting the dwell interpretation for this leaf.
 *
 * Graph: this is a pure read → return, no writes, no callees.  Full-RAM diff
 * trivially passes; the meaningful check is the returned r0.
 *
 * Verified: 100000 random inputs x 5 seeds (500000 total) vs the ROM emulator
 * on the return value r0, 0 mismatches.
 */
#include <stdint.h>

#define RAM_A0D4 (*(volatile uint16_t *)0xFFFFA0D4) /* u16 dwell (fixed-point) input */

uint32_t returnDwellTime_fp_0x1120A(void)
{
    uint32_t v = RAM_A0D4;          /* mov.w @r3,r4 ; extu.w r4,r4 */
    return v << 2 << 2;             /* shll2 r4 ; shll2 r4 */   /* *16 */
}