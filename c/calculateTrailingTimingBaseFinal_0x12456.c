/* calculateTrailingTimingBaseFinal_0x12456.c
 *
 * ROM: 60E0FC00 | Address: 0x12456 | Size: 0xE6 (230) bytes per CSV range
 * 0x12456..0x1253C.  Code runs to the `rts` @0x12538 (delay mov.l @r15+,r14
 * @0x1253A); the next function (calculateLeadingDerateRetard) starts at the
 * CSV end 0x1253C.  The CSV range is CORRECT — no correction needed.
 *
 * ENTRY VERIFICATION: 0x12456 matches the symbols CSV start.  Valid entry:
 * opens with the same prologue as the leading twin.  The preceding function
 * calculateLeadingTimingBaseFinal (0x12362) ends with `rts` @0x12452 (delay
 * @0x12454), so no fall-through into us; no incoming branches into the middle
 * (whole-ROM scan found none).  Called via the function-pointer slot @0x144D4
 * of the engineControlCalculateTiming dispatcher (0x141FC) dispatch table —
 * the slot immediately before calculateTrailingTimingDerateCompensated
 * @0x144D8 and after calculateTrailingDerateRetard @0x144D0.  The ROM literal
 * @0x144D4 is the ONLY 32-bit reference to 0x12456 in the binary.  The CSV
 * address IS the real entry point.
 *
 * SEMANTICS: byte-for-byte the structural twin of calculateLeadingTimingBaseFinal
 * (0x12362) with shifted RAM addresses and its own cal constants.  The body is
 * transcribed from the actual disassembly (NOT copied from the leading twin):
 *
 *   fr4 = f32@FFFFB594            ; raw input  (identical to leading)
 *   fr5 = f32@FFFFA7AC + 10000.0f ; high       (identical to leading)
 *   hysteresis flag u8@FFFFA65D  (write, retain band) — same shape as leading
 *   x = f32@FFFFA650
 *   if u8@FFFFAAC6 == 1 && FLAG == 0:  x = saturateLow_0x23E4(x - 0.05f, 0.0f)
 *   else:                              x = minValue_0x23F4(x + 1.0f, 1.0f)
 *   f32@FFFFA650 = x
 *   S = (f32@FFFFA5F8 + f32@FFFFA70C) + f32@FFFFC9A0
 *   acc = x * f32@FFFFA5F0
 *   acc = fmaf(1.0f - x, S, acc)
 *   acc = acc + f32@FFFFA784   - f32@FFFFA77C
 *   f32@FFFFA64C = acc
 *
 * TWIN COMPARISON (leading 0x12362 vs trailing 0x12456) — exact differences,
 * verified byte-by-byte:
 *   flag byte        u8@FFFFA65C            u8@FFFFA65D   (+1)
 *   ramp value       f32@FFFFA640           f32@FFFFA650  (+0x10)
 *   output           f32@FFFFA63C           f32@FFFFA64C  (+0x10)
 *   ramp-down const  0x6E09C (0.05)         0x6E0D0 (0.05)  (own cal cell)
 *   ramp-up const    0x6E0A0 (1.0)          0x6E0D4 (1.0)   (own cal cell)
 *   lerp S terms     A5F4 + A708 + C99C     A5F8 + A70C + C9A0
 *   lerp x term      A5EC                   A5F0
 *   lerp addend      A780                   A784
 *   lerp subtrahend  A778                   A77C
 *   shared: f32@B594, f32@A7AC, u8@AAC6, ROM 0x6E0B4 (10000.0),
 *   0x6E0B8 (100.0), helper 0x23E4/0x23F4, hysteresis shape, r0 result.
 * The two functions share a literal pool physically inside the leading CSV
 * range (@0x124B2..0x124F0); the trailing twin also reads its own pool at
 * @0x125FC..0x12606 (mov.w) and @0x12628..0x12634 (mov.l).
 *
 * LITERAL POOL (values verified against roms/stock/60E0FC00.bin):
 *   mov.w 0x124C0=0xB594, 0x124C2=0xA7AC, 0x124B2=0xAAC6 (shared),
 *   0x125FC=0xA70C, 0x125FE=0xA5F8, 0x12600=0xC9A0, 0x12602=0xA5F0,
 *   0x12604=0xA784, 0x12606=0xA77C (own)
 *   mov.l 0x124E4=0x6E0B4, 0x124E8=0xFFFFA65D, 0x124C4=0x6E0B8,
 *   0x124EC=0xFFFFA650, 0x124F0=0x6E0D0, 0x124D4=0x23E4 (shared),
 *   0x12628=0x6E0D4, 0x1262C=0x23F4, 0x12630=0xFFFFA64C (own)
 * RAM r/w: reads B594, A7AC, AAC6, A65D, A650, A70C, A5F8, C9A0, A5F0, A784,
 * A77C, A64C; writes A65D (hysteresis), A650 (ramp), A64C (output).
 * ROM read: consts 0x6E0B4 (10000.0), 0x6E0B8 (100.0), 0x6E0D0 (0.05),
 * 0x6E0D4 (1.0).
 * Sub-calls: saturateLow @0x23E4 (x1) and minValue @0x23F4 (x1); neither
 * writes r0.  r0 on return: byte@0xFFFFAAC6 & 0xFF.
 *
 * VERIFIED against the SH-2 emulator (tools/sh2emu.py, 60E0FC00.bin) in
 * c/tests/test_calculateTrailingTimingBaseFinal_0x12456.py — 0 mismatches over
 * 5 seeds x 100000 iterations (byte-exact full post-call RAM overlay + r0).
 */
#include <stdint.h>
#include <math.h>

/* ---- RAM globals (mov.w literals sign-extend to 0xFFFFxxxx) ---- */
#define RAM_B594   (*(volatile float *)0xFFFFB594)  /* f32 input (fr4)          */
#define RAM_A7AC   (*(volatile float *)0xFFFFA7AC)  /* f32 threshold base        */
#define G_AAC6     (*(volatile uint8_t *)0xFFFFAAC6)  /* u8 gateway (==1)        */
#define FLAG_A65D  (*(volatile uint8_t *)0xFFFFA65D)  /* u8 hysteresis flag r+w  */
#define FIL_A650   (*(volatile float *)0xFFFFA650)  /* f32 ramp value r+w        */
#define S1_A70C    (*(volatile float *)0xFFFFA70C)  /* f32 lerp S term 1         */
#define S2_A5F8    (*(volatile float *)0xFFFFA5F8)  /* f32 lerp S term 2         */
#define S3_C9A0    (*(volatile float *)0xFFFFC9A0)  /* f32 lerp S term 3         */
#define T_A5F0     (*(volatile float *)0xFFFFA5F0)  /* f32 lerp x term           */
#define U_A784     (*(volatile float *)0xFFFFA784)  /* f32 lerp addend           */
#define V_A77C     (*(volatile float *)0xFFFFA77C)  /* f32 lerp subtrahend       */
#define OUT_A64C   (*(volatile float *)0xFFFFA64C)  /* f32 output                */

/* ---- ROM calibration constants ---- */
#define CAL_HI_6E0B4   (*(const float *)0x0006E0B4)   /* f32 10000.0 high offset */
#define CAL_BAND_6E0B8 (*(const float *)0x0006E0B8)   /* f32 100.0 band width    */
#define CAL_DEC_6E0D0  (*(const float *)0x0006E0D0)   /* f32 0.05 ramp-down step */
#define CAL_ONE_6E0D4  (*(const float *)0x0006E0D4)   /* f32 1.0 ramp-up addend  */

/* ---- External helpers (in ROM, verified separately) ---- */
extern float saturateLow(float sig, float lower);  /* @0x23E4 max(sig, lower); NaN sig -> lower */
extern float minValue(float a, float b);           /* @0x23F4 min(a, b);       NaN a   -> b     */

void calculateTrailingTimingBaseFinal_0x12456(void)
{
    float fr4 = RAM_B594;                     /* fmov.s @r2,fr4 @0x1245E     */
    float fr5 = RAM_A7AC + CAL_HI_6E0B4;      /* fadd fr3,fr5 -> high         */

    /* hysteresis flag u8@FFFFA65D (fr4>=high -> 1; [low,high) retain; <low ->0) */
    if (fr5 > fr4) {                          /* fr4 < high                   */
        float low = fr5 - CAL_BAND_6E0B8;     /* fsub fr2,fr5 -> low          */
        if (low > fr4)                        /* fr4 < low                    */
            FLAG_A65D = 0;                    /* mov.b r0,@r4 @0x12486        */
        /* else retain (pre-call A65D kept) */
    } else {
        FLAG_A65D = 1;                        /* mov.b r1,@r4 @0x12476       */
    }

    /* ramp rate-limit the per-tap value f32@A650 toward 0 / 1 */
    {
        float x = FILT_A650;                  /* fmov.s @r14,fr4 @0x12496 (delay) */
        float v;
        if (G_AAC6 == 1 && FLAG_A65D == 0) {  /* cmp/eq #1 ; tst ; bf/s x2     */
            v = saturateLow(x - CAL_DEC_6E0D0, 0.0f);   /* fsub @0x124A8, fldi0 */
        } else {
            v = minValue(x + CAL_ONE_6E0D4, 1.0f);        /* fadd @0x124FC, fmov fr15 */
        }
        FILT_A650 = v;                      /* fmov.s fr0,@r14 @0x12502     */
    }

    /* trailing lerp into f32@A64C — order/rounding transcribed from disasm */
    {
        float x   = FILT_A650;                /* fmov.s @r14,fr2 @0x12510   */
        float S   = (S2_A5F8 + S1_A70C) + S3_C9A0;  /* fadd x2 @0x1250E/@0x12516 */
        float comp = 1.0f - x;               /* fsub fr2,fr15 @0x1251A      */
        float acc = x * T_A5F0;             /* fmul fr0,fr2 @0x12522       */
        acc = fmaf(comp, S, acc);            /* fmac fr0,fr3,fr2 @0x12528   */
        acc = acc + U_A784;                   /* fadd fr3,fr2 @0x1252E       */
        acc = acc - V_A77C;                   /* fsub fr1,fr2 @0x12530       */
        OUT_A64C = acc;                       /* fmov.s fr2,@r3 @0x12532    */
    }
}