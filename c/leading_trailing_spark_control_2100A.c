/* leading_trailing_spark_control_2100A.c
 *
 * ROM: 60E1D400  |  Address: 0x2100A  |  Size: 0x160 bytes (352 B)
 *       0x2100A..0x21168 code; literal pool 0x2116A..0x2118C (next
 *       function CLChangeoverEnrichment@0x21190).  VERIFIED vs ROM emulator.
 *
 * Gated "spark split" state controller (IDA: leading_trailing_spark_control).
 * Despite the IDA name, this routine does NOT compute a split angle and does
 * NOT touch the per-rotor timing words A734/A738 (those are written identically
 * by calc_ignition_all_rotors_13C2C; see its lift).  Instead it manages a pair
 * of RAM floats B18C/B188 plus a byte flag B240:
 *
 *   Inputs (RAM reads):
 *     f32@0xFFFFAA10  fr4  coolant-temp word (comparison input)
 *     f32@0xFFFFC6B4  fr7  compared against CAL_1000 (0x71C7C)
 *     u16@0xFFFFB1B2  r4   gate byte-pair (used unsigned)
 *     u8 @0xFFFFB1C7  r7   gate flag (compared ==1 / ==0)
 *     u8 @0xFFFFB1C9  r5   gate flag (==1 / ==0)
 *     u8 @0xFFFFB1C4  r6   gate flag (==1 / ==0)
 *     u8 @0xFFFFB1C2  r0   gate flag (==1)
 *     u8 @0xFFFFC600  r2   engine-off flag (!=0 -> zero outputs)
 *     u8 @0xFFFFCCE1  r1   enable gate (!=0 -> zero outputs)
 *     u8 @0xFFFFCDA0  r2   AC/extra gate (!=0 -> skip set-1.0 path)
 *     u8 @0xFFFFB19C  r3   allow-decrement gate (==1)
 *     f32@0xFFFFB18C, f32@0xFFFFB188  previous state (read in decay path)
 *   ROM constants: u8@0x71BD0 (==1), f32@0x71C54 (-40.0), f32@0x71C58 (3.0),
 *     f32@0x71C74 / 0x71C78 (0.0667 decay step), f32@0x71C7C (1000.0)
 *
 *   Outputs (RAM writes):
 *     u8 @0xFFFFB240  cold/validity flag, hysteresis on coolant temp
 *     f32@0xFFFFB18C  "leading" state word  (r13)
 *     f32@0xFFFFB188  "trailing" state word (r14)
 *
 * Flow (mirrors the ROM 1:1):
 *   1. B240 hysteresis: B240 = 1 if coolant >= -40; B240 = 0 if coolant < -43;
 *      unchanged in [-43, -40).
 *   2. Gates: if C600!=0 or CCE1!=0 or ROM71BD0!=1 -> B18C = B188 = 0.0.
 *   3. If (B240!=1 || CDA0!=0 || C6B4 > 1000.0) -> fc() (0x210FC).
 *   4. Else set-1.0 test: (B1C2==1 && u16@B1B2!=0) || (B1C9==1 && B1C4==1)
 *      || B1C7==1 -> B18C = B188 = 1.0; otherwise fc().
 *   5. fc() (0x210FC): if B19C!=1 -> 0.0/0.0; else if any of u16@B1B2==0,
 *      B1C7==0, B1C9==0, C6B4 > 1000.0, or B1C4==0 -> decay; if B1C4!=0 -> 0.0/0.0.
 *   6. decay (0x21132): B18C = max(B18C - 0.0667, 0.0), B188 = max(B188 -
 *      0.0667, 0.0), each via the shared max helper @0x23E4 (fr5=fr15=0.0).
 *
 * Note on fcmp/gt operand order (SH-2E): "fcmp/gt Fm,Fn" sets T = (Fn > Fm),
 * so the disassembly "fcmp/gt fr4,fr5" means -40.0 > coolant, "fcmp/gt fr3,fr7"
 * means fr7 > 1000.0, and "fcmp/gt fr4,fr6" means -43.0 > coolant.
 *
 * Verified: 100000 random inputs x 5 seeds (500000 total) vs the ROM emulator,
 * 0 mismatches (test_leading_trailing_spark_control_2100A.py).
 */
#include <stdint.h>

/* ---- RAM inputs ---- */
#define RAM_COOLANT   (*(volatile float *)0xFFFFAA10)  /* fr4 input  */
#define RAM_C6B4      (*(volatile float *)0xFFFFC6B4)  /* fr7 input  */
#define RAM_B1B2      (*(volatile uint16_t *)0xFFFFB1B2) /* r4 gate */
#define RAM_B1C7      (*(volatile uint8_t *)0xFFFFB1C7)  /* r7 gate */
#define RAM_B1C9      (*(volatile uint8_t *)0xFFFFB1C9)  /* r5 gate */
#define RAM_B1C4      (*(volatile uint8_t *)0xFFFFB1C4)  /* r6 gate */
#define RAM_B1C2      (*(volatile uint8_t *)0xFFFFB1C2)  /* r0 gate */
#define RAM_ENG_OFF   (*(volatile uint8_t *)0xFFFFC600)  /* r2 engine-off */
#define RAM_CCE1      (*(volatile uint8_t *)0xFFFFCCE1)  /* r1 gate */
#define RAM_CDA0      (*(volatile uint8_t *)0xFFFFCDA0)  /* r2 gate */
#define RAM_B19C      (*(volatile uint8_t *)0xFFFFB19C)  /* r3 gate */

/* ---- RAM outputs (also read as inputs in the decay path) ---- */
#define RAM_B240      (*(volatile uint8_t *)0xFFFFB240)  /* r12 cold flag */
#define RAM_B18C      (*(volatile float *)0xFFFFB18C)    /* r13 state word */
#define RAM_B188      (*(volatile float *)0xFFFFB188)    /* r14 state word */

/* ---- ROM constants ---- */
#define ROM_U8_71BD0  (*(const uint8_t *)0x00071BD0)     /* == 1 */
#define ROM_F_71C54   (*(const float *)0x00071C54)       /* -40.0  (fr5) */
#define ROM_F_71C58   (*(const float *)0x00071C58)       /*  3.0   (fr3, fr6 = fr5 - fr3) */
#define ROM_F_71C74   (*(const float *)0x00071C74)       /*  0.0667 decay step B18C */
#define ROM_F_71C78   (*(const float *)0x00071C78)       /*  0.0667 decay step B188 */
#define ROM_F_71C7C   (*(const float *)0x00071C7C)       /*  1000.0 threshold vs fr7 */

/* 0x23E4 — shared max helper (IDA mislabels it "fpu_mul_float"); returns
 * fr0 = max(fr4, fr5).  Called with fr5 = fr15 = 0.0, so it clamps its
 * argument to >= 0.0:  max(0.0, x).  (Verified against the emulator:
 * fr={4:10,5:5} -> fr0=10, fr={4:3,5:8} -> fr0=8.) */
static float max_0x23E4(float a, float b)
{
    return a > b ? a : b;
}

/* ---- 0x210FC + 0x21132 block (shared by two gate exits) ---- */
static void fc_block(uint16_t r4, uint8_t r5, uint8_t r6, uint8_t r7, float fr7)
{
    if (RAM_B19C != 1) {
        RAM_B18C = 0.0f;                 /* 0x21154 */
        RAM_B188 = 0.0f;
        return;
    }
    if (r4 == 0 || r7 == 0 || r5 == 0 || fr7 > ROM_F_71C7C) {
        /* fall through to decay @0x21132 */
    } else if (r6 != 0) {
        RAM_B18C = 0.0f;                 /* 0x21154 */
        RAM_B188 = 0.0f;
        return;
    }
    /* 0x21132: decay both words with shared max @0x23E4.
     * The ROM does fsub (rounds to f32) then selects via max(fr5=0, fr4). */
    {
        float v;
        v = RAM_B18C - ROM_F_71C74;             /* fsub @0x2113A, f32 */
        RAM_B18C = max_0x23E4(v, 0.0f);
        v = RAM_B188 - ROM_F_71C78;             /* fsub @0x2114A, f32 */
        RAM_B188 = max_0x23E4(v, 0.0f);
    }
}

void leading_trailing_spark_control_2100A(void)
{
    float   fr4 = RAM_COOLANT;            /* f32@0xFFFFAA10 */
    float   fr7 = RAM_C6B4;               /* f32@0xFFFFC6B4 */
    uint16_t r4 = RAM_B1B2;               /* u16@0xFFFFB1B2 */
    uint8_t r7 = RAM_B1C7;                /* u8@0xFFFFB1C7 */
    uint8_t r5 = RAM_B1C9;                /* u8@0xFFFFB1C9 */
    uint8_t r6 = RAM_B1C4;                /* u8@0xFFFFB1C4 */
    uint8_t r0 = RAM_B1C2;                /* u8@0xFFFFB1C2 */
    uint8_t eng_off = RAM_ENG_OFF;        /* u8@0xFFFFC600 */
    uint8_t cce1    = RAM_CCE1;           /* u8@0xFFFFCCE1 */
    uint8_t cda0    = RAM_CDA0;           /* u8@0xFFFFCDA0 */
    float fr5 = ROM_F_71C54;              /* -40.0 */
    float fr6 = fr5 - ROM_F_71C58;        /* -43.0 (fsub @0x2102A) */

    /* ---- Block A: B240 cold/validity flag (0x2103A..0x21084) ----
     * fcmp/gt fr4,fr5 -> T = (fr5 > fr4) = (-40.0 > coolant)
     * fcmp/gt fr4,fr6 -> T = (fr6 > fr4) = (-43.0 > coolant)  */
    if (fr5 > fr4) {                       /* coolant < -40.0  */
        if (fr6 > fr4)                     /* coolant < -43.0  */
            RAM_B240 = 0;
        /* else B240 unchanged */
    } else {
        RAM_B240 = 1;
    }

    /* ---- Block B: gated state update (0x21086..) ----
     * engine-off / enable / cal gate -> zero both outputs (0x2115A). */
    if (eng_off != 0 || cce1 != 0 || ROM_U8_71BD0 != 1) {
        RAM_B18C = 0.0f;
        RAM_B188 = 0.0f;
    } else if (RAM_B240 != 1 || cda0 != 0 || fr7 > ROM_F_71C7C) {
        /* bf/bt exits straight into fc() @0x210FC */
        fc_block(r4, r5, r6, r7, fr7);
    } else {
        /* set-1.0 test (0x210C8..0x210F4): */
        if ((r0 == 1 && r4 > 0) || (r5 == 1 && r6 == 1) || r7 == 1) {
            RAM_B18C = 1.0f;               /* 0x210F4 */
            RAM_B188 = 1.0f;
        } else {
            fc_block(r4, r5, r6, r7, fr7);
        }
    }
}
