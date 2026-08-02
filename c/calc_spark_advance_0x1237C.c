/* calc_spark_advance_0x1237C.c
 *
 * ROM: 60E1D400  |  Address: 0x1237C  |  Size: 0x114 bytes (0x1237C..0x12490;
 * 0x12490 starts the literal-pool word for the next function @0x13004).
 * VERIFIED vs ROM emulator (0 mismatches,
 * c/tests/test_calc_spark_advance_0x1237C.py).
 *
 * Called from engineControlCalculateTiming @0x147D4 dispatch
 * (c/engineControlCalculateTiming.c), right after calc_combustion_efficiency
 * _metric and before the knock-control / per-rotor timing group.  Old IDA name
 * "calc_combustion_load_factor" is NOT supported: the ROM performs NO
 * "combustion-load-factor" accumulation; it computes a RESULTANT IGNITION/
 * SPARK ADVANCE (deg) by combining a set of RPM x load (and RPM, and temp)
 * timing maps and cross-blending two candidate advance values by a rotor-sync
 * weight f32@FFFFB188.  Every map that feeds the result is calibrated as
 *   result = scale*cell + offset   (leaves 0x2068/0x20DC)
 * and the observable outputs (0xFFFFA5xx) are all spark-timing degree values.
 *
 * Semantics (execution order):
 *   1. TwoDLookup(desc 0x69A7C, x=f32@0xFFFFA7BC)   -> f32@0xFFFFA624
 *         (6-point RPM map, u8 cells, 0.5*cell - 50)
 *      ThreeDLookup(desc 0x69B14, x=LOAD, y=RPM)    -> f32@0xFFFFA628
 *         (10x7 load x RPM map, u8 cells, 0.5*cell - 50)
 *      TwoDLookup(desc 0x69A90, x=f32@0xFFFFAA10)   -> f32@0xFFFFA634
 *         (9-point table x=-40..120, u8 cells, 0.01*cell)
 *   2. 0xFFFFA5F8 = ROM32@0x6D56C(=0) - (A628 * A634) + A624
 *   3. 0xFFFFA604 = (RAM8@0xFFFFCDA0 == 0) ? ROM32@0x6D570(=80.0) : ROM32@0x6D574(=11)
 *      (lead-advance clamp selected by the CDA0 gate byte)
 *   4. selector RAM8@0xFFFFB19D == 1:
 *        A62C = ThreeDLookup(desc 0x69B4C, LOAD, RPM)   -> r1 = min(A62C, A604)
 *      else:
 *        A62C = ThreeDLookup(desc 0x69B68, LOAD, RPM)   -> r1 = min(A62C, A604)
 *      (both 20x18 load x RPM maps, u8 cells, 0.5*cell - 50)
 *      RAM32@0xFFFFA608 = r1 + ROM32@0x6D57C/0x6D580 (= 0)
 *   5. RAM32@0xFFFFA630 = ThreeDLookup(desc 0x69B30, LOAD, RPM)   (20x18)
 *      RAM32@0xFFFFA638 = ThreeDLookup(desc 0x69B98, x=RPM, y=TEMP) (4x3, type-0)
 *   6. adv = min(A630, A604)
 *      RAM32@0xFFFFA5F0 = max( fma((1-B188), ROM_6D578+adv, B188*A608), A638 )
 *         -- the blend term is a fused fmac fr0,fr1,fr2 (single rounding),
 *            reproduced with fmaf(); RAM_B188 (f32@0xFFFFB188) is the
 *            rotor-sync / trailing weight in ~0..1.
 *
 * Inputs (RAM reads): B5B8 (RPM f32), C12C (load f32), AA10 (f32 map input),
 *   A7BC (f32), B188 (f32 blend weight), gate bytes u8@0xFFFFCDA0 and
 *   u8@0xFFFFB19D.
 * ROM constants: desc 0x69A7C/0x69A90/0x69B14/0x69B4C/0x69B68/0x69B30/0x69B98
 *   (+axes/cells), f32@0x6D56C=0 / 0x6D570=80 / 0x6D574=11 / 0x6D578=0 /
 *   0x6D57C=0 / 0x6D580=0.
 * Outputs (RAM writes): A624, A628, A634, A5F8, A604, A62C, A608, A630, A638,
 *   A5F0 (all f32).
 *
 * 0x23E4 / 0x23F4 are the shared helpers (IDA mislabels them "fpu_mul_float" /
 * "fpu_sqrt_float"): 0x23E4 = max(fr4,fr5), 0x23F4 = min(fr4,fr5).  For a NaN
 * operand fcmp/gt clears T so the "second" float is returned.  These semantics
 * were confirmed directly against the ROM in the test harness.
 *
 * Verified: 100000 random inputs x 5 seeds (500000 total) vs the ROM emulator,
 * 0 mismatches.
 */
#include <stdint.h>
#include <math.h>

/* 1-D lookup descriptor (20 bytes, big-endian SH-2E) — same as c/2DLookup.c */
typedef struct {
    uint16_t     count;    /* +0 */
    uint8_t      type;     /* +2 */
    uint8_t      _pad;     /* +3 */
    const float *axis;     /* +4 */
    const void  *values;   /* +8 */
    float        scale;    /* +12 */
    float        offset;   /* +16 */
} Map1D;

/* 2-D lookup descriptor (28 bytes, big-endian SH-2E) — same as c/3dLookup.c */
typedef struct {
    uint16_t     count_x;  /* +0 */
    uint16_t     count_y;  /* +2 */
    const float *axis_x;   /* +4 */
    const float *axis_y;   /* +8 */
    const void  *values;   /* +12 */
    uint8_t      type;     /* +16 */
    uint8_t      _pad[3];
    float        scale;    /* +20 */
    float        offset;   /* +24 */
} Map2D;

#define RAM_RPM   (*(volatile float *)0xFFFFB5B8)  /* engine speed      */
#define RAM_LOAD  (*(volatile float *)0xFFFFC12C)  /* engine load       */
#define RAM_B188  (*(volatile float *)0xFFFFB188)  /* rotor-sync weight */
#define RAM_TEMP  (*(volatile float *)0xFFFFAA10)  /* map table input   */
#define RAM_A7BC  (*(volatile float *)0xFFFFA7BC)  /* RPM-map x input   */

#define RAM_A624  (*(volatile float *)0xFFFFA624)
#define RAM_A628  (*(volatile float *)0xFFFFA628)
#define RAM_A634  (*(volatile float *)0xFFFFA634)
#define RAM_A5F8  (*(volatile float *)0xFFFFA5F8)
#define RAM_A604  (*(volatile float *)0xFFFFA604)
#define RAM_A62C  (*(volatile float *)0xFFFFA62C)
#define RAM_A608  (*(volatile float *)0xFFFFA608)
#define RAM_A630  (*(volatile float *)0xFFFFA630)
#define RAM_A638  (*(volatile float *)0xFFFFA638)
#define RAM_A5F0  (*(volatile float *)0xFFFFA5F0)

#define RAM_CDA0  (*(volatile uint8_t *)0xFFFFCDA0)  /* clamp-select gate byte */
#define RAM_B19D  (*(volatile uint8_t *)0xFFFFB19D)  /* table-select byte      */

#define DESC_A7C  ((const Map1D *)0x00069A7C)   /* RPM map -> A624 */
#define DESC_A90  ((const Map1D *)0x00069A90)   /* temp map -> A634 */
#define DESC_B14  ((const Map2D *)0x00069B14)   /* load x RPM -> A628 */
#define DESC_B4C  ((const Map2D *)0x00069B4C)   /* load x RPM -> A62C (B19D==1)  */
#define DESC_B68  ((const Map2D *)0x00069B68)   /* load x RPM -> A62C (B19D!=1)  */
#define DESC_B30  ((const Map2D *)0x00069B30)   /* load x RPM -> A630 */
#define DESC_B98  ((const Map2D *)0x00069B98)   /* RPM x temp type-0 -> A638 */

#define ROM_F_6D56C (0.0f)   /* A5F8 base addend          */
#define ROM_F_6D570 (80.0f)  /* A604 clamp when CDA0 == 0 */
#define ROM_F_6D574 (11.0f)  /* A604 clamp when CDA0 != 0 */
#define ROM_F_6D578 (0.0f)   /* A5F0 blend addend         */
#define ROM_F_6D57C (0.0f)   /* A608 addend (B19D==1)     */
#define ROM_F_6D580 (0.0f)   /* A608 addend (B19D!=1)     */

/* ---- verified leaves (see c/2DLookup.c, c/3dLookup.c) ---- */
extern float TwoDLookup(const Map1D *m, float x);           /* 0x2068 */
extern float ThreeDLookup(const Map2D *m, float x, float y);/* 0x20DC */

/* 0x23E4 — shared max helper (IDA mislabels it "fpu_mul_float") */
static float max_0x23E4(float a, float b)
{
    return (b > a) ? b : a;
}

/* 0x23F4 — shared min helper (IDA mislabels it "fpu_sqrt_float") */
static float min_0x23F4(float a, float b)
{
    return (a > b) ? b : a;
}

void calc_spark_advance_0x1237C(void)
{
    float rpm  = RAM_RPM;
    float load = RAM_LOAD;
    float w	  = RAM_B188;              /* rotor-sync blend weight */
    float temp = RAM_TEMP;
    float adv_first, adv_lead, blended;

    /* ---- leading/trailing advance maps ---- */
    RAM_A624 = TwoDLookup(DESC_A7C, RAM_A7BC);      /* RPM map           */
    RAM_A628 = ThreeDLookup(DESC_B14, load, rpm);     /* load x RPM        */
    RAM_A634 = TwoDLookup(DESC_A90, temp);            /* temp map          */

    /* ---- A5F8 = 0.0 - (A628*A634) + A624 ---- */
    RAM_A5F8 = (ROM_F_6D56C - (RAM_A628 * RAM_A634)) + RAM_A624;

    /* ---- lead-clamp A604 ---- */
    RAM_A604 = (RAM_CDA0 == 0) ? ROM_F_6D570 : ROM_F_6D574;

    /* ---- leading advance path (maps 4C/68), A62C then A608 ---- */
    if (RAM_B19D == 1) {
        RAM_A62C  = ThreeDLookup(DESC_B4C, load, rpm);     /* 0x12408 */
        adv_first = min_0x23F4(RAM_A62C, RAM_A604);
        RAM_A608  = adv_first + ROM_F_6D57C;
    } else {
        RAM_A62C  = ThreeDLookup(DESC_B68, load, rpm);     /* 0x12420 */
        adv_first = min_0x23F4(RAM_A62C, RAM_A604);
        RAM_A608  = adv_first + ROM_F_6D580;
    }

    /* ---- trail advance A630, RPM/temp row A638 ---- */
    RAM_A630 = ThreeDLookup(DESC_B30, load, rpm);       /* 0x1243C x=LOAD,y=RPM */
    RAM_A638 = ThreeDLookup(DESC_B98, rpm, temp);       /* 0x12448 x=RPM,y=TEMP */

    /* ---- A5F0 = max( fma((1-w), min(A630,A604)+0, w*A608), A638 ) ----
     * The ROM does w*A608 as a separate fmul first, then the fused fmac
     * (fr2 = fr0*fr1 + fr2) — so the addend is pre-rounded. */
    adv_lead = min_0x23F4(RAM_A630, RAM_A604);
    {
        float prod = w * RAM_A608;                     /* fmul, single rounding */
        blended    = fmaf((1.0f - w), (ROM_F_6D578 + adv_lead), prod);
    }
    RAM_A5F0 = max_0x23E4(blended, RAM_A638);
}