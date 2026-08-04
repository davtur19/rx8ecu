/*
 * ldexp_481C  —  RX-8 PCM ldexp-style float reconstruction helper
 *                Address: 0x481C (60E1D400.bin; identical bytes at 0x481C in
 *                60E0FC00.bin)
 *
 * Third stage of the checkFloatValidity 0x46CC pipeline
 * (frexp 0x48C8 -> sqrt 0x4740 -> ldexp @0x481C).  Takes the (hi, lo)
 * word pair produced by the 0x4740 square-root helper and rebuilds the
 * single-precision float bit pattern, saturating to +/-Inf / zero for
 * out-of-range exponents.
 *
 * Calling convention (confirmed from the single call site at 0x46EE):
 *   - args on the stack, pushed by the caller:
 *         [r15]     = arg1  (moved to r3)
 *         [r15 + 4] = arg2  (moved to r0)
 *   - returns the float bits in r0 (also copied to fr0 via
 *     mov.l r0,@-r15 ; rts ; fmov.s @r15+,fr0 at 0x488E).
 *
 * Semantics (verified bit-exact vs the emulated ROM, 300k+ random inputs
 * + all edge cases, 0 mismatches — see c/tests/test_ldexp_481C.py):
 *   - arg1's low 16 bits are sign-extended (exts.w r3 -> r2) and treated
 *     as a signed exponent (bias 127 handled inline).
 *   - arg2 is the 32-bit mantissa word from div_4740.
 *   - the 0x483C-0x487E block is NOT part of this entry point: it is
 *     unreachable from 0x481C (0x4836 bt 0x4880 and 0x4838 bra 0x489C
 *     both jump over it) — a separate helper entry used elsewhere.
 *
 * Track A: verified behavior-equivalent to the emulated ROM
 * (tools/sh2emu.py) — see c/tests/test_ldexp_481C.py.
 */
#include <stdint.h>

uint32_t ldexp_481C(uint32_t arg1, uint32_t arg2)
{
    uint32_t r0, r1, r2, r3, t, t2;

    r3 = arg1;
    /* 0x481E  exts.w r3 -> r2  (sign-extend low 16 bits) */
    r2 = r3 & 0xFFFFu;
    r2 = (r2 & 0x8000u) ? (r2 | 0xFFFF0000u) : r2;
    r0 = arg2;

    /* 0x4822-0x4826  cmp/ge r1,r2 with r1 = 0x7FFF:
     * T = (r2 >= 0x7FFF) signed; bt/s 0x4894 (delay: nop) */
    r1 = 0x7FFFu;
    if ((int32_t)r2 >= (int32_t)r1) {
        /* 0x4894  tst r0,r0 */
        if (r0 == 0u) {
            /* 0x48A2  r2 = 0xFF; r0 = 0 */
            r2 = 0xFFu; r0 = 0u;
        } else {
            /* 0x48A8  r2 = 0xFF; r3 = 0; r0 = 0x100 (shll8 of #1) */
            r2 = 0xFFu; r3 = 0u; r0 = 0x100u;
        }
    } else {
        /* 0x482A-0x482C  r1 = 0x7F; r2 += 0x7F */
        r1 = 0x7Fu;
        r2 = r2 + r1;
        /* 0x482E-0x4830  cmp/ge r1,r2 with r1 = 0xFF: T = (r2 >= 0xFF) signed */
        r1 = 0xFFu;
        if ((int32_t)r2 >= (int32_t)r1) {
            /* 0x48A2  r2 = 0xFF; r0 = 0 */
            r2 = 0xFFu; r0 = 0u;
        } else if ((int32_t)r2 > 0) {   /* 0x4834-0x4836  cmp/pl r2; bt 0x4880 */
            /* direct to 0x4880 */
        } else {
            /* 0x489C  r2 = 0; r0 = 0 */
            r2 = 0u; r0 = 0u;
        }
    }

    /* ---- 0x4880 common reconstruction ---- */
    t = r0 >> 31; r0 = r0 << 1;         /* shll r0        (T = bit31)   */
    r0 = r0 >> 8;                       /* shlr8 r0                     */
    r2 = r2 << 16;                      /* shll16 r2                    */
    r2 = r2 << 8;                       /* shll8 r2                     */
    r0 = (r0 | r2) & 0xFFFFFFFFu;
    t = r3 >> 31; r3 = r3 << 1;         /* shll r3        (T = bit31)   */
    t2 = r0 & 1u;                       /* rotcr r0                     */
    r0 = ((r0 >> 1) | (t << 31)) & 0xFFFFFFFFu;
    t = t2;
    return r0;
}
