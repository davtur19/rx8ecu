/*
 * =============================================================================
 * rx8_calc_ignition_all_rotors_13c2c.c  —  MAIN IGNITION TIMING CORRECTION
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x13C2C  (code 0x13C2C..0x13CFA, literal pool 0x13CFA..0x13D3A;
 *               208 bytes)
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_calc_ignition_all_rotors_13c2c.py
 *               (host-gcc + mmap vs tools/sh2emu.py over edge + N random
 *               pre-state vectors; bit-exact IEEE-754 single-precision floats
 *               and byte-exact RAM side effects, real u8 1-D tables from this
 *               ROM; 0 mismatches).
 * Lift (truth): c/calc_ignition_all_rotors_13C2C.c (same address 0x13C2C)
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * Main ignition timing correction calculation, called by
 * engineControlCalculateTiming (0x14584) once per scheduler tick.  It
 * combines the engine-speed / knock-sensor / coolant-temperature state into
 * a per-rotor ignition correction and publishes it to the A734/A738 rotor
 * timing cells.  Disassembly of 60E1D400.bin @ 0x13C2C (condensed):
 *
 *     2FE6..2F86  mov.l r14,r13,r12 / fmov.s fr15,fr14 / sts.l pr  (prologue)
 *     DD0D  mov.l @(0x34,pc),r12 = 0xFFFFA744 ; F45C fmov.s @r12,fr5
 *     DC03  mov.w @(0x0C,pc),r13 = 0xA73C      ; F65C fmov.s @r13,fr6
 *     F65D  fmov fr5,fr15   ;  E502 mov #0,r5   ; ... r14 = u8@0xFFFFA740
 *     F45C  fmov fr6,fr4    ;  r2  = u8@0xFFFFA748 (knock sensor fault)
 *     2422  tst r2,r2
 *     8F04  bf/s 0x13c56    ;  faulted -> 0x13C56
 *     F0CE  fldi0 fr14      ;    (delay) fr14 = 0.0
 *     A018  bra 0x13c8a     ;  not faulted: fr15 = 0 (delay fmov fr14,fr15)
 *     25CE  fmov fr14,fr4   ;    (delay of 0x13c8a) fr4 = 0.0
 *     0x13c56: r0 = u8@0xFFFFA749 (knock detected)
 *       tst r0,r0 ; bf/s 0x13c74 (detected -> 0x13c74)
 *       0x13c60: r4 = 0x0006B68C ; jsr 0x2068 (1-D u8 lookup, x = f32@0xFFFFB5B8)
 *                 fr15 = fr0 ; f32@0xFFFFA74C = fr0 ; fr4 = 0.0
 *       0x13c74: r3 = u8@0xFFFFA75C (knock active) ; tst ; bf/s 0x13c8e
 *         extu.b r14,r0 ; cmp/eq #1,r0 ; bf/s 0x13cce (ign enable != 1: keep)
 *         fr15 = f32@0x0007987C (0.0) ;  bra 0x13cce ; fmov fr14,fr4 (delay)
 *       0x13c8e (knock active): extu.b r14,r0 ; cmp/eq #1,r0 ; bf/s 0x13cce
 *         r2 = u8@0xFFFFC0C7 (knock counter) ; r1 = u8@0x0007983B (==1)
 *         cmp/hs r1,r2 ; bf/s 0x13cac (counter < 1: skip the -2.5)
 *         fr4 = fr6 ; fr3 = f32@0x00079890 (2.5) ; fr4 = fr4 - fr3
 *         0x13cac (ECT): r0 = u8@0xFFFFC0C4 ; cmp/eq #1,r0 ; bf/s 0x13cce
 *           r1 = u8@0xFFFFC0C5 (corr enable; both arms use 1.0)
 *           fr15 = fr5 (delay) ; fr3 = f32@0x00079880 / 0x00079888 (1.0)
 *           fr15 = fr15 - fr3
 *     0x13cce (final dispatch):
 *       bsr 0x13ed2  ; A73C = saturate(fr4, f32@0x7989C, f32@0x798A0) = [-10,0]
 *       bsr 0x13e6c  ; A744 = saturate(fr15, table_sel(RPM), 0.0)
 *       bsr 0x13ee6  ; A734 = A738 = saturate(A744+A73C, t1(RPM), t2(RPM))
 *       u8@0xFFFFA75C = r14
 *     4F26..6DF6..000B  epilogue
 *
 * The three helper subroutines (0x13ED2, 0x13E6C, 0x13EE6) are modelled below
 * as static functions with their ROM behaviour; 0x2068 (generic 1-D/2-D
 * table lookup, type-dispatch + scale/offset) is a REAL ABI callee and stays
 * extern — the emulator harness runs its actual ROM bytes, the host test rig
 * supplies a faithful model of the type-4 (u8 cell) path (see the oracle).
 *
 * CALLING CONVENTION
 * ------------------
 * `void rx8_calc_ignition_all_rotors_13c2c(void)` — normal ABI entry, no
 * input registers, no meaningful return value.  Internally it makes three
 * `bsr` calls to 0x13ED2 / 0x13E6C / 0x13EE6 and, through them, three ABI
 * `jsr` calls to the generic table lookup 0x2068 (r4 = descriptor pointer,
 * fr4 = x, result in fr0).  Verified by comparing the RAM side-effects, not
 * a return value.
 *
 * RAM SIDE EFFECTS (all cells the harness compares, per path)
 * -----------------------------------------------------------
 *   WRITES (always): A734/A738 f32 = rotor timing, A73C f32 = clamp result,
 *                    A744 f32 = final timing, A75C u8 = ign-enable byte,
 *                    A750/A754 f32 = the two 0x13EE6 lookups (scratch)
 *   WRITE (knock detected==0 path only): A74C f32 = light-retard lookup
 *   READS  (never written): A740 u8, A748 u8, A749 u8, A75C u8 (input),
 *                    B5B8 f32, C0C4 u8, C0C5 u8, C0C7 u8,
 *                    B5A4 u8, BB55 u8, BCA9 u8 (0x13E6C table select)
 *
 * CALIBRATION (fixed ROM, read through the mapped ROM pages)
 * ----------------------------------------------------------
 *   0x79878 f32 = 0.0     (0x13E6C saturate upper bound)
 *   0x7987C f32 = 0.0     (zero correction constant)
 *   0x79880 f32 = 1.0     (ECT corr-enable==0 default, folded)
 *   0x79888 f32 = 1.0     (ECT corr-enable!=0 default, folded)
 *   0x79890 f32 = 2.5     (max knock retard)
 *   0x7989C f32 = -10.0   (0x13ED2 saturate lower bound)
 *   0x798A0 f32 = 0.0     (0x13ED2 saturate upper bound)
 *   0x79838 u8  = 5       (0x13E6C table-select threshold)
 *   0x7983B u8  = 1       (knock-counter threshold, byte vs byte)
 *   1-D descriptor 0x6B68C (knock detected==0 light-retard path): 5-pt u8,
 *     axis 0x798D4, values 0x798E8, scale 0.5, offset -64
 *   0x13E6C tables: A = 0x6B678 (4-pt u8, axis 0x798C0/values 0x798D0),
 *                   B = 0x6B664 (5-pt u8, axis 0x798A4/values 0x798B8)
 *   0x13EE6 rotor tables: t1 = 0x6B6A0 (12-pt u8, axis 0x798F0/values
 *     0x79920), t2 = 0x6B6B4 (12-pt u8, axis 0x7992C/values 0x7995C)
 *
 * LIFT-vs-ROM DISCREPANCIES
 * -------------------------
 * None: c/calc_ignition_all_rotors_13C2C.c matches the 60E1D400.bin
 * disassembly instruction-for-instruction (verified branch by branch above).
 * Points the lift calls out explicitly, confirmed against the ROM bytes here:
 *   1. The 2.5 deg knock retard is subtracted from the CLAMP INPUT
 *      (fr4 = fr6 - 2.5, fr6 = f32@A73C), NOT from the correction, and the
 *      counter comparison (0x13C9E) is BYTE-vs-BYTE (`cmp/hs` unsigned).
 *   2. The ECT block (0x13CAC..0x13CCC) OVERWRITES the correction with
 *      previous_timing - 1.0 (both corr_enable arms load 1.0).
 *   3. The final A744 store is the result of 0x13E6C and the rotor outputs
 *      are saturate(A744_result + A73C_result, t1(RPM), t2(RPM)); the sum is
 *      one fadd (single rounding) in the delay slot of the 0x13EE6 bsr.
 *
 * FP EXACTNESS (host model)
 * -------------------------
 *   - saturate helper 0x2404 (c/math_primitives.c, verified): the ROM's
 *     fcmp/gt pair returns `upper` when sig == upper (strict `>` on the
 *     in-range test), so -0.0 saturates to +0.0 at the 0.0 upper bound.
 *   - The type-4 handler @0x26B0 does one fsub then one fused fmac (SINGLE
 *     rounding each) -> `fmaf(t, v1 - v0, v0)` with the t == 0.0 fast path.
 *   - 0x2068 then applies scale/offset with one more fmac ->
 *     `fmaf(scale, interp, offset)`.
 *   - Axis search @0x2624: `!(x < axis[last])` clamps NaN/+inf high exactly
 *     like the ROM's fcmp/gt; t = (x - axis[i])/(axis[i+1] - axis[i]) is two
 *     fsubs + one fdiv.
 * =============================================================================
 */
#include <stdint.h>
#include <string.h>

/* ---- big-endian ROM reads (SH-2E is big-endian; the host oracle mmap()s
 * the ROM pages at their virtual addresses, so these assemble the numeric
 * value from the raw bytes) ------------------------------------------------ */
static uint8_t rom_u8(uint32_t a)
{
    return *(const uint8_t *)(uintptr_t)a;
}

static float rom_f32(uint32_t a)
{
    const uint8_t *p = (const uint8_t *)(uintptr_t)a;
    uint32_t u = ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16)
               | ((uint32_t)p[2] << 8) | (uint32_t)p[3];
    float f;
    memcpy(&f, &u, sizeof f);
    return f;
}

/* ---- RAM cells (see header; addresses straight from the mov.l/mov.w
 * literals of the ROM body) -------------------------------------------------- */
#define RAM_IGN_TIMING_LEAD   (*(volatile float *)0xFFFFA734)  /* rotor lead    */
#define RAM_IGN_TIMING_TRL    (*(volatile float *)0xFFFFA738)  /* rotor trail   */
#define RAM_CLAMP_INPUT       (*(volatile float *)0xFFFFA73C)  /* fr6 input; A73C output */
#define RAM_IGNITION_ENABLE   (*(volatile uint8_t *)0xFFFFA740)
#define RAM_IGNITION_TIMING   (*(volatile float *)0xFFFFA744)  /* fr5 input; A744 output */
#define RAM_KNOCK_SENSOR_FAULT (*(volatile uint8_t *)0xFFFFA748)
#define RAM_KNOCK_DETECTED    (*(volatile uint8_t *)0xFFFFA749)
#define RAM_KNOCK_SCRATCH     (*(volatile float *)0xFFFFA74C)  /* 0x13C6E store */
#define RAM_LKUP1_SCRATCH     (*(volatile float *)0xFFFFA750)  /* 0x13EE6       */
#define RAM_LKUP2_SCRATCH     (*(volatile float *)0xFFFFA754)  /* 0x13EE6       */
#define RAM_KNOCK_ACTIVE      (*(volatile uint8_t *)0xFFFFA75C) /* input; A75C = r14 output */
#define RAM_RPM_ALT           (*(volatile float *)0xFFFFB5B8)
#define RAM_ECT_STATUS        (*(volatile uint8_t *)0xFFFFC0C4)
#define RAM_ECT_CORR_ENABLE   (*(volatile uint8_t *)0xFFFFC0C5)
#define RAM_KNOCK_COUNTER     (*(volatile uint8_t *)0xFFFFC0C7)
#define RAM_STATUS_B5A4       (*(volatile uint8_t *)0xFFFFB5A4)
#define RAM_STATUS_BB55       (*(volatile uint8_t *)0xFFFFBB55)
#define RAM_STATUS_BCA9       (*(volatile uint8_t *)0xFFFFBCA9)

/* ---- calibration ROM addresses (see header) ------------------------------- */
#define CAL_13E6C_UPPER       0x00079878u   /* f32 0.0  */
#define CAL_ZERO              0x0007987Cu   /* f32 0.0  */
#define CAL_CORR_DEFAULT_1    0x00079880u   /* f32 1.0  */
#define CAL_CORR_DEFAULT_2    0x00079888u   /* f32 1.0  */
#define CAL_KNOCK_RETARD_MAX  0x00079890u   /* f32 2.5  */
#define CAL_13ED2_LOWER       0x0007989Cu   /* f32 -10.0*/
#define CAL_13ED2_UPPER       0x000798A0u   /* f32 0.0  */
#define CAL_13E6C_THRESH      0x00079838u   /* u8 5     */
#define CAL_KNOCK_THRESH_BYTE 0x0007983Bu   /* u8 1     */

#define CAL_TABLE_1D_DESC     ((const void *)0x0006B68Cu)  /* light-retard     */
#define CAL_13E6C_TABLE_A     ((const void *)0x0006B678u)  /* 4-pt u8          */
#define CAL_13E6C_TABLE_B     ((const void *)0x0006B664u)  /* 5-pt u8          */
#define CAL_13EE6_TABLE_1     ((const void *)0x0006B6A0u)  /* 12-pt u8         */
#define CAL_13EE6_TABLE_2     ((const void *)0x0006B6B4u)  /* 12-pt u8         */

/* Generic 1-D/2-D table lookup @0x2068 — real ABI callee (jsr @0x2068 in the
 * ROM body).  r4 = descriptor, fr4 = x, returns fr0.  The emulator harness
 * runs the ACTUAL ROM bytes of the callee; on the host build this is provided
 * by the oracle (see oracle_calc_ignition_all_rotors_13c2c.c). */
extern float rx8_table1d_lookup(const void *desc, float x);

/* ============================================================================
 * Helper 0x2404 — saturate into [lower, upper] (fr4=sig, fr5=lower,
 * fr6=upper; c/math_primitives.c verified model).  The ROM's fcmp/gt chain
 * uses a strict `>` for the in-range test, so sig == upper returns upper
 * (bit-exact: -0.0 at a 0.0 upper bound becomes +0.0).
 * ==========================================================================*/
static float saturate_0x2404(float sig, float lower, float upper)
{
    if (!(sig > lower)) return lower;
    if (upper > sig) return sig;
    return upper;
}

/* ============================================================================
 * Helper 0x13ED2 — clamp input to [-10.0, 0.0].
 * ROM: fr6 = f32@0x798A0 (upper 0.0), fr5 = f32@0x7989C (lower -10.0),
 *      jsr 0x2404.  Returns fr0 = saturate(fr4, -10.0, 0.0).
 * ==========================================================================*/
static float clamp_correction_0x13ED2(float v)
{
    return saturate_0x2404(v, rom_f32(CAL_13ED2_LOWER),
                              rom_f32(CAL_13ED2_UPPER));
}

/* ============================================================================
 * Helper 0x13E6C — final correction clamp: saturate(correction, table(RPM),
 * 0.0).  ROM table selection (0x13E76..0x13EB6, byte reads):
 *   if   byte@B5A4 == 1  &&  byte@BCA9 >= byte@0x79838 (5) -> table 0x6B678
 *   else if byte@B5A4 != 0                                  -> table 0x6B664
 *   else (byte@B5A4 == 0): byte@BB55 > 5 or byte@BB55 == 0  -> table 0x6B664
 *                          otherwise                        -> table 0x6B678
 * Then lower = table lookup(table, RPM@B5B8), upper = f32@0x79878 (0.0),
 *       return saturate(correction, lower, upper).
 * ==========================================================================*/
static const void *select_13E6C_table(void)
{
    uint8_t status = RAM_STATUS_B5A4;
    uint8_t bca9   = RAM_STATUS_BCA9;
    uint8_t bb55   = RAM_STATUS_BB55;
    uint8_t thr    = rom_u8(CAL_13E6C_THRESH);   /* 5 */

    if (status == 1 && bca9 >= thr)
        return CAL_13E6C_TABLE_A;
    if (status != 0)
        return CAL_13E6C_TABLE_B;
    if (bb55 > thr || bb55 == 0)
        return CAL_13E6C_TABLE_B;
    return CAL_13E6C_TABLE_A;
}

static float correction_final_clamp_0x13E6C(float correction)
{
    float rpm   = RAM_RPM_ALT;                       /* 0xFFFFB5B8 */
    float lower = rx8_table1d_lookup(select_13E6C_table(), rpm);
    float upper = rom_f32(CAL_13E6C_UPPER);          /* 0.0 */
    return saturate_0x2404(correction, lower, upper);
}

/* ============================================================================
 * Helper 0x13EE6 — rotor output clamp: saturate(v, t1(RPM), t2(RPM)).
 * ROM: lookup1 = table1D(0x6B6A0, RPM) -> RAM_A750,
 *      lookup2 = table1D(0x6B6B4, RPM) -> RAM_A754,
 *      then saturate(v, re-read A750, A754).  Caller passes v = A744 + A73C
 *      (the delay-slot fadd of the bsr).  The f32 store/reload of A750 is
 *      exact, so a local keeps the same value on the host.
 * ==========================================================================*/
static float rotor_output_clamp_0x13EE6(float v)
{
    float rpm   = RAM_RPM_ALT;                       /* 0xFFFFB5B8 */
    float lower = rx8_table1d_lookup(CAL_13EE6_TABLE_1, rpm);
    float upper = rx8_table1d_lookup(CAL_13EE6_TABLE_2, rpm);
    RAM_LKUP1_SCRATCH = lower;                       /* 0xFFFFA750 */
    RAM_LKUP2_SCRATCH = upper;                       /* 0xFFFFA754 */
    return saturate_0x2404(v, lower, upper);
}

/* ============================================================================
 * 0x13C2C — compute the combined ignition timing correction for all rotors.
 *
 * Register-level flow (mirrors the ROM exactly; fr15 = "correction" -> 0x13E6C
 * whose result lands at A744; fr4 = "clamp input" -> 0x13ED2 whose result
 * lands back at A73C):
 *   1. Load previous timing (fr5/A744), clamp input (fr6/A73C), enable byte
 *      (r14/A740), knock sensor fault (r2/A748).  fr15 = fr5, fr4 = fr6.
 *   2. If knock sensor NOT faulted: correction = 0, clamp input = 0.
 *   3. If faulted:
 *        a. knock_detected == 0: correction = table1D(0x6B68C, RPM),
 *           A74C = correction, clamp input = 0.
 *        b. knock_detected != 0, knock_active == 0:
 *              ign_enable == 1 -> correction = 0, clamp input = 0
 *              ign_enable != 1 -> keep fr15/fr4 (prev_timing / A73C)
 *        c. knock_detected != 0, knock_active != 0:
 *              ign_enable != 1 -> keep fr15/fr4 (prev_timing / A73C)
 *              ign_enable == 1 -> clamp input = A73C - 2.5 (when byte@C0C7
 *                                 >= byte@0x7983B) else A73C
 *              ECT byte@C0C4 == 1 -> OVERWRITE correction = prev_timing - 1.0
 *   4. Final dispatch: A73C = 0x13ED2(clamp input); A744 = 0x13E6C(correction);
 *      A734 = A738 = 0x13EE6(A744 + A73C); A75C = ign_enable byte.
 * ==========================================================================*/
void rx8_calc_ignition_all_rotors_13c2c(void)
{
    float previous_timing = RAM_IGNITION_TIMING;     /* fr5  = f32@A744 */
    float engine_speed    = RAM_CLAMP_INPUT;         /* fr6  = f32@A73C */
    uint8_t ign_enable_byte   = RAM_IGNITION_ENABLE; /* r14  = u8@A740  */
    uint8_t knock_sensor_fault = RAM_KNOCK_SENSOR_FAULT; /* r2 = u8@A748 */
    float correction  = previous_timing;             /* fr15 = fr5 */
    float clamp_input = engine_speed;                /* fr4  = fr6 */

    if (knock_sensor_fault == 0) {
        /* 0x13C4E not taken: bra 0x13C8A with fr14 = 0.0 (fldi0), then
         * fmov fr14,fr15 / fmov fr14,fr4. */
        correction  = rom_f32(CAL_ZERO);             /* 0.0 */
        clamp_input = 0.0f;
    } else {
        uint8_t knock_detected = RAM_KNOCK_DETECTED; /* 0xFFFFA749 */

        if (knock_detected == 0) {
            /* 0x13C60: light-retard path: RPM-based table lookup. */
            float rpm = RAM_RPM_ALT;                 /* 0xFFFFB5B8 */
            correction = rx8_table1d_lookup(CAL_TABLE_1D_DESC, rpm);
            RAM_KNOCK_SCRATCH = correction;          /* 0xFFFFA74C */
            clamp_input = 0.0f;                      /* fr4 = fr14 = 0.0 */
        } else {
            uint8_t knock_active = RAM_KNOCK_ACTIVE; /* 0xFFFFA75C */

            if (knock_active == 0) {
                /* 0x13C7E: knock detected but no knock control active. */
                if (ign_enable_byte == 1) {
                    correction  = rom_f32(CAL_ZERO); /* 0.0 */
                    clamp_input = 0.0f;              /* fr4 = fr14 = 0.0 */
                }
                /* else: bf 0x13CCE keeps fr15=previous_timing, fr4=A73C */
            } else {
                /* 0x13C8E: knock control active. */
                if (ign_enable_byte == 1) {
                    /* 0x13C96: BYTE-vs-BYTE threshold check (C0C7 vs
                     * cal@0x7983B, `cmp/hs` unsigned). */
                    uint8_t knock_counter = RAM_KNOCK_COUNTER;
                    uint8_t threshold     = rom_u8(CAL_KNOCK_THRESH_BYTE); /* 1 */
                    if (knock_counter >= threshold) {
                        /* 0x13CA4: fr4 = fr6 - 2.5 — the 2.5 deg knock
                         * retard comes out of the CLAMP INPUT (A73C), NOT
                         * out of the correction. */
                        clamp_input = engine_speed - rom_f32(CAL_KNOCK_RETARD_MAX);
                    } else {
                        clamp_input = engine_speed;
                    }

                    /* 0x13CAC: ECT block — OVERWRITES the correction with
                     * previous_timing - 1.0.  Both corr_enable arms load
                     * 1.0 (0x79880 / 0x79888), so the C0C5 byte read has no
                     * effect on the value (kept for fidelity). */
                    if (RAM_ECT_STATUS == 1) {       /* 0xFFFFC0C4 */
                        uint8_t corr_enable = RAM_ECT_CORR_ENABLE; /* C0C5 */
                        correction = previous_timing -
                            rom_f32(corr_enable == 0 ? CAL_CORR_DEFAULT_1
                                                     : CAL_CORR_DEFAULT_2);
                    }
                    /* else: fr15 stays = previous_timing */
                }
                /* else: bf 0x13CCE keeps fr15=previous_timing, fr4=A73C */
            }
        }
    }

    /* ---- Phase 3: final dispatch (0x13CCE..0x13CEC) ---- */

    /* bsr 0x13ED2: A73C = clamp(fr4, -10.0, 0.0) */
    float clamp_result = clamp_correction_0x13ED2(clamp_input);
    RAM_CLAMP_INPUT = clamp_result;                  /* 0xFFFFA73C */

    /* bsr 0x13E6C(fr4 = fr15): A744 = saturate(correction, table(RPM), 0.0) */
    float final_timing = correction_final_clamp_0x13E6C(correction);
    RAM_IGNITION_TIMING = final_timing;              /* 0xFFFFA744 */

    /* bsr 0x13EE6(fr4 = fadd fr3,fr4 = A744 + A73C):
     * A734 = A738 = saturate(sum, t1(RPM), t2(RPM)) */
    float rotor_timing = rotor_output_clamp_0x13EE6(final_timing + clamp_result);
    RAM_IGN_TIMING_LEAD = rotor_timing;              /* 0xFFFFA734 */
    RAM_IGN_TIMING_TRL  = rotor_timing;              /* 0xFFFFA738 */

    /* 0x13CEA: A75C = ign_enable_byte (r14) */
    RAM_KNOCK_ACTIVE = ign_enable_byte;
}
