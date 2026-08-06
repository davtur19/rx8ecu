/* calculateDriverConditions_0x42296.c
 *
 * ROM: 60E0FC00 | Address: 0x42296 | Size: 0x9A (154) bytes per CSV range
 * 0x42296..0x42330.  Straight-line leaf (no prologue/epilogue, no sub-calls).
 * Code runs to the `rts` @0x422F8 (delay nop @0x422FA); the interleaved
 * mov.w literal pool @0x4230A..0x42316 and the two mov.l literals @0x42328/
 * 0x4232C sit inside the CSV range.  The CSV range is CORRECT (the preceding
 * function calculateThrottlePercentDuringLift 0x042230 ends rts @0x42292 +
 * delay nop @0x42294, no fall-through; the next function starts exactly at
 * the CSV end 0x42330, `mov.l r14,@-r15` prologue).  No phantom rows.
 *
 * ENTRY VERIFICATION: 0x42296 matches the symbols CSV start.  Valid entry:
 * opens directly with the first literal loads (leaf with a single RAM store,
 * no register pushes needed).  The ONLY 32-bit ROM reference to 0x42296 is
 * the function-pointer slot @0x14454 inside the engineControlCalculateTiming
 * dispatcher (0x141FC) dispatch table literal pool (adjacent to
 * calculateCrankingTimingLeading @0x1444C / trailing @0x14450).  The
 * preceding function's rts is two instructions before us, no fall-through.
 * CSV address IS the real entry point.
 *
 * SEMANTICS (instruction-for-instruction, see disasm): computes a driver /
 * vehicle-condition gate flag u8@FFFFC947 (1 = condition satisfied).  The
 * name `calculateDriverConditions` is retained — it matches the well-formed
 * sibling calculateDriverConditions_43c4a (ROM 60E1D400) whose skeleton is
 * identical (same gate-byte + f32-threshold + two byte checks + latch into a
 * u8, same instruction sequence opcode-for-opcode, different RAM addrs).
 * Structure:
 *
*   b580 = u8@FFFFB580;  r4 = b580
 *   if b580 == 1 AND u8@FFFFB586 == 0:
 *       out = 1                                    // path 1 (bt @0x422AA)
 *   else:
 *       if f32@FFFFBFBC > f32@0x0007A1D8 (15.0):  // fcmp/gt, NaN -> false
 *           if u8@FFFFC940 != 0 AND u8@FFFFAD7C == 0:
 *               out = 1                            // path 2 (bt @0x422CC)
 *           else: ... -> path-3 gate below
 *       else: ... -> path-3 gate below
 *       if r4 != 0:  out = 0                       // bf @0x422D2 (b580!=0)
 *       elif u8@FFFFC94C == 1 AND u8@0x0007A17C == 1:   // ROM byte const =1
 *           out = 1                                // path 3 (fall @0x422EE)
 *       else:
 *           out = 0                                // bf @0x422F4
 *
 * i.e. out = (b580==1 && b586==0) || (f32@BFBC > 15.0 && c940!=0 &&
 *            ad7c==0) || (b580==0 && c94c==1 && rombyte@7A17C==1).
 *
 * NOTE (fcmp operand order): the SH-2E `fcmp/gt fr3,fr2` instruction sets
 * T = (FR2 > FR3).  Fr2 holds f32@FFFFBFBC, fr3 the ROM constant
 * f32@0x7A1D8 = 15.0 (verified against the emulator's fcmp: T = f[n]=BFBC
 * > f[m]=15.0).  NaN BFBC -> T=0 -> falls to the path-3 gate.
 *
 * NOTE (fcmp operand order): the SH-2E `fcmp/gt fr3,fr2` instruction sets
 * T = (FR2 > FR3).  Fr2 holds f32@FFFFBFBC, fr3 holds the ROM constant
 * f32@0x7A1D8 = 15.0 (verified against the emulator's fcmp implementation:
 * T = f[n=2] > f[m=3]).  On NaN the comparison is false (T=0), so NaN BFBC
 * falls straight to the path-3 gate, matching the emulator byte-for-byte.
 *
 * ROM constants (verified against roms/stock/60E0FC00.bin):
 *   0x7A1D8 -> f32 15.0   (speed/ratio threshold)
 *   0x7A17C -> u8  1      (always-true enable byte — read, never modified)
 *
 * r0 on return (path-dependent, carried byte-exact by the emulator diff):
 *   path1: u8@B580 & 0xFF  (=1) ; path2: 0xFFFFAD7C (mov.w literal address)
 *   path3: u8@ROM7A17C & 0xFF (=1) ; clear-via-r4: the D0 entry r0 =
 *   0xFFFFBFBC or 0xFFFFAD7C depending on which gate led to D0; clear-via-
 *   c94c: u8@C94C & 0xFF ; clear-via-rombyte: u8@ROM7A17C & 0xFF.
 *
 * RAM r/w: reads u8 FFFFB580, FFFFB586, FFFFC940, FFFFAD7C, FFFFC94C and f32
 *   FFFFBFBC; writes u8@FFFFC947.  ROM reads: f32@0x7A1D8, u8@0x7A17C.
 * No sub-calls.
 *
 * VERIFIED against the SH-2 emulator (tools/sh2emu.py,
 * roms/stock/60E0FC00.bin) in c/tests/test_calculateDriverConditions_0x42296.py —
 * 0 mismatches over 5 seeds x 100000 iterations (byte-exact full post-call
 * RAM overlay + r0).
 */
#include <stdint.h>

/* ---- RAM globals (mov.w literals sign-extend to 0xFFFFxxxx) ---- */
#define G_B580 (*(volatile uint8_t *)0xFFFFB580)  /* u8 condition gate in  */
#define G_B586 (*(volatile uint8_t *)0xFFFFB586)  /* u8 paired gate (==0)  */
#define T_BFBC (*(volatile float   *)0xFFFFBFBC)  /* f32 sampled float     */
#define G_C940 (*(volatile uint8_t *)0xFFFFC940)  /* u8 gate (!=0)         */
#define S_AD7C (*(volatile uint8_t *)0xFFFFAD7C)  /* u8 sys status bit latch */
#define G_C94C (*(volatile uint8_t *)0xFFFFC94C)  /* u8 gate (==1)         */
#define OUT_C947 (*(volatile uint8_t *)0xFFFFC947) /* u8 driver-condition flag */

/* ---- ROM constants ---- */
#define ROM_F_7A1D8 (*(const float *)0x0007A1D8)  /* f32 15.0 threshold   */
#define ROM_B_7A17C (*(const uint8_t *)0x0007A17C) /* u8 enable (==1)      */

void calculateDriverConditions_0x42296(void)
{
    uint8_t b580 = G_B580;
    if (b580 == 1 && G_B586 == 0) {        /* path 1 @0x422AA              */
        OUT_C947 = 1;
    } else {
        if (T_BFBC > ROM_F_7A1D8) {        /* fcmp/gt fr3,fr2 -> BFBC>15.0 */
            if (G_C940 != 0 && S_AD7C == 0) { /* path 2 @0x422CC           */
                OUT_C947 = 1;
                return;
            }
        }
        /* path-3 gate @0x422D0 */
        if (b580 != 0) {                   /* bf @0x422D2                  */
            OUT_C947 = 0;
        } else if (G_C94C == 1 && ROM_B_7A17C == 1) { /* path 3 @0x422EE   */
            OUT_C947 = 1;
        } else {
            OUT_C947 = 0;                  /* @0x422F4                     */
        }
    }
}