/* calc_decel_fuel_cut_445AA.c
 *
 * ROM: 60E1D400  |  Address: 0x445AA  |  Size: 234 bytes (0x445AA-0x44694)
 *
 * Deceleration fuel cut on throttle lift.
 * Function name from ghidra-hand-xmap in src/60E1D400_annotated.s.
 *
 * When the driver lifts off the throttle at speed, fuel injection is
 * temporarily suspended (fuel-cut flag = 1) to improve economy and reduce
 * emissions.  The fuel cut is gated by calibration/override flags and by a
 * hysteresis accumulator that prevents rapid toggling at the threshold
 * boundary.
 *
 * This is a BEHAVIORAL C model of the disassembly.  The ROM operates on
 * global RAM; every RAM / calibration address below is read exactly as in
 * the real code.  The model is verified against the actual ROM bytes via the
 * SH-2E emulator differential test c/tests/test_calc_decel_fuel_cut_445AA.py
 * (84,880 inputs, 0 mismatches).
 *
 * RAM footprint (from the disasm):
 *
 *   Read:
 *     0xFFFFCA30  f32   throttle position                  (fr4 = f32[CA30])
 *     0xFFFFCABB  u8    override flag                      (==1 -> force no cut)
 *     0xFFFFCAB9  u8    decel-fuel-cut enable              (den)
 *     0xFFFFCAB4  u8    fuel-cut mode                      (must be 1 to decide)
 *     0xFFFFCA38  f32   engine speed / over-run input      (spd)
 *     0xFFFFCA88  f32   throttle-position threshold        (thr88)
 *     0xFFFFCAAC  u8    accumulator, hysteresis            (in/out)
 *     0xFFFFCAB8  u8    decel enable #2 (cut permission)   (cab8)
 *     0xFFFFCAB6  u8    secondary-cut flag                 (sc)
 *     0x0007B3DC  u8    cal: feature enable                (f_en  = 0x01)
 *     0x0007B3DD  u8    cal: feature disable               (cdis  = 0x00)
 *     0x0007B418  f32   cal: "throttle closed" threshold   (tclosed = 0.01f)
 *     0x0007B41C  f32   cal: secondary RPM threshold       (t50    = 50.0f)
 *
 *   Write:
 *     0xFFFFCAB5  u8    fuel-cut flag (1 = cut, 0 = normal)
 *     0xFFFFCAAC  u8    accumulator:
 *                         sc == 0     -> 0
 *                         fuel_cut==1 -> min(acc+1, 255)   (addSaturate8Bit @0x2478)
 *                         else        -> unchanged
 */

#include <stdint.h>

/* ========================================================================
 * RAM variables
 * ======================================================================== */

#define RAM_THROTTLE_POS      (*(volatile float *)0xFFFFCA30)   /* f32 throttle position */
#define RAM_SPEED             (*(volatile float *)0xFFFFCA38)   /* f32 speed / over-run input */
#define RAM_THR_THRESHOLD     (*(volatile float *)0xFFFFCA88)   /* f32 throttle-position threshold */
#define RAM_OVERRIDE          (*(volatile uint8_t *)0xFFFFCABB) /* override: forces no cut */
#define RAM_DECEL_ENABLE      (*(volatile uint8_t *)0xFFFFCAB9) /* decel fuel cut enable (den) */
#define RAM_FUEL_CUT_MODE     (*(volatile uint8_t *)0xFFFFCAB4) /* fuel cut mode (must be 1) */
#define RAM_ACCUM             (*(volatile uint8_t *)0xFFFFCAAC) /* hysteresis accumulator (in/out) */
#define RAM_DECEL_PERM        (*(volatile uint8_t *)0xFFFFCAB8) /* decel permission flag (cab8) */
#define RAM_SECONDARY_CUT     (*(volatile uint8_t *)0xFFFFCAB6) /* secondary cut flag (sc) */
#define RAM_FUEL_CUT_FLAG     (*(volatile uint8_t *)0xFFFFCAB5) /* output: 1=cut, 0=normal */

/* ========================================================================
 * Calibration ROM constants (confirmed in 60E1D400.bin)
 * ======================================================================== */

#define CAL_FEATURE_ENABLE    (*(const uint8_t *)0x0007B3DC)   /* f_en  = 0x01 */
#define CAL_FEATURE_DISABLE   (*(const uint8_t *)0x0007B3DD)   /* cdis  = 0x00 */
#define CAL_THROTTLE_CLOSED   (*(const float *)0x0007B418)     /* tclosed = 0.01f */
#define CAL_RPM_THRESHOLD_2   (*(const float *)0x0007B41C)     /* t50     = 50.0f */

/* ========================================================================
 * External helpers
 * ======================================================================== */

/* addSaturate8Bit @ 0x2478 — saturating u8 add, returns min(a+b, 255)
 * (c/addSaturate8Bit.c) */
extern uint8_t addSaturate8Bit(uint8_t a, uint8_t b);

/* ========================================================================
 * calc_decel_fuel_cut_445AA
 *
 * Evaluates throttle-lift / over-run conditions and sets the fuel-cut flag.
 *
 * Control flow (from the disasm; note SH-2 fcmp/gt FRm,FRn sets
 * T = (FRn > FRm), and unordered NaN comparisons clear T):
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
 * All ">= " are IEEE: !(b > a).  NaN inputs therefore compare "passed"
 * (fcmp/gt clears T), matching the emulator.
 *
 * Accumulator (0x4466A onwards):
 *   sc == 0          -> [CAAC] = 0
 *   fuel_cut == 1    -> [CAAC] = addSaturate8Bit([CAAC], 1)   // min(acc+1, 255)
 *   else             -> [CAAC] unchanged
 * ======================================================================== */
void calc_decel_fuel_cut_445AA(void)
{
    float th     = RAM_THROTTLE_POS;    /* fr4 = f32[CA30] */
    float spd    = RAM_SPEED;           /* fr2 = f32[CA38] */
    float thr88  = RAM_THR_THRESHOLD;   /* fr1 = f32[CA88] */
    uint8_t acc  = RAM_ACCUM;           /* [CAAC] */
    uint8_t fuel_cut = 0;
    uint8_t caldec;

    /* ---- Gating: override / decel-enable+feature-enable ---- */
    if (RAM_OVERRIDE == 1 ||
        (RAM_DECEL_ENABLE == 1 && CAL_FEATURE_ENABLE == 1)) {
        fuel_cut = 0;                                   /* 0x445D8 */
    } else if (RAM_FUEL_CUT_MODE != 1) {                /* 0x44608 */
        fuel_cut = 0;                                   /* 0x44668 */
    } else if (CAL_THROTTLE_CLOSED > spd) {             /* 0x4461C fcmp/gt */
        fuel_cut = 0;                                   /* 0x44668 */
    } else {
        /* ---- Throttle-lift condition passed: compute the cut gate ---- */
        caldec = (CAL_FEATURE_DISABLE != 0 || RAM_DECEL_PERM == 1) ? 1 : 0;
        if (((!(thr88 > th) && acc == 0) ||             /* th >= thr88, acc==0 */
             (!(CAL_RPM_THRESHOLD_2 > th) && acc > 0))) {  /* th >= t50,  acc>0 */
            fuel_cut = caldec;                          /* 0x4464C -> 0x44662 */
        } else {
            fuel_cut = 0;                               /* 0x44668 */
        }
    }

    RAM_FUEL_CUT_FLAG = fuel_cut;                       /* [CAB5] */

    /* ---- Hysteresis accumulator (0x4466A onwards) ---- */
    if (RAM_SECONDARY_CUT == 0) {
        RAM_ACCUM = 0;                                  /* 0x44676 */
    } else if (fuel_cut == 1) {
        RAM_ACCUM = addSaturate8Bit(acc, 1);            /* 0x44688: jsr 0x2478 */
    }
    /* else: [CAAC] unchanged */
}

/* ========================================================================
 * NOTES:
 *
 * 1. Verified by differential emulator test (c/tests/test_calc_decel_fuel_cut_445AA.py):
 *    84,880 inputs, 0 mismatches vs the real ROM bytes of 60E1D400.bin at 0x445AA.
 *
 * 2. Historical inaccuracies in earlier versions of this lift (now corrected):
 *    - Throttle was read as f32 from 0xFFFFCA2C; the ROM reads f32[0xFFFFCA30]
 *      (mov.w literal 0xCA30, 0x445AE).
 *    - 0xFFFFCA88 is an f32 throttle-position THRESHOLD (fr1 = f32[CA88],
 *      0x44622-0x44624), not the accumulator output byte.
 *    - The accumulator output is written back to 0xFFFFCAAC, not to 0xFFFFCA88,
 *      and addSaturate8Bit is only called when sc != 0 AND fuel_cut == 1
 *      (0x44670-0x4468C), with the second argument hard-coded to 1.
 *    - The fuel-cut decision itself was wrong; the disasm-verified formula is
 *      given in the header block above.
 *
 * 3. IEEE single-precision comparisons: the model preserves the SH-2 fcmp/gt
 *    semantics (T = FRn > FRm, cleared on unordered/NaN) by writing every
 *    threshold check in the "!(b > a)" form.
 *
 * 4. Calibration values read from 60E1D400.bin:
 *    - 0x7B3DC = 0x01  (feature enable)
 *    - 0x7B3DD = 0x00  (feature disable; cdis != 0 enables cutting)
 *    - 0x7B418 = 0.01f ("throttle closed" / minimum speed threshold)
 *    - 0x7B41C = 50.0f (secondary RPM threshold)
 * ======================================================================== */
