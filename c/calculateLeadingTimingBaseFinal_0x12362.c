/* calculateLeadingTimingBaseFinal_0x12362.c
 *
 * ROM: 60E0FC00 | Address: 0x12362 | Size: 0xF4 (244) bytes per CSV range
 * 0x12362..0x12456.  Code runs to the `rts` @0x12452 (delay mov.l @r15+,r14
 * @0x12454); the trailing twin calculateTrailingTimingBaseFinal starts at the
 * CSV end 0x12456.  The CSV range is CORRECT (function code to 0x12454, next
 * function exactly at 0x12456) — no phantom rows to remove.
 *
 * ENTRY VERIFICATION: 0x12362 matches the symbols CSV start.  Valid entry:
 * opens with the standard prologue (`mov.l r14,@-r15 ; fmov.s fr15,@-r15 ;
 * sts.l pr,@-r15`).  The preceding function calculateTrailingTimingDerateCompensated
 * (0x12342) ends with `rts` @0x1235E (delay nop @0x12360), so there is no
 * fall-through into us; no incoming branches into the middle (a whole-ROM scan
 * of branch targets/branches into 0x12362..0x12456 found none — the only brute
 * hits were in data pools that decode as bra-like opcodes).  Called via the
 * function-pointer slot @0x144C0 of the engineControlCalculateTiming dispatcher
 * (0x141FC) dispatch table (immediately precedes the 0x121A4 slot @0x144C8).
 * The ROM literal @0x144C0 is the ONLY 32-bit reference to 0x12362 in the
 * binary.  The CSV address IS the real entry point.
 *
 * SEMANTICS (instruction-for-instruction, see disasm): the leading-timing
 * per-rotor "base final" ramp writer — structural twin of
 * calculateTrailingTimingBaseFinal (0x12456).  It computes:
 *
 *   fr5 = f32@B594                                            ; raw input (fr4)
 *   fr5 = f32@A7AC + 10000.0f                                 // high threshold
 *   // hysteresis flag u8@FFFFA65C (write, retain band):
 *   FLAG  = (fr5 > fr4) ? ( ((high-100) > fr4) ? 0 : retain ) : 1
 *            i.e. fr4 >= high -> 1 ; fr4 < high-100 -> 0 ; [high-100,high) retain
 *
 *   x = f32@FFFFA640                                          // per-rotor ramp
 *   if u8@FFFFAAC6 == 1 && FLAG == 0:       // ramp down toward 0
 *       x = saturateLow_0x23E4(x - 0.05f, 0.0f)              // 0x23E4 max leaf
 *   else:                                   // ramp up toward 1
 *       x = minValue_0x23F4(x + 1.0f, 1.0f)                 // 0x23F4 min leaf
 *   f32@FFFFA640 = x
 *
 *   S = (f32@FFFFA5F4 + f32@FFFFA708) + f32@FFFFC99C
 *   acc = x * f32@FFFFA5EC
 *   acc = fmaf(1.0f - x, S, acc)                        // fmac fr0,fr3,fr2
 *   acc = acc + f32@FFFFA780   - f32@FFFFA778
 *   f32@FFFFA63C = acc
 *
 * NaN semantics (matches the emulator byte-for-byte): fcmp/gt clears T on NaN,
 * so fr4>=high sets flag=1; the low check only runs when fr5>fr4 was true (both
 * finite), so the retain band is only reachable for real inputs.  The 0x23E4 /
 * 0x23F4 leaves are pure fcmp/select — a NaN x reads as "the other operand
 * wins" (NaN >= 0 -> 0 ; NaN < 1 -> 1).
 *
 * LITERAL POOL (values verified against roms/stock/60E0FC00.bin): the function
 * reads a shared mov.w pool @0x124B2..0x124C2 (0xAAC6 gateway, 0xB594 input,
 * 0xA7AC threshold base, and the trailing twin's mov.w entries) and a shared
 * mov.l pool @0x124C4..0x124E0 (0x6E0B4, 0xFFFFA65C, 0x0006E0B8, 0xFFFFA640,
 * 0x6E09C, 0x000023E4, 0x6E0A0, 0x000023F4, 0xFFFFA63C).  Both pools are
 * physically inside the CSV range but shared with the trailing twin 0x12456.
 * RAM r/w: reads B594, A7AC, AAC6, A65C, A640, A708, A5F4, C99C, A5EC, A780,
 * A778, A63C; writes A65C (hysteresis), A640 (ramp), A63C (output).
 * ROM read: consts 0x6E0B4 (10000.0), 0x6E0B8 (100.0), 0x6E09C (0.05),
 * 0x6E0A0 (1.0).
 * Sub-calls: saturateLow @0x23E4 (x1) and minValue @0x23F4 (x1).  SH-2E conv:
 * float args fr4/fr5, float result fr0; neither leaf writes r0.
 * r0 on return: byte@0xFFFFAAC6 & 0xFF (the mov.b/extu.b at the gateway check).
 *
 * VERIFIED against the SH-2 emulator (tools/sh2emu.py, 60E0FC00.bin) in
 * c/tests/test_calculateLeadingTimingBaseFinal_0x12362.py — 0 mismatches over
 * 5 seeds x 100000 iterations (byte-exact full post-call RAM overlay + r0).
 */
#include <stdint.h>
#include <math.h>

/* ---- RAM globals (mov.w literals sign-extend to 0xFFFFxxxx) ---- */
#define RAM_B594   (*(volatile float *)0xFFFFB594)  /* f32 input (fr4)          */
#define RAM_A7AC   (*(volatile float *)0xFFFFA7AC)  /* f32 threshold base        */
#define G_AAC6     (*(volatile uint8_t *)0xFFFFAAC6)  /* u8 gateway (==1)        */
#define FLAG_A65C  (*(volatile uint8_t *)0xFFFFA65C)  /* u8 hysteresis flag r+w  */
#define FIL_A640   (*(volatile float *)0xFFFFA640)  /* f32 ramp value r+w        */
#define S1_A708    (*(volatile float *)0xFFFFA708)  /* f32 lerp S term 1         */
#define S2_A5F4    (*(volatile float *)0xFFFFA5F4)  /* f32 lerp S term 2         */
#define S3_C99C    (*(volatile float *)0xFFFFC99C)  /* f32 lerp S term 3         */
#define T_A5EC     (*(volatile float *)0xFFFFA5EC)  /* f32 lerp x term           */
#define U_A780     (*(volatile float *)0xFFFFA780)  /* f32 lerp addend           */
#define V_A778     (*(volatile float *)0xFFFFA778)  /* f32 lerp subtrahend       */
#define OUT_A63C   (*(volatile float *)0xFFFFA63C)  /* f32 output                */

/* ---- ROM calibration constants ---- */
#define CAL_HI_6E0B4   (*(const float *)0x0006E0B4)   /* f32 10000.0 high offset */
#define CAL_BAND_6E0B8 (*(const float *)0x0006E0B8)   /* f32 100.0 band width    */
#define CAL_DEC_6E09C  (*(const float *)0x0006E09C)   /* f32 0.05 ramp-down step */
#define CAL_ONE_6E0A0  (*(const float *)0x0006E0A0)   /* f32 1.0 ramp-up addend  */

/* ---- External helpers (in ROM, verified separately) ---- */
extern float saturateLow(float sig, float lower);  /* @0x23E4 max(sig, lower); NaN sig -> lower */
extern float minValue(float a, float b);           /* @0x23F4 min(a, b);       NaN a   -> b     */

void calculateLeadingTimingBaseFinal_0x12362(void)
{
    float fr4 = RAM_B594;                     /* fmov.s @r2,fr4 @0x1234A     */
    float fr5 = RAM_A7AC + CAL_HI_6E0B4;      /* fadd fr3,fr5 -> high         */

    /* hysteresis flag u8@FFFFA65C (fr4>=high -> 1; [low,high) retain; <low ->0) */
    if (fr5 > fr4) {                          /* fr4 < high                   */
        float low = fr5 - CAL_BAND_6E0B8;     /* fsub fr2,fr5 -> low          */
        if (low > fr4)                        /* fr4 < low                    */
            FLAG_A65C = 0;                    /* mov.b r0,@r4 @0x123E2        */
        /* else retain (pre-call A65C kept) */
    } else {
        FLAG_A65C = 1;                        /* mov.b r1,@r4 @0x12382       */
    }

    /* ramp rate-limit the per-tap value f32@A640 toward 0 / 1 */
    {
        float x = FILT_A640;                  /* fmov.s @r14,fr4 @0x123F2 (delay) */
        float v;
        if (G_AAC6 == 1 && FLAG_A65C == 0) {  /* cmp/eq #1 ; tst ; bf/s x2     */
            v = saturateLow(x - CAL_DEC_6E09C, 0.0f);   /* fsub @0x12404, fldi0 */
        } else {
            v = minValue(x + CAL_ONE_6E0A0, 1.0f);        /* fadd @0x12416, fmov fr15 */
        }
        FILT_A640 = v;                      /* fmov.s fr0,@r14 @0x1241C     */
    }

    /* leading lerp into f32@A63C — order/rounding transcribed from disasm */
    {
        float x   = FILT_A640;                /* fmov.s @r14,fr2 @0x1242C   */
        float S   = (S2_A5F4 + S1_A708) + S3_C99C;  /* fadd x2 @0x12426/@0x1242E */
        float comp = 1.0f - x;               /* fsub fr2,fr15 @0x12432      */
        float acc = x * T_A5EC;             /* fmul fr0,fr2 @0x1243A       */
        acc = fmaf(comp, S, acc);            /* fmac fr0,fr3,fr2 @0x12442   */
        acc = acc + U_A780;                   /* fadd fr3,fr2 @0x12446       */
        acc = acc - V_A778;                   /* fsub fr1,fr2 @0x1244A       */
        OUT_A63C = acc;                       /* fmov.s fr2,@r3 @0x1244C    */
    }
}