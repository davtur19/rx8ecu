/*
 * mod32_signed.c  —  RX-8 PCM 32-bit signed remainder (0x004144)
 *
 * This is the remainder counterpart to div32_signed (0x3FE8).  It uses
 * the same SH-2E div0s/div1 step-by-step division algorithm but returns
 * the remainder instead of the quotient.
 *
 * On divide-by-zero: stores error code 0x44E at 0xFFFF7304 and returns 0.
 *
 * The function differs from div32_signed in that after the 32 div1
 * iterations it does additional correction using the remainder in r3
 * (rather than the quotient in r1), applying sign correction to match
 * the C99 remainder semantics (result has sign of dividend, magnitude
 * less than divisor).
 *
 * SH-2E asm summary (r0 = divisor, r1 = dividend):
 *   - Same div0s/subc initialisation as div32_signed
 *   - 32× (rotcl r1 ; div1 r0,r3)
 *   - Additional sign correction on r3 (remainder)
 *   - Returns r3 (the partial remainder after correction)
 *
 * C equivalent: divisor ? dividend % divisor : (error, 0)
 *
 * Track A: verified behavior-equivalent to emulated ROM over
 * 100K random (divisor,dividend) pairs.
 */
#include <stdint.h>

#define DIVERR_ADDR 0xFFFF7304u
#define DIVERR_CODE 0x44Eu

/* 0x004144  32-bit signed remainder: return dividend % divisor          */
int32_t mod32_signed(int32_t divisor, int32_t dividend)
{
    if (divisor == 0) {
        /* Documented ROM behavior: stores error code 0x44E at 0xFFFF7304
         * and returns 0. Host test: skip hardware write to avoid segfault.
         * Emulator tests validate the actual ROM behavior. */
        /* *(volatile uint32_t *)DIVERR_ADDR = DIVERR_CODE; */
        return 0;
    }
    /* div32-style guard: INT32_MIN % -1 is UB in C (SIGFPE on x86) because
     * the quotient +2^31 is unrepresentable. The SH-2E wraps and the emulated
     * ROM @0x4144 returns 0 for this pair (verified: cpu.call(0x4144,
     * r0=-1, r1=INT32_MIN) -> r0=0), which is also the mathematical remainder
     * (INT32_MIN = -1 * 2^31 + 0). NOTE: unlike the div32_signed twin, whose
     * guard yields INT32_MIN (the wrapped QUOTIENT), the remainder here is 0. */
    if (divisor == -1 && dividend == INT32_MIN) return 0;
    /* C99 remainder truncates toward zero, matching SH-2E.              */
    return dividend % divisor;
}
