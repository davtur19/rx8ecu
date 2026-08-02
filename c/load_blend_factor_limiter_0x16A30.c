/* load_blend_factor_limiter_0x16A30.c
 *
 * ROM: 60E1D400  |  Address: 0x16A30  |  Size: 0x44 bytes code (0x16A30..0x16A72)
 *       + literal pool @0x16A74..0x16A92; next function idle_processing_dispatch @0x16A94.
 *       Called from engine_control_main_loop @0x16AA8 (dispatch literal @0x16B78).
 *       VERIFIED vs ROM emulator (0 mismatches, c/tests/test_load_blend_factor_limiter_0x16A30.py).
 *
 * Rockwell (IDA) name "load_blend_factor_limiter" confirmed as a faithful description:
 * the function computes a load/temperature blend factor from a 2-D or 3-D calibration
 * map and feeds it into a two-word RAM limiter pair (A8D4/A8D8) with a +20 degC
 * reunion hysteresis.
 *
 * Semantics (execution order):
 *   1. Selector RAM8@0xFFFFB5A4:
 *        ==1  -> blend = TwoDLookup(desc 0x69EAC, x = RAM_A_AA14)     (ROM 0x2068)
 *        else -> blend = ThreeDLookup(desc 0x69EC0, x = RAM[AA14],
 *                                     y = RAM[AA1C])                   (ROM 0x20DC)
 *      desc 0x69EAC: 1-D, count 9, u8 cells, axis temp -40..100 (0x6ED18),
 *        values 0x6ED3C, scale 0.01, offset 0.
 *      desc 0x69EC0: 2-D, 9x3, u8 cells, axis_x temp -40..100 (0x6ED48),
 *        axis_y -20..20 (0x6ED6C), values 0x6ED78, scale 0.01, offset 0.
 *      (both maps model coolant temp on x and the "blend" split on the second
 *       axis; cells 0x02..0x34, so blend lands in 0.02..0.52 degC units.)
 *   2. Limiter step (0x16A56..0x16A72):
 *        if (blend < RAM[0xFFFFA8D8] + 20.0f)   -> RAM[0xFFFFA8D4] = blend
 *        RAM[0xFFFFA8D8] = RAM[0xFFFFA8D4]       (always, rts delay slot)
 *      i.e. the lagged word A8D8 keeps tracking A8D4; A8D4 only takes the fresh
 *      blend when that blend is within 20 units of the lagged (+20 reunion window),
 *      otherwise the previous A8D4 is retained (slew/limit on the branch).
 *
 * Inputs (RAM reads): B5A4 (u8 selector), AA14 (f32 x), AA1C (f32 y), A8D8 (f32
 *   lag). ROM constants: desc 0x69EAC / 0x69EC0 (+ axes/cells), f32 20.0 @0x6ED14.
 * Outputs (RAM writes): A8D4 (f32, conditional), A8D8 (f32, always = A8D4).
 *
 * Verified: 100000 random inputs x 5 seeds (500000 total) vs the ROM emulator,
 * 0 mismatches.
 */
#include <stdint.h>
#include <math.h>

#define RAM_SEL      (*(volatile uint8_t *)0xFFFFB5A4) /* blend selector */
#define RAM_AA14     (*(volatile float   *)0xFFFFAA14) /* 1-D / 3-D x input */
#define RAM_AA1C     (*(volatile float   *)0xFFFFAA1C) /* 3-D y input        */
#define RAM_A8D4     (*(volatile float   *)0xFFFFA8D4) /* blend out (limiter) */
#define RAM_A8D8     (*(volatile float   *)0xFFFFA8D8) /* lagged word          */

/* 1-D descriptor layout (Map1D, c/2DLookup.c) — 20 bytes, big-endian SH-2E */
typedef struct {
    uint16_t     count;   /* +0 */
    uint8_t      type;    /* +2 */
    uint8_t      _pad;    /* +3 */
    const float *axis;    /* +4 */
    const void  *values;  /* +8 */
    float        scale;   /* +12 */
    float        offset;  /* +16 */
} Map1D;

/* 2-D descriptor layout (Map2D, c/3dLookup.c) — 28 bytes, big-endian SH-2E */
typedef struct {
    uint16_t     count_x; /* +0 */
    uint16_t     count_y; /* +2 */
    const float *axis_x;  /* +4 */
    const float *axis_y;  /* +8 */
    const void  *values;  /* +12 */
    uint8_t      type;    /* +16 */
    uint8_t      _pad[3];
    float        scale;   /* +20 */
    float        offset;  /* +24 */
} Map2D;

#define DESC_2D ((const Map1D *)0x00069EAC)   /* blend map (select==1) */
#define DESC_3D ((const Map2D *)0x00069EC0)   /* blend map (else)       */

/* ---- verified leaves ---- */
extern float TwoDLookup(const Map1D *m, float x);     /* ROM 0x2068 */
extern float ThreeDLookup(const Map2D *m, float x, float y); /* ROM 0x20DC */

void load_blend_factor_limiter_16A30(void)
{
    float blend;

    if (RAM_SEL == 1) {
        blend = TwoDLookup(DESC_2D, RAM_AA14);
    } else {
        blend = ThreeDLookup(DESC_3D, RAM_AA14, RAM_AA1C);
    }

    if (blend < RAM_A8D8 + 20.0f)       /* fcmp/gt fr4(fr5:blend+20)… reunion window */
        RAM_A8D4 = blend;               /* conditional store @0x16A6A */
    RAM_A8D8 = RAM_A8D4;                 /* always (rts delay slot @0x16A72) */
}