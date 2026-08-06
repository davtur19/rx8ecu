/* calculateTrailingTimingBase_0x1202A.c
 *
 * ROM: 60E0FC00 | Address: 0x1202A | Size: 0x156 (342) bytes actual code+pool
 *       code 0x1202A..0x1215C (rts @0x1215A, delay mov.l @r15+,r14 @0x1215C);
 *       the next function (getIgnitionTimingInit? @0x12180) starts exactly at
 *       the CSV end.  VERIFIED vs the ROM emulator (0 mismatches,
 *       c/tests/test_calculateTrailingTimingBase_0x1202A.py).
 *
 * ENTRY VERIFICATION: 0x1202A matches the CSV start.  Valid entry: opens with
 * the standard prologue (mov.l r14/r13 pushes + 3 fmov.s fr pushes + sts.l pr);
 * the leading twin 0x11F78 ends rts @0x12026 (delay @0x12028), so no
 * fall-through into us.  The ROM function-pointer slot @0x14408 of the
 * engineControlCalculateTiming dispatcher (0x141FC) table is the ONLY 32-bit
 * reference to 0x1202A in the binary (slot @0x14404 holds the leading twin
 * 0x11F78 right next to it).  The CSV address IS the real entry point.
 *
 * SEMANTICS (instruction-for-instruction, see disasm): trailing-timing "base"
 * writer — structural twin of calculateLeadingTimingBase_0x11F78 with shifted
 * RAM outputs and its own descriptors/constants; publishes the pre-derate
 * trailing spark advance at f32@0xFFFFA5F0:
 *
 *   A618 = TwoDLookup(desc 0x67930, x=f32@A7AC)      // 6-pt RPM map
 *   A61C = ThreeDLookup(desc 0x67990, x=f32@C0D8, y=f32@B594)   // 8x7 load x RPM
 *   A624 = TwoDLookup(desc 0x67944, x=f32@A9FC)      // 9-pt temp map
 *   A5F8 = ROM32@0x6DA64(=0) - A61C*A624 + A618
 *   A600 = (u8@CC2C == 0) ? ROM32@0x6DA68(=80.0) : ROM32@0x6DA6C(=11.0)
 *   A620 = ThreeDLookup(desc 0x679AC, x=f32@C0D8, y=f32@B594)   // 20x18 load x RPM
 *   A628 = ThreeDLookup(desc 0x679DC, x=f32@B594, y=f32@A9FC)   // 4x3 RPM x temp, f32 cells
 *   A5F0 = saturateLow_0x23E4( ROM32@0x6DA70(=0) + minValue_0x23F4(A620, A600), A628 )
 *
 * r0 on return = 4 * (x-axis index of f32@B594 on desc 0x679DC's X axis)
 *   — the last helper call is the 0x20DC lookup on desc 0x679DC (type-0 f32
 *   cells); its interpolate handler 0x253C leaves r0 = ix<<2 and the two
 *   0x23xx leaves never write r0 (verified vs emulator).
 *
 * RANGE NOTE: the CSV row (0x01202A,0x012180) is CORRECT — the next function
 * (getIgnitionTimingInit? @0x12180, mov.l literal prologue) starts exactly at
 * the CSV end.  This function's code straddles the shared mov.w/mov.l pool
 * @0x12092..0x120EC (shared with the leading twin 0x11F78); its own mov.l
 * pool continues @0x120F0..0x1217E.
 *
 * LITERAL POOL (values verified against roms/stock/60E0FC00.bin):
 *   0x12092 0xB594   (mov.w -> f32 @0xFFFFB594, RPM, y/x of the 3D maps)
 *   0x12094 0xC0D8   (mov.w -> f32 @0xFFFFC0D8, load, x of the 3D maps)
 *   0x12096 0xA9FC   (mov.w -> f32 @0xFFFFA9FC, temp, x of the temp maps)
 *   0x12098 0xA7AC   (mov.w -> f32 @0xFFFFA7AC, x of the 6-pt RPM map)
 *   0x1209C 0xCC2C   (mov.w -> u8 gate @0xFFFFCC2C)
 *   0x120A0 0xA5F8   (mov.w -> f32 output @0xFFFFA5F8)
 *   0x120F0 0x00067930 (mov.l -> TwoDLookup desc, 6-pt RPM map)
 *   0x120F4 0xFFFFA618 (mov.l -> f32 output @0xFFFFA618)
 *   0x120F8 0x00067990 (mov.l -> ThreeDLookup desc, 8x7)
 *   0x120FC 0xFFFFA61C (mov.l -> f32 output @0xFFFFA61C)
 *   0x12100 0x00067944 (mov.l -> TwoDLookup desc, 9-pt temp map)
 *   0x12104 0xFFFFA624 (mov.l -> f32 output @0xFFFFA624)
 *   0x12108 0x0006DA64 (mov.l -> f32 0.0, A5F8 base addend)
 *   0x1210C 0xFFFFA600 (mov.l -> f32 output @0xFFFFA600)
 *   0x12110 0x0006DA68 (mov.l -> f32 80.0, clamp when CC2C == 0)
 *   0x12114/0x12116 0x0006DA6C (mov.l -> f32 11.0, clamp when CC2C != 0)
 *   0x12160 0x0006DA6C (mov.l -> f32 11.0, CC2C!=0 branch)
 *   0x12164 0x000679AC (mov.l -> ThreeDLookup desc, 20x18)
 *   0x12168 0xFFFFA620 (mov.l -> f32 output @0xFFFFA620)
 *   0x1216C 0x000679DC (mov.l -> ThreeDLookup desc, 4x3 f32 cells)
 *   0x12170 0xFFFFA628 (mov.l -> f32 output @0xFFFFA628)
 *   0x12174 0x000023F4 (mov.l -> minValue helper @0x23F4)
 *   0x12178 0x0006DA70 (mov.l -> f32 0.0, A5F0 addend)
 *   0x1217C 0x000023E4 (mov.l -> saturateLow helper @0x23E4)
 * RAM r/w: reads A7AC, B594, C0D8, A9FC, CC2C; writes A618, A61C, A624,
 *   A5F8, A600, A620, A628, A5F0 (all f32) + the task-stack window.
 * ROM read: descriptor tables @0x67930/0x67990/0x67944/0x679AC/0x679DC
 *   (+ their axis/value tables in 0x6DAC4..0x6E064) and the f32 constants
 *   @0x6DA64/0x6DA68/0x6DA6C/0x6DA70.
 * Sub-calls: TwoDLookup @0x2068 (x2), ThreeDLookup @0x20DC (x3), minValue
 *   @0x23F4 (x1), saturateLow @0x23E4 (x1).
 * TWIN (structural, byte-for-byte same skeleton): calculateLeadingTimingBase
 *   @0x11F78 (c/calculateLeadingTimingBase_0x11F78.c).  Differences ONLY:
 *   +0x0C-shifted RAM outputs (A618..A628 vs leading A604..A614), descriptors
 *   0x67930/0x67990/0x67944/0x679AC/0x679DC vs 0x67908/0x67958/0x6791C/
 *   0x67974/0x679C8, ROM constants 0x6DA64/0x6DA68/0x6DA6C/0x6DA70 vs
 *   0x6DA54/0x6DA58/0x6DA5C/0x6DA60, outputs A5F8/A5F0 vs A5F4/A5EC, and the
 *   6-pt RPM map axis (trailing 1890 vs leading 1880 at the 5th breakpoint).
 *   The clamp when CC2C != 0 is 11.0 (trailing) vs 16.0 (leading).
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

#define OUT_A618  (*(volatile float *)0xFFFFA618)
#define OUT_A61C  (*(volatile float *)0xFFFFA61C)
#define OUT_A624  (*(volatile float *)0xFFFFA624)
#define OUT_A5F8  (*(volatile float *)0xFFFFA5F8)
#define OUT_A600  (*(volatile float *)0xFFFFA600)
#define OUT_A620  (*(volatile float *)0xFFFFA620)
#define OUT_A628  (*(volatile float *)0xFFFFA628)
#define OUT_A5F0  (*(volatile float *)0xFFFFA5F0)

/* ---- ROM calibration constants ---- */
#define ROM_F_6DA64 (*(const float *)0x0006DA64)  /* 0.0  A5F8 base addend */
#define ROM_F_6DA68 (*(const float *)0x0006DA68)  /* 80.0 clamp when CC2C==0 */
#define ROM_F_6DA6C (*(const float *)0x0006DA6C)  /* 11.0 clamp when CC2C!=0 */
#define ROM_F_6DA70 (*(const float *)0x0006DA70)  /* 0.0  A5F0 addend      */

#define DESC_67930 ((const Map1D *)0x00067930)  /* 6-pt RPM map   -> A618 */
#define DESC_67944 ((const Map1D *)0x00067944)  /* 9-pt temp map  -> A624 */
#define DESC_67990 ((const Map2D *)0x00067990)  /* 8x7 load x RPM -> A61C */
#define DESC_679AC ((const Map2D *)0x000679AC)  /* 20x18 load x RPM -> A620 */
#define DESC_679DC ((const Map2D *)0x000679DC)  /* 4x3 RPM x temp f32 -> A628 */

/* ---- verified leaves (see c/2DLookup.c, c/3dLookup.c, c/math_primitives.c) ---- */
extern float TwoDLookup(const Map1D *m, float x);            /* 0x2068 */
extern float ThreeDLookup(const Map2D *m, float x, float y); /* 0x20DC */
extern float minValue(float a, float b);                     /* 0x23F4 */
extern float saturateLow(float sig, float lower);            /* 0x23E4 */

void calculateTrailingTimingBase_0x1202A(void)
{
    /* ---- lookup group 1 ---- */
    OUT_A618 = TwoDLookup(DESC_67930, RAM_A7AC);                 /* 6-pt RPM map */
    OUT_A61C = ThreeDLookup(DESC_67990, RAM_C0D8, RAM_B594);     /* 8x7 load x RPM */
    OUT_A624 = TwoDLookup(DESC_67944, RAM_A9FC);                 /* 9-pt temp map */

    /* ---- A5F8 = 0.0 - A61C*A624 + A618 ---- */
    OUT_A5F8 = (ROM_F_6DA64 - (OUT_A61C * OUT_A624)) + OUT_A618;

    /* ---- advance clamp A600 ---- */
    OUT_A600 = (RAM_CC2C == 0) ? ROM_F_6DA68 : ROM_F_6DA6C;

    /* ---- lookup group 2 ---- */
    OUT_A620 = ThreeDLookup(DESC_679AC, RAM_C0D8, RAM_B594);     /* 20x18 load x RPM */
    OUT_A628 = ThreeDLookup(DESC_679DC, RAM_B594, RAM_A9FC);     /* 4x3 RPM x temp */

    /* ---- A5F0 = saturateLow( 0.0 + min(A620, A600), A628 ) ---- */
    OUT_A5F0 = saturateLow(ROM_F_6DA70 + minValue(OUT_A620, OUT_A600),
                           OUT_A628);
}
