/* dscRelatedTiming_0x18D3C.c
 *
 * ROM: 60E0FC00 | Address: 0x18D3C | Size: 0x200 (512) bytes actual code+pool
 *       code 0x18D3C..0x18F28 (rts @0x18F26, delay mov.l @r15+,r14 @0x18F28);
 *       literal pool @0x18F2A..0x18F3A; next function starts @0x18F3C.
 *       VERIFIED vs the ROM emulator (0 mismatches, 500000 random inputs across
 *       5 seeds, c/tests/test_dscRelatedTiming_0x18D3C.py).
 *
 * ENTRY VERIFICATION: 0x18D3C matches the CSV start.  The ONLY 32-bit
 * reference in the whole ROM is the function-pointer slot @0x14448 of the
 * engineControlCalculateTiming dispatcher (0x141FC) table — right next to the
 * derate family (0x1441C = calculateKnockTimingDerateConditionEvents @0x178E8,
 * 0x14428/0x1442C = idleLeading/TrailingTimingCorrection, 0x1444C/0x14450 =
 * the cranking-timing pair) — so the CSV address IS the real entry point.  The
 * preceding bytes @0x18D00..0x18D3A are the previous function's literal pool
 * (no fall-through: it ends with its own rts).  Valid prologue (mov.l r14..r9
 * pushes + 4x fmov.s + sts.l pr, add #0xF0).
 *
 * RANGE: the CSV row (0x018D3C,0x018F3C) is CORRECT — code runs to rts @0x18F26
 * (delay @0x18F28), the mov.w/mov.l literal pool @0x18F2A..0x18F3A belongs to
 * us, and the next function (byte-clears A9C1..A9CC, @0x18F3C) starts exactly
 * at the CSV end.
 *
 * SEMANTICS (instruction-for-instruction, see disasm): DSC-related timing
 * derate writer — publishes two derate values (A98C "lead", A998 "trail"),
 * their maxes with a third lookup, and a comparison flag, driven by the u8
 * mode selector RAM8@0xFFFFBCB3 (like the spark lead/trail split @0x19220):
 *
 *   A98C (f32@A98C):
 *     mode == 4                          -> BCC4
 *     else |BCC0| <= 1e-5 (0x2440 guard) -> -20.0
 *     else                               -> BCC4 - sqrt(max(X,0)/BCC0), X =
 *        (BCE8+BCEC+BCC8) + ((BCD8-BCA8-BCE4) - base) * 4/(4-mode) - BCD8,
 *        base = (A9A0 > A99C) ? BAFC : BC0C   (sqrt chain @0x46CC)
 *   A998 (f32@A998) by selector:
 *     mode == 1 -> 0.5*byte@0x6E8DC - 50      (@0x2500)
 *     mode == 2 -> ThreeDLookup(desc 0x67D58, load, RPM)   (20x18 u8 cells)
 *     mode == 3 -> 0.5*byte@0x6E8DD - 50      (@0x2500)
 *     else      -> ThreeDLookup(desc 0x67D3C, load, RPM)
 *   split = ThreeDLookup(desc 0x67D74, load, RPM)   (20x18 u8 cells)
 *   A994 (f32) = max(A98C, A998)                         (helper 0x23E4)
 *   A990 (f32) = max(A98C + split, A998 + split)
 *   A9AC (u8)  = (A98C > A998) ? 0 : 1
 *
 * 0x2440 = window-out leaf: r0 = 1 iff |fr4 - fr5| > fr6.  The branch is
 * `tst r4,r4` (T = r4==0) + bf/s, so the -20 default fires when the guard
 * returns 0 (|BCC0| <= 1e-5) and the division runs when it returns 1.
 * 0x46CC = the sqrt chain (frexp@0x48C8 -> sqrt@0x4740 -> ldexp@0x481C, same
 * bytes as c/checkFloatValidity.c in this bank): NaN result -> fault code
 * 0x044D written to RAM32@0xFFFF768C (this bank's sink address).
 *
 * r0 on return is undefined (scratch, clobbered by every helper leaf).
 *
 * RAM r/w: reads B594 (RPM), C0D8 (load), BCC0/BCC4/BCC8/BC0C/BAFC/BCD8/BCA8/
 *   BCE4/BCE8/BCEC/A9A0/A99C (f32), BCB3 (u8 mode); writes A98C/A998/A994/A990
 *   (f32), A9AC (u8), and on the 0x46CC NaN path RAM32@0xFFFF768C = 0x044D.
 * ROM read: bytes @0x6E8DC/@0x6E8DD, f32 constants @0x18E84 (1e-5) / @0x18E94
 *   (-20.0) / @0x18E98 (4.0) / @0x18EA0 (0.5) / @0x18EA4 (-50.0), descriptor
 *   tables @0x67D3C/0x67D58/0x67D74 (+ their axis/value tables).
 * Sub-calls: window_out_0x2440 (x1), f32_to_byte_0x2500 (x1 + selector x2),
 *   max_0x23E4 (x2), checkFloatValidity_0x46CC (x1, sqrt), ThreeDLookup
 *   @0x20DC (x3).
 */
#include <stdint.h>
#include <math.h>

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
#define RAM_B594  (*(volatile float *)0xFFFFB594)  /* RPM  (fr13, 3D y) */
#define RAM_C0D8  (*(volatile float *)0xFFFFC0D8)  /* load (fr14, 3D x) */
#define RAM_BCC0  (*(volatile float *)0xFFFFBCC0)  /* sqrt divisor / guard */
#define RAM_BCC4  (*(volatile float *)0xFFFFBCC4)  /* A98C base / stack[0] */
#define RAM_BCC8  (*(volatile float *)0xFFFFBCC8)  /* sum component / stack[C] */
#define RAM_BC0C  (*(volatile float *)0xFFFFBC0C)  /* base select default */
#define RAM_BAFC  (*(volatile float *)0xFFFFBAFC)  /* base select high  */
#define RAM_BCD8  (*(volatile float *)0xFFFFBCD8)  /* sum subtract / stack[4] */
#define RAM_BCA8  (*(volatile float *)0xFFFFBCA8)  /* base subtract */
#define RAM_BCE4  (*(volatile float *)0xFFFFBCE4)  /* base subtract */
#define RAM_BCE8  (*(volatile float *)0xFFFFBCE8)  /* sum component */
#define RAM_BCEC  (*(volatile float *)0xFFFFBCEC)  /* sum component */
#define RAM_A9A0  (*(volatile float *)0xFFFFA9A0)  /* base-select compare */
#define RAM_A99C  (*(volatile float *)0xFFFFA99C)  /* base-select compare */
#define RAM_BCB3  (*(volatile uint8_t *)0xFFFFBCB3) /* mode selector */

#define OUT_A98C  (*(volatile float *)0xFFFFA98C)
#define OUT_A998  (*(volatile float *)0xFFFFA998)
#define OUT_A994  (*(volatile float *)0xFFFFA994)
#define OUT_A990  (*(volatile float *)0xFFFFA990)
#define OUT_A9AC  (*(volatile uint8_t *)0xFFFFA9AC)
#define RAM_768C  (*(volatile uint32_t *)0xFFFF768C) /* 0x46CC fault sink */

/* ---- ROM calibration constants ---- */
#define ROM_B_6E8DC (*(const uint8_t *)0x0006E8DC)  /* mode==1 offset byte */
#define ROM_B_6E8DD (*(const uint8_t *)0x0006E8DD)  /* mode==3 offset byte */
#define ROM_F_EPS   (*(const float *)0x00018E84)    /* 1e-5  0x2440 tol    */
#define ROM_F_M20   (*(const float *)0x00018E94)    /* -20.0 A98C default  */
#define ROM_F_4     (*(const float *)0x00018E98)    /* 4.0   scale base    */
#define ROM_F_050   (*(const float *)0x00018EA0)    /* 0.5   byte scale    */
#define ROM_F_M50   (*(const float *)0x00018EA4)    /* -50.0 byte offset   */

#define DESC_67D3C ((const Map2D *)0x00067D3C)  /* A998 "else"  map */
#define DESC_67D58 ((const Map2D *)0x00067D58)  /* A998 mode==2 map */
#define DESC_67D74 ((const Map2D *)0x00067D74)  /* A990/A994 split map */

/* ---- verified leaves (see c/2DLookup.c, c/3dLookup.c, c/math_primitives.c,
 *      c/checkFloatValidity.c, c/calc_combustion_chamber_temp_0x12938.c) ---- */
extern int      window_out_0x2440(float x, float center, float tol);   /* 0x2440 */
extern float    f32_to_byte_0x2500(uint8_t raw, float mult, float add);/* 0x2500 */
extern float    ThreeDLookup(const Map2D *m, float x, float y);        /* 0x20DC */
extern float    checkFloatValidity(float value);                       /* 0x46CC */
extern float    saturateLow(float sig, float lower);                   /* 0x23E4 (max) */

void dscRelatedTiming_0x18D3C(void)
{
    uint8_t mode = RAM_BCB3;
    float   rpm  = RAM_B594;
    float   load = RAM_C0D8;
    float   a98c, a998, split;

    /* ---- A98C (leading derate) ---- */
    if (mode == 4) {
        a98c = RAM_BCC4;
    } else if (window_out_0x2440(RAM_BCC0, 0.0f, ROM_F_EPS) == 0) {
        /* |BCC0| <= 1e-5 -> default (division is guarded) */
        a98c = ROM_F_M20;
    } else {
        float base = (RAM_A9A0 > RAM_A99C) ? RAM_BAFC : RAM_BC0C;
        float fr15 = ((RAM_BCD8 - RAM_BCA8) - RAM_BCE4) - base;
        float byf  = f32_to_byte_0x2500(mode, 1.0f, 0.0f);   /* = (float)mode */
        fr15 = fr15 * (ROM_F_4 / (ROM_F_4 - byf));
        float s   = ((RAM_BCE8 + RAM_BCEC) + RAM_BCC8) + fr15 - RAM_BCD8;
        float m   = saturateLow(s, 0.0f) / RAM_BCC0;         /* max(s,0) */
        a98c = RAM_BCC4 - checkFloatValidity(m);             /* sqrt chain */
    }
    OUT_A98C = a98c;

    /* ---- A998 (trailing derate) by selector ---- */
    switch (mode) {
    case 1:  a998 = f32_to_byte_0x2500(ROM_B_6E8DC, ROM_F_050, ROM_F_M50); break;
    case 2:  a998 = ThreeDLookup(DESC_67D58, load, rpm);                  break;
    case 3:  a998 = f32_to_byte_0x2500(ROM_B_6E8DD, ROM_F_050, ROM_F_M50); break;
    default: a998 = ThreeDLookup(DESC_67D3C, load, rpm);                  break;
    }
    OUT_A998 = a998;

    /* ---- split lookup + clamps ---- */
    split = ThreeDLookup(DESC_67D74, load, rpm);

    OUT_A994 = saturateLow(a98c, a998);                    /* max(A98C,A998) */
    OUT_A990 = saturateLow(a98c + split, a998 + split);    /* max(A98C+sp, A998+sp) */

    /* fcmp/gt A998,A98C: T=(A98C>A998); A9AC = T ? 0 : 1 */
    OUT_A9AC = (a98c > a998) ? 0 : 1;
}
