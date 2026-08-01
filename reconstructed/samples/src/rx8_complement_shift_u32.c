/*
 * =============================================================================
 * rx8_complement_shift_u32.c  —  FLOAT DEADBAND / RANGE-VIOLATION TEST
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x2440
 * Status      : VERIFIED — behavioural equivalence to the ROM held by
 *               reconstructed/samples/tests/harness_complement_shift_u32.py
 *               (host-gcc vs tools/sh2emu.py over random single-precision
 *               triples), in addition to the existing c/tests entry
 *               (test_complement_shift_u32.py, 710 tests, 0 failures).
 * Lift (truth): c/complement_shift_u32.c  (same address; IDA-ai symbol
 *               `complement_shift_u32`).
 *
 * WHAT THE FUNCTION DOES
 * ----------------------
 * Single-precision deadband test used by PID controllers to decide whether an
 * error signal has left the calibrated window.  It answers
 *
 *     is |threshold - value| > adjustment ?
 *
 * with the arithmetic split into exactly the two comparisons the ROM emits:
 *
 *     0x2440  fmov   fr5,fr3        ; fr3 = value
 *     0x2442  fsub   fr6,fr3        ; fr3 = value - adjustment
 *     0x2444  fcmp/gt fr4,fr3       ; T = (value - adjustment > threshold)
 *     0x2446  bt/s   0x2458         ; outside (above)  if taken
 *     0x2448  nop                   ;   (delay slot)
 *     0x244A  fmov   fr5,fr3        ; fr3 = value
 *     0x244C  fadd   fr6,fr3        ; fr3 = value + adjustment
 *     0x244E  fcmp/gt fr3,fr4       ; T = (threshold > value + adjustment)
 *     0x2450  bt/s   0x2458         ; outside (below)  if taken
 *     0x2452  nop                   ;   (delay slot)
 *     0x2454  bra    0x245A         ; inside
 *     0x2456  mov    #0,r4          ;   (delay slot)
 *     0x2458  mov    #1,r4          ;   (shared "outside" target)
 *     0x245A  rts                   ; r0 = r4 via the delay slot
 *     0x245C  mov    r4,r0
 *
 * So the result is 1 when the threshold lies strictly outside the open
 * interval (value - adjustment, value + adjustment) and 0 when it lies inside
 * the closed interval.  With NaN operands both fcmp/gt instructions report
 * unordered (T = 0) on the SH-2E FPU, i.e. a NaN yields 0 — exactly like
 * IEEE-754 `>` on the host, so the C below is NaN-compatible with the ROM.
 *
 * CALLERS / ROLE
 * --------------
 * Callee of calc_intake_pressure_pid_output_1252C (@0x1252C, called twice:
 * |target| and |error| against a calibrated epsilon) and cooling_fan_control.c;
 * c/math_primitives.c wraps the same ROM function as
 * isNotZero_wDivideByZeroProtect().  In all three it gates an action on a
 * small calibrated deadband so a noisy near-zero error never accumulates.
 * =============================================================================
 */
#include <stdint.h>
#include "rx8_samples.h"

/* Return values of the deadband test.  Names follow the caller semantics in
 * c/calc_intake_pressure_pid_output_1252C.c (r1 = "target out of range"). */
#define RX8_DEADBAND_VIOLATION  1u   /* |threshold - value| > adjustment  */
#define RX8_DEADBAND_OK         0u   /* |threshold - value| <= adjustment */

/* 0x2440 — deadband range-violation test
 *
 * Args (SH-2E FPU registers, as the ROM reads them):
 *   fr4 = threshold  (value under test — e.g. actual pressure)
 *   fr5 = value      (deadband centre — e.g. target pressure)
 *   fr6 = adjustment (half-width of the deadband)
 *
 * Returns:
 *   RX8_DEADBAND_VIOLATION (1) if |threshold - value| > adjustment
 *   RX8_DEADBAND_OK        (0) otherwise
 */
uint32_t rx8_complement_shift_u32(float threshold, float value, float adjustment)
{
    /* Above the upper bound: value - adjustment > threshold. */
    if (value - adjustment > threshold) {
        return RX8_DEADBAND_VIOLATION;
    }

    /* Below the lower bound: threshold > value + adjustment. */
    if (threshold > value + adjustment) {
        return RX8_DEADBAND_VIOLATION;
    }

    /* Inside the deadband: |threshold - value| <= adjustment. */
    return RX8_DEADBAND_OK;
}
