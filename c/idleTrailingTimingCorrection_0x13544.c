/* idleTrailingTimingCorrection_0x13544.c
 *
 * ROM: 60E0FC00 | Address: 0x13544 | Size: 0x130 (304) bytes = code + pool
 *       code 0x13544..0x13626 (rts @0x13624, delay mov.l @r15+,r14 @0x13626),
 *       literal pool 0x13628..0x13672; the thunk updateKnockRamTHUNK starts at
 *       the CSV end 0x13674.  VERIFIED vs the ROM emulator (0 mismatches,
 *       c/tests/test_idleTrailingTimingCorrection_0x13544.py).
 *
 * ENTRY VERIFICATION: 0x13544 matches the CSV start (row 0x013544..0x013674 —
 * CORRECT, no widening needed).  Valid entry: opens with the standard prologue
 * (mov.l r14/r13 pushes + 2 fmov.s fr pushes + sts.l pr); the preceding
 * function idleLeadingTimingCorrection (0x13414) ends rts @0x134F4 (delay
 * @0x134F6), so no fall-through into us.  The ROM function-pointer slot
 * @0x1442C of the engineControlCalculateTiming dispatcher (0x141FC) table is
 * the ONLY 32-bit reference to 0x13544 in the binary (the leading twin sits
 * at the adjacent slot @0x14428).  The CSV address IS the real entry point.
 *
 * SEMANTICS: structural twin of idleLeadingTimingCorrection_0x13414 —
 * instruction-for-instruction the same skeleton with the trailing-timing
 * RAM/ROM block:
 *
 *   fr2  = ts(f32@B594 - f32@B5A0)          ; f32@A71C = fr2  (always)
 *   if u8@B580 == 0: desc = (u8@B588 == 0) ? 0x686D4 : 0x686E8
 *   else:            desc = (u8@B586 == 1) ? 0x686D4 : 0x686E8
 *   res  = TwoDLookup(desc, x = fr2)        ; f32@A714 = res (always)
 *   fr15 = res  if  u8@AAC6 == 1  &&  f32@726E8 (1500.0) > f32@B594
 *              && (f32@726EC (1/1024) > f32@C030 || word@A424 >= word@726D2 (375))
 *   fr15 = 0.0 otherwise            (SH-2E fcmp/gt Fm,Fn sets T when Fn > Fm)
 *
 *   A721 gate (u8@FFFFA721), load = f32@C0D8 (fr14, preserved through the
 *   lookup — 0x2068 touches only fr0..fr5):
 *       if load >= f32@726F0 (0.6):   u8@A721 = 1
 *       elif load <  ts(0.6 + f32@13660 (-0.045)):  u8@A721 = 0
 *       (else: u8@A721 unchanged)
 *   if u8@A721 == 1: fr15 = saturate(fr15, f32@726F4 (-2.8), f32@726F8 (0.7))
 *   f32@A70C = fr15 (always)
 *
 * r0 on return = u8@A721 & 0xFF (the 0x2404 saturate leaf never writes r0).
 *
 * RAM r/w: reads B594 (f32), C0D8 (f32), B5A0 (f32), B580/B588/B586 (bytes),
 * AAC6 (byte), C030 (f32), A424 (word), A721 (byte); writes A71C (f32),
 * A714 (f32), A721 (byte, conditional), A70C (f32).
 * ROM read: 2D descriptors 0x686D4/0x686E8 (+ shared axis 0x7275C/0x7278C and
 *   u8 value tables 0x72780/0x727B0, type-4 scaled-byte: value = u8*0.25-32.0,
 *   axis -100..100), f32 0x726E8/0x726EC/0x726F0/0x726F4/0x726F8, u16 0x726D2,
 *   pool f32 @0x13660 (-0.045).
 * Sub-calls: TwoDLookup @0x2068 (x1), saturate @0x2404 (x1).
 *
 * TWIN diff (vs 0x13414, the leading twin): RAM outputs +4 (A71C/A714/A70C),
 * gate byte A721, descriptors 0x686D4/0x686E8, ROM const block +0x14
 * (726E8/726EC/726F0/726F4/726F8, word 726D2, pool 13660).  All values
 * identical (1500.0/0.009765625/0.6/-2.8/0.7/375/-0.045).
 *
 * Range  : 0x13544 .. 0x13674 (CSV end == thunk start, no phantom rows)
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
#define RAM_A721  (*(volatile uint8_t *)0xFFFFA721)/* saturate gate  */

#define OUT_A71C  (*(volatile float *)0xFFFFA71C)  /* RPM error       */
#define OUT_A714  (*(volatile float *)0xFFFFA714)  /* 2D lookup result*/
#define OUT_A70C  (*(volatile float *)0xFFFFA70C)  /* idle advance corr */

/* ---- ROM calibration constants ---- */
#define ROM_F_726E8 (*(const float *)0x000726E8)   /* 1500.0 RPM gate    */
#define ROM_F_726EC (*(const float *)0x000726EC)   /* 0.009765625 (1/1024)*/
#define ROM_U16_726D2 (*(const uint16_t *)0x000726D2)/* 375 word gate    */
#define ROM_F_726F0 (*(const float *)0x000726F0)   /* 0.6 load threshold */
#define ROM_F_13660 (*(const float *)0x00013660)   /* -0.045 pool f32    */
#define ROM_F_726F4 (*(const float *)0x000726F4)   /* -2.8 saturate lo   */
#define ROM_F_726F8 (*(const float *)0x000726F8)   /* 0.7 saturate hi    */

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

#define DESC_686D4 ((const Map1D *)0x000686D4)  /* 9-pt %RPM-error map A  */
#define DESC_686E8 ((const Map1D *)0x000686E8)  /* 9-pt %RPM-error map B  */

/* ---- verified leaves ---- */
extern float TwoDLookup(const Map1D *m, float x);      /* 0x2068 */
extern float fpu_compare_and_select(float val, float lo, float hi);
/* @0x2404: clamp(val, lo, hi) */

void idleTrailingTimingCorrection_0x13544(void)
{
    float fr2 = RAM_B594 - RAM_B5A0;       /* fsub fr3,fr2 (single-precision) */
    float res, fr15;
    const Map1D *desc;

    OUT_A71C = fr2;

    /* ---- 2D lookup: B580==0 -> B588 picks, else B586==1 picks ---- */
    if (RAM_B580 == 0)
        desc = (RAM_B588 == 0) ? DESC_686D4 : DESC_686E8;
    else
        desc = (RAM_B586 == 1) ? DESC_686D4 : DESC_686E8;
    res = TwoDLookup(desc, fr2);
    OUT_A714 = res;

    /* ---- idle-gate: keep the correction only inside the idle window ----
     * The SH-2E fcmp/gt Fm,Fn sets T when Fn > Fm, so every comparison below
     * is written in that (constant-vs-register) direction.
     *   RPM < 1500.0 && (f32@C030 < 0.009765625 || word@A424 >= 375) ---- */
    if (RAM_AAC6 == 1 && ROM_F_726E8 > RAM_B594 &&
        (ROM_F_726EC > RAM_C030 || RAM_A424 >= ROM_U16_726D2))
        fr15 = res;
    else
        fr15 = 0.0f;

    /* ---- load gate byte A721: 1 if load >= 0.6, 0 if load < 0.555,
     *      unchanged between (fr14 = load is preserved through the lookup,
     *      which only touches fr0..fr5) ---- */
    if (RAM_C0D8 < ROM_F_726F0) {
        if (RAM_C0D8 < ROM_F_726F0 + ROM_F_13660)
            RAM_A721 = 0;
    } else {
        RAM_A721 = 1;
    }

    /* ---- saturate into [-2.8, 0.7] when the load gate is set ---- */
    if (RAM_A721 == 1)
        fr15 = fpu_compare_and_select(fr15, ROM_F_726F4, ROM_F_726F8);

    OUT_A70C = fr15;
}
