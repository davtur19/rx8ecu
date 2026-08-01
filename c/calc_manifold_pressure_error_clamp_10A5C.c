/* calc_manifold_pressure_error_clamp_10A5C.c
 *
 * ROM: 60E1D400  |  Address: 0x10A5C  |  Size: 44 bytes
 *
 * Manifold pressure error clamping with fixed-point arithmetic.
 * Wraps a scaled pressure error into a bounded range using modulo-like
 * subtraction/addition of the range constant (0x2D00000).
 *
 * The ECM uses this to keep the intake manifold pressure error signal
 * within controlled bounds, preventing windup in the pressure control
 * loop.
 *
 * Algorithm:
 *   1. Read 8-bit raw sensor value from RAM (0xFFFFA5D4)
 *   2. Scale by 0x1E0000 (fixed-point multiplication)
 *   3. Subtract the input argument (r4)
 *   4. Apply a fixed offset of -0x50000
 *   5. If result >=  0x2D00000: result -= 0x2D00000  (wrap down)
 *   6. If result <  0x00000000: result += 0x2D00000  (wrap up)
 *   7. Return the clamped result
 */

#include <stdint.h>

/* Calibration constants (from literal pool) */
#define SCALE_FACTOR    0x001E0000u    /* 1,966,080 = scaling multiplier */
#define RANGE           0x02D00000u    /* 47,185,920 = wrap range */
#define OFFSET_DOWN     0xFFFB0000u    /* -327,680 = negative offset (= -0x50000) */
#define OFFSET_UP       0xFD300000u    /* -47,185,920 (= -0x2D00000, same as -RANGE) */

/* RAM location for raw sensor byte */
#define RAM_MAP_SENSOR  (*(volatile uint8_t *)0xFFFFA5D4)

/**
 * calc_manifold_pressure_error_clamp_10A5C
 *
 * Computes a bounded error term from a raw sensor reading.
 *
 * @param input  Intake pressure target or reference (r4)
 * @return       Clamped error in range [0, 0x2D00000)
 *
 * NOTE: This uses 32-bit integer fixed-point math (no FPU).
 * The result is a fixed-point number suitable for further
 * integer-domain control computations.
 */
uint32_t calc_manifold_pressure_error_clamp_10A5C(uint32_t input)
{
    uint32_t result;
    uint32_t raw_val;

    /* Step 1: Read raw 8-bit sensor value */
    raw_val = RAM_MAP_SENSOR;

    /* Step 2: Scale and subtract input */
    /* result = (raw_val * SCALE_FACTOR) - input - 0x50000 */
    result = (raw_val * SCALE_FACTOR) - input;
    result = result + OFFSET_DOWN;  /* equivalent to: result -= 0x50000 */

    /* Step 3: Wrap into [0, RANGE)
     * NOTE: SH-2E cmp/ge is a SIGNED comparison, and cmp/pz is signed >= 0.
     * The wrapping is:
     *   if (signed)temp >= (signed)RANGE: temp -= RANGE
     *   if (signed)temp < 0:              temp += RANGE
     */
    if ((int32_t)result >= (int32_t)RANGE) {
        /* Subtract RANGE to wrap down: add 0xFD300000 (= -0x02D00000) */
        result = result + OFFSET_UP;
    } else if ((int32_t)result < 0) {
        /* Add RANGE to wrap up from negative */
        result += RANGE;
    }

    /* Step 4: Return clamped result */
    return result;
}
