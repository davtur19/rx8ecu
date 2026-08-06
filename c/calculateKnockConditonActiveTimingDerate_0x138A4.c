/* calculateKnockConditonActiveTimingDerate_0x138A4.c
 *
 * ROM: 60E0FC00 | Address: 0x138A4 | Size: 0x110 (272) bytes = code + pool
 *       code 0x138A4..0x13972 (rts @0x13970, delay mov.l @r15+,r14 @0x13972),
 *       literal pool 0x13974..0x139B2; next function
 *       (calculateKnockConditonClearedAddTimingBack) starts @0x139B4.
 *       VERIFIED vs the ROM emulator (0 mismatches,
 *       c/tests/test_calculateKnockConditonActiveTimingDerate_0x138A4.py).
 *
 * ENTRY VERIFICATION: 0x138A4 matches the CSV start (row 0x0138A4..0x0139B4 —
 * CORRECT, no widening needed).  Valid entry: opens with the standard prologue
 * (mov.l r14/r13/r12 pushes + 2 fmov.s fr pushes + sts.l pr); the preceding
 * function updateKnockMaxRAM (0x13808) ends rts @0x138A0 (delay @0x138A2), so
 * no fall-through into us.  The ROM function-pointer slot @0x1441C of the
 * engineControlCalculateTiming dispatcher (0x141FC) table is the ONLY 32-bit
 * reference to 0x138A4 in the binary (slots @0x14428/@0x1442C hold the two
 * idle-timing twins 0x13414/0x13544 lifted alongside).  The CSV address IS
 * the real entry point.
 *
 * SEMANTICS (instruction-for-instruction, see disasm): the knock-conditon
 * "active" timing derate writer.  It reads the currently-accumulated knock
 * retard values f32@A734 (rotor-synced) and f32@A72C plus four gate bytes
 * (A738/A739/A74C/A730) and a 2D RPM-vs-knock-max lookup, then re-clamps the
 * retard into the calibration min/max tables and publishes the results at
 * f32@A724/A728 (and f32@A72C/A734).  Control flow:
 *
 *   fr15 <- f32@A734 ; fr4 <- f32@A72C          (fr15/fr4 fan-in candidates)
 *
 *   if u8@A738 == 0:                            -> fr15 = 0.0, fr4 = 0.0
 *   elif u8@A739 == 0:  fr15 = TwoDLookup(desc 0x693E0, x=f32@B594)
 *                       f32@A73C = fr15 ; fr4 = 0.0      (5-pt RPM knock-max map)
 *   elif u8@A74C == 0:
 *       if u8@A730 == 1: fr15 = f32@ROM 0x78588 (==0.0) ; fr4 = 0.0
 *   else (u8@A74C != 0):
 *       if u8@A730 == 1:
 *           if u8@C073 >= u8@ROM 0x78547 (==1):
 *               fr4 = fr4 - f32@ROM 0x7859C (==2.5)
 *           if u8@C070 == 1:
 *               fr15 = fr15 - f32@ROM 0x78594 (==1.0)   (both C071 sub-cases;
 *                                                        0x7858C also ==1.0)
 *
 *   f32@A72C = limitKnockRetardMax_CalValue(fr4)         bsr 0x13B4A
 *   f32@A734 = limitKnockRetardMax_ConditonalRPM(fr15)   bsr 0x13AE4
 *   f32@A724 = f32@A728 = saturateBetweenKnockRetardMinMaxTables(
 *                                             f32@A734 + f32@A72C)  bsr 0x13B5E
 *   u8@A74C  = u8@A730 (stored on every path)
 *
 * Sub-call semantics (all run inside the ROM, executed in the test via the
 * dedicated emulator instance):
 *   - limitKnockRetardMax_CalValue @0x13B4A = clamp(fr4, f32@785A8 (=-10.0),
 *     f32@785AC (=0.0)) — pure cal clamp, no RAM side effects.
 *   - limitKnockRetardMax_ConditonalRPM @0x13AE4 = clamp(fr4,
 *     lo = TwoDLookup(desc 0x693B8 (5-pt) / 0x693CC (4-pt), x=f32@B594),
 *     hi = f32@78584 (==0.0)); the descriptor is picked from bytes @B580 and
 *     @BB25/@BC75 vs u8@ROM 0x78544 (==5).
 *   - saturateBetweenKnockRetardMinMaxTables @0x13B5E = clamp(fr4,
 *     lo = TwoDLookup(desc 0x693F4, x=f32@B594),
 *     hi = TwoDLookup(desc 0x69408, x=f32@B594)); writes the two lookup
 *     results to f32@A740/A744.
 *
 * r0 on return = r0 left by the last sub-call (bsr 0x13B5E): 0x2404 is a
 * pure-FPU leaf that never writes r0, so r0 is the index*4 value of the last
 * 2D lookup (desc 0x69408 vs f32@B594) — verified vs the emulator.
 *
 * RAM r/w: reads A734, A72C, A730, A738, A739, A74C, B594, C073, C070, C071
 * (bytes C07x gated on A730==1); writes A73C (path 2 only), A72C, A734,
 * A724, A728, A74C + the sub-call outputs A740/A744.
 * ROM read: 2D descriptor 0x693E0 (+ axis 0x785E0 / u8 values 0x785F4,
 *   type-4 scaled-byte: value = u8 * 0.5 - 64.0, axis 2000..5000 RPM), the
 *   f32 constants 0x78588/0x7858C/0x78594/0x7859C, u8 0x78547; the sub-call
 *   descriptors 0x693B8/0x693CC/0x693F4/0x69408 and constants 0x78544,
 *   0x78584, 0x785A8, 0x785AC.
 * Sub-calls: TwoDLookup @0x2068 (x1), limitKnockRetardMax_CalValue @0x13B4A
 *   (x1), limitKnockRetardMax_ConditonalRPM @0x13AE4 (x1),
 *   saturateBetweenKnockRetardMinMaxTables @0x13B5E (x1).
 *
 * Range  : 0x138A4 .. 0x139B4 (CSV end == next function start, no phantom rows)
 */
#include <stdint.h>

/* ---- RAM globals (mov.w literals sign-extend to 0xFFFFxxxx) ---- */
#define RAM_A72C  (*(volatile float *)0xFFFFA72C)  /* accumulated retard 1    */
#define RAM_A734  (*(volatile float *)0xFFFFA734)  /* accumulated retard 2    */
#define RAM_A730  (*(volatile uint8_t *)0xFFFFA730)/* gate byte (stored->A74C)*/
#define RAM_A738  (*(volatile uint8_t *)0xFFFFA738)/* gate byte 1             */
#define RAM_A739  (*(volatile uint8_t *)0xFFFFA739)/* gate byte 2             */
#define RAM_A74C  (*(volatile uint8_t *)0xFFFFA74C)/* gate byte 3             */
#define RAM_B594  (*(volatile float *)0xFFFFB594)  /* RPM (2D x input)        */
#define RAM_C073  (*(volatile uint8_t *)0xFFFFC073)/* A730==1 gate (>= cal)   */
#define RAM_C070  (*(volatile uint8_t *)0xFFFFC070)/* A730==1 gate (==1)      */
#define RAM_C071  (*(volatile uint8_t *)0xFFFFC071)/* A730==1 gate (unused?)  */

#define OUT_A73C  (*(volatile float *)0xFFFFA73C)  /* path-2 lookup output    */
#define OUT_A72C  (*(volatile float *)0xFFFFA72C)  /* retard 1 (re-clamped)   */
#define OUT_A734  (*(volatile float *)0xFFFFA734)  /* retard 2 (re-clamped)   */
#define OUT_A724  (*(volatile float *)0xFFFFA724)  /* saturated retard output */
#define OUT_A728  (*(volatile float *)0xFFFFA728)  /* twin of A724            */

/* ---- ROM calibration constants ---- */
#define ROM_U8_78547 (*(const uint8_t *)0x00078547)  /* 1   A730==1 threshold  */
#define ROM_F_78588  (*(const float *)0x00078588)    /* 0.0 fr15 reset (A730==1)*/
#define ROM_F_7858C  (*(const float *)0x0007858C)    /* 1.0 C071==0 subtract   */
#define ROM_F_78594  (*(const float *)0x00078594)    /* 1.0 C071!=0 subtract   */
#define ROM_F_7859C  (*(const float *)0x0007859C)    /* 2.5 C073>=cal subtract */

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

#define DESC_693E0 ((const Map1D *)0x000693E0)  /* 5-pt RPM knock-max map     */

/* ---- verified leaves ---- */
extern float TwoDLookup(const Map1D *m, float x);              /* 0x2068 */
/* 0x13B4A: clamp(x, f32@785A8 = -10.0, f32@785AC = 0.0) */
extern float limitKnockRetardMax_CalValue(float x);
/* 0x13AE4: clamp(x, TwoDLookup(0x693B8/0x693CC, RPM), f32@78584 = 0.0) */
extern float limitKnockRetardMax_ConditonalRPM(float x);
/* 0x13B5E: clamp(x, TwoDLookup(0x693F4, RPM), TwoDLookup(0x69408, RPM)),
 *           writes f32@A740/A744 */
extern float saturateBetweenKnockRetardMinMaxTables(float x);

void calculateKnockConditonActiveTimingDerate_0x138A4(void)
{
    uint8_t a730 = RAM_A730;
    float   fr15 = RAM_A734;               /* fr5 <- @A734 ; fr15 <- fr5 */
    float   fr4  = RAM_A72C;               /* fr6 <- @A72C ; fr4  <- fr6 */

    /* ---- fan-in selection (0x138A4..0x13944) ---- */
    if (RAM_A738 == 0) {
        fr15 = 0.0f;                       /* fldi0 fr14 -> fr15 (delay)  */
        fr4  = 0.0f;                       /* fr4 <- fr14 (bra delay)     */
    } else if (RAM_A739 == 0) {
        fr15 = TwoDLookup(DESC_693E0, RAM_B594);   /* 5-pt RPM knock-max   */
        OUT_A73C = fr15;
        fr4  = 0.0f;
    } else if (RAM_A74C == 0) {
        if (a730 == 1) {
            fr15 = ROM_F_78588;            /* == 0.0                      */
            fr4  = 0.0f;
        }
    } else {
        if (a730 == 1) {
            if (RAM_C073 >= ROM_U8_78547)
                fr4 = fr4 - ROM_F_7859C;   /* -2.5 when C073 >= cal(1)    */
            if (RAM_C070 == 1)
                fr15 = fr15 - ROM_F_78594; /* -1.0 (both C071 sub-cases)  */
        }
    }

    /* ---- re-clamp chain ---- */
    OUT_A72C = limitKnockRetardMax_CalValue(fr4);            /* bsr 0x13B4A */
    OUT_A734 = limitKnockRetardMax_ConditonalRPM(fr15);      /* bsr 0x13AE4 */
    OUT_A724 = OUT_A728 =
        saturateBetweenKnockRetardMinMaxTables(OUT_A734 + OUT_A72C);
                                                             /* bsr 0x13B5E */
    RAM_A74C = a730;                       /* mov.b r14,@A74C (low byte)   */
}
