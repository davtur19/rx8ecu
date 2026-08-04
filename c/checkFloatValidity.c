/*
 * checkFloatValidity  —  RX-8 PCM single-precision SQUARE ROOT entry
 *                        Address: 0x46CC (60E1D400.bin; identical bytes at
 *                        0x46CC in 60E0FC00.bin)
 *                        body 0x46CC..0x4724.
 *
 * Purpose: compute sqrt(value) via the soft-float pipeline
 *     frexp @0x48C8  ->  fixed-point sqrt @0x4740  ->  ldexp @0x481C,
 * and flag the hardware when the RESULT is Inf/NaN by writing a fault code to
 * RAM 0xFFFF7304.  Despite its historical name, this is a SQUARE ROOT entry
 * (see docs/notes/FINDINGS.md "0x4740" and the emulator-verified lifts
 * c/bitfield_extract_merge.c, c/div_4740.c, c/ldexp_481C.c).
 *
 * Semantics (confirmed instruction-for-instruction, 100k+ random float
 * inputs + all IEEE edge cases, emulator vs lift, 0 mismatches — see
 * c/tests/test_check_float_validity_0x46CC.py):
 *    1. bitfield_extract_merge(value, out)            ; frexp: out[0]=exp word
 *                                                    ;        out[1]=significand
 *    2. div_4740(out[0], out[1], &hi, &lo)           ; restoring square root
 *    3. bits = ldexp_481C(hi, lo)                    ; rebuild float bit pattern
 *    4. if ((bits & 0x7F800000) == 0x7F800000)        ; result exponent == 0xFF
 *          *(u32)0xFFFF7304 = (bits & 0x007FFFFF) ? 0x044D   ; NaN
 *                                                 : 0x044C;  ; ±Inf
 *    5. return bits as float.
 *
 * Verified behaviors (emulator): sqrt(4.0)=2.0, sqrt(9.0)=3.0,
 * sqrt(0.25)=0.5, sqrt(2.0)=1.4142135; sqrt(0.0)=0.0 (no fault write).
 * Fault write only fires for a non-finite RESULT: +inf input -> result +inf
 * -> *(0xFFFF7304)=0x044C; negative input or NaN input -> result NaN ->
 * *(0xFFFF7304)=0x044D.  The store is a 32-bit big-endian WRITE
 * (mov.l r0,@r2 @0x4714), so 0xFFFF7304 holds 0x0000044C / 0x0000044D.
 *
 * Calling convention (matches the lift symbol): float arg in fr4 / compiler
 * ABI r4/fr0, result returned in fr0 / ABI xmm0.  The fault address is a
 * redirected volatile pointer so host tests can observe the write without
 * touching real ECU MMIO (default = 0xFFFF7304, the ROM target).
 *
 * Track A: verified behavior-equivalent to the emulated ROM
 * (tools/sh2emu.py) — see c/tests/test_check_float_validity_0x46CC.py.
 */
#include <stdint.h>
#include <string.h>

/* Third-stage helpers (verified lifts, external symbols). */
void bitfield_extract_merge(float value, uint32_t *out);   /* frexp  @0x48C8 */
void div_4740(uint32_t arg1, uint32_t arg2, uint32_t *hi, uint32_t *lo);
uint32_t ldexp_481C(uint32_t arg1, uint32_t arg2);          /* @0x481C        */

/* Fault-code sink.  Default = ROM target; host tests redirect to a buffer. */
volatile uint32_t *checkFloatValidity_fault_addr =
    (volatile uint32_t *)0xFFFF7304;

float checkFloatValidity(float value)
{
    uint32_t out[2];
    uint32_t hi, lo;
    uint32_t bits;
    float    result;

    bitfield_extract_merge(value, out);   /* frexp 0x48C8 -> (exp, sig) */
    div_4740(out[0], out[1], &hi, &lo);   /* sqrt  0x4740 -> (hi, lo)   */
    bits = ldexp_481C(hi, lo);            /* ldexp 0x481C -> float bits */

    if ((bits & 0x7F800000u) == 0x7F800000u) {
        /* result exponent == 0xFF: Inf (mantissa 0) -> 0x044C, else NaN -> 0x044D */
        *checkFloatValidity_fault_addr =
            (bits & 0x007FFFFFu) ? 0x044Du : 0x044Cu;
    }

    memcpy(&result, &bits, sizeof(uint32_t));
    return result;
}