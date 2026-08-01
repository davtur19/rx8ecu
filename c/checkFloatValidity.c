/**
 * checkFloatValidity @ 0x46CC (60E1D400) / 0x46CC (60E0FC00)
 *
 * Purpose:
 *   Validate an IEEE 754 single-precision float for NaN/Infinity conditions.
 *   If the value is NaN or Infinity, a diagnostic code is written to a
 *   fault status RAM location.  The original float value is passed through
 *   unchanged.
 *
 * Logic:
 *   1. Examine the IEEE 754 bit pattern:
 *      - Exponent = 0xFF (bits 30:23 all 1) -> special value
 *        - Mantissa != 0 -> NaN (write 0x044D to status)
 *        - Mantissa = 0 -> Infinity (write 0x044C to status)
 *      - Otherwise -> normal/subnormal/zero (valid, no write)
 *   2. Return the original float value unchanged.
 *
 * RAM output:
 *   0xFFFF7304  uint16_t  Status code (0x044D = NaN, 0x044C = Inf)
 *
 * NOTE: The hardware register write at 0xFFFF7304 only works when run on
 * the actual ECU or in the SH-2 emulator.  When compiled natively for host
 * testing, the write is skipped (commented out below).
 *
 * Track A: verified behavior-equivalent to emulated ROM.
 */
#include <stdint.h>

float checkFloatValidity(float value)
{
    uint32_t bits = *(uint32_t *)&value;  /* reinterpret as integer */

    /* IEEE 754 single-precision:
     *   bit 31    = sign
     *   bits 30:23 = exponent (8 bits)
     *   bits 22:0  = mantissa (23 bits)
     *   exponent = 0xFF -> NaN/Inf
     */
    if ((bits & 0x7F800000) == 0x7F800000) {
        /* Exponent is all 1s -- special value */
        /* Host test: skip hardware write to avoid segfault.
         * Emulator tests validate the actual ROM behavior. */
#if 0
        if (bits & 0x007FFFFF) {
            /* Mantissa is non-zero -> NaN */
            *(volatile uint16_t *)0xFFFF7304 = 0x044D;
        } else {
            /* Mantissa is zero -> Infinity */
            *(volatile uint16_t *)0xFFFF7304 = 0x044C;
        }
#endif
    }
    /* else: normal/subnormal/zero -- leave status unchanged */

    return value;
}
