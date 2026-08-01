/*
 * bitfield_extract_merge  —  RX-8 PCM frexp-style float bit-pattern helper
 *                            @ ROM 0x48C8 (60E1D400.bin; identical bytes at
 *                            0x48C8 in 60E0FC00.bin)
 *
 * Purpose: decompose a single-precision float into a (exponent, significand)
 * pair used by the fixed-point math helpers (its only caller is
 * checkFloatValidity @0x46CC, which feeds the two words straight into
 * mul16_signed_saturated @0x4740 as stack args).
 *
 * Calling convention (confirmed from the single call site at 0x46D8):
 *   - float argument in FR4 (register),
 *   - result pointer pushed by the caller on the stack BEFORE the call:
 *         jsr @r3
 *         mov.l r15,@-r15     ; delay: [r15] = ptr to 8-byte result buffer
 *   - writes out[0] = exponent word, out[1] = significand word.
 *
 * Semantics (verified against the emulated ROM, 200k random + all edge cases):
 *   out[0] = exponent word:
 *       bit 31        = sign of the input float (EXCEPT for NaN, see below)
 *       bits 15:0     = signed 16-bit exponent e with x = sig * 2^e,
 *                       sig in [1.0, 2.0) (frexp-style, but the significand
 *                       is normalized to [1,2) instead of [0.5,1))
 *       special values:
 *           ±0.0  -> 0x00008001 | sign          (exp sentinel 0x8001 = -32767)
 *           ±Inf  -> 0x00007FFF | sign          (exp saturated to +32767)
 *           NaN   -> 0x00007FFF                 (sign bit DROPPED — ROM zeroes
 *                                                r2 on this path, so -NaN loses
 *                                                its sign; +Inf/-Inf keep it)
 *   out[1] = significand word:
 *       bit 31        = implicit leading 1 (always set for finite nonzero)
 *       bits 30:8     = 23-bit mantissa << 8
 *       special values:
 *           0.0       -> 0x00000000
 *           ±Inf      -> 0x00000000
 *           NaN       -> 0xFFFFFFFF  (-1)
 *   Subnormals are normalized: the mantissa is shifted left until its top bit
 *   sits at bit 31 and the exponent is decreased by one per shift, so a
 *   subnormal comes out as a normal (sig in [1,2)) pair with e in [-149,-127].
 *
 * Original SH-2E (big-endian) listing:
 *   0x48C8  fmov.s fr4,@-r15     ; [r15-4] = float bits (FR4 -> GPR trick)
 *   0x48CA  mov.l  @r15+,r4      ; r4 = float bits; r15 restored
 *   0x48CC  mov.l  @(.lit0,pc),r0 ; r0 = 0x000000FF
 *   0x48CE  mov    r4,r2         ; r2 = bits (kept for sign)
 *   0x48D0  shll   r4            ; r4 = bits<<1; T = sign
 *   0x48D2  mov    r4,r1
 *   0x48D4  shlr16 r1
 *   0x48D6  shlr8  r1
 *   0x48D8  and    r0,r1         ; r1 = (bits>>23) & 0xFF = exponent byte
 *   0x48DA  shll8  r4            ; r4 = bits<<9
 *   0x48DC  cmp/eq r0,r1
 *   0x48DE  bt     .expff        ; exp == 0xFF -> Inf/NaN
 *   0x48E0  tst    r1,r1
 *   0x48E2  bt     .exp0         ; exp == 0    -> zero/subnormal
 *   ; ---- normal: exp in [1,254] ----
 *   0x48E4  mov    #-127,r0
 *   0x48E6  add    r0,r1         ; e = exp - 127
 *   0x48E8  sett
 *   0x48EA  rotcr  r4            ; r4 = (bits<<8) | 0x80000000 (implicit 1)
 *   ; ---- common exit ----
 *   0x48EC  extu.w r1,r1         ; e & 0xFFFF
 *   0x48EE  shll   r1
 *   0x48F0  shll   r2            ; T = sign of input
 *   0x48F2  rotcr  r1            ; out0 = (e & 0xFFFF) | (sign << 31)
 *   0x48F4  mov.l  @r15,r0       ; r0 = result pointer
 *   0x48F6  mov.l  r1,@r0        ; *ptr       = out0
 *   0x48F8  rts
 *   0x48FA  mov.l  r4,@(4,r0)    ; *(ptr + 4) = out1   [delay]
 *   ; ---- exp == 0xFF ----
 *   0x48FC  tst    r4,r4         ; r4 = bits<<9  == 0  <=>  mantissa == 0
 *   0x48FE  bf     .nan          ; mantissa != 0 -> NaN
 *   0x4900  bra    .inf          ; mantissa == 0 -> Inf (r2 = bits kept)
 *   0x4902  nop
 *   ; ---- exp == 0 ----
 *   0x4904  tst    r4,r4
 *   0x4906  bt     .zero
 *   0x4908  shll   r4            ; T = bit22 of bits (top mantissa bit)
 *   0x490A  bt     .normdone     ; skip loop if already normalized
 *   .loop: 0x490C add #-1,r1     ; e--
 *   0x490E  shll   r4            ; next mantissa bit into T
 *   0x4910  bf     .loop         ; while T == 0
 *   0x4912  bra    .norm         ; -> 0x48E4 with e = -1 - n, r4 normalized
 *   0x4914  nop
 *   ; ---- zero ----
 *   0x4916  mov.l  @(.lit1,pc),r1 ; r1 = 0xFFFF8001
 *   0x4918  bra    .exit         ; -> 0x48EC  (r2 = bits -> sign kept)
 *   0x491A  mov    #0,r4         ; out1 = 0
 *   ; ---- Inf ----
 *   0x491C  mov.l  @(.lit2,pc),r1 ; r1 = 0x00007FFF
 *   0x491E  bra    .exit
 *   0x4920  mov    #0,r4         ; out1 = 0
 *   ; ---- NaN ----
 *   0x4922  mov.l  @(.lit2,pc),r1 ; r1 = 0x00007FFF
 *   0x4924  mov    #0,r2         ; <-- r2 zeroed: sign bit LOST here
 *   0x4926  bra    .exit
 *   0x4928  mov    #-1,r4        ; out1 = 0xFFFFFFFF
 *   0x492A  nop                  ; (padding; function ends)
 *   .lit0: 0x492C .long 0x000000FF
 *   .lit2: 0x4930 .long 0x00007FFF
 *   .lit1: 0x4934 .long 0xFFFF8001
 *
 * Track A: verified behavior-equivalent to the emulated ROM
 * (tools/sh2emu.py) — see c/tests/test_bitfield_extract_merge.py.
 */
#include <stdint.h>

/* 0x48C8  frexp-style float decomposition: x = sig * 2^e, sig in [1,2) */
void bitfield_extract_merge(float value, uint32_t *out)
{
    uint32_t bits = *(uint32_t *)&value;   /* IEEE-754 bit pattern */
    uint32_t sign = bits & 0x80000000u;
    uint32_t exp8 = (bits >> 23) & 0xFFu;
    uint32_t mant = bits & 0x007FFFFFu;
    uint32_t frac;                          /* out[1]: significand << 8 */
    int32_t  e;                             /* out[0]: signed exponent  */

    if (exp8 == 0xFFu) {
        /* Inf or NaN */
        if (mant == 0u) {
            out[0] = 0x00007FFFu | sign;    /* ±Inf: exponent saturated, sign kept */
            out[1] = 0x00000000u;
        } else {
            out[0] = 0x00007FFFu;           /* NaN: sign dropped (r2 zeroed in ROM) */
            out[1] = 0xFFFFFFFFu;
        }
        return;
    }

    if (exp8 == 0u) {
        if (mant == 0u) {
            out[0] = 0x00008001u | sign;    /* ±0.0: exponent sentinel 0x8001 */
            out[1] = 0x00000000u;
            return;
        }
        /* subnormal: normalize so the top mantissa bit lands at bit 31 */
        frac = (mant << 9) & 0xFFFFFFFFu;
        e = 0;
        if ((frac & 0x80000000u) == 0u) {
            do {
                e--;
                frac = (frac << 1) & 0xFFFFFFFFu;
            } while ((frac & 0x80000000u) == 0u);
        }
        frac |= 0x80000000u;                /* implicit leading 1 */
        e -= 127;
    } else {
        /* normal: exp in [1,254] */
        e = (int32_t)exp8 - 127;
        frac = (mant << 8) | 0x80000000u;   /* 1.mantissa << 8 */
    }

    out[0] = (uint32_t)(e & 0xFFFF) | sign; /* 16-bit exponent + sign in bit 31 */
    out[1] = frac;
}
