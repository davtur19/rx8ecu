/*
 * math_primitives.c  —  RX-8 PCM core scalar helpers (equinox names, hand Ghidra RE
 * by equinox311).  These thirteen tiny functions live in the 0x2044..0x2510 cluster and are
 * the most-called leaf routines in the firmware (clamping, min, float<->fixed-point
 * conversions, a divide-by-zero guard, the value/complement checksum encoder/residual, a
 * saturating Q16.16 multiply, and an int blend). Verifying them pins down the whole
 * scalar-math layer that fueling/ignition/sensors are built on.
 *
 * SH-2E calling convention: float args fr4,fr5,fr6 (return fr0); int args r4.. (return r0).
 *
 * Track A: every function below verified behavior-equivalent to the emulated ROM
 * (tools/sh2emu.py) over >=30000 random inputs each (float-domain ones single-precision,
 * int-domain ones spanning the full int32 range) — 0 mismatches.
 * Test/oracle: c/tests/test_math_primitives.py.
 * (ftrc truncates toward zero; the +0.5 before it makes the conversions round-to-nearest
 *  for the non-negative results they are then clamped to.)
 */
#include <stdint.h>
#include <math.h>

/* 0x23DC  fsub fr5,fr4 ; fabs fr4 ; -> fr0            |a - b|                       */
float subtractAbsolute(float a, float b)
{
    return fabsf(a - b);
}

/* 0x23E4  clamp a signal to a lower bound (low-side saturation): max(sig, lower)    */
float saturateLow(float sig, float lower)
{
    return (sig > lower) ? sig : lower;
}

/* 0x23F4  minimum of two floats                                                     */
float minValue(float a, float b)
{
    return (b > a) ? a : b;
}

/* 0x2404  clamp a signal into [lower, upper]                                        */
float saturate(float sig, float lower, float upper)
{
    if (!(sig > lower)) return lower;      /* sig <= lower  -> lower */
    if (upper > sig)    return sig;        /* in range               */
    return upper;                          /* sig >= upper  -> upper */
}

/* 0x2420  value/complement byte encoder: high = x, low = ~x  (redundant store)      */
uint16_t encode(uint8_t x)
{
    return (uint16_t)((x << 8) | (uint8_t)(~x));
}

/* 0x2440  is |x - center| outside the tolerance band?  (guards divides: 1 = safe)
 * SAME ROM function as complement_shift_u32 (0x2440) — see c/complement_shift_u32.c
 * for the canonical implementation (deadband test, verified vs the emulator). This is
 * a thin wrapper keeping the old equinox name/signature working: param mapping
 * x=threshold, center=value, tol=adjustment (|threshold - value| > adjustment).      */
extern uint32_t complement_shift_u32(float threshold, float value, float adjustment);
int isNotZero_wDivideByZeroProtect(float x, float center, float tol)
{
    return (int)complement_shift_u32(x, center, tol);
}

/* 0x2490  float -> unsigned 16-bit fixed point:
 *         round((number - offset) / scalar), clamped to [0, 65535]                  */
uint16_t floatToFP_16bit(float number, float scalar, float offset)
{
    int32_t i = (int32_t)(((number - offset) / scalar) + 0.5f);   /* ftrc: trunc toward 0 */
    if (i > 0xFFFF) i = 0xFFFF;
    if (i < 0)      i = 0;
    return (uint16_t)i;
}

/* 0x24D0  float -> unsigned 8-bit:
 *         round((signal - offset) / mult), clamped to [0, 255]                      */
uint8_t floatToInt(float signal, float mult, float offset)
{
    int32_t i = (int32_t)(((signal - offset) / mult) + 0.5f);
    if (i > 0xFF) i = 0xFF;
    if (i < 0)    i = 0;
    return (uint8_t)i;
}

/* 0x24C0  unsigned 16-bit fixed point -> float:  mult * raw + off  (fused mac)       */
float fixedPointToFloat_16bit(float mult, float off, uint16_t raw)
{
    return mult * (float)raw + off;
}

/* 0x2500  unsigned 8-bit fixed point -> float:  mult * raw + off                     */
float fixedPointToFloat_8bit(float mult, float off, uint8_t raw)
{
    return mult * (float)raw + off;
}

/* ---------------------------------------------------------------------------------
 * Batch 2 (0x2044, 0x231C, 0x2510) — confirmed from asm, not guessed from the name.
 * Track A: each verified vs the emulated ROM (tools/sh2emu.py) over 30000 random inputs
 * (invertAndReturn_8bit_ADDR and multiply32Bit_saturating spanning the full uint8/int32
 * domains respectively, plus 37 exact-complement edge pairs for invertAndReturn;
 * fixedPointScaling spanning the full int32 domain for a,b) — 0 mismatches each.
 * Verifying multiply32Bit_saturating required adding dmuls.l and rotcr to the emulator
 * subclass (base sh2emu.py doesn't implement them).
 * Test/oracle: c/tests/test_math_primitives.py.
 * ---------------------------------------------------------------------------------
 */

/* 0x2044  invertAndReturn_8bit_ADDR: read a 16-bit big-endian (value,complement) cell at
 * *addr* and return the ones'-complement residual ~(hi8 + lo8) & 0xFF. This is 0 exactly
 * when hi8 == ~lo8 (i.e. the pair is self-consistent, the same value/complement convention
 * `encode()` above produces and c/mem_accessors.c's redundant-cell family validates) —
 * nonzero reflects the corruption amount otherwise. Order-independent in (hi,lo): it is a
 * symmetric checksum residual, not a value extractor.                                    */
uint8_t invertAndReturn_8bit_ADDR(const uint8_t *addr)
{
    uint8_t hi = addr[0];
    uint8_t lo = addr[1];
    return (uint8_t)~(uint8_t)(hi + lo);
}

/* 0x231C  multiply32Bit_saturating (ghidra-hand: "multiply32Bit"): Q16.16 fixed-point
 * multiply with 32-bit saturation — ((int64_t)a * b) >> 16 (arithmetic shift), clamped to
 * [INT32_MIN, INT32_MAX]. Confirmed from asm: dmuls.l computes the signed 64-bit product,
 * 16x (shar/rotcr) arithmetic-shifts the 64-bit {hi:lo} pair right by 16, then the result is
 * saturated only if the high word isn't just the sign-extension of the low word's top bit.  */
int32_t multiply32Bit_saturating(int32_t a, int32_t b)
{
    int64_t p = (int64_t)a * (int64_t)b;
    int64_t s = p >> 16;                 /* arithmetic (sign-preserving) shift */
    if (s > INT32_MAX) return INT32_MAX;
    if (s < INT32_MIN) return INT32_MIN;
    return (int32_t)s;
}

/* 0x2510  fixedPointScaling (ghidra-hand: "fixedPointScaling"): NOT a unit conversion like
 * its neighbors above despite the name — confirmed from asm to be an inverse-weighted blend
 * between two ints using an 8-bit fractional counter (frac, zero-extended from 16 bits by
 * the ROM's `extu.w`):
 *     result = a + (int)trunc((b - a) * (1 - frac/256.0))
 * frac==0 -> b exactly; frac==256 -> a exactly (typical use: frac counts 0..255 as a ramp/
 * fade progresses from the new value b back toward the old value a, or vice versa).        */
int32_t fixedPointScaling(int32_t a, int32_t b, uint16_t frac)
{
    float t    = 1.0f - (float)frac * (1.0f / 256.0f);
    float diff = (float)b - (float)a;
    int32_t d  = (int32_t)(diff * t);    /* ftrc: truncate toward zero */
    return a + d;
}
