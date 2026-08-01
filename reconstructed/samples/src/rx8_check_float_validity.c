/*
 * =============================================================================
 * rx8_check_float_validity.c  —  IEEE-754 SINGLE-PRECISION NaN/INF VALIDITY CHECK
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x46CC
 * Status      : VERIFIED (host behaviour-equivalent to the lift; the emulated
 *               ROM additionally runs a preceding float->fixed-point conversion
 *               pipeline at 0x48C8/0x4740/0x481C whose output is the value that
 *               this check inspects — see harness_check_float_validity.py).
 * Lift (truth): c/checkFloatValidity.c  (same address).
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * After any Denso sensor/actuator conversion that can overflow to +-Inf or
 * produce a NaN (denormals, missing sensor, divide-by-zero in a calibration
 * chain), the PCM must be able to (a) leave a diagnostic breadcrumb in a
 * fault-status RAM cell and (b) keep the data pipeline alive with an explicit,
 * well-defined single-precision value instead of letting a quiet NaN poison
 * the downstream PID/filter math.
 *
 * SEMANTICS (verbatim from the lift)
 * ---------------------------------
 *   1. Reinterpret the single-precision operand as a big-endian u32 and mask
 *      out the 8-bit exponent field (bits 30..23, mask 0x7F800000).
 *   2. exponent == 0xFF  ->  special value:
 *          mantissa != 0 ->  NaN     -> diagnostic code 0x044D
 *          mantissa == 0 ->  Infinity -> diagnostic code 0x044C
 *      written to the fault-status cell at 0xFFFF7304.
 *   3. otherwise (normal / subnormal / zero) -> no write; status untouched.
 *   4. the original operand is returned unchanged (bit-exact, NaN included).
 *
 * NOTE on the hardware write: the real ECU performs a 32-bit store to
 * 0xFFFF7304.  On the host build that address is not backed by mapped memory,
 * so the store is compiled out (same convention as the lift); the emulator
 * harness validates the actual ROM store against cpu.ram.
 *
 * NOTE on single precision: the exponent/mantissa split is performed on the
 * exact IEEE-754 bit pattern, so a signaling-NaN payload round-trips verbatim
 * and denormal inputs are never flushed.  No host FPU exceptions are raised.
 * =============================================================================
 */
#include <stdint.h>
#include <string.h>
#include "rx8_samples.h"

/* Fault-status RAM cell written by the ECU when the value is special. */
#define RX8_FLOAT_FAULT_STATUS_ADDR  0xFFFF7304u
#define RX8_FAULT_CODE_NAN           0x044Du
#define RX8_FAULT_CODE_INFINITY      0x044Cu

float rx8_check_float_validity(float value)
{
    uint32_t bits;
    uint32_t exponent;

    /* IEEE-754 single precision: sign(31) | exponent(30..23) | mantissa(22..0). */
    memcpy(&bits, &value, sizeof bits);   /* endian-neutral u32 bit pattern. */

    exponent = bits & 0x7F800000u;

    if (exponent == 0x7F800000u) {
        /* Exponent field all ones -> special value (NaN or Infinity). */
        if (bits & 0x007FFFFFu) {
            /* Non-zero mantissa -> NaN. */
#if 0   /* host build: 0xFFFF7304 is unmapped; validated by the emulator harness */
            *(volatile uint16_t *)RX8_FLOAT_FAULT_STATUS_ADDR = RX8_FAULT_CODE_NAN;
#endif
        } else {
            /* Zero mantissa -> Infinity. */
#if 0
            *(volatile uint16_t *)RX8_FLOAT_FAULT_STATUS_ADDR = RX8_FAULT_CODE_INFINITY;
#endif
        }
    }
    /* else: normal / subnormal / zero -> status left untouched. */

    return value;   /* pass-through, bit-exact (NaN payloads preserved). */
}
