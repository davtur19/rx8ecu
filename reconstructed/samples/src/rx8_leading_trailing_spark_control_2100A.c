/*
 * =============================================================================
 * rx8_leading_trailing_spark_control_2100A.c  —  SPARK LEAD/TRAIL
 *                                                COLD-VALIDITY / DECAY CONTROLLER
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x2100A  (body 0x2100A..0x21168; literal pool 0x2116A..0x2118C,
 *               next function CLChangeoverEnrichment @0x21190)
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_leading_trailing_spark_control_2100A.py
 *               (host-gcc + mmap vs tools/sh2emu.py over edge + N random
 *               pre-states; every RAM side-effect compared bit-exactly).
 * Lift (truth): c/leading_trailing_spark_control_2100A.c (same address,
 *               committed 4e52ec6 with docs/subsystems/IGNITION_SUBSYSTEM.md;
 *               independently re-verified here against the ROM bytes).
 *
 * WHAT THIS IS
 * ------------
 * Despite the IDA name, this routine does NOT compute a lead/trail split angle
 * and does NOT touch the per-rotor timing words A734/A738 (written identically
 * by calc_ignition_all_rotors_13C2C; see docs/subsystems/IGNITION_SUBSYSTEM.md
 * §4.14 — the real split lives in wankel_leading_trailing_split_487DC).
 * Instead it manages a cold/validity byte plus a pair of state floats that the
 * rest of the ignition software uses as a "spark split engaged" magnitude:
 *
 *   u8  @0xFFFFB240   cold/validity flag  (hysteresis on the coolant word)
 *   f32 @0xFFFFB18C   "leading"  state word (set to 1.0 / decayed / zeroed)
 *   f32 @0xFFFFB188   "trailing" state word (set to 1.0 / decayed / zeroed)
 *
 * Flow (mirrors the ROM 1:1; see the disassembly below):
 *   1.  B240 hysteresis:  B240 = 1 if coolant >= -40;  B240 = 0 if coolant
 *       < -43;  unchanged in [-43, -40).  (fcmp/gt unordered => NaN coolant
 *       takes the B240 = 1 arm, exactly like the hardware.)
 *   2.  Gates:  engine-off (C600) / enable (CCE1) / cal-byte (ROM 0x71BD0 != 1)
 *       -> clear both state words to 0.0.
 *   3.  Else if B240 != 1, AC/extra gate CDA0 != 0, or C6B4 > 1000.0
 *       -> fc() block (0x210FC).
 *   4.  Else set-1.0 test:  (B1C2 == 1 && u16@B1B2 != 0) || (B1C9 == 1 &&
 *       B1C4 == 1) || B1C7 == 1  ->  both state words = 1.0;  otherwise fc().
 *   5.  fc() (0x210FC):  B19C != 1 -> clear both;  else if u16@B1B2 == 0 or
 *       B1C7 == 0 or B1C9 == 0 or C6B4 > 1000.0 -> decay;  else if B1C4 != 0
 *       -> clear both;  else decay.
 *   6.  decay (0x21132):  B18C = max(B18C - 0.0667, 0.0) and
 *       B188 = max(B188 - 0.0667, 0.0), each through the shared jsr'd max
 *       helper @0x23E4 called with the second argument fr5 = fr15 = +0.0.
 *
 * DISASSEMBLY (60E1D400.bin @0x2100A, hand-annotated; fcmp/gt Fm,Fn sets
 * T = (Fn > Fm), fmov.s FRm,@Rn stores FRm):
 *
 *     mov.l r14,@-r15; mov.l r13,@-r15; mov.l r12,@-r15   ; prologue
 *     fmov.s fr15,@-r15; sts.l pr,@-r15
 *     mov.w 0x21044,r3 ; fmov.s @r3,fr4    ; fr4 = coolant (f32@0xFFFFAA10)
 *     mov.w 0x21046,r2 ; fmov.s @r2,fr7    ; fr7 = C6B4      (f32@0xFFFFC6B4)
 *     mov.l 0x21064,r1 ; fmov.s @r1,fr5    ; fr5 = -40.0 (ROM f32 @0x71C54)
 *     mov.l 0x21068,r3 ; fmov fr5,fr6      ; fr6 = -40.0
 *     mov.l 0x2106C,r2 ; fmov.s @r3,fr3    ; fr3 = 3.0  (ROM f32 @0x71C58)
 *     mov.w @r2,r4                          ; r4  = s16 u16@0xFFFFB1B2
 *     fsub fr3,fr6                          ; fr6 = -43.0  (runtime fsub)
 *     mov.l 0x21070,r3 ; fcmp/gt fr4,fr5    ; T = (-40.0 > coolant)
 *     mov.l 0x21060,r1 ; mov.b @r3,r7       ; r7  = u8@0xFFFFB1C7
 *     mov.b @r1,r5                          ; r5  = u8@0xFFFFB1C9
 *     mov.l 0x21074,r2 ; mov.l 0x21078,r12  ; r12 = &0xFFFFB240
 *     bt/s 0x2107C ; mov.b @r2,r6           ; T (coolant < -40) -> 0x2107C
 *     mov #0x01,r0 ; bra 0x21086 ; mov.b r0,@r12   ; B240 = 1 (>= -40)
 *     0x2107C: fcmp/gt fr4,fr6              ; T = (-43.0 > coolant)
 *     bf/s 0x21086 ; nop                    ; coolant >= -43 -> B240 unchanged
 *     mov #0x00,r3 ; mov.b r3,@r12          ; B240 = 0 (coolant < -43)
 *     ; ---- gated update (0x21086) ----
 *     mov.w 0x2116A,r13 ; mov.w 0x2116C,r14 ; r13/r14 = &0xFFFFB18C/0xFFFFB188
 *     mov.w 0x2116E,r3  ; mov.b @r3,r2      ; r2 = engine-off (u8@0xFFFFC600)
 *     tst r2,r2 ; bf/s 0x2115A ; fldi0 fr15  ; != 0 -> clear both (fr15 = 0.0)
 *     mov.w 0x21170,r1 ; mov.b @r1,r0       ; r0 = enable (u8@0xFFFFCCE1)
 *     tst r0,r0 ; bf/s 0x2115A ; nop        ; != 0 -> clear both
 *     mov.l 0x21178,r2 ; mov.b @r2,r0       ; r0 = cal byte (ROM u8 @0x71BD0)
 *     extu.b r0,r0 ; cmp/eq #0x01,r0
 *     bf/s 0x2115A ; nop                    ; != 1 -> clear both
 *     mov.b @r12,r0 ; extu.b r0,r0
 *     cmp/eq #0x01,r0 ; bf/s 0x210FC ; nop  ; B240 != 1 -> fc()
 *     mov.w 0x21172,r3 ; mov.b @r3,r2       ; r2 = AC gate (u8@0xFFFFCDA0)
 *     tst r2,r2 ; bf/s 0x210FC ; nop        ; != 0 -> fc()
 *     mov.l 0x2117C,r1 ; fmov.s @r1,fr3     ; fr3 = 1000.0 (ROM f32 @0x71C7C)
 *     fcmp/gt fr3,fr7 ; bt/s 0x210FC ; nop  ; C6B4 > 1000.0 -> fc()
 *     ; ---- set-1.0 test (0x210C8) ----
 *     mov.l 0x21180,r2 ; mov.b @r2,r0       ; r0 = u8@0xFFFFB1C2
 *     extu.b r0,r0 ; cmp/eq #0x01,r0
 *     bf/s 0x210DC ; nop                    ; B1C2 != 1 -> next
 *     extu.w r4,r0 ; cmp/pl r0              ; (u16)B1B2 > 0
 *     bt/s 0x210F4 ; nop                    ; -> set 1.0
 *     0x210DC: extu.b r5,r0 ; cmp/eq #0x01,r0
 *     bf/s 0x210EC ; nop                    ; B1C9 != 1 -> next
 *     extu.b r6,r0 ; cmp/eq #0x01,r0
 *     bt/s 0x210F4 ; nop                    ; B1C4 == 1 -> set 1.0
 *     0x210EC: extu.b r7,r0 ; cmp/eq #0x01,r0
 *     bf/s 0x210FC ; nop                    ; B1C7 != 1 -> fc()
 *     0x210F4: fldi1 fr4 ; fmov.s fr4,@r13  ; B18C = 1.0
 *     bra 0x2115E ; fmov.s fr4,@r14         ; B188 = 1.0
 *     ; ---- fc() (0x210FC) ----
 *     mov.w 0x21174,r3 ; mov.b @r3,r0       ; r0 = allow-dec (u8@0xFFFFB19C)
 *     extu.b r0,r0 ; cmp/eq #0x01,r0
 *     bf/s 0x21154 ; nop                    ; B19C != 1 -> clear both
 *     extu.w r4,r4 ; tst r4,r4 ; bt/s 0x21132 ; nop   ; B1B2 == 0 -> decay
 *     extu.b r7,r7 ; tst r7,r7 ; bt/s 0x21132 ; nop   ; B1C7 == 0 -> decay
 *     extu.b r5,r5 ; tst r5,r5 ; bt/s 0x21132 ; nop   ; B1C9 == 0 -> decay
 *     mov.l 0x2117C,r2 ; fmov.s @r2,fr3     ; fr3 = 1000.0
 *     fcmp/gt fr3,fr7 ; bt/s 0x21132 ; nop  ; C6B4 > 1000.0 -> decay
 *     extu.b r6,r6 ; tst r6,r6 ; bf/s 0x21154 ; nop   ; B1C4 != 0 -> clear
 *     ; ---- decay (0x21132) ----
 *     mov.l 0x21184,r3 ; fmov.s @r13,fr4    ; fr4 = B18C
 *     fmov.s @r3,fr3 ; mov.l 0x21188,r2     ; fr3 = 0.0667 (ROM f32 @0x71C74)
 *     fsub fr3,fr4 ; jsr @r2 ; fmov fr15,fr5  ; max_0x23E4(B18C - 0.0667, 0.0)
 *     fmov.s fr0,@r13                       ; B18C = result
 *     mov.l 0x2118C,r3 ; fmov.s @r14,fr4    ; fr4 = B188
 *     fmov.s @r3,fr3 ; mov.l 0x21188,r2     ; fr3 = 0.0667 (ROM f32 @0x71C78)
 *     fsub fr3,fr4 ; jsr @r2 ; fmov fr15,fr5  ; max_0x23E4(B188 - 0.0667, 0.0)
 *     bra 0x2115E ; fmov.s fr0,@r14         ; B188 = result
 *     0x21154: fmov.s fr15,@r13 ; bra 0x2115E ; fmov.s fr15,@r14 ; B18C=B188=0.0
 *     0x2115A: fmov.s fr15,@r13 ; fmov.s fr15,@r14 ; B18C = B188 = 0.0
 *     0x2115E: lds.l @r15+,pr ; fmov.s @r15+,fr15 ; mov.l @r15+,r12 ...
 *     rts ; mov.l @r15+,r14
 *
 * CALLING CONVENTION
 * ------------------
 * `void rx8_leading_trailing_spark_control_2100A(void)` — entered with a
 * normal `jsr`; no ABI arguments, no meaningful return value (the only exits
 * are `rts`).  Its whole effect is on the three RAM cells above, so the
 * harness drives it through the standard SH2.call() entry and compares RAM
 * side-effects, exactly like the rx8_ssv_control / rx8_purge_control_state_update
 * rigs.
 *
 * INTERNAL CALLEE
 * ---------------
 * The decay path makes one real ABI `jsr` call (twice) to the shared max
 * helper @0x23E4 with fr4 = (state - 0.0667) and fr5 = fr15 = +0.0.  The
 * emulator executes the ACTUAL ROM bytes of the helper; the host sample
 * inlines its net effect (`static float max_0x23E4` below) so it stays
 * self-contained.  Verified @0x23E4:
 *
 *     0x23E4 fcmp/gt fr5,fr4      ; T = (fr4 > fr5)
 *     0x23E6 bf/s 0x23EE ; nop    ; !(fr4 > fr5) -> fr6 = fr5
 *     0x23EA bra 0x23F0 ; fmov fr4,fr6     ; fr6 = fr4
 *     0x23EE fmov fr5,fr6                  ; fr6 = fr5
 *     0x23F0 rts ; fmov fr6,fr0            ; (delay) fr0 = fr6
 *
 * so fr0 = max(fr4, fr5).  With fr5 = +0.0 this clamps its argument to >= 0.0.
 * The final `fmov fr6,fr0` sits in the `rts` DELAY SLOT at 0x23F2 (opcode
 * F06C) — disassemblers that stop at `rts` miss it; the C `a > b ? a : b`
 * reproduces the net effect, including NaN (unordered fcmp -> T=0 -> fr0 =
 * fr5) and -0.0 (clamped to +0.0).
 *
 * FP EXACTNESS
 * ------------
 *   - `B18C - 0.0667` is one fsub (single rounding) then the max select, so
 *     `float v = state - 0.0667f; state = v > 0.0f ? v : 0.0f;` round-trips
 *     bit-exactly.  The decay step 0x0667 lives in the ROM as f32
 *     0x3D888889 = 0.06669999659..., and the two ROM constants 0x71C74 and
 *     0x71C78 hold identical values.
 *   - All `>`-based comparisons in this file are fcmp/gt in the ROM: C's `>`
 *     with a NaN operand yields false, matching the SH-2E FPU (unordered
 *     compare -> T = 0).  NaN coolant therefore takes the "warm" B240 = 1 arm
 *     and a NaN C6B4 never trips the `> 1000.0` gates, exactly like the ROM.
 *   - ROM constants are read big-endian by the ROM; the host oracle mmap()s
 *     the actual ROM pages at the same virtual addresses, so both sides read
 *     byte-identical constants.
 *
 * CALIBRATION CONSTANTS (ROM, fixed in this stock bin)
 * ----------------------------------------------------
 *   0x71BD0 u8   cal-enable gate        (= 1)
 *   0x71C54 f32  cold upper threshold   (= -40.0)
 *   0x71C58 f32  hysteresis delta       (= 3.0, so the lower threshold is -43.0)
 *   0x71C74 f32  decay step for B18C    (= 0.0667)
 *   0x71C78 f32  decay step for B188    (= 0.0667)
 *   0x71C7C f32  C6B4 over-threshold    (= 1000.0)
 *
 * RAM CELLS (all documented in c/leading_trailing_spark_control_2100A.c)
 * ---------------------------------------------------------------------
 * Reads:  f32@0xFFFFAA10 coolant, f32@0xFFFFC6B4 compare input,
 *         u16@0xFFFFB1B2 gate, u8@0xFFFFB1C7 / B1C9 / B1C4 / B1C2 gates,
 *         u8@0xFFFFC600 engine-off, u8@0xFFFFCCE1 enable, u8@0xFFFFCDA0
 *         AC/extra gate, u8@0xFFFFB19C allow-decay, f32@0xFFFFB18C / B188
 *         previous state (decay path).
 * Writes: u8@0xFFFFB240 cold flag, f32@0xFFFFB18C, f32@0xFFFFB188.
 * =============================================================================
 */
#include <stdint.h>

#include "rx8_samples.h"
#include "rx8_hw.h"

/* ---- RAM cells (addresses straight from the mov.l/mov.w literals) --------- */
#define RX8_LTSP_COOLANT_ADDR   0xFFFFAA10u   /* f32 coolant-temp input        */
#define RX8_LTSP_C6B4_ADDR      0xFFFFC6B4u   /* f32 compared vs CAL 1000.0    */
#define RX8_LTSP_GATE_WORD_ADDR 0xFFFFB1B2u   /* u16 gate word                 */
#define RX8_LTSP_B1C7_ADDR      0xFFFFB1C7u   /* u8 gate flag                  */
#define RX8_LTSP_B1C9_ADDR      0xFFFFB1C9u   /* u8 gate flag                  */
#define RX8_LTSP_B1C4_ADDR      0xFFFFB1C4u   /* u8 gate flag                  */
#define RX8_LTSP_B1C2_ADDR      0xFFFFB1C2u   /* u8 gate flag                  */
#define RX8_LTSP_ENG_OFF_ADDR   0xFFFFC600u   /* u8 engine-off flag            */
#define RX8_LTSP_ENABLE_ADDR    0xFFFFCCE1u   /* u8 enable gate                */
#define RX8_LTSP_AC_GATE_ADDR   0xFFFFCDA0u   /* u8 AC/extra gate              */
#define RX8_LTSP_ALLOW_DEC_ADDR 0xFFFFB19Cu   /* u8 allow-decay gate           */
#define RX8_LTSP_COLD_FLAG_ADDR 0xFFFFB240u   /* u8 cold/validity flag (out)   */
#define RX8_LTSP_LEAD_ADDR      0xFFFFB18Cu   /* f32 leading state word (out)  */
#define RX8_LTSP_TRAIL_ADDR     0xFFFFB188u   /* f32 trailing state word (out) */

/* ---- calibration constants read from the ROM (host: mapped pages) --------- */
#define ROM_LTSP_CAL_ENABLE   (*(const uint8_t *)0x00071BD0u)   /* 1         */
#define ROM_LTSP_COLD_HI      (*(const float   *)0x00071C54u)   /* -40.0     */
#define ROM_LTSP_HYST         (*(const float   *)0x00071C58u)   /* 3.0       */
#define ROM_LTSP_DECAY_LEAD   (*(const float   *)0x00071C74u)   /* 0.0667    */
#define ROM_LTSP_DECAY_TRAIL  (*(const float   *)0x00071C78u)   /* 0.0667    */
#define ROM_LTSP_CAL_1000     (*(const float   *)0x00071C7Cu)   /* 1000.0    */

/* 0x23E4 — shared max helper (real jsr callee in the ROM's decay path; the
 * emulator executes its actual bytes, this sample inlines the net effect).
 * Returns fr0 = max(fr4, fr5); the ROM calls it with fr5 = fr15 = +0.0, so it
 * clamps its argument to >= 0.0 (see "INTERNAL CALLEE" in the header). */
static float rx8_ltsp_max_0x23E4(float a, float b)
{
    return a > b ? a : b;
}

/* ---- 0x210FC + 0x21132 block (shared by the two fc() exits) -------------- */
static void rx8_ltsp_fc_block(uint16_t r4, uint8_t r5, uint8_t r6,
                              uint8_t r7, float fr7)
{
    if (RX8_IO8(RX8_LTSP_ALLOW_DEC_ADDR) != 1) {   /* 0x21154 clear path */
        *(volatile float *)(uintptr_t)RX8_LTSP_LEAD_ADDR  = 0.0f;
        *(volatile float *)(uintptr_t)RX8_LTSP_TRAIL_ADDR = 0.0f;
        return;
    }
    /* r4/r7/r5 zero or C6B4 > 1000.0 -> decay; else B1C4 != 0 -> clear. */
    if (r4 == 0 || r7 == 0 || r5 == 0 || fr7 > ROM_LTSP_CAL_1000) {
        /* fall through to the decay block @0x21132 */
    } else if (r6 != 0) {
        *(volatile float *)(uintptr_t)RX8_LTSP_LEAD_ADDR  = 0.0f;
        *(volatile float *)(uintptr_t)RX8_LTSP_TRAIL_ADDR = 0.0f;
        return;
    }

    /* 0x21132 decay: B18C = max(B18C - 0.0667, 0.0), then the same for B188.
     * The ROM does one fsub (single rounding) then selects via the jsr'd max
     * helper @0x23E4 (fr5 = fr15 = +0.0).  The two 0.0667 constants come from
     * two different ROM words (0x71C74 / 0x71C78) holding identical values. */
    {
        float v = *(volatile float *)(uintptr_t)RX8_LTSP_LEAD_ADDR - ROM_LTSP_DECAY_LEAD;
        *(volatile float *)(uintptr_t)RX8_LTSP_LEAD_ADDR = rx8_ltsp_max_0x23E4(v, 0.0f);
        v = *(volatile float *)(uintptr_t)RX8_LTSP_TRAIL_ADDR - ROM_LTSP_DECAY_TRAIL;
        *(volatile float *)(uintptr_t)RX8_LTSP_TRAIL_ADDR = rx8_ltsp_max_0x23E4(v, 0.0f);
    }
}

/* ---- 0x2100A  spark lead/trail cold-validity / decay controller ---------- */
void rx8_leading_trailing_spark_control_2100A(void)
{
    float    fr4   = *(volatile float *)(uintptr_t)RX8_LTSP_COOLANT_ADDR;
    float    fr7   = *(volatile float *)(uintptr_t)RX8_LTSP_C6B4_ADDR;
    uint16_t r4    = RX8_IO16(RX8_LTSP_GATE_WORD_ADDR);
    uint8_t  r7    = RX8_IO8(RX8_LTSP_B1C7_ADDR);
    uint8_t  r5    = RX8_IO8(RX8_LTSP_B1C9_ADDR);
    uint8_t  r6    = RX8_IO8(RX8_LTSP_B1C4_ADDR);
    uint8_t  r0    = RX8_IO8(RX8_LTSP_B1C2_ADDR);
    uint8_t  eng   = RX8_IO8(RX8_LTSP_ENG_OFF_ADDR);
    uint8_t  enab  = RX8_IO8(RX8_LTSP_ENABLE_ADDR);
    uint8_t  ac    = RX8_IO8(RX8_LTSP_AC_GATE_ADDR);
    float    fr5   = ROM_LTSP_COLD_HI;              /* -40.0 */
    float    fr6   = fr5 - ROM_LTSP_HYST;           /* -43.0 (fsub @0x2102A) */

    /* ---- Block A: B240 cold/validity flag (0x2103A..0x21084).  The ROM's
     * `fcmp/gt fr4,fr5` sets T = (-40.0 > coolant); an unordered (NaN)
     * coolant clears T, so NaN takes the B240 = 1 arm. ---------------- */
    if (fr5 > fr4) {                          /* coolant < -40.0 */
        if (fr6 > fr4)                        /* coolant < -43.0 */
            RX8_IO8(RX8_LTSP_COLD_FLAG_ADDR) = 0;
        /* else B240 unchanged in [-43, -40) */
    } else {
        RX8_IO8(RX8_LTSP_COLD_FLAG_ADDR) = 1;
    }

    /* ---- Block B: gated state update (0x21086..).  The three hard gates
     * clear both state words (0x2115A); the soft gates fall into fc(). - */
    if (eng != 0 || enab != 0 || ROM_LTSP_CAL_ENABLE != 1) {
        *(volatile float *)(uintptr_t)RX8_LTSP_LEAD_ADDR  = 0.0f;
        *(volatile float *)(uintptr_t)RX8_LTSP_TRAIL_ADDR = 0.0f;
    } else if (RX8_IO8(RX8_LTSP_COLD_FLAG_ADDR) != 1 || ac != 0 ||
               fr7 > ROM_LTSP_CAL_1000) {
        rx8_ltsp_fc_block(r4, r5, r6, r7, fr7);
    } else {
        /* set-1.0 test (0x210C8..0x210F4) */
        if ((r0 == 1 && r4 > 0) || (r5 == 1 && r6 == 1) || r7 == 1) {
            *(volatile float *)(uintptr_t)RX8_LTSP_LEAD_ADDR  = 1.0f;
            *(volatile float *)(uintptr_t)RX8_LTSP_TRAIL_ADDR = 1.0f;
        } else {
            rx8_ltsp_fc_block(r4, r5, r6, r7, fr7);
        }
    }
}
