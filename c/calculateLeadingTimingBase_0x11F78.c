/* calculateLeadingTimingBase_0x11F78.c
 *
 * ROM: 60E0FC00 | Address: 0x11F78 | Size: 0xB2 (178) bytes actual code+pool
 *       code 0x11F78..0x12028 (rts @0x12026, delay mov.l @r15+,r14 @0x12028);
 *       the trailing twin 0x1202A starts exactly at the CSV end.  VERIFIED vs
 *       the ROM emulator (0 mismatches, c/tests/test_calculateLeadingTimingBase_0x11F78.py).
 *
 * ENTRY VERIFICATION: 0x11F78 matches the CSV start.  Valid entry: opens with
 * the standard prologue (mov.l r14/r13 pushes + 3 fmov.s fr pushes + sts.l pr);
 * the preceding function getKnownBooleanValue?? (0x11F54) ends rts @0x11F6C
 * (delay @0x11F6E) with its own pool @0x11F70..0x11F76, so no fall-through
 * into us.  The ROM function-pointer slot @0x14404 of the engineControl-
 * CalculateTiming dispatcher (0x141FC) table is the ONLY 32-bit reference to
 * 0x11F78 in the binary (slot @0x14408 holds the trailing twin 0x1202A right
 * next to it — same table family as setPerRotorTimingValuesLeading/Trailing
 * @0x144E8/0x144EC).  The CSV address IS the real entry point.
 *
 * SEMANTICS (instruction-for-instruction, see disasm): leading-timing "base"
 * writer — computes the pre-derate leading spark advance and publishes it at
 * f32@0xFFFFA5EC by combining five calibration lookups (helpers 0x2068 =
 * TwoDLookup, 0x20DC = ThreeDLookup), the rotor-sync ramp inputs f32@B594 /
 * f32@C0D8 / f32@A9FC / f32@A7AC and the CC2C-gated advance clamp:
 *
 *   A604 = TwoDLookup(desc 0x67908, x=f32@A7AC)      // 6-pt RPM map
 *   A608 = ThreeDLookup(desc 0x67958, x=f32@C0D8, y=f32@B594)   // 8x7 load x RPM
 *   A610 = TwoDLookup(desc 0x6791C, x=f32@A9FC)      // 9-pt temp map
 *   A5F4 = ROM32@0x6DA54(=0) - A608*A610 + A604
 *   A5FC = (u8@CC2C == 0) ? ROM32@0x6DA58(=80.0) : ROM32@0x6DA5C(=16.0)
 *   A60C = ThreeDLookup(desc 0x67974, x=f32@C0D8, y=f32@B594)   // 20x18 load x RPM
 *   A614 = ThreeDLookup(desc 0x679C8, x=f32@B594, y=f32@A9FC)   // 4x3 RPM x temp, f32 cells
 *   A5EC = saturateLow_0x23E4( ROM32@0x6DA60(=0) + minValue_0x23F4(A60C, A5FC), A614 )
 *
 * r0 on return = 4 * (x-axis index of f32@B594 on desc 0x679C8's X axis)
 *   — the last helper call is the 0x20DC lookup on desc 0x679C8 (type-0 f32
 *   cells); its interpolate handler 0x253C leaves r0 = ix<<2 and the two
 *   0x23xx leaves never write r0 (verified vs emulator).
 *
 * RANGE NOTE: the CSV row (0x011F78,0x01202A) is CORRECT — the trailing twin
 * begins at 0x1202A (its mov.l r14,@-r15 prologue).  The mov.w/mov.l literal
 * pool @0x12092..0x120EC is shared with the trailing twin (both functions
 * reference the same 0x12092/0x12094/... entries; the trailing twin's own
 * mov.l pool continues @0x120F0..0x1217E).
 *
 * LITERAL POOL (values verified against roms/stock/60E0FC00.bin):
 *   0x12092 0xB594   (mov.w -> f32 @0xFFFFB594, RPM, y/x of the 3D maps)
 *   0x12094 0xC0D8   (mov.w -> f32 @0xFFFFC0D8, load, x of the 3D maps)
 *   0x12096 0xA9FC   (mov.w -> f32 @0xFFFFA9FC, temp, x of the temp maps)
 *   0x12098 0xA7AC   (mov.w -> f32 @0xFFFFA7AC, x of the 6-pt RPM map)
 *   0x1209A 0xA5F4   (mov.w -> f32 output @0xFFFFA5F4)
 *   0x1209C 0xCC2C   (mov.w -> u8 gate @0xFFFFCC2C)
 *   0x1209E 0xA5EC   (mov.w -> f32 output @0xFFFFA5EC)
 *   0x120A4 0x00067908 (mov.l -> TwoDLookup desc, 6-pt RPM map)
 *   0x120A8 0x00002068 (mov.l -> TwoDLookup helper @0x2068)
 *   0x120AC 0xFFFFA604 (mov.l -> f32 output @0xFFFFA604)
 *   0x120B0 0x000020DC (mov.l -> ThreeDLookup helper @0x20DC)
 *   0x120B4 0x00067958 (mov.l -> ThreeDLookup desc, 8x7)
 *   0x120B8 0xFFFFA608 (mov.l -> f32 output @0xFFFFA608)
 *   0x120BC 0x0006791C (mov.l -> TwoDLookup desc, 9-pt temp map)
 *   0x120C0 0xFFFFA610 (mov.l -> f32 output @0xFFFFA610)
 *   0x120C4 0x0006DA54 (mov.l -> f32 0.0, A5F4 base addend)
 *   0x120C8 0xFFFFA5FC (mov.l -> f32 output @0xFFFFA5FC)
 *   0x120CC 0x0006DA58 (mov.l -> f32 80.0, clamp when CC2C == 0)
 *   0x120D0 0x0006DA5C (mov.l -> f32 16.0, clamp when CC2C != 0)
 *   0x120D4 0x00067974 (mov.l -> ThreeDLookup desc, 20x18)
 *   0x120D8 0xFFFFA60C (mov.l -> f32 output @0xFFFFA60C)
 *   0x120DC 0x000679C8 (mov.l -> ThreeDLookup desc, 4x3 f32 cells)
 *   0x120E0 0xFFFFA614 (mov.l -> f32 output @0xFFFFA614)
 *   0x120E4 0x000023F4 (mov.l -> minValue helper @0x23F4)
 *   0x120E8 0x0006DA60 (mov.l -> f32 0.0, A5EC addend)
 *   0x120EC 0x000023E4 (mov.l -> saturateLow helper @0x23E4)
 * RAM r/w: reads A7AC, B594, C0D8, A9FC, CC2C; writes A604, A608, A610,
 *   A5F4, A5FC, A60C, A614, A5EC (all f32) + the task-stack window.
 * ROM read: descriptor tables @0x67908/0x67958/0x6791C/0x67974/0x679C8
 *   (+ their axis/value tables in 0x6DA74..0x6E018) and the f32 constants
 *   @0x6DA54/0x6DA58/0x6DA5C/0x6DA60.
 * Sub-calls: TwoDLookup @0x2068 (x2), ThreeDLookup @0x20DC (x3), minValue
 *   @0x23F4 (x1), saturateLow @0x23E4 (x1).
 * TWIN (structural, byte-for-byte same skeleton): calculateTrailingTimingBase
 *   @0x1202A (c/calculateTrailingTimingBase_0x1202A.c).  Differences ONLY:
 *   +0x0C-shifted RAM outputs (A604..A614 -> A618..A628), descriptors
 *   0x67908/0x67958/0x6791C/0x67974/0x679C8 -> 0x67930/0x67990/0x67944/
 *   0x679AC/0x679DC, ROM constants 0x6DA54/0x6DA58/0x6DA5C/0x60DA60 ->
 *   0x6DA64/0x6DA68/0x6DA6C/0x6DA70, outputs A5F4/A5EC -> A5F8/A5F0, and the
 *   6-pt RPM map axis (leading 1880 vs trailing 1890 at the 5th breakpoint).
 *   The clamp when CC2C != 0 is 16.0 (leading) vs 11.0 (trailing).
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

/* ---- RAM globals (mov.w literals sign-extend to 0xFFFFxxxx) ---- */
#define RAM_A7AC  (*(volatile float *)0xFFFFA7AC)  /* 6-pt RPM map x input   */
#define RAM_B594  (*(volatile float *)0xFFFFB594)  /* RPM (y/x of the 3D maps)*/
#define RAM_C0D8  (*(volatile float *)0xFFFFC0D8)  /* load (x of the 3D maps) */
#define RAM_A9FC  (*(volatile float *)0xFFFFA9FC)  /* temp (x of temp maps)  */
#define RAM_CC2C  (*(volatile uint8_t *)0xFFFFCC2C)/* clamp-select gate byte  */

#define OUT_A604  (*(volatile float *)0xFFFFA604)
#define OUT_A608  (*(volatile float *)0xFFFFA608)
#define OUT_A610  (*(volatile float *)0xFFFFA610)
#define OUT_A5F4  (*(volatile float *)0xFFFFA5F4)
#define OUT_A5FC  (*(volatile float *)0xFFFFA5FC)
#define OUT_A60C  (*(volatile float *)0xFFFFA60C)
#define OUT_A614  (*(volatile float *)0xFFFFA614)
#define OUT_A5EC  (*(volatile float *)0xFFFFA5EC)

/* ---- ROM calibration constants ---- */
#define ROM_F_6DA54 (*(const float *)0x0006DA54)  /* 0.0  A5F4 base addend */
#define ROM_F_6DA58 (*(const float *)0x0006DA58)  /* 80.0 clamp when CC2C==0 */
#define ROM_F_6DA5C (*(const float *)0x0006DA5C)  /* 16.0 clamp when CC2C!=0 */
#define ROM_F_6DA60 (*(const float *)0x0006DA60)  /* 0.0  A5EC addend      */

#define DESC_67908 ((const Map1D *)0x00067908)  /* 6-pt RPM map   -> A604 */
#define DESC_6791C ((const Map1D *)0x0006791C)  /* 9-pt temp map  -> A610 */
#define DESC_67958 ((const Map2D *)0x00067958)  /* 8x7 load x RPM -> A608 */
#define DESC_67974 ((const Map2D *)0x00067974)  /* 20x18 load x RPM -> A60C */
#define DESC_679C8 ((const Map2D *)0x000679C8)  /* 4x3 RPM x temp f32 -> A614 */

/* ---- verified leaves (see c/2DLookup.c, c/3dLookup.c, c/math_primitives.c) ---- */
extern float TwoDLookup(const Map1D *m, float x);            /* 0x2068 */
extern float ThreeDLookup(const Map2D *m, float x, float y); /* 0x20DC */
extern float minValue(float a, float b);                     /* 0x23F4 */
extern float saturateLow(float sig, float lower);            /* 0x23E4 */

void calculateLeadingTimingBase_0x11F78(void)
{
    /* ---- lookup group 1 ---- */
    OUT_A604 = TwoDLookup(DESC_67908, RAM_A7AC);                 /* 6-pt RPM map */
    OUT_A608 = ThreeDLookup(DESC_67958, RAM_C0D8, RAM_B594);     /* 8x7 load x RPM */
    OUT_A610 = TwoDLookup(DESC_6791C, RAM_A9FC);                 /* 9-pt temp map */

    /* ---- A5F4 = 0.0 - A608*A610 + A604 ---- */
    OUT_A5F4 = (ROM_F_6DA54 - (OUT_A608 * OUT_A610)) + OUT_A604;

    /* ---- advance clamp A5FC ---- */
    OUT_A5FC = (RAM_CC2C == 0) ? ROM_F_6DA58 : ROM_F_6DA5C;

    /* ---- lookup group 2 ---- */
    OUT_A60C = ThreeDLookup(DESC_67974, RAM_C0D8, RAM_B594);     /* 20x18 load x RPM */
    OUT_A614 = ThreeDLookup(DESC_679C8, RAM_B594, RAM_A9FC);     /* 4x3 RPM x temp */

    /* ---- A5EC = saturateLow( 0.0 + min(A60C, A5FC), A614 ) ---- */
    OUT_A5EC = saturateLow(ROM_F_6DA60 + minValue(OUT_A60C, OUT_A5FC),
                           OUT_A614);
}
