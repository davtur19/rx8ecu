/* calc_spark_lead_trail_split_19220.c
 *
 * ROM: 60E1D400  |  Address: 0x19220  |  Size: 0x1EE bytes (0x19220..0x19340C)
 *       code 0x19220..0x19342 + 0x19398..0x193F4; literal pools @0x19344..0x19396
 *       and @0x1940E..0x1941E; next function @0x19480.
 *       VERIFIED vs ROM emulator (0 mismatches, c/tests/test_calc_spark_lead_trail_split_19220.py).
 *
 * Leading/trailing spark-advance split calc.  Called from
 * engineControlCalculateTiming @0x14584 (dispatch site 0x147D0).  Old IDA name:
 * "dscRelatedTiming"; ghidra-hand xmap name: "air_temp_comp_multivar_calc" — the
 * xmap name is NOT supported by the lift: no air-temp multi-var path exists; the
 * observable effect is a lead/trail split computation from the u8 selector
 * RAM8@0xFFFFBCEF, plus a min-split clamp.
 *
 * Semantics (execution order):
 *   1. A9A0 (leading timing, f32@0xFFFFA9A0):
 *        sel == 4            -> A9A0 = BD00
 *        else if 0x2440(BCFC, 0, 1e-5) == 0   (|BCFC| <= 1e-5)
 *                            -> A9A0 = -20
 *        else                -> A9A0 = BD00 - 0x46CC(max(X,0)/BCFC) with
 *           base  = (A9B4 > A9B0) ? BB2C : BC40
 *           f     = (BD14 - BCE4 - BD20 - base) * 4/(4 - sel)
 *           X     = BD24 + BD28 + BD04 + f - BD14
 *   2. A9AC (trailing timing, f32@0xFFFFA9AC) by selector:
 *        sel 1 -> 0x2500(0.5, -50, byte@0x6ED98)          = 0.5*b1 - 50
 *        sel 2 -> ThreeDLookup(desc 0x69F14 "TrailingA", x=load, y=RPM)
 *        sel 3 -> 0x2500(0.5, -50, byte@0x6ED99)          = 0.5*b2 - 50
 *        else  -> ThreeDLookup(desc 0x69EF8 "TrailingB", x=load, y=RPM)
 *      (desc x-axis = engine load 0.0625..1.25, y-axis = RPM 500..9000,
 *       u8 cells, result = 0.5*interp - 50; ROM tables, not RAM)
 *   3. minSplit = ThreeDLookup(desc 0x69F30 "MinSplit", x=load, y=RPM)
 *   4. A9A8 = max(A9A0, A9AC)                      (helper 0x23E4, a max)
 *      A9A4 = max(A9A0 + minSplit, A9AC + minSplit)
 *      A9C0 = (A9A0 > A9AC) ? 0 : 1  (1 when lead <= trail; fcmp/gt A9AC,A9A0)
 *
 * Inputs (RAM reads):  B5B8 (RPM f32), C12C (load f32), BCFC (f32), BCEF (u8
 *   selector), BD00/BD04/BD14/BD20/BD24/BD28/BCE4/BC40/BB2C (f32), A9B0/A9B4
 *   (f32, base-select inputs written by a not-yet-lifted predecessor).
 * ROM constants:  byte @0x6ED98 / @0x6ED99 (stock 126), desc 0x69EF8/0x69F14/
 *   0x69F30 (+ axes/cells), f32 1e-5/-20/4/0.5/-50.
 * Outputs (RAM writes): A9A0, A9AC, A9A8, A9A4 (f32), A9C0 (u8); and — only on
 *   the 0x46CC NaN path — RAM32@0xFFFF7304 = 0x044D (NaN fault code).
 *
 * 0x46CC is a software-float helper (frexp@0x48C8 -> 32-bit div @0x4740 ->
 * ldexp@0x481C) that reads stack garbage below the frame.  In the emulator (and
 * on the real ECU's rarely-taken fallback path) that region is 0, so the
 * observable effect is: m==0.0 or m==+-Inf -> 1.0 (no write); any other m ->
 * NaN + RAM32@0xFFFF7304 = 0x044D.  (NOTE: the older c/checkFloatValidity.c
 * pass-through lift does NOT match the emulated 0x46CC for nonzero inputs.)
 *
 * Verified: 100000 random inputs x 5 seeds (500000 total) vs the ROM emulator,
 * 0 mismatches.
 */
#include <stdint.h>
#include <math.h>

#define RAM_RPM      (*(volatile float *)0xFFFFB5B8) /* engine speed */
#define RAM_LOAD     (*(volatile float *)0xFFFFC12C) /* engine load */
#define RAM_BCFC     (*(volatile float *)0xFFFFBCFC)
#define RAM_SEL      (*(volatile uint8_t *)0xFFFFBCEF) /* split selector */

#define RAM_BD00     (*(volatile float *)0xFFFFBD00)
#define RAM_BD04     (*(volatile float *)0xFFFFBD04)
#define RAM_BD14     (*(volatile float *)0xFFFFBD14)
#define RAM_BD20     (*(volatile float *)0xFFFFBD20)
#define RAM_BD24     (*(volatile float *)0xFFFFBD24)
#define RAM_BD28     (*(volatile float *)0xFFFFBD28)
#define RAM_BCE4     (*(volatile float *)0xFFFFBCE4)
#define RAM_BC40     (*(volatile float *)0xFFFFBC40)
#define RAM_BB2C     (*(volatile float *)0xFFFFBB2C)
#define RAM_A9B0     (*(volatile float *)0xFFFFA9B0)
#define RAM_A9B4     (*(volatile float *)0xFFFFA9B4)

#define RAM_A9A0     (*(volatile float *)0xFFFFA9A0) /* leading timing  */
#define RAM_A9AC     (*(volatile float *)0xFFFFA9AC) /* trailing timing */
#define RAM_A9A8     (*(volatile float *)0xFFFFA9A8)
#define RAM_A9A4     (*(volatile float *)0xFFFFA9A4)
#define RAM_A9C0     (*(volatile uint8_t *)0xFFFFA9C0)
#define RAM_7304     (*(volatile uint32_t *)0xFFFF7304) /* NaN/Inf fault code */

#define ROM_6ED98    (*(const uint8_t *)0x0006ED98)   /* trailing case 1 offset byte */
#define ROM_6ED99    (*(const uint8_t *)0x0006ED99)   /* trailing case 3 offset byte */

/* Map2D descriptor layout (28 bytes, big-endian SH-2E) — same as c/3dLookup.c */
typedef struct {
    uint16_t     count_x;
    uint16_t     count_y;
    const float *axis_x;
    const float *axis_y;
    const void  *values;
    uint8_t      type;
    uint8_t      _pad[3];
    float        scale;
    float        offset;
} Map2D;

#define DESC_TRAILING_B  ((const Map2D *)0x69EF8)  /* TrailingB  map */
#define DESC_TRAILING_A  ((const Map2D *)0x69F14)  /* TrailingA  map */
#define DESC_MIN_SPLIT   ((const Map2D *)0x69F30)  /* MinSplit   map */

/* ---- verified leaves ---- */
extern uint32_t complement_shift_u32(float threshold, float value, float adjustment); /* 0x2440 */
extern float    fixedPointToFloat_8bit(float mult, float off, uint8_t raw);            /* 0x2500 */
extern float    ThreeDLookup(const Map2D *m, float x, float y);                        /* 0x20DC */

/* 0x23E4 — shared max helper ("fpu_mul_float" mislabel; returns the larger of the
 * two float args, NaN-comparison -> picks the second arg). */
static float max_0x23E4(float a, float b)
{
    return (a > b) ? a : b;
}

/* 0x46CC — software-float helper (frexp/int-div/ldexp).  Emulator-observable
 * behavior with the stack region below the frame at 0: m==0.0/+-Inf -> 1.0
 * (no side effect); any other m -> NaN + RAM32@0xFFFF7304 = 0x044D. */
static float helper_0x46CC(float m)
{
    if (m == 0.0f || isinf(m))
        return 1.0f;
    RAM_7304 = 0x0000044D;
    return NAN;
}

void calc_spark_lead_trail_split_19220(void)
{
    uint8_t sel = RAM_SEL;
    float   rpm = RAM_RPM;
    float   load = RAM_LOAD;
    float   lead, trail, minsplit;

    /* ---- leading timing A9A0 ---- */
    if (sel == 4) {
        lead = RAM_BD00;
    } else if (complement_shift_u32(RAM_BCFC, 0.0f, 1e-5f) == 0) {
        lead = -20.0f;                      /* |BCFC| <= 1e-5 */
    } else {
        float base = (RAM_A9B4 > RAM_A9B0) ? RAM_BB2C : RAM_BC40;
        float f    = (RAM_BD14 - RAM_BCE4 - RAM_BD20 - base)
                   * (4.0f / (4.0f - (float)sel));
        float X    = RAM_BD24 + RAM_BD28 + RAM_BD04 + f - RAM_BD14;
        float m    = (X > 0.0f ? X : 0.0f) / RAM_BCFC;   /* 0x23E4 max(X,0) */
        lead       = RAM_BD00 - helper_0x46CC(m);
    }
    RAM_A9A0 = lead;

    /* ---- trailing timing A9AC ---- */
    switch (sel) {
    case 1:  trail = fixedPointToFloat_8bit(0.5f, -50.0f, ROM_6ED98); break;
    case 2:  trail = ThreeDLookup(DESC_TRAILING_A, load, rpm);        break;
    case 3:  trail = fixedPointToFloat_8bit(0.5f, -50.0f, ROM_6ED99); break;
    default: trail = ThreeDLookup(DESC_TRAILING_B, load, rpm);        break;
    }
    RAM_A9AC = trail;

    /* ---- minimum split ---- */
    minsplit = ThreeDLookup(DESC_MIN_SPLIT, load, rpm);

    /* ---- clamps ---- */
    RAM_A9A8 = max_0x23E4(lead, trail);                       /* 0x193CC */
    RAM_A9A4 = max_0x23E4(lead + minsplit, trail + minsplit); /* 0x193D6 */

    /* 0x193E4 fcmp/gt A9AC,A9A0: T=(lead>trail); A9C0 = T ? 0 : 1 */
    RAM_A9C0 = (lead > trail) ? 0 : 1;
}
