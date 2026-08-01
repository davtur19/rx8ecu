/*
 * =============================================================================
 * rx8_calc_fan1_control.c  —  COOLING-FAN RELAY CONTROL (THERMOSTAT + ENABLE)
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x303A6  (size 288 bytes; a leaf: no stack frame, no calls)
 * Status      : VERIFIED — behavioural equivalence to the ROM held by
 *               reconstructed/samples/tests/harness_calc_fan1_control.py
 *               (host-gcc + mmap vs tools/sh2emu.py over edge + N random
 *               vectors; RAM side-effects compared byte-for-byte).
 * Lift (truth): c/calc_fan1_control.c  (same address; the ground truth for
 *               this port — one documented discrepancy fixed, see below).
 *
 * WHAT THIS IS
 * ------------
 * Cooling-fan relay control, called from the periodic task layer.  It turns
 * two fan relays on/off from one shared temperature input with per-fan
 * hysteresis, then computes a fan-enable latch from a branch tree over 13
 * status cells and publishes all three outputs back to RAM.
 *
 * Input:
 *   RAM[0xFFFFAA10]  (f32) temperature for the thermostat bands
 *
 * Outputs:
 *   RAM[0xFFFFBE16]  (u8)  fan 1 relay command (1 = on)
 *   RAM[0xFFFFBE17]  (u8)  fan 2 relay command (1 = on)
 *   RAM[0xFFFFBE0D]  (u8)  fan enable latch (1 = enable)
 *
 * ROM path (60E1D400.bin @0x303A6):
 *
 *     mov        #0x01,r6               ; r6 = 1 ("on" value)
 *     mov.l      @lit,r5                ; r5 = &RAM[0xFFFFBE16]
 *     mov.w      @lit,r2                ; r2 = &RAM[0xFFFFAA10] (temp)
 *     mov.l      @lit,r3                ; r3 = &ROM[0x7793C]  (T1_ON)
 *     fmov.s     @r2,fr4                ; fr4 = temp
 *     fmov.s     @r3,fr5                ; fr5 = T1_ON
 *     fmov       fr5,fr7                ; fr7 = T1_ON
 *     fmov.s     @r1,fr3                ; fr3 = T1_HY (ROM[0x77940])
 *     fsub       fr3,fr7                ; fr7 = T1_ON - T1_HY  (single rounding)
 *     fmov.s     @r7,fr6                ; fr6 = T2_ON (ROM[0x77944])
 *     fsub       fr2,fr6                ; fr6 = T2_ON - T2_HY  (single rounding)
 *     fcmp/gt    fr4,fr5                ; T = (T1_ON > temp)
 *     bt/s       .off1                  ; cold: test the low band
 *     mov        #0x00,r4               ;   (delay) r4 = 0 ("off" value)
 *     bra        .on1
 *     mov.b      r6,@r5                 ;   (delay) fan1 = 1   (hot or NaN)
 * .off1: fcmp/gt fr4,fr7                ; T = (T1_ON - T1_HY > temp)
 *     bf/s       .fan2                  ; warm band: hold fan1 unchanged
 *     nop
 *     mov.b      r4,@r5                 ; cold: fan1 = 0
 * .fan2: fmov.s   @r7,fr3               ; fr3 = T2_ON
 *     fcmp/gt    fr4,fr3                ; T = (T2_ON > temp)
 *     bt/s       .off2                  ; cold: test the low band
 *     nop
 *     mov.l      @lit,r2 ; bra .latch   ; hot or NaN: fan2 = 1
 *     mov.b      r6,@r2                 ;   (delay) fan2 = 1
 * .off2: fcmp/gt fr4,fr6                ; T = (T2_ON - T2_HY > temp)
 *     bf/s       .latch                 ; warm band: hold fan2 unchanged
 *     nop
 *     mov.l      @lit,r3 ; mov.b r4,@r3 ; cold: fan2 = 0
 * .latch: ... branch tree over the 13 status cells (0x30416..0x304C0),
 *     driving RAM[0xFFFFBE0D] = 1 or 0 (always written) ...
 *     rts
 *
 * Hysteresis calibration floats (ROM 0x7793C..0x77948, all exact in f32):
 *   T1_ON = 97.0   T1_HY = 3.0   T2_ON = 97.0   T2_HY = 3.0
 *   fan1 band: on when temp >= T1_ON, off when temp < T1_ON - T1_HY,
 *              previous state held in between (same band for fan2).
 *
 * DISCREPANCY vs THE LIFT (fixed here)
 * ------------------------------------
 * c/calc_fan1_control.c phrases the on-test as `t >= ROM_T1_ON`.  That is
 * NOT bit-exact for NaN inputs: IEEE `NaN >= x` is false, so the lift falls
 * into the "else if (t < T1_ON - T1_HY)" arm, which is also false for NaN,
 * and it leaves the relay at its PREVIOUS value.  The ROM instead branches
 * on `fcmp/gt` T = (T1_ON > temp) and takes the "on" (r6=1) path whenever T
 * is false — including NaN (all NaN comparisons are false), so the ROM
 * unconditionally writes fan1 = fan2 = 1 for NaN temp (same for +inf).
 * The verified emulator test (c/tests/test_calc_fan1_control.py) only ever
 * drew temps from [-50,150], so it never saw NaN.
 *
 * This port therefore keeps the ROM's exact comparison shape:
 * `!(t < T1_ON)` (identical to `!(T1_ON > t)` in IEEE-754) — hot AND NaN
 * (and +inf) turn the relay on, matching the hardware bit-for-bit.  All
 * non-NaN behaviour is identical to the lift.
 *
 * FP EXACTNESS
 * ------------
 * The band edges are computed at runtime as `T_ON - T_HY` in single
 * precision (one fsub in the ROM, one float subtraction here — 97.0f - 3.0f
 * = 94.0f exactly, but the expression keeps the ROM's single rounding).
 * No fmac/fmaf involved in this function.
 *
 * The enable-latch branch tree (0x30416..0x304C0) is mirrored exactly; see
 * the `for (;;)` state machine below with the per-state ROM addresses in
 * comments.  The "=="-vs-"!=" reads reproduce the ROM's extu.b+cmp/eq
 * (unsigned byte compare) and tst (zero-test) pairing per cell.
 * =============================================================================
 */
#include <stdint.h>

#define RAM_FAN_TEMP   (*(volatile float *)0xFFFFAA10)
#define RAM_FAN1_OUT   (*(volatile uint8_t *)0xFFFFBE16)
#define RAM_FAN2_OUT   (*(volatile uint8_t *)0xFFFFBE17)
#define RAM_FAN_ENABLE (*(volatile uint8_t *)0xFFFFBE0D)

#define ROM_T1_ON  (*(const float *)0x7793C)   /* 97.0 */
#define ROM_T1_HY  (*(const float *)0x77940)   /*  3.0 */
#define ROM_T2_ON  (*(const float *)0x77944)   /* 97.0 */
#define ROM_T2_HY  (*(const float *)0x77948)   /*  3.0 */

static uint8_t cell(uint32_t a) { return *(volatile uint8_t *)(uintptr_t)a; }

void rx8_calc_fan1_control(void)
{
    float t = RAM_FAN_TEMP;
    uint8_t be16, be17;
    uint8_t en;

    /* --- fan 1 thermostat (hysteresis) -------------------------------
     * `!(t < T1_ON)` is the ROM's `fcmp/gt fr4,fr5` / bt not-taken:
     * t >= T1_ON (and NaN/+inf) -> on; t < T1_ON - T1_HY -> off; else hold. */
    if (!(t < ROM_T1_ON))
        RAM_FAN1_OUT = 1;
    else if (t < ROM_T1_ON - ROM_T1_HY)
        RAM_FAN1_OUT = 0;
    be16 = RAM_FAN1_OUT;

    /* --- fan 2 thermostat (hysteresis) --- */
    if (!(t < ROM_T2_ON))
        RAM_FAN2_OUT = 1;
    else if (t < ROM_T2_ON - ROM_T2_HY)
        RAM_FAN2_OUT = 0;
    be17 = RAM_FAN2_OUT;

    /* --- fan enable latch ---------------------------------------------
     * Branch tree over 13 status cells; the state machine below mirrors
     * the firmware CFG at 0x30416..0x304C0 exactly (same as the lift). */
    en  = 0;
    {
        int loc = 0;
        for (;;) {
            if (loc == 0) {                       /* 0x30416: entry branch tree */
                if (be16 == 1 ||
                    (be17 == 1 && cell(0xFFFFB13D) == 1) ||
                    (cell(0xFFFFAAE0) == 0 && cell(0xFFFFBE0C) == 1 &&
                     cell(0xFFFFCD06) == 0 && cell(0xFFFFA96A) == 0 &&
                     cell(0xFFFFBFF5) == 0))
                    loc = 2;                      /* -> 0x30486 */
                else
                    loc = 1;                      /* -> 0x3046E */
            } else if (loc == 1) {                /* 0x3046E */
                if (cell(0xFFFFBDD4) == 1)
                    loc = 2;                      /* -> 0x30486 */
                else if (cell(0xFFFFBDD6) != 1)
                    loc = 3;                      /* -> 0x3049A */
                else
                    loc = 2;                      /* -> 0x30486 */
            } else if (loc == 2) {                /* 0x30486 */
                if (cell(0xFFFFD07C) != 0)
                    loc = 3;                      /* -> 0x3049A */
                else if (cell(0xFFFFD0E4) == 0)
                    loc = 4;                      /* -> 0x304B2 */
                else
                    loc = 3;                      /* -> 0x3049A */
            } else if (loc == 3) {                /* 0x3049A */
                if (cell(0xFFFFD2A0) == 1 || cell(0xFFFFD2A5) == 1)
                    loc = 4;                      /* -> 0x304B2 */
                else
                    loc = 5;                      /* -> 0x304C0 (enable=0) */
            } else if (loc == 4) {                /* 0x304B2 */
                if (cell(0xFFFFD29F) != 0)
                    loc = 5;                      /* -> 0x304C0 (enable=0) */
                else {
                    en = 1;                       /* -> 0x304BC (enable=1) */
                    break;
                }
            } else {                              /* 0x304C0: enable = 0 */
                break;
            }
        }
    }
    RAM_FAN_ENABLE = en;
}
