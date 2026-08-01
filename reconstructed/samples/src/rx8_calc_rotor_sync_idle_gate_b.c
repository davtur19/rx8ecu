/*
 * =============================================================================
 * rx8_calc_rotor_sync_idle_gate_b.c  —  ROTOR-SYNC IDLE/ANTI-STALL GATE, BANK B
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x12BC8  (196 bytes: 0x12BC8 .. 0x12C8B)
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_calc_rotor_sync_idle_gate_b.py
 *               (host-gcc + mmap vs tools/sh2emu.py over edge + random
 *               pre-states, default N=20000; the control flag AND both float
 *               side-effect cells are compared bit-exactly).
 * Lift (truth): c/calc_rotor_sync_idle_gate_B.c  (same address; ground truth
 *               for this port; the ROM bytes themselves are executed here via
 *               tools/sh2emu.py).
 *
 * WHAT THIS IS
 * ------------
 * A rotor-sync idle/anti-stall control gate for the "Rotor B" bank of the
 * 2-rotor Renesis (a Wankel — it has NO camshafts, NO VVT and NO oil control
 * valve; the original IDA-AI "cam timing PID / rotor sync PID" annotation was
 * a piston-engine misnomer, there is no PID here).  Each call:
 *
 *   - samples the current RPM (RAM[0xFFFFB5B8]) into RAM[0xFFFFA694], so that
 *     cell always holds the *previous* RPM sample after the call,
 *   - computes drop = prev_rpm - rpm (signed, single-precision float),
 *   - drives the gate flag RAM[0xFFFFA690] to 1 iff ALL of these hold:
 *       1. (RAM[0xFFFFB5A4] closed-loop-enable == 1) OR (RAM[0xFFFFCABC]
 *          warmup == 1)                              [first test short-circuits]
 *       2. RAM[0xFFFFAADA] closed-loop-active == 1
 *       3. rotor-select: (RAM[0xFFFFA6A3] enable-A == 1 AND RAM[0xFFFFA444]
 *          rotor-A == 0) OR (RAM[0xFFFFA6A4] enable-B == 1 AND
 *          RAM[0xFFFFA445] rotor-B == 0)             [gate armed for the rotor
 *                                                     that is NOT currently
 *                                                     running]
 *       4. drop >= 40.0   (cal ROM[0x72BC4])
 *       5. rpm <= 2000.0  (cal ROM[0x72BC8])
 *   - always (both branches) latches the rotor status bytes into
 *     RAM[0xFFFFA6A3]/RAM[0xFFFFA6A4] (overwriting the enable bits read above).
 *
 * ROM path (60E1D400.bin @0x12BC8):
 *
 *     mov.w 0x12C48,r3 ; mov.b @r3,r4   ; r4 = rotor-A status  (0xFFFFA444)
 *     mov.w 0x12C4A,r2 ; mov.b @r2,r5   ; r5 = rotor-B status  (0xFFFFA445)
 *     mov.w 0x12C4C,r1 ; fmov.s @r1,fr4 ; fr4 = rpm            (0xFFFFB5B8)
 *     mov.l 0x12C58,r6 ; fmov.s @r6,fr5 ; fr5 = prev rpm       (0xFFFFA694)
 *     mov.l 0x12C70,r7                 ; r7 = 0xFFFFA690 (gate flag)
 *     mov.w 0x12C4E,r3 ; mov.b @r3,r0   ; cl-enable (0xFFFFB5A4)
 *     extu.b r0,r0 ; cmp/eq #1,r0 ; bt/s PASS_CL   ; if ==1, skip the OR
 *       fsub fr4,fr5                    ;   (delay) fr5 = prev - rpm (ALWAYS)
 *       mov.w 0x12C50,r2 ; mov.b @r2,r0 ; warmup (0xFFFFCABC); if !=1
 *       ... cmp/eq #1 ; bf/s DISABLE
 *     PASS_CL: mov.w 0x12C52,r3 ; mov.b @r3,r0  ; cl-active (0xFFFFAADA)
 *       ... cmp/eq #1 ; bf/s DISABLE
 *       mov.l 0x12C5C,r2 ; mov.b @r2,r0         ; enable-A (0xFFFFA6A3)
 *       ... cmp/eq #1 ; bf/s B_CHECK ; nop
 *       mov.b @r4,r0 ; tst r0,r0 ; bt/s PASS_DROP ; nop   ; rotor-A == 0
 *     B_CHECK: mov.l 0x12C60,r3 ; mov.b @r3,r0  ; enable-B (0xFFFFA6A4)
 *       ... cmp/eq #1 ; bf/s DISABLE ; nop
 *       mov.b @r5,r1 ; tst r1,r1 ; bf/s DISABLE ; nop   ; rotor-B != 0
 *     PASS_DROP: mov.l 0x12C74,r3 ; fmov.s @r3,fr3       ; fr3 = cal 40.0
 *       fcmp/gt fr5,fr3 ; bt/s DISABLE ; nop             ; 40.0 > drop?
 *       mov.l 0x12C78,r2 ; fmov.s @r2,fr2                ; fr2 = cal 2000.0
 *       fcmp/gt fr4,fr2 ; bt/s DISABLE ; nop             ; rpm > 2000?
 *       mov #1,r3 ; bra TAIL ; mov.b r3,@r7              ; flag = 1 (delay)
 *     DISABLE: mov #0,r1 ; mov.b r1,@r7                  ; flag = 0
 *     TAIL: fmov.s fr4,@r6       ; RAM[0xFFFFA694] = rpm (new prev sample)
 *       mov.l 0x12D50,r3 ; mov.l 0x12D54,r2
 *       mov.b r4,@r3 ; rts ; mov.b r5,@r2                ; latch rotor-A/B
 *                                                        ;   status into
 *                                                        ;   0xFFFFA6A3/A6A4
 *
 * FP EXACTNESS
 * ------------
 * The only FP math is ONE `fsub` (fr5 - fr4, a single rounding) plus two
 * `fcmp/gt` strict-greater-than tests — there is NO fmac here, so no fmaf()
 * is required; `drop = prev - rpm` in C with -O2 on SSE reproduces the single
 * rounding exactly.  The gate comparisons are written `!(40.0f > drop)` and
 * `!(rpm > 2000.0f)` to mirror the ROM's `fcmp/gt; bt disable` exactly: a NaN
 * operand makes the comparison false on both sides, so NaN drop/NaN rpm PASS
 * the checks just like the hardware.
 *
 * SUBTLE ENCODING NOTE (discrepancy check vs the lift)
 * ----------------------------------------------------
 * The two flag stores are `mov #1,r3 ; mov.b r3,@r7` (enable) and
 * `mov #0,r1 ; mov.b r1,@r7` (disable) — note E100 is `mov #0,R1`, NOT R0
 * (the register nibble is the low nibble of the first opcode byte: E1nn =
 * mov #imm,Rn).  Misreading E100 as R0 leads to the false conclusion that the
 * disable path leaves RAM[0xFFFFA690] untouched; in fact BOTH paths store the
 * flag, exactly as the lift writes `RAM_CAM_TIMING_FLAG = out;`.  No other
 * discrepancy was found: the lift (c/calc_rotor_sync_idle_gate_B.c) matches
 * the ROM byte-for-byte on every path, including the unconditional
 * rpm->0xFFFFA694 sample and the rotor-status latch into 0xFFFFA6A3/A6A4.
 *
 * CALLING CONVENTION
 * ------------------
 * Normal ABI call (via jsr from the task layer): takes no arguments (all
 * inputs are fixed RAM/ROM addresses) and returns nothing.  Its whole effect
 * is on RAM, so the harness compares the four side-effect cells
 * (0xFFFFA690 u8, 0xFFFFA694 float, 0xFFFFA6A3/A6A4 u8) bit-exactly; the
 * emulator runs the REAL ROM bytes via the stock SH2.call() entry.
 * =============================================================================
 */
#include <stdint.h>

#include "rx8_samples.h"
#include "rx8_hw.h"

/* ---- fixed RAM footprint (on-chip window 0xFFFF6000..0xFFFFDFFF) ---- */
#define RX8_ROTOR_A_STATUS   RX8_IO8(0xFFFFA444)   /* rotor-A run status   */
#define RX8_ROTOR_B_STATUS   RX8_IO8(0xFFFFA445)   /* rotor-B run status   */
#define RX8_ENGINE_RPM       (*(volatile float *)0xFFFFB5B8u) /* rpm input */
#define RX8_PREV_RPM         (*(volatile float *)0xFFFFA694u) /* prev sample */
#define RX8_GATE_FLAG        RX8_IO8(0xFFFFA690)   /* control output flag  */
#define RX8_CL_LOOP_ENABLE   RX8_IO8(0xFFFFB5A4)   /* closed-loop enable   */
#define RX8_CL_LOOP_ACTIVE   RX8_IO8(0xFFFFAADA)   /* closed-loop active   */
#define RX8_WARMUP_ENRICH    RX8_IO8(0xFFFFCABC)   /* warmup enrichment    */
#define RX8_ENABLE_A         RX8_IO8(0xFFFFA6A3)   /* enable-A / latch     */
#define RX8_ENABLE_B         RX8_IO8(0xFFFFA6A4)   /* enable-B / latch     */

/* ---- calibration constants read from the ROM's own cal table ---- */
#define RX8_CAL_DROP_MIN     (*(const float *)0x00072BC4u)   /* 40.0   */
#define RX8_CAL_RPM_MAX      (*(const float *)0x00072BC8u)   /* 2000.0 */

/* 0x12BC8 — rotor-sync idle/anti-stall gate, bank B. */
void rx8_calc_rotor_sync_idle_gate_b(void)
{
    uint8_t rotor_a = RX8_ROTOR_A_STATUS;
    uint8_t rotor_b = RX8_ROTOR_B_STATUS;
    float   rpm     = RX8_ENGINE_RPM;
    float   prev    = RX8_PREV_RPM;
    float   drop    = prev - rpm;      /* ROM's fsub in the delay slot — always */
    uint8_t out     = 0;

    if ((RX8_CL_LOOP_ENABLE == 1u || RX8_WARMUP_ENRICH == 1u) &&
        RX8_CL_LOOP_ACTIVE == 1u) {

        /* rotor-select: gate is armed for the rotor that is NOT running */
        int rotor_ok =
            (RX8_ENABLE_A == 1u && rotor_a == 0u) ||
            (RX8_ENABLE_B == 1u && rotor_b == 0u);

        if (rotor_ok &&
            !(RX8_CAL_DROP_MIN > drop) &&     /* fcmp/gt 40.0,drop: T=(40>drop) */
            !(rpm > RX8_CAL_RPM_MAX)) {       /* fcmp/gt rpm,2000: T=(rpm>2000) */
            out = 1;
        }
    }

    RX8_GATE_FLAG = out;                /* RAM[0xFFFFA690] (both paths store)   */
    RX8_PREV_RPM = rpm;                 /* sample current RPM as prev for next  */
    RX8_ENABLE_A = rotor_a;             /* latch rotor status (0xFFFFA6A3)      */
    RX8_ENABLE_B = rotor_b;             /* latch rotor status (0xFFFFA6A4)      */
}
