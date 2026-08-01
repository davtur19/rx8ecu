/*
 * =============================================================================
 * rx8_mod32_signed.c  —  SIGNED 32-BIT REMAINDER (TRUNCATING TOWARD ZERO)
 * =============================================================================
 * ROM         : roms/stock/60E1D400.bin (Mazda RX-8 PCM, N3J1 family)
 * Address     : 0x4144
 * Status      : VERIFIED — behavioural equivalence to the ROM held by
 *               reconstructed/samples/tests/harness_mod32_signed.py
 *               (host-gcc vs tools/sh2emu.py over random (divisor,dividend)
 *               pairs), in addition to the existing c/ lift.
 * Lift (truth): c/mod32_signed.c  (same address; the merged-symbol name for
 *               this range — `engineSomethingConditonCheckAndSet?` — is a
 *               placeholder; the code is the div0s/div1 remainder counterpart
 *               of div32_signed @0x3FE8).
 *
 * WHY THIS FUNCTION EXISTS
 * ------------------------
 * The SH-2E core has no hardware instruction for signed 32-bit division;
 * Denso implements the remainder with the classic div0s/div1 step-by-step
 * non-restoring division, fully unrolled 32 times.  After the loop the ROM
 * applies an extra sign correction on the partial remainder (r3) so the
 * result matches C99 remainder semantics:  |result| < |divisor| and
 * sign(result) == sign(dividend).
 *
 * ROM register convention — NOTE: this uses the SAME "broken" r0/r1 argument
 * pair as div32_signed @0x3FE8, NOT the r4/r5 ABI:
 *
 *     r0 = divisor, r1 = dividend, result returned in r0.
 *
 * ROM asm summary:
 *     tst r0,r0 ; bt .div_zero        ; divisor == 0 -> error path
 *     div0s r2,r1 ; movt r4           ; r4 = sign(dividend)
 *     subc r3,r3 ; subc r2,r1         ; dividend -> 2's-complement magnitude
 *     div0s r0,r3
 *     {rotcl r1 ; div1 r0,r3} x32     ; r3 = partial remainder
 *     div0s r2,r3 ; movt r2 ; xor r4,r2
 *     rotcr r2 ; bf .skip             ; sign-mismatch? then one more step
 *     div0s r0,r3 ; shar r3 ; div1 r0,r3
 * .skip: add r4,r3 ; mov r3,r0        ; r3 += sign(dividend) -> result
 * .div_zero: *(uint32_t *)0xFFFF7304 = 0x44E ; r0 = 0 ; rts
 *
 * The C below is `dividend % divisor` (C99, truncates toward zero) with one
 * explicit special case:  INT32_MIN % -1 is 0 in the ROM, but the C99
 * quotient for that pair overflows (undefined behaviour — and x86 `idiv`
 * raises SIGFPE), so it is handled as its own well-defined branch.
 * The other deliberate difference is the divide-by-zero path: the ROM also
 * stores diag code 0x44E at the diag-code register 0xFFFF7304
 * (RX8_DIAG_CODE_REG in rx8_hw.h).  A host process cannot dereference that
 * fixed address, so — exactly like the reference lift — the store is
 * documented here and validated emulator-side by harness_mod32_signed.py.
 * =============================================================================
 */
#include <stdint.h>
#include <limits.h>
#include "rx8_samples.h"

/* Diag-code register written by the ROM's divide-by-zero path (shared with
 * div32_signed @0x3FE8).  Commented out on the host build (see header);
 * the emulator validates the write. */
#define RX8_DIVERR_ADDR 0xFFFF7304u
#define RX8_DIVERR_CODE 0x044Eu

int32_t rx8_mod32_signed(int32_t divisor, int32_t dividend)
{
    if (divisor == 0) {
        /* *(volatile uint32_t *)RX8_DIVERR_ADDR = RX8_DIVERR_CODE; */
        return 0;
    }
    /* C99 signed remainder: the quotient truncates toward zero, so the
     * result takes the sign of the dividend and |result| < |divisor| — the
     * exact semantics the ROM's div0s/div1 + sign-correction loop produces. */
    if (dividend == INT32_MIN && divisor == -1) {
        /* The only pair whose QUOTIENT would overflow (INT32_MIN / -1);
         * C99 leaves it undefined and x86 `idiv` traps, but the ROM's
         * non-restoring loop yields remainder 0 (verified emulator-side). */
        return 0;
    }
    return dividend % divisor;
}
