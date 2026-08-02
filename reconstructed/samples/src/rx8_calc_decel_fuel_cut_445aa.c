/*
 * =============================================================================
 * rx8_calc_decel_fuel_cut_445aa.c  —  DECELERATION FUEL CUT (THROTTLE LIFT)
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x445AA  (234 bytes, 0x445AA..0x44694)
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_calc_decel_fuel_cut_445aa.py
 *               (host-gcc vs tools/sh2emu.py over edge + random vectors;
 *               byte-exact outputs at RAM[0xFFFFCAB5] and RAM[0xFFFFCAAC],
 *               0 mismatches).
 * Lift (truth): c/calc_decel_fuel_cut_445AA.c (same address) — cross-checked
 *               instruction-for-instruction against the 60E1D400.bin
 *               disassembly (src/60E1D400_annotated.s @0x445AA) during this
 *               lift; NO discrepancy found (the lift's own NOTES already
 *               document the historical inaccuracies that were fixed inside
 *               the lift itself — all confirmed correct here).
 *
 * WHAT THE FUNCTION DOES
 * ----------------------
 * Deceleration fuel cut on throttle lift.  When the driver lifts off the
 * throttle at speed, fuel injection is temporarily suspended (fuel-cut flag =
 * 1) to improve economy and reduce emissions.  The cut is gated by
 * calibration/override flags and by a hysteresis accumulator that prevents
 * rapid toggling at the threshold boundary.
 *
 *   th    = RAM[0xFFFFCA30] (f32)  throttle position
 *   spd   = RAM[0xFFFFCA38] (f32)  engine speed / over-run input
 *   thr88 = RAM[0xFFFFCA88] (f32)  throttle-position threshold
 *
 *   fuel_cut = 0
 *   if override == 1 or (den == 1 and f_en == 1):   -> 0   (0x445D8 / 0x4466A)
 *   elif mode != 1:                                  -> 0   (0x44608 -> 0x44668)
 *   elif tclosed > spd:                              -> 0   (0x44614: fcmp/gt)
 *   else:
 *       caldec = 1 if (cdis != 0 or cab8 == 1) else 0
 *       fuel_cut = caldec iff
 *           (th >= thr88 and acc == 0) or (th >= t50 and acc > 0)
 *       else fuel_cut = 0
 *
 *   RAM[0xFFFFCAB5] = fuel_cut
 *   RAM[0xFFFFCAAC] = (sc == 0)            -> 0
 *                   = (fuel_cut == 1)      -> min(acc + 1, 255)   (0x2478)
 *                   = otherwise            -> unchanged
 *
 * All ">=" are IEEE: !(b > a).  NaN inputs therefore compare "passed"
 * (fcmp/gt clears T on unordered), matching the emulator.
 *
 * CALLING CONVENTION / CALLEES
 * ----------------------------
 * `void rx8_calc_decel_fuel_cut_445aa(void)` — no ABI arguments, no ABI
 * return value; the whole effect is the two RAM byte writes above.  The ROM
 * internally jsr's ONE non-ABI leaf whose REAL ROM bytes the emulator harness
 * executes:
 *
 *   - addSaturate8Bit  @0x2478  (r4 = a, r5 = b; returns min(a+b, 255) in r0).
 *     Inlined here as the static rx8_add_saturate_8bit_2478() so this sample
 *     stays self-contained (the oracle build links only this file + its
 *     oracle), exactly like the 0x2440/0x2404 leaves inlined in
 *     rx8_calc_intake_pressure_pid_output.c.  The ROM calls it once, with
 *     a = [0xFFFFCAAC] and b = 1 hard-coded.
 *
 * FP EXACTNESS
 * ------------
 * The function performs NO FP arithmetic: the three floats are only compared
 * with SH-2E `fcmp/gt` (T = (FRn > FRm), cleared on unordered), which is the
 * plain IEEE-754 `>` that C `float > float` already performs on the host.
 * The float inputs therefore need no rounding/byte-assembly work beyond the
 * bit-exact seed (big-endian numeric value -> memcpy into a host float).
 *
 * RAM FOOTPRINT
 * -------------
 *   Read:
 *     0xFFFFCA30  f32  throttle position               (fr4 = f32[CA30])
 *     0xFFFFCABB  u8   override flag                   (==1 -> force no cut)
 *     0xFFFFCAB9  u8   decel-fuel-cut enable           (den)
 *     0xFFFFCAB4  u8   fuel-cut mode                   (must be 1 to decide)
 *     0xFFFFCA38  f32  engine speed / over-run input   (spd)
 *     0xFFFFCA88  f32  throttle-position threshold     (thr88)
 *     0xFFFFCAAC  u8   hysteresis accumulator          (in/out)
 *     0xFFFFCAB8  u8   decel permission flag #2        (cab8)
 *     0xFFFFCAB6  u8   secondary-cut flag              (sc)
 *   Write:
 *     0xFFFFCAB5  u8   fuel-cut flag (1 = cut, 0 = normal)
 *     0xFFFFCAAC  u8   hysteresis accumulator (see the rules above)
 *
 *   Calibration (ROM constants, confirmed in 60E1D400.bin; the harness
 *   asserts these stock values and ships them inline so both sides read
 *   byte-identical constants):
 *     0x0007B3DC  u8   feature enable   (f_en   = 0x01)
 *     0x0007B3DD  u8   feature disable  (cdis   = 0x00; != 0 enables cutting)
 *     0x0007B418  f32  "throttle closed" / min speed threshold (tclosed = 0.01)
 *     0x0007B41C  f32  secondary RPM threshold                   (t50 = 50.0)
 * =============================================================================
 */
#include <stdint.h>
#include "rx8_samples.h"

/* ---- RAM map (all addresses verified against the 0x4468E literal pool:
 *      L_0445ee=0xCA30, L_0445f4=0xCAB5, L_0445f6=0xCABB, L_0445f8=0xCAB9,
 *      L_0446e0=0xCAB4, L_0446e2=0xCA38, L_0446e4=0xCA88, L_0446e6=0xCAAC,
 *      L_0446e8=0xCAB8, L_0446ea=0xCAB6) ---- */
#define RAM_THROTTLE_POS     (*(volatile float   *)0xFFFFCA30u)  /* f32 throttle */
#define RAM_SPEED            (*(volatile float   *)0xFFFFCA38u)  /* f32 speed    */
#define RAM_THR_THRESHOLD    (*(volatile float   *)0xFFFFCA88u)  /* f32 thr88    */
#define RAM_OVERRIDE         (*(volatile uint8_t *)0xFFFFCABBu)  /* u8 override  */
#define RAM_DECEL_ENABLE     (*(volatile uint8_t *)0xFFFFCAB9u)  /* u8 den       */
#define RAM_FUEL_CUT_MODE    (*(volatile uint8_t *)0xFFFFCAB4u)  /* u8 mode      */
#define RAM_ACCUM            (*(volatile uint8_t *)0xFFFFCAACu)  /* u8 acc (io)  */
#define RAM_DECEL_PERM       (*(volatile uint8_t *)0xFFFFCAB8u)  /* u8 cab8      */
#define RAM_SECONDARY_CUT    (*(volatile uint8_t *)0xFFFFCAB6u)  /* u8 sc        */
#define RAM_FUEL_CUT_FLAG    (*(volatile uint8_t *)0xFFFFCAB5u)  /* u8 output    */

/* ---- Calibration constants (real ROM values; the harness asserts these and
 *      the oracle seeds its MAP_FIXED ROM page with the same bytes) ---- */
#define CAL_FEATURE_ENABLE   (*(const uint8_t *)0x0007B3DCu)  /* f_en  = 0x01 */
#define CAL_FEATURE_DISABLE  (*(const uint8_t *)0x0007B3DDu)  /* cdis  = 0x00 */
#define CAL_THROTTLE_CLOSED  (*(const float   *)0x0007B418u)  /* tclosed = 0.01f */
#define CAL_RPM_THRESHOLD_2  (*(const float   *)0x0007B41Cu)  /* t50    = 50.0f  */

/* 0x2478 — addSaturate8Bit (leaf, called once via jsr with b = 1).
 *
 * ROM (c/addSaturate8Bit.c):
 *     extu.b r4,r4          ; add1 = (uint8)add1
 *     extu.b r5,r5          ; add2 = (uint8)add2
 *     add    r5,r4          ; r4 = add1 + add2        (0..510)
 *     extu.w r4,r3          ; r3 = r4
 *     mov.w  @(pc),r5       ; r5 = 255
 *     cmp/ge r5,r3          ; T = (r3 >= 255)
 *     bf/s   .ret
 *     nop
 *     mov    r5,r4          ; r4 = 255                (clamp)
 * .ret:
 *     rts    / mov r4,r0    ; return r4
 *
 * Semantics: saturating unsigned 8-bit add — min(add1 + add2, 255). */
static uint8_t rx8_add_saturate_8bit_2478(uint8_t add1, uint8_t add2)
{
    unsigned sum = (unsigned)add1 + (unsigned)add2;
    return sum >= 255u ? (uint8_t)255u : (uint8_t)sum;
}

/* 0x445AA — deceleration fuel cut on throttle lift (void; results are the two
 * RAM byte writes).  Control flow mirrors the disassembly exactly: every
 * threshold test is `fcmp/gt` in the ROM, so each is written as `!(b > a)`
 * / `>` to reproduce the IEEE-754 semantics including unordered (NaN) ->
 * condition false. */
void rx8_calc_decel_fuel_cut_445aa(void)
{
    float   th    = RAM_THROTTLE_POS;    /* fr4 = f32[CA30] */
    float   spd   = RAM_SPEED;           /* fr2 = f32[CA38] */
    float   thr88 = RAM_THR_THRESHOLD;   /* fr1 = f32[CA88] */
    uint8_t acc   = RAM_ACCUM;           /* [CAAC] */
    uint8_t fuel_cut = 0;
    uint8_t caldec;

    /* ---- Gating: override / decel-enable+feature-enable (0x445BC..0x445DA) */
    if (RAM_OVERRIDE == 1 ||
        (RAM_DECEL_ENABLE == 1 && CAL_FEATURE_ENABLE == 1)) {
        fuel_cut = 0;                                   /* 0x445D8 */
    } else if (RAM_FUEL_CUT_MODE != 1) {                /* 0x44608 */
        fuel_cut = 0;                                   /* 0x44668 */
    } else if (CAL_THROTTLE_CLOSED > spd) {             /* 0x4461C fcmp/gt */
        fuel_cut = 0;                                   /* 0x44668 */
    } else {
        /* ---- Throttle-lift condition passed: compute the cut gate.
         * fuel_cut = caldec iff
         *   (NOT(thr88 > th) && acc == 0)          (0x44626 -> 0x4464C)
         *   OR (NOT(t50 > th) && acc > 0)          (0x4463A -> 0x4464C) */
        caldec = (CAL_FEATURE_DISABLE != 0 || RAM_DECEL_PERM == 1) ? 1 : 0;
        if (((!(thr88 > th) && acc == 0) ||
             (!(CAL_RPM_THRESHOLD_2 > th) && acc > 0))) {
            fuel_cut = caldec;                          /* 0x4464C -> 0x44662 */
        } else {
            fuel_cut = 0;                               /* 0x44668 */
        }
    }

    RAM_FUEL_CUT_FLAG = fuel_cut;                       /* [CAB5] */

    /* ---- Hysteresis accumulator (0x4466A onwards) ---- */
    if (RAM_SECONDARY_CUT == 0) {
        RAM_ACCUM = 0;                                  /* 0x44676 (r5 == 0) */
    } else if (fuel_cut == 1) {
        RAM_ACCUM = rx8_add_saturate_8bit_2478(acc, 1); /* 0x44688: jsr 0x2478 */
    }
    /* else: [CAAC] unchanged */
}
