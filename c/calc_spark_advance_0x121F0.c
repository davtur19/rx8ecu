/* calc_spark_advance_0x121F0.c
 *
 * ROM: 60E1D400  |  Address: 0x121F0  |  Size: 0x18C bytes
 *       code 0x121F0..0x12302; literal pool @0x12304..0x1237A; next function
 *       @0x1237C.  VERIFIED vs ROM emulator (0 mismatches,
 *       c/tests/test_calc_spark_advance_0x121F0.py).
 *
 * Called FIRST of the ignition-timing group from engineControlCalculateTiming
 * @0x14584 (dispatch 0x14594), immediately before calc_spark_advance_0x1237C
 * (0x1459A).  Old IDA name "calc_combustion_efficiency_metric" is NOT
 * supported: the ROM performs NO combustion-efficiency computation.  Like its
 * sibling 0x1237C (which the repo names calc_spark_advance), it computes a
 * RESULTANT SPARK ADVANCE (deg) at f32@0xFFFFA5EC by combining RPM/load/temp
 * timing maps, clamping against a gate-selected maximum, and cross-blending
 * two candidate advances by the rotor-sync weight f32@0xFFFFB188.  Every map
 * that feeds the result is calibrated as result = scale*cell + offset
 * (leaves 0x2068/0x20DC) and the observable outputs (0xFFFFA5xx) are all
 * spark-timing degree values.  Proper name: calc_spark_advance (first of the
 * pair; 0x1237C is the second, computing A5F0).
 *
 * Semantics (execution order):
 *   1. TwoDLookup(desc 0x69A54, x=f32@0xFFFFA7BC)   -> f32@0xFFFFA60C
 *         (6-point RPM map, axis 700..2000, u8 cells, 0.5*cell - 50)
 *      ThreeDLookup(desc 0x69AA4, x=LOAD, y=RPM)    -> f32@0xFFFFA610
 *         (10x7 load x RPM map, x 0.0625..0.625, y 800..2000, u8, 0.5*cell-50)
 *      TwoDLookup(desc 0x69A68, x=f32@0xFFFFAA10)   -> f32@0xFFFFA61C
 *         (9-point table x=-40..120, u8 cells, 0.01*cell)
 *   2. 0xFFFFA5F4 = ROM32@0x6D554(=0) - (A610 * A61C) + A60C
 *   3. 0xFFFFA5FC = (RAM8@0xFFFFCDA0 == 0) ? ROM32@0x6D558(=80.0) : ROM32@0x6D55C(=16.0)
 *      (advance clamp selected by the CDA0 gate byte)
 *   4. selector RAM8@0xFFFFB19D == 1:
 *        A614 = ThreeDLookup(desc 0x69ADC, LOAD, RPM)   -> r1 = min(A614, A5FC)
 *      else:
 *        A614 = ThreeDLookup(desc 0x69AF8, LOAD, RPM)   -> r1 = min(A614, A5FC)
 *      (both 20x18 load x RPM maps, u8 cells, 0.5*cell - 50)
 *      RAM32@0xFFFFA600 = r1 + ROM32@0x6D564/0x6D568 (= 0)
 *   5. RAM32@0xFFFFA618 = ThreeDLookup(desc 0x69AC0, LOAD, RPM)   (20x18)
 *      RAM32@0xFFFFA620 = ThreeDLookup(desc 0x69B84, x=RPM, y=TEMP) (4x3,
 *         x 1300..2500, y 0..10, type-0 f32 cells: row0 5/0/0/0, rows1-2 -25)
 *   6. adv = min(A618, A5FC)
 *      RAM32@0xFFFFA5EC = max( fma((1-B188), ROM_6D560+adv, B188*A600), A620 )
 *         -- the blend term is a fused fmac fr0,fr1,fr2 (single rounding),
 *            reproduced with fmaf(); RAM_B188 (f32@0xFFFFB188) is the
 *            rotor-sync / trailing weight in ~0..1.
 *
 * Inputs (RAM reads): B5B8 (RPM f32), C12C (load f32), AA10 (f32 map input),
 *   A7BC (f32), B188 (f32 blend weight), gate bytes u8@0xFFFFCDA0 and
 *   u8@0xFFFFB19D.
 * ROM constants: desc 0x69A54/0x69A68/0x69AA4/0x69ADC/0x69AF8/0x69AC0/0x69B84
 *   (+axes/cells), f32@0x6D554=0 / 0x6D558=80 / 0x6D55C=16 / 0x6D560=0 /
 *   0x6D564=0 / 0x6D568=0.
 * Outputs (RAM writes): A60C, A610, A61C, A5F4, A5FC, A614, A600, A618, A620,
 *   A5EC (all f32).
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

#define RAM_A60C  (*(volatile float *)0xFFFFA60C)
#define RAM_A610  (*(volatile float *)0xFFFFA610)
#define RAM_A61C  (*(volatile float *)0xFFFFA61C)
#define RAM_A5F4  (*(volatile float *)0xFFFFA5F4)
#define RAM_A5FC  (*(volatile float *)0xFFFFA5FC)
#define RAM_A614  (*(volatile float *)0xFFFFA614)
#define RAM_A600  (*(volatile float *)0xFFFFA600)
#define RAM_A618  (*(volatile float *)0xFFFFA618)
#define RAM_A620  (*(volatile float *)0xFFFFA620)
#define RAM_A5EC  (*(volatile float *)0xFFFFA5EC)

#define RAM_CDA0  (*(volatile uint8_t *)0xFFFFCDA0)  /* clamp-select gate byte */
#define RAM_B19D  (*(volatile uint8_t *)0xFFFFB19D)  /* table-select byte      */

#define DESC_A54  ((const Map1D *)0x00069A54)   /* RPM map -> A60C */
#define DESC_A68  ((const Map1D *)0x00069A68)   /* temp map -> A61C */
#define DESC_AA4  ((const Map2D *)0x00069AA4)   /* load x RPM -> A610 */
#define DESC_ADC  ((const Map2D *)0x00069ADC)   /* load x RPM -> A614 (B19D==1)  */
#define DESC_AF8  ((const Map2D *)0x00069AF8)   /* load x RPM -> A614 (B19D!=1)  */
#define DESC_AC0  ((const Map2D *)0x00069AC0)   /* load x RPM -> A618 */
#define DESC_B84  ((const Map2D *)0x00069B84)   /* RPM x temp type-0 -> A620 */

#define ROM_F_6D554 (0.0f)   /* A5F4 base addend          */
#define ROM_F_6D558 (80.0f)  /* A5FC clamp when CDA0 == 0 */
#define ROM_F_6D55C (16.0f)  /* A5FC clamp when CDA0 != 0 */
#define ROM_F_6D560 (0.0f)   /* A5EC blend addend         */
#define ROM_F_6D564 (0.0f)   /* A600 addend (B19D==1)     */
#define ROM_F_6D568 (0.0f)   /* A600 addend (B19D!=1)     */

/* ---- verified leaves (see c/2DLookup.c, c/3dLookup.c) ---- */
extern float TwoDLookup(const Map1D *m, float x);            /* 0x2068 */
extern float ThreeDLookup(const Map2D *m, float x, float y); /* 0x20DC */

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

void calc_spark_advance_0x121F0(void)
{
    float rpm  = RAM_RPM;
    float load = RAM_LOAD;
    float w    = RAM_B188;              /* rotor-sync blend weight */
    float temp = RAM_TEMP;
    float adv_first, adv_lead, blended;

    /* ---- advance maps ---- */
    RAM_A60C = TwoDLookup(DESC_A54, RAM_A7BC);       /* RPM map          */
    RAM_A610 = ThreeDLookup(DESC_AA4, load, rpm);    /* load x RPM       */
    RAM_A61C = TwoDLookup(DESC_A68, temp);           /* temp map         */

    /* ---- A5F4 = 0.0 - (A610*A61C) + A60C ---- */
    RAM_A5F4 = (ROM_F_6D554 - (RAM_A610 * RAM_A61C)) + RAM_A60C;

    /* ---- advance clamp A5FC ---- */
    RAM_A5FC = (RAM_CDA0 == 0) ? ROM_F_6D558 : ROM_F_6D55C;

    /* ---- leading advance path (maps ADC/AF8), A614 then A600 ---- */
    if (RAM_B19D == 1) {
        RAM_A614  = ThreeDLookup(DESC_ADC, load, rpm);     /* 0x12280 */
        adv_first = min_0x23F4(RAM_A614, RAM_A5FC);
        RAM_A600  = adv_first + ROM_F_6D564;
    } else {
        RAM_A614  = ThreeDLookup(DESC_AF8, load, rpm);     /* 0x12296 */
        adv_first = min_0x23F4(RAM_A614, RAM_A5FC);
        RAM_A600  = adv_first + ROM_F_6D568;
    }

    /* ---- trail advance A618, RPM/temp row A620 ---- */
    RAM_A618 = ThreeDLookup(DESC_AC0, load, rpm);       /* 0x122B0 x=LOAD,y=RPM */
    RAM_A620 = ThreeDLookup(DESC_B84, rpm, temp);       /* 0x122BC x=RPM,y=TEMP */

    /* ---- A5EC = max( fma((1-w), min(A618,A5FC)+0, w*A600), A620 ) ----
     * The ROM does w*A600 as a separate fmul first, then the fused fmac
     * (fr2 = fr0*fr1 + fr2) — so the addend is pre-rounded. */
    adv_lead = min_0x23F4(RAM_A618, RAM_A5FC);
    {
        float prod = w * RAM_A600;                     /* fmul, single rounding */
        blended    = fmaf((1.0f - w), (ROM_F_6D560 + adv_lead), prod);
    }
    RAM_A5EC = max_0x23E4(blended, RAM_A620);
}
