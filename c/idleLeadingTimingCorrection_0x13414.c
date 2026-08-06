/* idleLeadingTimingCorrection_0x13414.c
 *
 * ROM: 60E0FC00 | Address: 0x13414 | Size: 0x130 (304) bytes = code + pool
 *       code 0x13414..0x134F6 (rts @0x134F4, delay mov.l @r15+,r14 @0x134F6),
 *       literal pool 0x134F8..0x13542; the trailing twin 0x13544 starts
 *       exactly at the CSV end.  VERIFIED vs the ROM emulator (0 mismatches,
 *       c/tests/test_idleLeadingTimingCorrection_0x13414.py).
 *
 * ENTRY VERIFICATION: 0x13414 matches the CSV start (row 0x013414..0x013544 —
 * CORRECT, no widening needed).  Valid entry: opens with the standard prologue
 * (mov.l r14/r13 pushes + 2 fmov.s fr pushes + sts.l pr); the preceding
 * function calc_fuel_trim_correction_map (0x13368) ends rts @0x13410 (delay
 * @0x13412), so no fall-through into us.  The ROM function-pointer slot
 * @0x14428 of the engineControlCalculateTiming dispatcher (0x141FC) table is
 * the ONLY 32-bit reference to 0x13414 in the binary (the trailing twin sits
 * at the adjacent slot @0x1442C).  The CSV address IS the real entry point.
 *
 * SEMANTICS (instruction-for-instruction, see disasm): idle leading-timing
 * correction writer.  Builds an RPM error (f32@B594 - f32@B5A0), looks up a
 * 9-pt correction table in %RPM-error (-100..100 axis), gates the result on
 * the idle-condition byte AAC6 + RPM/load idle-range checks, and applies a
 * load-dependent saturate before publishing at f32@A708.  Step by step:
 *
 *   fr2  = ts(f32@B594 - f32@B5A0)          ; f32@A718 = fr2  (always)
 *   if u8@B580 == 0: desc = (u8@B588 == 0) ? 0x686AC : 0x686C0
 *   else:            desc = (u8@B586 == 1) ? 0x686AC : 0x686C0
 *   res  = TwoDLookup(desc, x = fr2)        ; f32@A710 = res (always)
 *   fr15 = res  if  u8@AAC6 == 1  &&  f32@726D4 (1500.0) > f32@B594
 *              && (f32@726D8 (1/1024) > f32@C030 || word@A424 >= word@726D0 (375))
 *   fr15 = 0.0 otherwise            (SH-2E fcmp/gt Fm,Fn sets T when Fn > Fm)
 *
 *   A720 gate (u8@FFFFA720), load = f32@C0D8 (fr14, preserved through the
 *   lookup — 0x2068 touches only fr0..fr5):
 *       if load >= f32@726DC (0.6):   u8@A720 = 1
 *       elif load <  ts(0.6 + f32@13530 (-0.045)):  u8@A720 = 0
 *       (else: u8@A720 unchanged)
 *   if u8@A720 == 1: fr15 = saturate(fr15, f32@726E0 (-2.8), f32@726E4 (0.7))
 *   f32@A708 = fr15 (always)
 *
 * r0 on return = u8@A720 & 0xFF: read back at 0x134CE (mov.b @A720,r0 +
 * extu.b); the 0x2404 saturate leaf is pure-FPU and never writes r0, so the
 * value survives to the rts on every path (verified vs the emulator).
 *
 * RAM r/w: reads B594 (f32), C0D8 (f32), B5A0 (f32), B580/B588/B586 (bytes),
 * AAC6 (byte), C030 (f32), A424 (word), A720 (byte); writes A718 (f32),
 * A710 (f32), A720 (byte, conditional), A708 (f32).
 * ROM read: 2D descriptors 0x686AC/0x686C0 (+ shared axis 0x726FC/0x7272C and
 *   u8 value tables 0x72720/0x72750, type-4 scaled-byte: value = u8*0.25-32.0,
 *   axis -100..100), f32 0x726D4/0x726D8/0x726DC/0x726E0/0x726E4, u16 0x726D0,
 *   pool f32 @0x13530 (-0.045).
 * Sub-calls: TwoDLookup @0x2068 (x1), saturate @0x2404 (x1).
 *
 * TWIN (structural, instruction-for-instruction identical skeleton):
 * idleTrailingTimingCorrection @0x13544 (c/idleTrailingTimingCorrection_0x13544.c).
 * Differences ONLY: RAM outputs +4 (A718/A710/A708 -> A71C/A714/A70C), gate
 * byte A720 -> A721, descriptors 0x686AC/0x686C0 -> 0x686D4/0x686E8 (value
 * tables 0x72720/0x72750 -> 0x72780/0x727B0, same axis -100..100), ROM const
 * block +0x14 (RPM gate 0x726D4->0x726E8, 1/1024 gate 0x726D8->0x726EC, load
 * thr 0x726DC->0x726F0, clamps 0x726E0/0x726E4 -> 0x726F4/0x726F8, word
 * 0x726D0->0x726D2, pool 0x13530->0x13660).  ALL values identical
 * (1500.0/0.009765625/0.6/-2.8/0.7/375/-0.045).
 *
 * Range  : 0x13414 .. 0x13544 (CSV end == twin start, no phantom rows)
 */
#include <stdint.h>

/* ---- RAM globals (mov.w literals sign-extend to 0xFFFFxxxx) ---- */
#define RAM_B594  (*(volatile float *)0xFFFFB594)  /* RPM            */
#define RAM_C0D8  (*(volatile float *)0xFFFFC0D8)  /* load           */
#define RAM_B5A0  (*(volatile float *)0xFFFFB5A0)  /* idle RPM target*/
#define RAM_B580  (*(volatile uint8_t *)0xFFFFB580)/* lookup sel byte*/
#define RAM_B588  (*(volatile uint8_t *)0xFFFFB588)/* lookup sel byte*/
#define RAM_B586  (*(volatile uint8_t *)0xFFFFB586)/* lookup sel byte*/
#define RAM_AAC6  (*(volatile uint8_t *)0xFFFFAAC6)/* idle gate byte */
#define RAM_C030  (*(volatile float *)0xFFFFC030)  /* idle gate f32  */
#define RAM_A424  (*(volatile uint16_t *)0xFFFFA424)/* idle gate word */
#define RAM_A720  (*(volatile uint8_t *)0xFFFFA720)/* saturate gate  */

#define OUT_A718  (*(volatile float *)0xFFFFA718)  /* RPM error       */
#define OUT_A710  (*(volatile float *)0xFFFFA710)  /* 2D lookup result*/
#define OUT_A708  (*(volatile float *)0xFFFFA708)  /* idle advance corr */

/* ---- ROM calibration constants ---- */
#define ROM_F_726D4 (*(const float *)0x000726D4)   /* 1500.0 RPM gate    */
#define ROM_F_726D8 (*(const float *)0x000726D8)   /* 0.009765625 (1/1024)*/
#define ROM_U16_726D0 (*(const uint16_t *)0x000726D0)/* 375 word gate    */
#define ROM_F_726DC (*(const float *)0x000726DC)   /* 0.6 load threshold */
#define ROM_F_13530 (*(const float *)0x00013530)   /* -0.045 pool f32    */
#define ROM_F_726E0 (*(const float *)0x000726E0)   /* -2.8 saturate lo   */
#define ROM_F_726E4 (*(const float *)0x000726E4)   /* 0.7 saturate hi    */

/* ---- 1-D lookup descriptor (20 bytes, big-endian SH-2E) — same as c/2DLookup.c */
typedef struct {
    uint16_t     count;    /* +0 */
    uint8_t      type;     /* +2 */
    uint8_t      _pad;     /* +3 */
    const float *axis;     /* +4 */
    const void  *values;   /* +8 */
    float        scale;    /* +12 */
    float        offset;   /* +16 */
} Map1D;

#define DESC_686AC ((const Map1D *)0x000686AC)  /* 9-pt %RPM-error map A  */
#define DESC_686C0 ((const Map1D *)0x000686C0)  /* 9-pt %RPM-error map B  */

/* ---- verified leaves ---- */
extern float TwoDLookup(const Map1D *m, float x);      /* 0x2068 */
extern float fpu_compare_and_select(float val, float lo, float hi);
/* @0x2404: clamp(val, lo, hi) */

void idleLeadingTimingCorrection_0x13414(void)
{
    float fr2 = RAM_B594 - RAM_B5A0;       /* fsub fr3,fr2 (single-precision) */
    float res, fr15;
    const Map1D *desc;

    OUT_A718 = fr2;

    /* ---- 2D lookup: B580==0 -> B588 picks, else B586==1 picks ---- */
    if (RAM_B580 == 0)
        desc = (RAM_B588 == 0) ? DESC_686AC : DESC_686C0;
    else
        desc = (RAM_B586 == 1) ? DESC_686AC : DESC_686C0;
    res = TwoDLookup(desc, fr2);
    OUT_A710 = res;

    /* ---- idle-gate: keep the correction only inside the idle window ----
     * The SH-2E fcmp/gt Fm,Fn sets T when Fn > Fm, so every comparison below
     * is written in that (constant-vs-register) direction.
     *   RPM < 1500.0 && (f32@C030 < 0.009765625 || word@A424 >= 375) ---- */
    if (RAM_AAC6 == 1 && ROM_F_726D4 > RAM_B594 &&
        (ROM_F_726D8 > RAM_C030 || RAM_A424 >= ROM_U16_726D0))
        fr15 = res;
    else
        fr15 = 0.0f;

    /* ---- load gate byte A720: 1 if load >= 0.6, 0 if load < 0.555,
     *      unchanged between (fr14 = load is preserved through the lookup,
     *      which only touches fr0..fr5) ---- */
    if (RAM_C0D8 < ROM_F_726DC) {
        if (RAM_C0D8 < ROM_F_726DC + ROM_F_13530)
            RAM_A720 = 0;
    } else {
        RAM_A720 = 1;
    }

    /* ---- saturate into [-2.8, 0.7] when the load gate is set ---- */
    if (RAM_A720 == 1)
        fr15 = fpu_compare_and_select(fr15, ROM_F_726E0, ROM_F_726E4);

    OUT_A708 = fr15;
}
