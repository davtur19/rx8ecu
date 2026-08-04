/*
 * div_4740  —  RX-8 PCM fixed-point SQUARE-ROOT helper
 *              Address: 0x4740 (60E1D400.bin; identical bytes at 0x4740 in
 *              60E0FC00.bin)
 *
 * NOTE ON THE NAME: the working name "div_4740" (and the older "q15 saturating
 * mul" / "mul16_signed_saturated" disassembler labels) are MISNOMERS.  The
 * math is a restoring fixed-point SQUARE ROOT, not a division:
 *
 *   r1 = round(sqrt(arg2 << (31 + (arg1 & 1))))      (main path)
 *   r3 = (sext16(arg1) >> 1) & 0xFFFF                (exponent word, halved)
 *
 * (closed form confirmed on the main path, 49932/49932 random inputs, worst
 * error 1 ulp = rounding mode; the LSB of arg1 selects a 1-bit pre-shift to
 * keep the radicand normalized).
 *
 * This is the second stage of the checkFloatValidity 0x46CC pipeline
 * (frexp 0x48C8 -> sqrt @0x4740 -> ldexp 0x481C).  It performs a
 * restoring square root on the 32-bit mantissa word arg2, with the trial
 * divisor r0 growing one bit per iteration (r0 = (r0<<1)|1, +1 on each
 * successful subtract) and the 2-bit-at-a-time radicand shift (shll/rotcl
 * pairs) that are the signature of a binary square root:
 *
 *   radicand (r2:r5) shifted left 1..2 bits pre-loop, then 2 bits per
 *   iteration over 29 iterations (r6 = 29..1), quotient/root bits
 *   accumulated in r1 via rotcl; final restore phase adds the last bits and
 *   ORs a sticky 1 into r1 if any remainder survives (rounding).
 *
 * Calling convention (confirmed from the single call site at 0x46E4):
 *   - args on the stack, pushed by the caller:
 *         [r15 + 4] = arg1   (moved to r4)
 *         [r15 + 8] = arg2   (moved to r2)
 *   - result pointer at [r15]:
 *         mov.l @r15,r5 ; mov.l r3,@r5 ; rts ; mov.l r1,@(4,r5)
 *   - writes r3 (extu.w, 16-bit) to [ptr] and r1 (32-bit) to [ptr+4].
 *
 * Semantics (verified bit-exact vs the emulated ROM, 300k+ random inputs
 * + all edge cases, 0 mismatches — see c/tests/test_div_4740.py):
 *   - arg1's low 16 bits are sign-extended (exts.w r4 -> r3); its LSB
 *     selects the pre-shift.
 *   - arg2 is the 32-bit mantissa/radicand word.
 *   - early exits mirror the ROM's special-value paths exactly:
 *         r3 <= -32768    -> (0x8001 | bit31(arg1)<<31, 0)      [0x47F8]
 *         bit31(arg1)==1  -> (0x7FFF, 0xFFFFFFFF)               [0x480C]
 *         r3 >= +32767    -> (0x7FFF, 0 / 0xFFFFFFFF per arg2)  [0x47F0]
 *   - otherwise runs 29 restoring-iteration steps (T = carry/borrow
 *     flag emulated exactly, including cmp/pl r6 updating T at 0x4788,
 *     which the loop-top rotcl r0 depends on — a previous model left T
 *     unset there and diverged from the ROM), then the final restore
 *     and two post-shift pairs, and ORs a sticky 1 into r1 if any
 *     remainder bit survives.
 *
 * Track A: verified behavior-equivalent to the emulated ROM
 * (tools/sh2emu.py) — see c/tests/test_div_4740.py.
 */
#include <stdint.h>

/* Returns r3 (hi, 16-bit) and r1 (lo, 32-bit) exactly as the ROM writes them. */
void div_4740(uint32_t arg1, uint32_t arg2, uint32_t *hi, uint32_t *lo)
{
    uint32_t r0 = 0, r1 = 0, r2 = arg2, r3, r4 = arg1, r5 = 0, r6 = 0, r7 = 0;
    uint32_t t = 0, t2;               /* t = SH-2 T (carry) flag */
    int64_t d;

    /* 0x4742  exts.w r4 -> r3  (sign-extend low 16 bits) */
    r3 = r4 & 0xFFFFu;
    r3 = (r3 & 0x8000u) ? (r3 | 0xFFFF0000u) : r3;

    /* 0x4746-0x474A  cmp/ge r3,r5 with r5 = 0xFFFF8001:
     * T = (r5 >= r3) signed; bt 0x47F8 */
    if ((int32_t)0xFFFF8001 >= (int32_t)r3) {
        /* 0x47F8  r3 = 0xFFFF8001; extu.w -> 0x8001 */
        r3 = 0x8001u;
        /* 0x47FC  shll r3: T = bit31(r3) = 0; r3 = 0x10002 */
        t = r3 >> 31; r3 = r3 << 1;
        /* 0x47FE  shll r4: T = bit31(r4); r4 <<= 1 */
        t = r4 >> 31; r4 = r4 << 1;
        /* 0x4800  rotcr r3 */
        t2 = r3 & 1u; r3 = (r3 >> 1) | (t << 31); t = t2;
        /* 0x4802-0x4804  bra 0x47E8; delay: r1 = 0 */
        r1 = 0;
        *hi = r3;
        *lo = r1;
        return;
    }

    /* 0x474C  shll r4: T = bit31(r4) */
    t = r4 >> 31; r4 = r4 << 1;
    if (t) {
        /* 0x480C  r3 = 0x7FFF; r1 = 0xFF sign-extended = 0xFFFFFFFF */
        *hi = 0x7FFFu;
        *lo = 0xFFFFFFFFu;
        return;
    }

    /* 0x4750-0x4754  cmp/ge r5,r3 with r5 = 0x7FFF:
     * T = (r3 >= r5) signed; bt 0x47F0 */
    r5 = 0x7FFFu;
    if ((int32_t)r3 >= (int32_t)r5) {
        /* 0x47F0  tst r2,r2 ; bf 0x480C ; r3 = 0x7FFF, r1 = 0 */
        if (r2 == 0u) {
            *hi = 0x7FFFu;
            *lo = 0u;
        } else {
            *hi = 0x7FFFu;
            *lo = 0xFFFFFFFFu;
        }
        return;
    }

    /* 0x4756-0x475C  r5 = r1 = r0 = 0; r6 = 29 */
    r5 = 0; r1 = 0; r0 = 0; r6 = 29;
    /* 0x475E  shlr r3: T = bit0(r3); r3 >>= 1 */
    t = r3 & 1u; r3 = r3 >> 1;
    if (t) {
        /* 0x4762-0x4764  shll r2; rotcl r5 */
        t = r2 >> 31; r2 = r2 << 1;
        t2 = r5 >> 31; r5 = (r5 << 1) | t; t = t2;
    }
    /* 0x4766-0x4768  shll r2; rotcl r5 */
    t = r2 >> 31; r2 = r2 << 1;
    t2 = r5 >> 31; r5 = (r5 << 1) | t; t = t2;
    t = 1;                              /* 0x476A  sett */

    /* 0x476C-0x478A  main division loop (r6 = 29 iterations) */
    for (;;) {
        /* 0x476C  rotcl r0 */
        t2 = r0 >> 31; r0 = (r0 << 1) | t; t = t2;
        /* 0x476E  cmp/hs r0,r5: T = (r5 >= r0) unsigned */
        t = (r5 >= r0) ? 1u : 0u;
        if (t) {
            /* 0x4770-0x4778  bt taken branch: rotcl r1; sub r0,r5;
             * bra 0x477E (delay: add #1,r0) */
            t2 = r1 >> 31; r1 = (r1 << 1) | t; t = t2;
            r5 = r5 - r0;
            r0 = r0 + 1u;
        } else {
            /* 0x477A-0x477C  xor #1,r0; rotcl r1 (T still 0) */
            r0 = r0 ^ 1u;
            t2 = r1 >> 31; r1 = (r1 << 1) | t; t = t2;
        }
        /* 0x477E-0x4780  shll r2; rotcl r5 */
        t = r2 >> 31; r2 = r2 << 1;
        t2 = r5 >> 31; r5 = (r5 << 1) | t; t = t2;
        /* 0x4782-0x4784  shll r2; rotcl r5 */
        t = r2 >> 31; r2 = r2 << 1;
        t2 = r5 >> 31; r5 = (r5 << 1) | t; t = t2;
        /* 0x4786  add #0xFF,r6 */
        r6 = r6 - 1u;
        /* 0x4788  cmp/pl r6: T = (r6 > 0) signed — loop-top rotcl r0
         * depends on this T at the next iteration! */
        t = ((int32_t)r6 > 0) ? 1u : 0u;
        if (t) continue;                /* 0x478A  bt 0x476C */
        break;
    }

    /* ---- final restore phase ---- */
    /* 0x478C-0x4790  r6 = 0; r7 = 0; sett */
    r6 = 0; r7 = 0; t = 1;
    /* 0x4792  rotcl r0 */
    t2 = r0 >> 31; r0 = (r0 << 1) | t; t = t2;
    /* 0x4794  cmp/hs r0,r5: T = (r5 >= r0) */
    t = (r5 >= r0) ? 1u : 0u;
    if (t) {
        /* 0x4796-0x479E  rotcl r1; sub r0,r5; bra 0x47A4 (delay: add #1,r0) */
        t2 = r1 >> 31; r1 = (r1 << 1) | t; t = t2;
        r5 = r5 - r0;
        r0 = r0 + 1u;
    } else {
        /* 0x47A0-0x47A2  xor #1,r0; rotcl r1 (T still 0) */
        r0 = r0 ^ 1u;
        t2 = r1 >> 31; r1 = (r1 << 1) | t; t = t2;
    }

    /* 0x47A4-0x47AE  shll r2; rotcl r5; rotcl r6; shll r2; rotcl r5; rotcl r6 */
    t = r2 >> 31; r2 = r2 << 1;
    t2 = r5 >> 31; r5 = (r5 << 1) | t; t = t2;
    t2 = r6 >> 31; r6 = (r6 << 1) | t; t = t2;
    t = r2 >> 31; r2 = r2 << 1;
    t2 = r5 >> 31; r5 = (r5 << 1) | t; t = t2;
    t2 = r6 >> 31; r6 = (r6 << 1) | t; t = t2;
    /* 0x47B0-0x47B4  sett; rotcl r0; rotcl r7 */
    t = 1;
    t2 = r0 >> 31; r0 = (r0 << 1) | t; t = t2;
    t2 = r7 >> 31; r7 = (r7 << 1) | t; t = t2;

    /* 0x47B6-0x47C0  compare {r5:r6} >= {r0:r7} (unsigned 64-bit):
     * cmp/hi r7,r6 -> T = (r6 > r7); bt 0x47C2
     * else cmp/hs r7,r6 -> T = (r6 >= r7); bf 0x47CA
     *      cmp/hs r0,r5 -> T = (r5 >= r0); bf 0x47CA   */
    t = (r6 > r7) ? 1u : 0u;
    if (!t) {
        t = (r6 >= r7) ? 1u : 0u;
        if (t) t = (r5 >= r0) ? 1u : 0u;
    }
    if (t) {
        /* 0x47C2-0x47C8  rotcl r1 (T=1); subc r0,r5;
         * bra 0x47CC (delay: subc r7,r6) */
        t2 = r1 >> 31; r1 = (r1 << 1) | t; t = t2;
        d = (int64_t)r5 - (int64_t)r0 - (int64_t)t;
        t = (d < 0) ? 1u : 0u; r5 = (uint32_t)d;
        d = (int64_t)r6 - (int64_t)r7 - (int64_t)t;
        t = (d < 0) ? 1u : 0u; r6 = (uint32_t)d;
    } else {
        /* 0x47CA  rotcl r1 (T=0) */
        t2 = r1 >> 31; r1 = (r1 << 1) | t; t = t2;
    }

    /* 0x47CC-0x47D6  shll r2; rotcl r5; rotcl r6; shll r2; rotcl r5; rotcl r6 */
    t = r2 >> 31; r2 = r2 << 1;
    t2 = r5 >> 31; r5 = (r5 << 1) | t; t = t2;
    t2 = r6 >> 31; r6 = (r6 << 1) | t; t = t2;
    t = r2 >> 31; r2 = r2 << 1;
    t2 = r5 >> 31; r5 = (r5 << 1) | t; t = t2;
    t2 = r6 >> 31; r6 = (r6 << 1) | t; t = t2;
    /* 0x47D8  shll r1 */
    t = r1 >> 31; r1 = r1 << 1;
    /* 0x47DA-0x47E4  tst r6,r6 ; bf 0x47E2 ; tst r5,r5 ; bt 0x47E6 ;
     * mov #1,r7 ; or r7,r1  (sticky bit: any surviving remainder -> |1) */
    if (r6 != 0u || r5 != 0u) r1 = r1 | 1u;

    r3 = r3 & 0xFFFFu;                  /* 0x47E6  extu.w r3 */
    *hi = r3;
    *lo = r1;
}
