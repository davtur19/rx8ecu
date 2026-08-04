/* air_charge_calc_0x19190.c
 *
 * ROM: 60E1D400  |  Address: 0x19190  |  Size: 0x52 bytes (code 0x19190..0x191E0);
 *       mov.w literal pool @0x191E2..0x191F0, padding @0x191F2..0x19207, mov.l
 *       literal pool @0x19208..0x19220; next function air_temp_comp_multivar_calc
 *       @0x19220.
 *       VERIFIED vs ROM emulator (0 mismatches, c/tests/test_air_charge_calc_0x19190.py).
 *
 * Air-charge estimate refresh.  Old IDA name "air_charge_calc_0x19190".  The
 * observable effect is an f32@0xFFFFA9B8 air-charge quantity derived from the
 * RPM x charge-temp 3-D map 0x69EDC, gated by the u16 load-estimate counter
 * @0xFFFFA9BC that engine_load_estimator_0x190A6 keeps refreshed/decremented.
 *
 * Semantics (execution order):
 *   1. gate = u16@FFFFA9BC.  If gate == 0: A9B8 = 0.0 and return (A9C4/A9C8
 *      are NOT touched).
 *   2. lookup = ThreeDLookup(desc 0x69EDC, x = RPM f32@FFFFB5B8, y = charge-temp
 *      f32@FFFFAA10).  Desc: 12x8 u8 cells, scale 1.0/offset 0.0, axis_x = RPM
 *      0..3000 (f32 @0x6EDA4), axis_y = temp -40..100 (f32 @0x6EDD4), values
 *      @0x6EDF4 (cal60E1D400 "Table 3D - 14_"); the x-axis is RPM so the
 *      lookup reads x=RPM (fr4) against axis_x, y=temp (fr5) against axis_y.
 *   3. A9C4 = lookup
 *   4. A9C8 = f32@FFFFBD0C - lookup          (fsub fr0,fr3)
 *   5. m   = max_0x23E4(f32@FFFFA9B0, f32@FFFFA9B4)   (helper 0x23E4)
 *   6. A9B8 = min_0x23F4(f32@FFFFA9C8, m)             (helper 0x23F4)
 *   Helpers 0x23E4/0x23F4 are the ROM's mislabeled fpu_mul_float / fpu_sqrt_float:
 *   max / min of the two float args with the second arg winning on NaN
 *   (fcmp/gt is false on unordered, so both fall through to fr6 = fr5).
 *
 * Inputs (RAM reads):  A9BC (u16 gate), B5B8 (f32 RPM), AA10 (f32 charge temp),
 *   BD0C (f32), A9B0/A9B4 (f32, same shared state engine_load_estimator_0x190A6
 *   uses for its refresh condition).  ROM: desc 0x69EDC + axes/cells.
 * Outputs (RAM writes): A9B8 (f32, always), A9C4 (f32, gate != 0 only),
 *   A9C8 (f32, gate != 0 only).
 *
 * Verified: 100000 random inputs x 5 seeds (500000 total) vs the ROM emulator,
 * 0 mismatches.
 */
#include <stdint.h>

#define RAM_GATE  (*(volatile uint16_t *)0xFFFFA9BC) /* load-estimate counter (gate) */
#define RAM_RPM   (*(volatile float *)0xFFFFB5B8)    /* engine speed                */
#define RAM_TEMP  (*(volatile float *)0xFFFFAA10)    /* charge-temp map input       */
#define RAM_BD0C  (*(volatile float *)0xFFFFBD0C)
#define RAM_A9B0  (*(volatile float *)0xFFFFA9B0)    /* shared with 0x190A6         */
#define RAM_A9B4  (*(volatile float *)0xFFFFA9B4)    /* shared with 0x190A6         */

#define RAM_A9B8  (*(volatile float *)0xFFFFA9B8)    /* air-charge output           */
#define RAM_A9C4  (*(volatile float *)0xFFFFA9C4)    /* raw lookup output           */
#define RAM_A9C8  (*(volatile float *)0xFFFFA9C8)    /* BD0C - lookup output        */

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

#define DESC_AIR_CHARGE ((const Map2D *)0x69EDC)  /* RPM x charge-temp surface */

/* ---- verified leaf ---- */
extern float ThreeDLookup(const Map2D *m, float x, float y); /* 0x20DC */

/* 0x23E4 — "fpu_mul_float" mislabel; returns max(fr4, fr5); NaN compare is
 * false so the second arg (fr5) wins on unordered. */
static float max_0x23E4(float a, float b)
{
    return (a > b) ? a : b;
}

/* 0x23F4 — "fpu_sqrt_float" mislabel; returns min(fr4, fr5); NaN compare is
 * false so the second arg (fr5) wins on unordered. */
static float min_0x23F4(float a, float b)
{
    return (b > a) ? a : b;
}

void air_charge_calc_0x19190(void)
{
    float lookup, m;

    if (RAM_GATE == 0) {                 /* 0x19194 mov.w / 0x19196 extu.w / 0x19198 cmp/pl */
        RAM_A9B8 = 0.0f;                 /* 0x191D6 fldi0 + 0x191DA store */
        return;
    }

    /* 0x191A8 jsr 0x20DC: r4=desc, fr4=RPM, fr5=temp (delay-slot load @0x191AA) */
    lookup = ThreeDLookup(DESC_AIR_CHARGE, RAM_RPM, RAM_TEMP);
    RAM_A9C4 = lookup;                   /* 0x191AE */

    RAM_A9C8 = RAM_BD0C - lookup;        /* 0x191B6 fsub fr0,fr3 */

    m = max_0x23E4(RAM_A9B0, RAM_A9B4);  /* 0x191C2 jsr 0x23E4 */
    RAM_A9B8 = min_0x23F4(RAM_A9C8, m);  /* 0x191CC jsr 0x23F4 -> 0x191D4 store */
}
