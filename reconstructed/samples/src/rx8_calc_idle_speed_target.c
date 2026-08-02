/*
 * =============================================================================
 * rx8_calc_idle_speed_target.c  —  IDLE SPEED TARGET CALCULATION
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x12F5E  (274 bytes, 0x12F5E..0x1306F)
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_calc_idle_speed_target.py
 *               (host-gcc + mmap vs tools/sh2emu.py over edge + N random
 *               vectors; every side-effected RAM cell compared bit-for-bit;
 *               0 mismatches).
 * Lift (truth): c/calc_idle_speed_target.c (same address) — re-verified
 *               instruction-for-instruction against the 60E1D400.bin
 *               disassembly during this lift; the discrepancies listed at the
 *               bottom were found in the lift and are corrected here.
 *
 * WHAT THE FUNCTION DOES
 * ----------------------
 * Periodic idle-speed target calculation.  It gates on three enable
 * conditions, computes a coolant-temperature-based target through the
 * sensor_range_check leaf, publishes it to RAM[0xFFFFA678], then runs an
 * adaptive-learning accumulator.  ROM body (60E1D400.bin @0x12F5E):
 *
 *     mov.l r14/r13/r12/r11,@-r15 ; fmov.s fr15,@-r15 ; sts.l pr,@-r15
 *     mov.b @0xFFFFA444,r14       ; rotor A status
 *     mov.b @0xFFFFA445,r13       ; rotor B status
 *     mov.b @0xFFFFC600,r1        ; engine-running flag
 *     tst r1,r1 ; bf/s zero        ; (delay) fldi0 fr15      fr15 = 0.0
 *     mov.w @0xFFFFA424,r3        ; engine RPM (raw)
 *     mov.w @0x00072BC0,r2        ; idle RPM threshold (u16, 2500)
 *     cmp/hs r2,r3 ; bf/s zero    ; rpm < threshold        -> target 0
 *     mov.b @0xFFFFAADA,r2        ; closed-loop flag
 *     tst r2,r2 ; bf/s zero       ; closed-loop active     -> target 0
 *     fmov.s @0xFFFFC12C,fr5      ; coolant temp (main)
 *     fmov.s @0xFFFFC128,fr4      ; coolant temp (alt)
 *     jsr    @0x0003ED0C          ; sensor_range_check
 *     fsub   fr5,fr4              ;   (delay) fr4 = alt - main
 *     bra    done / fmov.s fr0,@0xFFFFA678    ; RAM[0xA678] = fr0
 *   zero:
 *     fmov.s fr15,@0xFFFFA678     ; RAM[0xA678] = 0.0
 *   done:
 *     ... phase 2 (increment flag), phase 3 (adaptive), phase 4 (save rotors)
 *
 * RAM side effects (all cells the harness compares):
 *   written: 0xFFFFA678 f32 idle target
 *            0xFFFFA68F u8  increment flag
 *            0xFFFFA680 f32 adaptive accumulator
 *            0xFFFFA6A9 u8  rotor A status (persisted)
 *            0xFFFFA6AA u8  rotor B status (persisted)
 *   read:    0xFFFFA444 u8  rotor A status
 *            0xFFFFA445 u8  rotor B status
 *            0xFFFFA424 u16 engine RPM raw
 *            0xFFFFC600 u8  engine-running flag
 *            0xFFFFAADA u8  closed-loop flag
 *            0xFFFFC12C f32 coolant temperature (main)
 *            0xFFFFC128 f32 coolant temperature (alt)
 *            0xFFFFA670 f32 adaptive reference 1 (zero-check path only)
 *            0xFFFFA674 f32 adaptive reference 2 (zero-check path only)
 *            0xFFFFA6A9 / 0xFFFFA6AA u8 state flags (read in phase 2)
 *
 * CALLING CONVENTION / CALLEES
 * ----------------------------
 * `void rx8_calc_idle_speed_target(void)` — no ABI arguments, no meaningful
 * return value; the whole effect is the RAM side effects above.  The ROM
 * internally jsr's TWO non-ABI leaves whose REAL ROM bytes the emulator
 * executes; the host sample inlines their net semantics as static helpers
 * (exactly like rx8_calc_intake_pressure_pid_output.c inlines its 0x2440 /
 * 0x2404 leaves):
 *
 *   - sensor_range_check @0x3ED0C  (fr4 = a, fr5 = b; returns fr0):
 *         if (b == 0.0f) {
 *             if (a == 0.0f) return  0.0f;          (fldi0, +0.0)
 *             if (a >  0.0f) return *(f32*)0x3EF78; (+3.402823e38, 0x7F7FFFFC)
 *             else           return *(f32*)0x3EF7C; (-3.402823e38, 0xFF7FFFFC)
 *         }
 *         return a / b;                              (one fdiv)
 *   - fpu_max @0x23E4  (fr4 = a, fr5 = b; returns fr0): the greater of the
 *         two arguments, via a single fcmp/gt (fr4 > fr5 ? fr4 : fr5); a NaN
 *         operand makes the compare unordered (false), so the result is fr5.
 *
 * FP EXACTNESS
 * ------------
 * The arithmetic is limited to: one fsub (alt - main), one fdiv (a / b) and
 * one more read-modify of the accumulator — each a single IEEE-754
 * single-precision rounding, reproduced exactly by native C `float` ops.  All
 * branch conditions are `fcmp/eq` / `fcmp/gt` on the SH-2E FPU, which report
 * unordered (false) for NaN operands exactly like the C `==` / `>` used here.
 *
 * ROM constants are big-endian; the host oracle mmap()s the ROM pages, so all
 * multi-byte calibration reads here go through explicit byte assembly
 * (rom_u16 / rom_f32) exactly as rx8_get_maf_sensor_value.c does — identical
 * value on both sides.
 *
 * DISCREPANCIES vs c/calc_idle_speed_target.c (fixed here)
 * --------------------------------------------------------
 *   1. ROTOR-B GATE INVERTED.  The lift's "else if (state_flag_b == 1 &&
 *      rotor_b != 0): continue with existing inc_flag" has the wrong
 *      polarity.  The ROM (0x12FFC..0x13016) loads the calibration byte for
 *      BOTH rotor gates when the matching rotor status is ZERO — `cmp/eq #1`
 *      on the flag, then `tst` on the rotor byte, so `rotor_b == 0` (not
 *      != 0) selects the table load, symmetric with rotor A.  This sample
 *      loads the table when `state_flag_b == 1 && rotor_b == 0`.
 *   2. ADAPTIVE LEAF MISIDENTIFIED.  The lift calls 0x23E4 "fpu_mul_float"
 *      and leaves `float learned = adaptive;` as a placeholder; the ROM leaf
 *      is a plain MAX selection (fr4 vs fr5, one fcmp/gt):
 *      RAM[0xFFFFA680] = max(RAM[0xFFFFA680], RAM[0xFFFFA678]).
 *   3. INC-FLAG DECREMENT CALLED "SATURATING".  The lift's comment says
 *      "saturation counter", but the ROM does a plain byte add of 0xFF
 *      (i.e. -1, wrapping modulo 256): RAM[0xFFFFA68F] += 0xFF.
 *   4. sensor_range_check DESCRIPTION INCOMPLETE.  The lift's comment
 *      ("if b == 0: return range constant") omits the a == 0.0 case, which
 *      the ROM handles first (fldi0 -> +0.0).
 *   5. The lift reads the phase-2 state flags only on the "store_target"
 *      fall-through; behaviourally identical, restructured here to the ROM's
 *      linear flow (flag read at 0x12FEA, final save at 0x1305A).
 * =============================================================================
 */
#include <stdint.h>
#include <string.h>

#include "rx8_samples.h"

/* ---- RAM map (all addresses from the mov.w/mov.l literals of the ROM body) */
#define RAM_ROTOR_A_STATUS      0xFFFFA444u  /* u8   rotor A status (input)   */
#define RAM_ROTOR_B_STATUS      0xFFFFA445u  /* u8   rotor B status (input)   */
#define RAM_ENGINE_RPM_RAW      0xFFFFA424u  /* u16  engine speed (raw)       */
#define RAM_ENGINE_RUNNING      0xFFFFC600u  /* u8   engine-running flag      */
#define RAM_CLOSED_LOOP_ACTIVE  0xFFFFAADAu  /* u8   closed-loop flag         */
#define RAM_COOLANT_TEMP_MAIN   0xFFFFC12Cu  /* f32  coolant temperature      */
#define RAM_COOLANT_TEMP_ALT    0xFFFFC128u  /* f32  coolant temperature (alt)*/
#define RAM_IDLE_SPEED_TARGET   0xFFFFA678u  /* f32  idle target (result)     */
#define RAM_TARGET_INC_FLAG     0xFFFFA68Fu  /* u8   increment flag           */
#define RAM_IDLE_STATE_FLAG_A   0xFFFFA6A9u  /* u8   rotor A state flag       */
#define RAM_IDLE_STATE_FLAG_B   0xFFFFA6AAu  /* u8   rotor B state flag       */
#define RAM_IDLE_SPEED_ADAPTIVE 0xFFFFA680u  /* f32  adaptive accumulator     */
#define RAM_IDLE_ADAPT_REF_1    0xFFFFA670u  /* f32  adaptive reference 1     */
#define RAM_IDLE_ADAPT_REF_2    0xFFFFA674u  /* f32  adaptive reference 2     */

/* ---- Calibration constants (real stock values; the oracle maps the ROM
 *      pages so both sides read identical big-endian bytes) ----------------- */
#define ROM_IDLE_RPM_THRESHOLD  0x00072BC0u  /* u16  2500  (idle RPM gate)    */
#define ROM_IDLE_INC_VALUE      0x00072BBBu  /* u8   0xFF  (flag reload)      */
#define ROM_RANGE_POS           0x0003EF78u  /* f32  +3.402823e38 (0x7F7FFFFC)*/
#define ROM_RANGE_NEG           0x0003EF7Cu  /* f32  -3.402823e38 (0xFF7FFFFC)*/

#define IO8(a)   (*(volatile uint8_t *)(uintptr_t)(a))
#define IO16(a)  (*(volatile uint16_t *)(uintptr_t)(a))
#define IOF(a)   (*(volatile float   *)(uintptr_t)(a))

/* Big-endian ROM word: the SH-2E stores multi-byte constants big-endian, so a
 * straight little-endian dereference on the host would byte-swap them. */
static uint16_t rom_u16(uint32_t addr)
{
    const uint8_t *p = (const uint8_t *)(uintptr_t)addr;
    return (uint16_t)((uint16_t)p[0] << 8) | p[1];
}

static float rom_f32(uint32_t addr)
{
    const uint8_t *p = (const uint8_t *)(uintptr_t)addr;
    uint32_t u = ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16)
               | ((uint32_t)p[2] << 8) | (uint32_t)p[3];
    float f;
    memcpy(&f, &u, sizeof f);
    return f;
}

/* ---- 0x3ED0C — sensor_range_check (called once via jsr, fr4=a, fr5=b).
 *
 * ROM:
 *     fldi0 fr3            ; fr3 = 0.0
 *     fcmp/eq fr3,fr5      ; T = (b == 0.0)
 *     bf/s  divide         ; b != 0 -> a / b
 *     nop
 *     fcmp/eq fr3,fr4      ; T = (a == 0.0)
 *     bf/s  const          ; a != 0 -> range constant
 *     nop
 *     bra  done / fldi0 fr6 ; a == 0 -> +0.0
 *   const:
 *     fcmp/gt fr3,fr4      ; T = (a > 0.0)
 *     mova 0x3EF78,r0 / bf/s neg_const
 *     bra  done / fmov.s @r0,fr6   ; +3.402823e38
 *   neg_const:
 *     mova 0x3EF7C,r0 / bra done / fmov.s @r0,fr6   ; -3.402823e38
 *   divide:
 *     fmov fr4,fr6 ; fdiv fr5,fr6 ; fmov fr6,fr6
 *   done:
 *     rts / fmov fr6,fr0
 *
 * Inlined here with the near-max single range constants read from the ROM
 * literal pool.  NaN b: `b == 0.0` is unordered (false) -> falls to a / b
 * = NaN, exactly like the C below. */
static float rx8_sensor_range_check_3ED0C(float a, float b)
{
    if (b == 0.0f) {
        if (a == 0.0f) {
            return 0.0f;
        }
        if (a > 0.0f) {
            return rom_f32(ROM_RANGE_POS);
        }
        return rom_f32(ROM_RANGE_NEG);
    }
    return a / b;
}

/* ---- 0x23E4 — fpu_max (called once via jsr, fr4=a, fr5=b).
 *
 * ROM:
 *     fcmp/gt fr5,fr4      ; T = (a > b)
 *     bf/s  else
 *     nop
 *     bra  done / fmov fr4,fr6   ; a > b -> a
 *   else:
 *     fmov fr5,fr6         ; else -> b
 *   done:
 *     rts / fmov fr6,fr0
 *
 * Plain max; with a NaN operand fcmp/gt reports unordered (false) and the
 * result is fr5 (b), matching the C comparisons below. */
static float rx8_fpu_max_23e4(float a, float b)
{
    if (a > b) {
        return a;
    }
    return b;
}

/* ---- 0x12F5E — idle speed target calculation (void; result is RAM) ------- */
void rx8_calc_idle_speed_target(void)
{
    uint8_t  rotor_a;
    uint8_t  rotor_b;
    uint16_t rpm_raw;
    float    idle_target;

    /* Prologue snapshot (ROM 0x12F6C..0x12F76). */
    rotor_a = IO8(RAM_ROTOR_A_STATUS);
    rotor_b = IO8(RAM_ROTOR_B_STATUS);
    rpm_raw = IO16(RAM_ENGINE_RPM_RAW);

    /* ---- Phase 1: enable gates -> idle target (0x12F78..0x12FA6). ---- */
    if (IO8(RAM_ENGINE_RUNNING) != 0u) {                 /* 0x12F78 tst      */
        idle_target = 0.0f;                              /* fldi0 fr15        */
    } else if (rpm_raw < rom_u16(ROM_IDLE_RPM_THRESHOLD)) {  /* 0x12F86 cmp/hs */
        idle_target = 0.0f;
    } else if (IO8(RAM_CLOSED_LOOP_ACTIVE) != 0u) {      /* 0x12F90 tst      */
        idle_target = 0.0f;
    } else {
        /* 0x12F96..0x12FA2: fr5 = coolant_main, fr4 = alt - main (fsub in
         * the jsr delay slot), then sensor_range_check -> fr0. */
        float coolant_main = IOF(RAM_COOLANT_TEMP_MAIN);
        float coolant_alt  = IOF(RAM_COOLANT_TEMP_ALT);
        idle_target = rx8_sensor_range_check_3ED0C(
                          coolant_alt - coolant_main, coolant_main);
    }
    IOF(RAM_IDLE_SPEED_TARGET) = idle_target;            /* 0x12FA6 / 0x12FE4 */

    /* ---- Phase 2: increment-flag update (0x12FE6..0x13028). ---------- */
    if (IO8(RAM_IDLE_STATE_FLAG_A) == 1u && rotor_a == 0u) {
        /* 0x13010: reload the flag from the ROM calibration byte. */
        IO8(RAM_TARGET_INC_FLAG) = *(const uint8_t *)(uintptr_t)ROM_IDLE_INC_VALUE;
    } else if (IO8(RAM_IDLE_STATE_FLAG_B) == 1u && rotor_b == 0u) {
        /* 0x12FFC..0x1300C: same gate for rotor B (see discrepancy #1). */
        IO8(RAM_TARGET_INC_FLAG) = *(const uint8_t *)(uintptr_t)ROM_IDLE_INC_VALUE;
    } else if (IO8(RAM_TARGET_INC_FLAG) != 0u) {
        /* 0x13018..0x13028: byte decrement by 1 (add 0xFF, wraps). */
        IO8(RAM_TARGET_INC_FLAG) = (uint8_t)(IO8(RAM_TARGET_INC_FLAG) + 0xFFu);
    }

    /* ---- Phase 3: adaptive learning (0x1302A..0x13058). ---------------- */
    if (IO8(RAM_TARGET_INC_FLAG) != 0u) {
        /* 0x13036..0x13040: jsr fpu_max_23E4(fr4 = adaptive, fr5 = target). */
        float adaptive = IOF(RAM_IDLE_SPEED_ADAPTIVE);
        float target   = IOF(RAM_IDLE_SPEED_TARGET);
        IOF(RAM_IDLE_SPEED_ADAPTIVE) = rx8_fpu_max_23e4(adaptive, target);
    } else if (!(IOF(RAM_IDLE_ADAPT_REF_1) > 0.0f) &&
               !(IOF(RAM_IDLE_ADAPT_REF_2) > 0.0f)) {
        /* 0x13042..0x13058: zero the accumulator when both references are
         * not > 0 (two fcmp/gt; NaN counts as "not > 0"). */
        IOF(RAM_IDLE_SPEED_ADAPTIVE) = 0.0f;             /* fmov fr15 */
    }

    /* ---- Phase 4: persist rotor state (0x1305A..0x13060). ------------- */
    IO8(RAM_IDLE_STATE_FLAG_A) = rotor_a;
    IO8(RAM_IDLE_STATE_FLAG_B) = rotor_b;
}
