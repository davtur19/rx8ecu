/*
 * =============================================================================
 * rx8_calc_fuel_pump_duty_trim.c  —  FUEL-PUMP DUTY-CYCLE TRIM CALCULATION
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x135F6  (92 bytes, 0x135F6..0x13650; next function at 0x13652)
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_calc_fuel_pump_duty_trim.py
 *               (host-gcc vs tools/sh2emu.py over edge + random vectors;
 *               bit-exact f32 outputs at RAM[0xFFFFA6F4 / 0xFFFFA6E4 /
 *               0xFFFFA6E8], 0 mismatches).
 * Lift (truth): c/calc_fuel_pump_duty_trim.c (same address; listed in
 *               c/verified_addrs.txt) — re-verified instruction-for-instruction
 *               against the 60E1D400.bin disassembly during this lift; no
 *               discrepancy found.
 *
 * WHAT THE FUNCTION DOES
 * ----------------------
 * Called from engineControlCalculateTiming Phase 2.  Computes the fuel-pump
 * PWM duty-cycle trim for the two pump channels from a calibration-time mode
 * byte stored at ROM 0x6E430.  The disassembly (60E1D400.bin @0x135F6):
 *
 *     D638   mov.l  0x136D8,r6       ; r6 = 0x0006E430  (mode byte, ROM cal)
 *     955B   mov.w  0x136B2,r5       ; r5 = 0xFFFFA6F4  (base duty / out m0)
 *     6360   mov.b  @r6,r3           ; r3 = mode
 *     2338   tst    r3,r3
 *     8F03   bf/s   0x13608          ; mode != 0  -> skip mode-0 block
 *     0009   nop
 *     9257   mov.w  0x136B4,r2       ; r2 = 0xFFFFA63C  (mode-0 cal source)
 *     F328   fmov.s @r2,fr3
 *     F53A   fmov.s fr3,@r5          ; RAM[0xFFFFA6F4] = RAM[0xFFFFA63C]
 *     13608: 9755   mov.w  0x136B6,r7 ; r7 = 0xFFFFA6E4  (front duty out)
 *     6460   mov.b  @r6,r4           ; mode (again)
 *     604C   extu.b r4,r0
 *     8801   cmp/eq #0x01,r0         ; mode == 1 ?
 *     8F12   bf/s   0x13638
 *     6403   mov    r0,r4
 *     ...    fmov/fadd chain:
 *             front = (base + RAM[A6FC]) + RAM[A70C]   -> RAM[A6E4]
 *             rear  = (base + RAM[A700]) + RAM[A710]   -> RAM[A6E8]
 *     (base = RAM[0xFFFFA6F4]; A6FC/ A70C = front comps,
 *      A700/A710 = rear comps)
 *     ...    bra 0x1364E (skip mode-2 block)
 *     13638: cmp/eq #0x02,r0         ; mode == 2 ?
 *     ...    RAM[A6E4] = *(f32*)0x6E438 ; RAM[A6E8] = *(f32*)0x6E43C
 *     1364E: rts
 *
 * Modes:
 *   mode == 0 (stock):  RAM[0xFFFFA6F4] = RAM[0xFFFFA63C]  (flat copy)
 *   mode == 1:          front = (base + VAL_A) + VAL_B,
 *                       rear  = (base + VAL_C) + VAL_D      (active trim)
 *   mode == 2:          front = ROM 0x6E438, rear = ROM 0x6E43C (safe mode)
 *   any other mode:     no writes at all
 *
 * The checks are sequential (branch-out per test), so the modes are mutually
 * exclusive in practice — exactly one byte value can be set at a time.
 *
 * CALLING CONVENTION / CALLEES
 * ----------------------------
 * `void rx8_calc_fuel_pump_duty_trim(void)` — no arguments, no ABI return
 * value; the whole effect is the RAM writes above.  The function is a LEAF:
 * its body contains NO jsr/bsr at all (every operand is a direct fmov.s /
 * fadd on the RAM/ROM literals).  There are therefore no internal callees to
 * model on the host side.
 *
 * FP EXACTNESS
 * ------------
 * Modes 0 and 2 are pure bit copies (fmov.s load/store) — no arithmetic, so
 * any bit pattern (NaN, inf, denormals) round-trips exactly.  Mode 1 emits
 * exactly two fadds per channel, each a single IEEE-754 single-precision
 * rounding: `(base + comp) + comp`.  The emulator computes the intermediate
 * in double precision (exact for two f32 operands) and rounds once to f32;
 * the host C `-O2` SSE fadd rounds once to f32 — both correctly-rounded, so
 * the results are bit-identical for every operand combination including
 * NaN/Inf (empirically checked in the harness).  NaN payload propagation and
 * signed-zero arithmetic follow IEEE-754 on both sides.
 *
 * CALIBRATION NOTES
 * -----------------
 * The mode byte at ROM 0x6E430 is a *fixed calibration-time selection* (the
 * stock 60E1D400.bin has 0x00 = mode 0); tuners could reflash it.  The two
 * safe-mode constants at 0x6E438/0x6E43C are both 0.0f in the stock bin.
 * To exercise all three branches the harness overrides the mode byte on BOTH
 * sides: the emulator's sparse RAM overlay (which takes precedence over ROM
 * in sh2emu.py) and the oracle's MAP_FIXED-mapped ROM cal page — i.e. the
 * oracle ships the mode byte inline per vector, exactly as the lift was
 * verified.
 * =============================================================================
 */
#include <stdint.h>

#include "rx8_samples.h"

/* ---- RAM map (all addresses verified against the 0x136B2..0x136C0 literal
 *      pool of the ROM body) ---- */
#define RAM_FUEL_BASE_DUTY   (*(volatile float *)0xFFFFA6F4u)  /* base duty (in; mode-0 out) */
#define RAM_FUEL_TRIM_SRC    (*(volatile float *)0xFFFFA63Cu)  /* mode-0 flat-copy source  */
#define RAM_FUEL_FRONT_OUT   (*(volatile float *)0xFFFFA6E4u)  /* front channel duty out   */
#define RAM_FUEL_REAR_OUT    (*(volatile float *)0xFFFFA6E8u)  /* rear channel duty out    */
#define RAM_FUEL_COMP_A      (*(volatile float *)0xFFFFA6FCu)  /* mode-1 front comp 1      */
#define RAM_FUEL_COMP_B      (*(volatile float *)0xFFFFA70Cu)  /* mode-1 front comp 2      */
#define RAM_FUEL_COMP_C      (*(volatile float *)0xFFFFA700u)  /* mode-1 rear comp 1       */
#define RAM_FUEL_COMP_D      (*(volatile float *)0xFFFFA710u)  /* mode-1 rear comp 2       */

/* ---- Calibration constants (real ROM values; the oracle seeds this page
 *      with the stock 60E1D400.bin bytes — the mode byte is overridden per
 *      vector so every branch is exercised) ---- */
#define CAL_FUEL_MODE        (*(const uint8_t *)0x0006E430u)  /* mode selector (0 stock)   */
#define CAL_FUEL_SAFE_FRONT  (*(const float *)0x0006E438u)    /* mode-2 safe front (0.0f)  */
#define CAL_FUEL_SAFE_REAR   (*(const float *)0x0006E43Cu)    /* mode-2 safe rear  (0.0f)  */

/* 0x135F6 — fuel-pump duty trim (void; result is the RAM writes). */
void rx8_calc_fuel_pump_duty_trim(void)
{
    uint8_t mode;

    /* ---- Read operating mode (calibration byte at ROM 0x6E430) ---- */
    mode = CAL_FUEL_MODE;

    /* ---- Mode 0: Default — flat copy of the calibration float ---- */
    if (mode == 0) {
        RAM_FUEL_BASE_DUTY = RAM_FUEL_TRIM_SRC;
    }

    /* ---- Mode 1: Active trim (two fadds per channel) ---- */
    if (mode == 1) {
        float base = RAM_FUEL_BASE_DUTY;

        /* front = (base + VAL_A) + VAL_B */
        RAM_FUEL_FRONT_OUT = (base + RAM_FUEL_COMP_A) + RAM_FUEL_COMP_B;

        /* rear  = (base + VAL_C) + VAL_D */
        RAM_FUEL_REAR_OUT = (base + RAM_FUEL_COMP_C) + RAM_FUEL_COMP_D;
    }

    /* ---- Mode 2: Safe defaults from ROM calibration ---- */
    if (mode == 2) {
        RAM_FUEL_FRONT_OUT = CAL_FUEL_SAFE_FRONT;
        RAM_FUEL_REAR_OUT = CAL_FUEL_SAFE_REAR;
    }
}
