/* complement_shift_u32.c
 *
 * ROM: 60E1D400  |  Address: 0x2440  |  Size: 16 bytes (0x2440-0x2450)
 *
 * Floating-point deadband / range violation test.
 * Returns 1 when |threshold - value| > adjustment (outside deadband).
 * Returns 0 when |threshold - value| <= adjustment (inside deadband).
 *
 * Used by PID controllers to detect when an error signal has exceeded
 * the calibrated deadband or threshold window.
 *
 * SH-2A implementation (verified against emulator):
 *   fr3 = fr5             ; fr3 = value
 *   fr3 = fr5 - fr6       ; fr3 = value - adjustment
 *   if fr3 > fr4 -> ret 1 ; if value - adj > threshold: outside (above)
 *   fr3 = fr5 + fr6       ; fr3 = value + adjustment
 *   if fr4 > fr3 -> ret 1 ; if threshold > value + adj: outside (below)
 *   ret 0                 ; inside deadband
 *
 * Callee of: calc_intake_pressure_pid_output_1252C (0x1252C)
 *
 * NOTE — CANONICAL lift of ROM 0x2440. c/math_primitives.c also carried this same
 * function as `isNotZero_wDivideByZeroProtect(float x, float center, float tol)`
 * (same deadband test, different param names/order); that duplicate was consolidated
 * into a thin wrapper delegating to this function. All callers use this name
 * (cooling_fan_control.c:45, calc_intake_pressure_pid_output_1252C.c:90/92) — keep
 * this as the single canonical implementation.
 */

#include <stdint.h>

/* complement_shift_u32 — deadband range violation test
 *
 * Args:
 *   fr4 = threshold  (the value to test — e.g. actual pressure)
 *   fr5 = value      (center of deadband — e.g. target pressure)
 *   fr6 = adjustment (half-width of deadband)
 *
 * Returns:
 *   r0 = 1 if |threshold - value| > adjustment (OUTSIDE deadband → error)
 *   r0 = 0 if |threshold - value| <= adjustment (INSIDE deadband → OK)
 */
uint32_t complement_shift_u32(float threshold, float value, float adjustment)
{
    /* Check if threshold is above the upper bound of deadband */
    /* i.e. value - adjustment > threshold → threshold is too low */
    if (value - adjustment > threshold) {
        return 1;
    }

    /* Check if threshold is below the lower bound of deadband */
    /* i.e. threshold > value + adjustment → threshold is too high */
    if (threshold > value + adjustment) {
        return 1;
    }

    /* Threshold is within the deadband: |threshold - value| <= adjustment */
    return 0;
}
