/*
 * =============================================================================
 * rx8_iat_sensor.c  —  INTAKE-AIR-TEMPERATURE SENSOR COMPARE + STATUS FLAGS
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x3C214  (body 0x3C214..0x3C2F6; 228 bytes, no literal pools
 *               inside the body beyond the mov.w/mov.l pool 0x3C25C..0x3C26E)
 * Status      : VERIFIED — behavioural equivalence to the ROM bytes held by
 *               reconstructed/samples/tests/harness_iat_sensor.py
 *               (host-gcc + mmap vs tools/sh2emu.py over edge + N random
 *               pre-state vectors; every side-effected RAM cell compared
 *               byte-for-byte, including the "left-unchanged" status cells;
 *               0 mismatches).
 * Lift (truth): c/iat_sensor.c  (iat_sensor_3C214 @ 0x3C214 — the lift's
 *               *descriptions* of the ADC/TwoDLookup pipeline are NOT what
 *               the bytes do; see DISCREPANCIES below).
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * IAT sensor validation task.  It performs NO ADC read, NO 2-D lookup and
 * NO floating-point work.  The whole body is integer byte compares followed
 * by flag / status writes.  Disassembly of 60E1D400.bin @0x3C214:
 *
 *     mov.l  r14,@-r15                     ; prologue (r14 + r13)
 *     mov    #0x00,r5
 *     mov.w  lit,r1  ; r1 = 0xFFFFC5EC     ; compare-channel A input
 *     mov.l  r13,@-r15
 *     mov.w  lit,r3  ; r3 = 0xFFFFD201     ; "reset request" input byte
 *     mov.b  @r3,r6                        ; r6 = *0xFFFFD201 (read once)
 *     mov.l  lit,r7  ; r7 = 0x0007A9A8     ; cal threshold byte 0
 *     mov.b  @r1,r2 ; mov.b @r7,r0         ; r2 = *C5EC ; r0 = thr0
 *     cmp/hi r0,r2 ; bf/s next ; mov #1,r4 ; if (*C5EC > thr0)
 *     ...  mov.b r4,@r0  /  mov.b r5,@r0   ;    flag A (*C5F4) = 1 else 0
 *     ...  same shape with *C5ED -> *C5F5  ;    flag B (*C5F5) = (*C5ED > thr0)
 *     ...  same shape with *C5EE -> *C5F6  ;    flag C (*C5F6) = (*C5EE > thr0)
 *
 *     mov.w lit,r7  ; r7 = 0xFFFFC5F8      ; status byte 1
 *     if (*C5F5 == 1 || *C5F4 == 1 || r6 == 1)  *C5F8 = 0   ; clear
 *     else if (*C5EF > thr1 || *C5F7 == 1)       *C5F8 = 1   ; arm
 *     else  ( *C5F8 left UNCHANGED )
 *     mov.w lit,r7  ; r7 = 0xFFFFC5F9      ; status byte 2
 *     if (*C5F6 == 1 || *C5F4 == 1 || r6 == 1)  *C5F9 = 0   ; clear
 *     else if (*C5F0 > thr1 || *C5F7 == 1)       *C5F9 = 1   ; arm
 *     else  ( *C5F9 left UNCHANGED )
 *     mov.l  @r15+,r13 ; rts ; mov.l @r15+,r14
 *
 * CALLEES: none.  There is no jsr/bsr in the whole body; the emulator harness
 * runs the exact bytes with no call graph, and the host build is completely
 * self-contained.
 *
 * CALLING CONVENTION
 * ------------------
 * `void rx8_iat_sensor(void)` — no arguments, no meaningful return value.
 * The function is driven through the standard SH2.call() entry and verified
 * by comparing the side-effected RAM cells (9 bytes seeded, 5 read back).
 *
 * INPUTS (RAM, u8; the harness seeds all of them)
 * -------------------------------------------------
 *   0xFFFFD201  reset request byte — 1 clears both status bytes.  This cell is
 *               already documented in the verified lifts
 *               c/dtc_debounce_monitor_43760.c ("reset request (1 = zero
 *               everything)") and c/calibration_apply_4B770.c.
 *   0xFFFFC5EC  compare-channel A input  (> thr0  -> flag A @0xFFFFC5F4)
 *   0xFFFFC5ED  compare-channel B input  (> thr0  -> flag B @0xFFFFC5F5)
 *   0xFFFFC5EE  compare-channel C input  (> thr0  -> flag C @0xFFFFC5F6)
 *   0xFFFFC5EF  status-1 arm-threshold input (> thr1 -> arm status 1)
 *   0xFFFFC5F0  status-2 arm-threshold input (> thr1 -> arm status 2)
 *   0xFFFFC5F7  fault-active input — 1 arms both status bytes
 *   (0xFFFFC5F8 / 0xFFFFC5F9 pre-state matters: both status bytes are
 *    "hold last value" when neither the clear nor the arm condition fires)
 *
 * OUTPUTS (RAM, u8)
 * -----------------
 *   0xFFFFC5F4  flag A  (channel-A over-threshold), written 0/1
 *   0xFFFFC5F5  flag B  (channel-B over-threshold), written 0/1
 *   0xFFFFC5F6  flag C  (channel-C over-threshold), written 0/1
 *   0xFFFFC5F8  status byte 1
 *   0xFFFFC5F9  status byte 2
 *
 * CALIBRATION (ROM, u8)
 * ---------------------
 *   0x0007A9A8  thr0  = 0xFA  (first compare threshold; "sensor present"
 *                              validity bound used by all three channels)
 *   0x0007A9A9  thr1  = 0xFA  (second threshold gating the arm paths)
 *   (values from the stock bin; the oracle seeds the mapped page from the
 *    ROM file, so they stay live on the host exactly as on the target.)
 *
 * DISCREPANCIES vs c/iat_sensor.c  (the lift is a fabricated description)
 * -----------------------------------------------------------------------
 * The lift documents an ADC->voltage->TwoDLookup pipeline (reads 0xFFFF9EE6,
 * scales by 7.62939e-5, interpolates the cal table, writes a float to
 * 0xFFFFC5F0, compares the ADC against thresholds at 0x6D462/0x6D464 and
 * packs a bit-field status).  NONE of that is present in the ROM bytes:
 *   1. There is no FPU instruction and no jsr in 0x3C214..0x3C2F6 — no ADC
 *      read, no 2-D lookup, no float write.
 *   2. The compare inputs are the byte cells 0xFFFFC5EC/C5ED/C5EE (not an
 *      ADC word); 0xFFFFC5F0 is used here as a u8 compare input (the doc
 *      table in docs/subsystems/SENSOR_PIPELINE.md calls it an "IAT processed
 *      temperature float" — that is wrong for this function).
 *   3. There are TWO status bytes (0xFFFFC5F8, 0xFFFFC5F9), each with
 *      clear-by-fault-or-reset / arm-by-threshold-or-fault-input / HOLD
 *      semantics; the lift's single packed byte `(over<<2)|(hi<<1)|lo` does
 *      not exist.
 *   4. The documented "over-temperature" threshold bytes at 0x6D462/0x6D464
 *      are never read; the real thresholds are bytes 0/1 of the table at
 *      0x7A9A8 (both 0xFA).
 *   5. The status bytes are left UNCHANGED when neither condition fires — the
 *      lift's unconditional writes would clobber the held state.
 *
 * NOTE ON THE COMPARES: the ROM sign-extends each u8 into a 32-bit register
 * (`mov.b @r,r`) and compares with `cmp/hi` (unsigned).  Sign-extension is
 * monotonic for unsigned comparison, so the model below is the equivalent
 * `(uint8_t)lhs > (uint8_t)rhs` — byte-identical results on every input.
 * =============================================================================
 */
#include <stdint.h>

#include "rx8_samples.h"

/* ---- input cells (u8) ------------------------------------------------ */
#define RX8_IAT_RESET_ADDR     0xFFFFD201u  /* reset request: 1 clears status */
#define RX8_IAT_CMP_A_ADDR     0xFFFFC5ECu  /* compare channel A              */
#define RX8_IAT_CMP_B_ADDR     0xFFFFC5EDu  /* compare channel B              */
#define RX8_IAT_CMP_C_ADDR     0xFFFFC5EEu  /* compare channel C              */
#define RX8_IAT_ST1_THR_ADDR   0xFFFFC5EFu  /* status-1 arm-threshold input   */
#define RX8_IAT_ST2_THR_ADDR   0xFFFFC5F0u  /* status-2 arm-threshold input   */
#define RX8_IAT_FAULT_IN_ADDR  0xFFFFC5F7u  /* fault-active input (arms both) */

/* ---- output cells (u8) ----------------------------------------------- */
#define RX8_IAT_FLAG_A_ADDR    0xFFFFC5F4u  /* channel-A over-threshold flag  */
#define RX8_IAT_FLAG_B_ADDR    0xFFFFC5F5u  /* channel-B over-threshold flag  */
#define RX8_IAT_FLAG_C_ADDR    0xFFFFC5F6u  /* channel-C over-threshold flag  */
#define RX8_IAT_STATUS_1_ADDR  0xFFFFC5F8u  /* status byte 1 (hold-by-default)*/
#define RX8_IAT_STATUS_2_ADDR  0xFFFFC5F9u  /* status byte 2 (hold-by-default)*/

/* ---- calibration bytes (ROM; oracle seeds them from the bin) ---------- */
#define RX8_IAT_CAL_THR0_ADDR  0x0007A9A8u  /* u8 = 0xFA : channel threshold  */
#define RX8_IAT_CAL_THR1_ADDR  0x0007A9A9u  /* u8 = 0xFA : status-arm thr.    */

/* 0x3C214 — IAT sensor compare + status flags. */
void rx8_iat_sensor(void)
{
    const uint8_t reset = *(volatile uint8_t *)(uintptr_t)RX8_IAT_RESET_ADDR;
    const uint8_t thr0  = *(const uint8_t *)(uintptr_t)RX8_IAT_CAL_THR0_ADDR;
    const uint8_t thr1  = *(const uint8_t *)(uintptr_t)RX8_IAT_CAL_THR1_ADDR;

    /* (1) per-channel over-threshold flags (0x3C222..0x3C25A, 0x3C270). */
    *(volatile uint8_t *)(uintptr_t)RX8_IAT_FLAG_A_ADDR =
        (*(volatile uint8_t *)(uintptr_t)RX8_IAT_CMP_A_ADDR > thr0) ? 1u : 0u;
    *(volatile uint8_t *)(uintptr_t)RX8_IAT_FLAG_B_ADDR =
        (*(volatile uint8_t *)(uintptr_t)RX8_IAT_CMP_B_ADDR > thr0) ? 1u : 0u;
    *(volatile uint8_t *)(uintptr_t)RX8_IAT_FLAG_C_ADDR =
        (*(volatile uint8_t *)(uintptr_t)RX8_IAT_CMP_C_ADDR > thr0) ? 1u : 0u;

    /* (2) status byte 1 @0xFFFFC5F8 (0x3C272..0x3C2B2): cleared by any fault
     * flag or the reset request, armed by the arm-threshold input or the
     * fault-active input, otherwise HOLD LAST VALUE. */
    if (*(volatile uint8_t *)(uintptr_t)RX8_IAT_FLAG_B_ADDR == 1u ||
        *(volatile uint8_t *)(uintptr_t)RX8_IAT_FLAG_A_ADDR == 1u ||
        reset == 1u) {
        *(volatile uint8_t *)(uintptr_t)RX8_IAT_STATUS_1_ADDR = 0u;
    } else if (*(volatile uint8_t *)(uintptr_t)RX8_IAT_ST1_THR_ADDR > thr1 ||
               *(volatile uint8_t *)(uintptr_t)RX8_IAT_FAULT_IN_ADDR == 1u) {
        *(volatile uint8_t *)(uintptr_t)RX8_IAT_STATUS_1_ADDR = 1u;
    }

    /* (3) status byte 2 @0xFFFFC5F9 (0x3C2B2..0x3C2F2): same shape, driven
     * by flag C / the status-2 arm-threshold input. */
    if (*(volatile uint8_t *)(uintptr_t)RX8_IAT_FLAG_C_ADDR == 1u ||
        *(volatile uint8_t *)(uintptr_t)RX8_IAT_FLAG_A_ADDR == 1u ||
        reset == 1u) {
        *(volatile uint8_t *)(uintptr_t)RX8_IAT_STATUS_2_ADDR = 0u;
    } else if (*(volatile uint8_t *)(uintptr_t)RX8_IAT_ST2_THR_ADDR > thr1 ||
               *(volatile uint8_t *)(uintptr_t)RX8_IAT_FAULT_IN_ADDR == 1u) {
        *(volatile uint8_t *)(uintptr_t)RX8_IAT_STATUS_2_ADDR = 1u;
    }
}
