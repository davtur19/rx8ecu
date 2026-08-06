/* getEngineCrankingState_0x1477C.c
 *
 * ROM: 60E0FC00 | Address: 0x1477C | CSV range 0x01477C..0x014804.
 * Code ends at `rts` @0x147DE (delay mov @0x147E0); the next function
 * (dispatcher follower) starts at 0x14804.  CSV range is CORRECT.
 *
 * ENTRY VERIFICATION: 0x1477C matches the symbols CSV row
 * (0x01477C..0x014804, getEngineCrankingState??).  Valid entry (opens by
 * pushing r14/r13 + pr; no fall-through).  CSV address IS the real entry.
 *
 * NAME: CSV had `getEngineCrankingState??` — kept (the function maintains the
 * A79C/A79D/A79E engine-count / state cluster), "??" removed as verified lift.
 *
 * SEMANTICS (line-for-line, see disasm; two SH-2 traps resolved during
 * verification: fcmp/gt Fm,Fn compares FRn > FRm, and `add #0xFF,r0`
 * sign-extends to -1):
 *   a79d = u8@0xFFFFA79D ; fr4 = f32@0xFFFFB594
 *   if a79d != 0: u8@0xFFFFA79D = (a79d - 1) & 0xFF
 *   v = u8@0xFFFFA79E ; r14 = v
 *   if fr4 < 500.0:                 // 0x147A0: 500.0 > fr4
 *       if fr4 < 300.0: r14 = 0     // 0x147C0: 300.0 > fr4
 *   else:                           // fr4 >= 500.0
 *       r14 = 1
 *       if v == 0:                  // countdown expired -> table lookup
 *           u8@0xFFFFA79D = sub_0x20AC(f32@0xFFFFA9FC) & 0xFF
 *   u8@0xFFFFA79E = r14
 *   if u8@0xFFFFA79D != 0: r14 = 0
 *   u8@0xFFFFA79C = r14
 *   r0 = subcall byte if the lookup ran, else entry r0 (register-only).
 *
 * sub_0x20AC(x) — calibration-table float -> byte (struct@0x68C04:
 *   w[0] = 6, tblA@0x753F8 (float), tblB@0x75410 (byte lerp table)):
 *     idx, frac = sub_0x2624(6, tblA, x)   // descending float search+frac
 *     y         = sub_0x26B0(idx, tblB, frac)  // two-byte lerp, single prec.
 *     return (uint8_t)((int)(y) & 0xFF)    // ftrc ; r0 &= 0xFF
 *
 * RAM r/w: reads 0xFFFFA79D/0xFFFFA79E, f32@0xFFFFB594, f32@0xFFFFA9FC and
 *          ROM tables @0x68C04/0x753F8/0x75410; writes 0xFFFFA79D,
 *          0xFFFFA79E, 0xFFFFA79C.
 * VERIFIED vs tools/sh2emu.py (60E0FC00.bin) in
 * c/tests/test_getEngineCrankingState_0x1477C.py — 0 mismatches over
 * 5 seeds x 100000 (byte-exact post-call RAM overlay + r0).
 */
#include <stdint.h>

#define RAM_A79D (*(volatile uint8_t *)0xFFFFA79D)
#define RAM_A79E (*(volatile uint8_t *)0xFFFFA79E)
#define RAM_A79C (*(volatile uint8_t *)0xFFFFA79C)
#define RAM_B594 (*(volatile float  *)0xFFFFB594)
#define RAM_A9FC (*(volatile float  *)0xFFFFA9FC)

/* ---- ROM calibration structure / tables (60E0FC00.bin) ---- */
#define CAL_P0   (*(volatile uint16_t *)0x00068C04)   /* w[0] = 6 */
#define CAL_TBLA ((volatile float *)0x000753F8)       /* float search table */
#define CAL_TBLB ((volatile uint8_t *)0x00075410)     /* byte lerp table */

/* 0x26B0: two-byte lerp over the byte table at CAL_TBLB+idx with single
 * precision rounding; fraction 0.0 short-circuits (returns float(tbl[idx])). */
static float lerp_byte(uint32_t idx, float frac)
{
    uint32_t b0 = CAL_TBLB[idx];
    float fr2 = (float)b0;                       /* fldi0 ; float fpul,fr2 */
    if (frac == 0.0f)                            /* fcmp/eq -> rts */
        return fr2;
    float fr1 = (float)CAL_TBLB[idx + 1] - fr2;  /* fsub */
    return frac * fr1 + fr2;                     /* fmac (single rounding) */
}

/* 0x2624: descending float-table index search + fraction (single precision).
 * Walk DOWN from (P0-1) while T[idx] > x, then interpolate T[idx]..T[idx+4];
 * idx==0 -> fraction 0.  Returns the byte-table index for lerp_byte. */
static uint32_t lookup_float_idx(float x, float *frac)
{
    int idx = (int)(CAL_P0 - 1) << 2;            /* add #0xFF = -1, shll2 */
    const volatile float *t = CAL_TBLA;
    if (t[idx] <= x) {                           /* !(T[idx] > x) -> 0x264C */
        *frac = 0.0f;
        return (uint32_t)idx >> 2;
    }
    for (;;) {
        if (idx == 0) {                          /* 0x2630 bt (r0==0) */
            *frac = 0.0f;
            return 0;
        }
        idx -= 4;
        if (t[idx] <= x) {                       /* exit loop */
            *frac = (x - t[idx]) / (t[idx + 4] - t[idx]);   /* fsub/fdiv */
            return (uint32_t)idx >> 2;
        }
    }
}

/* 0x20AC: calibration-table float -> byte. */
static uint8_t sub_0x20AC(float x)
{
    float frac;
    uint32_t idx = lookup_float_idx(x, &frac);
    float y = lerp_byte(idx, frac);
    return (uint8_t)((int)y & 0xFF);             /* ftrc ; r0 &= 0xFF */
}

void getEngineCrankingState_0x1477C(void)
{
    uint8_t a79d = RAM_A79D;
    float fr4 = RAM_B594;
    uint8_t v, r14;

    if (a79d != 0)                               /* cmp/pl ; bf/s skip */
        RAM_A79D = (uint8_t)(a79d - 1);          /* +0xFF -> -1 mod 256 */

    v = RAM_A79E;
    r14 = v;                                     /* bt/s delay: mov r4,r14 */
    if (fr4 < 500.0f) {                          /* fcmp/gt FR4,FR3: 500>fr4 */
        if (fr4 < 300.0f)                        /* fcmp/gt FR4,FR2: 300>fr4 */
            r14 = 0;
    } else {
        r14 = 1;                                 /* bf/s delay: mov #1,r14 */
        if (v == 0)
            RAM_A79D = sub_0x20AC(RAM_A9FC);     /* jsr @0x20AC */
    }

    RAM_A79E = r14;
    if (RAM_A79D != 0)                           /* cmp/pl post */
        r14 = 0;
    RAM_A79C = r14;
}