/*
 * =============================================================================
 * rx8_battery_voltage_monitor.c  —  BATTERY VOLTAGE / CHARGING-FAULT MONITOR
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x26766 .. 0x2687E   (body ends with `rts` at 0x2687A, delay
 *               slot `mov.l @r15+,r14` at 0x2687C; next function starts at
 *               0x2687E).
 *
 * Status    : VERIFIED — behavioural equivalence to the ROM held by
 *             reconstructed/samples/tests/harness_battery_voltage_monitor.py
 *             (host-gcc + mmap vs tools/sh2emu.py over edge + 20000 random
 *             pre-states; every RAM side-effect compared byte-for-byte).
 *
 * Lift (truth): c/battery_voltage_monitor.c — a speculative, hand-written
 *               description (float flags, adcToBatteryVoltage,
 *               readBatteryVoltageADC) that does NOT match this ROM vector.
 *               This reconstruction is derived directly from the ROM bytes and
 *               wins where the two disagree (see DISCREPANCIES below).
 *
 * WHAT THIS IS
 * ------------
 * A void, no-argument periodic monitor task (jsr entry, plain rts exit, no
 * ABI return value).  It classifies the OV charging-fault byte and maintains
 * two saturating counters with an optional compensation write.  RAM side
 * effects (compared byte-for-byte by the harness):
 *
 *    RAM8  [0xFFFFB6B6]  charging-fault byte: 0 if bat<9.0, 1 if bat>=10.0,
 *                         held for 9.0<=bat<10.0 (fault = not-normally-high)
 *    RAM16 [0xFFFFB67A]  compensation word         = 312 (skip) | -1 (dec>0)
 *    RAM16 [0xFFFFB6AC]  counter A  +1 saturating  (or cleared if TPS byte 0)
 *    RAM16 [0xFFFFB6AE]  counter B  +1 saturating  (or cleared if OV byte 0)
 *
 * Input cells (read only):
 *    RAM32 [0xFFFFB600]  battery voltage f32
 *    RAM8  [0xFFFFA428]  TPS / engine-state byte (throttle_position_sensor.c,
 *                         getEngineOnTimeForOilMetering.c refer to it)
 *    RAM32 [0xFFFFB6C4]  ADC-processing intermediate f32
 *    RAM32 [0xFFFFB6C8]  reference voltage f32
 *
 * SUBROUTINES
 * -----------
 * One `jsr` to the saturating-u16-add leaf @0x2460 (pure integer, no RAM
 * side effect beyond its result, so inlined here).  The harness executes the
 * REAL ROM bytes of that leaf on the emulator side.
 *
 * NaN / INF HANDLING  (why the C uses `!(a > b)` guards)
 * -----------------------------------------------------
 * The ROM evaluates with fcmp/gt, which clears T for unordered (NaN)
 * operands; a C `a > b` with NaN is also false.  The fault gate is therefore
 * reproduced faithfully with `!(hi > x)` wherever the ROM `bf` was taken on a
 * cleared T.  This matters for NaN/+-inf inputs, which the vector mix includes.
 *
 * DISCREPANCIES vs c/battery_voltage_monitor.c
 * --------------------------------------------
 *  - The lift read "over-voltage" as setting the flag to 1 on bat>10; the ROM
 *    is reversed WITH hysteresis: fault byte = 0 for bat<9.0, 1 for
 *    bat>=10.0, and holds its pre-state in the [9.0,10.0) band (f32 1.0 @
 *    0x751B4 is the hysteresis delta).
 *  - The lift treated 0xFFFFB67A as a float compensated voltage; the ROM uses
 *    it as a u16 compensation WORD (mov.w in / mov.w out).
 *  - adcToBatteryVoltage() and readBatteryVoltageADC() are not in this body.
 *  - 16.973/10.938 gate block 2 as f32 compares (0x751C0 / 0x751C4), not as
 *    the "fault bits" the lift imagined.
 * =============================================================================
 */
#include <stdint.h>
#include <stdbool.h>
#include "rx8_samples.h"
#include "rx8_hw.h"

/* ---- RAM cells (addr, width) ---- */
#define RX_BAT_VOLTAGE_ADDR  0xFFFFB600u   /* f32 battery voltage (V)          */
#define RX_TPS_BYTE_ADDR     0xFFFFA428u   /* u8  TPS / engine-state byte      */
#define RX_OV_FLAG_ADDR      0xFFFFB6B6u   /* u8  charging-fault byte          */
#define RX_CMP_WORD_ADDR     0xFFFFB67Au   /* u16 compensation word            */
#define RX_INTERMED_ADDR     0xFFFFB6C4u   /* f32 ADC-processing intermediate  */
#define RX_REF_ADDR          0xFFFFB6C8u   /* f32 reference voltage            */
#define RX_CNT_A_ADDR        0xFFFFB6ACu   /* u16 counter A                    */
#define RX_CNT_B_ADDR        0xFFFFB6AEu   /* u16 counter B                    */

/* ---- ROM calibration table (validated against the ROM by the harness) ---- */
#define CAL_BAT_HI   (*(volatile float    *)0x000751B0u)  /* 10.0            */
#define CAL_BAT_LO   (*(volatile float    *)0x000751B4u)  /* 1.0  (dead)     */
#define CAL_CRIT     (*(volatile float    *)0x000751C0u)  /* 16.973          */
#define CAL_UW       (*(volatile float    *)0x000751C4u)  /* 10.938          */
#define CAL_ACC_A    (*(volatile uint16_t *)0x000751A2u)  /* 63              */
#define CAL_ACC_B    (*(volatile uint16_t *)0x000751A4u)  /* 63              */
#define CAL_LOAD     (*(volatile uint16_t *)0x000751A8u)  /* 312             */

/* ---- saturating-u16-add @0x2460 (r4=extu.w-r4; r5=extu.w-r5; r4+=r5;
 *      r4 = r4 >= 0xFFFF ? 0xFFFF : r4; r0 = r4). ---- */
static uint16_t sat_add16(uint16_t a, uint16_t b)
{
    uint32_t s = (uint32_t)a + (uint32_t)b;
    return (uint16_t)(s > 0xFFFFu ? 0xFFFFu : s);
}

/* ===========================================================================
 * 0x26766 — battery voltage (charging-fault) monitor task (void).
 * =========================================================================== */
void rx8_battery_voltage_monitor(void)
{
    float   bat = *(volatile float *)RX_BAT_VOLTAGE_ADDR;
    uint8_t tps = (uint8_t)RX8_IO8(RX_TPS_BYTE_ADDR);
    uint8_t ov;

/* ---- block 1 (0x26766..0x26797): charging-fault byte -----------------
     * The ROM runs fcmp/gt with its registers mapped as f[6]>f[4] for the
     * on-test and f[5]>f[4] for the off-test (fr6=10.0, fr5=10.0-1.0=9.0,
     * fr4=bat).  So:
     *
     *     if (10.0 > bat) {            bat < 10.0
     *         if (9.0 > bat) ov = 0;   bat < 9.0
     *         else hold ov;           9.0 <= bat < 10.0 (no write)
     *     } else {
     *         ov = 1;                  bat >= 10.0
     *     }
     *
     * The 9.0 threshold is the ROM's runtime fsub: fr5 = fr6 - fr3 = 10.0 -
     * 1.0 (f32 @ CAL_BAT_LO).  Writing the held pre-state back is equivalent
     * to the ROM not writing at all in the [9,10) band.  NaN bat -> 10.0>NaN
     * is false -> ov = 1 (matches the emulator's fcmp/gt, see header).  */
    ov = (uint8_t)RX8_IO8(RX_OV_FLAG_ADDR);   /* held band pre-state */
    float off_t = (float)CAL_BAT_HI - (float)CAL_BAT_LO;  /* 10.0 - 1.0 = 9.0 */
    if ((float)CAL_BAT_HI > bat) {
        if (off_t > bat)
            ov = 0u;
    } else {
        ov = 1u;
    }
    RX8_IO8(RX_OV_FLAG_ADDR) = ov;

    /* ---- block 2 (0x26798..0x26842): compensation / counter gate ---------
     * A test-and-branch chain.  The "skip" path (0x267F6) writes
     * [0xFFFFB67A] = 312 (CAL_LOAD); the DEC path (0x26834) instead
     * decrements that word when it is positive (cmp/pl, signed).  Both then
     * converge on the shared counter block below.  Conditions to reach DEC
     * (mirror the fcmp-gt/cmp sequence; NaN fails every guard and always
     * falls into "skip"):
     *
     *  (1) [0xFFFFB6C4] > CAL_CRIT (16.9)      fcmp: f[2]>f[3] (intermed)
     *  (2) CAL_UW (10.94) > [0xFFFFB6C8]        fcmp: f[1]>f[0] (ref)
     *  (3) tps != 0
     *  (4) if tps == 1 then [0xFFFFB6AC] >= CAL_ACC_A (63)     cmp/hs
     *  (5) ov guard (0x267D4..0x267F2):
     *         ov == 0                                   -> skip
     *         ov == 1 and [0xFFFFB6AE] <  CAL_ACC_B      -> skip
     *         ov == 1 and [0xFFFFB6AE] >= CAL_ACC_B      -> dec
     *         ov != 1 (and ov != 0)                      -> dec
     * ---------------------------------------------------------------------- */
    bool dec = false;

    if (!(*(volatile float *)RX_INTERMED_ADDR > (float)CAL_CRIT))
        goto skip;                                  /* 0x267A4 bf  */
    if (!((float)CAL_UW > *(volatile float *)RX_REF_ADDR))
        goto skip;                                  /* 0x267B2 bf  */
    if (tps == 0)
        goto skip;                                  /* 0x267BA bt/s */
    if (tps == 1 && !(RX8_IO16(RX_CNT_A_ADDR) >= (uint16_t)CAL_ACC_A))
        goto skip;                                  /* 0x267D0 bf/s */

    /* 0x267D4 */
    if (ov == 0)
        goto skip;                                  /* 0x267DA bt/s */
    dec = (ov != 1) || (RX8_IO16(RX_CNT_B_ADDR) >= (uint16_t)CAL_ACC_B);

    if (dec) {
        /* ---- 0x26834: decrement compensation word (when nonzero) --------
         * The ROM extu.w's the word (so it is a non-negative 32-bit value
         * 0..0xFFFF) and tests it with cmp/pl (signed > 0): every value
         * except exactly 0 is decremented by 1. */
        uint16_t w = (uint16_t)RX8_IO16(RX_CMP_WORD_ADDR);
        if (w > 0)                                  /* cmp/pl (w != 0)   */
            RX8_IO16(RX_CMP_WORD_ADDR) = (uint16_t)(w - 1u);
        goto common;
    }

skip:                                   /* 0x267F6 */
    RX8_IO16(RX_CMP_WORD_ADDR) = (uint16_t)CAL_LOAD;  /* [0xFFFFB67A] = 312 */

common:                                 /* 0x26844 */
    /* counter A: tps==0 clears it, else saturating +1 */
    if (tps == 0)
        RX8_IO16(RX_CNT_A_ADDR) = 0;
    else
        RX8_IO16(RX_CNT_A_ADDR) = sat_add16((uint16_t)RX8_IO16(RX_CNT_A_ADDR), 1u);
    /* counter B: ov==0 clears it, else saturating +1 */
    if (ov == 0)
        RX8_IO16(RX_CNT_B_ADDR) = 0;
    else
        RX8_IO16(RX_CNT_B_ADDR) = sat_add16((uint16_t)RX8_IO16(RX_CNT_B_ADDR), 1u);
}