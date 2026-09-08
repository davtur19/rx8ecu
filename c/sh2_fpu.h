/*
 * sh2_fpu.h  —  host-side model of the SH-2E `ftrc` (float-to-int32,
 * truncate-toward-zero with saturation) instruction.
 *
 * Hardware semantics (confirmed against tools/sh2emu.py, which models the
 * real FPU; SH-2E hardware yields the same saturated values):
 *   NaN               -> 0x80000000 (INT32_MIN)
 *   v >=  2147483648.0 -> 0x7FFFFFFF (INT32_MAX)
 *   v <  -2147483648.0 -> 0x80000000 (INT32_MIN)
 *   otherwise          -> truncation toward zero
 *
 * A bare C `(int32_t)v` cast is WRONG outside [-2^31, 2^31): out-of-range
 * float->int32 conversion is undefined behavior on the host (x86 saturates
 * +overflow to INT32_MIN instead of INT32_MAX, and traps/UB on some targets),
 * and NaN conversion is UB as well. Every host lift that mirrors an `ftrc`
 * must pass the value through ftrc_sat() FIRST.
 */
#ifndef SH2_FPU_H
#define SH2_FPU_H

#include <stdint.h>

static inline int32_t ftrc_sat(float v)
{
    if (v != v)              /* NaN -> INT32_MIN (matches SH-2 hardware) */
        return INT32_MIN;
    if (v >= 2147483648.0f)  /* +overflow -> INT32_MAX */
        return INT32_MAX;
    if (v < -2147483648.0f)  /* -overflow -> INT32_MIN */
        return INT32_MIN;
    return (int32_t)v;       /* in range: trunc toward zero */
}

#endif /* SH2_FPU_H */
