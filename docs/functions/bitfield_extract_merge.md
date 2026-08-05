# bitfield_extract_merge @ 0x48C8

**ROM:** 60E1D400.bin (byte-identical code also in 60E0FC00.bin @0x48C8)
**Track-A verification:** SH-2E emulator vs independent model (30 edge cases +
100k random bit patterns, 0 mismatches) **and** C lift vs emulated ROM
(100k+ inputs, 0 mismatches) — `c/tests/test_bitfield_extract_merge.py`

## Overview

Frexp-style float bit-pattern decomposition helper: splits a single-precision
float into a normalized significand and a signed exponent such that

```
x = sig * 2^e ,   sig in [1.0, 2.0),   e in [-149 .. +127]
```

(the significand is kept in [1,2) instead of frexp's [0.5,1) — bit 31 of the
fraction word is the implicit leading 1). The two 32-bit words are written
through a caller-supplied result pointer.

Its **only caller** is `checkFloatValidity` @0x46CC (call site 0x46D8), which
immediately feeds both words into `mul16_signed_saturated` @0x4740 as stack
args — so this pair of words is the fixed-point representation the calibration
math layer works with.

## Calling convention (confirmed from the call site)

```asm
    mov.l  L_004728,r3        ; r3 = 0x000048C8
    ...
    jsr    @r3
    mov.l  r15,@-r15          ; [delay] push result pointer at [r15]
```

- float argument in **FR4** (fp register; the callee does the classic
  `fmov.s fr4,@-r15; mov.l @r15+,r4` bits->GPR transfer),
- result pointer at **[r15]** on entry, pointing at an 8-byte buffer:
  `*ptr = out[0]` (exponent word), `*(ptr+4) = out[1]` (significand word).

## Output encoding

| Input                        | out[0] (exponent word)      | out[1] (significand word)   |
|------------------------------|-----------------------------|------------------------------|
| finite normal, e = exp-127   | `(e & 0xFFFF)`, sign in bit31 | `(mantissa << 8)` with bit31 = 1 |
| subnormal (normalized)       | `(e & 0xFFFF)`, sign in bit31, e in [-149,-127] | sig << 8, bit31 = 1 |
| +0.0                         | `0x00008001`                | `0x00000000`                |
| -0.0                         | `0x80008001`                | `0x00000000`                |
| +Inf                         | `0x00007FFF`                | `0x00000000`                |
| -Inf                         | `0x80007FFF`                | `0x00000000`                |
| NaN (either sign)            | `0x00007FFF`                | `0xFFFFFFFF`  (-1)          |

Notes:

- The **sign lives in bit 31 of the exponent word**, not in the significand
  word (the significand is always a positive [1,2) magnitude).
- **NaN drops its sign**: the ROM zeroes r2 on the NaN path
  (`mov #0,r2` @0x4924), so even a negative NaN comes out as `0x00007FFF`.
  Infinities keep the sign (that path preserves r2 = original bits).
- `0x8001` = -32767 is the zero sentinel; `0x7FFF` = +32767 is the
  Inf/NaN saturation.
- Subnormals are fully normalized: the mantissa is shifted left until its top
  set bit reaches bit 31, decrementing the exponent once per shift
  (exp_out = -127 - n, n = 22 - ⌊log2(mant)⌋). Smallest subnormal (2^-149)
  → `(0xFF6B, 0x80000000)`.

## Worked examples (from the emulator)

```
input          out[0]      out[1]
 1.0  3F800000 00000000    80000000     -> 1.0 * 2^0
-2.5  C0200000 80000001    A0000000     -> 1.25 * 2^1, sign in bit31
 3.14 4048F5C3 00000001    C8F5C300     -> 1.5700001 * 2^1
 0.5  3F000000 0000FFFF    80000000     -> 1.0 * 2^-1
min normal     0000FF82    80000000     -> 1.0 * 2^-126
min subnormal  0000FF6B    80000000     -> 1.0 * 2^-149
max subnormal  0000FF81    FFFFFE00     -> 1.9999998 * 2^-127
+Inf           00007FFF    00000000
-Inf           80007FFF    00000000
±NaN           00007FFF    FFFFFFFF     (sign dropped)
+0.0           00008001    00000000
-0.0           80008001    00000000
```

## SH-2E Assembly

| Address | Instruction        | Meaning |
|---------|--------------------|---------|
| 0x48C8  | `fmov.s fr4,@-r15` | [r15-4] = float bits (FR4→GPR trick) |
| 0x48CA  | `mov.l @r15+,r4`   | r4 = float bits; r15 restored |
| 0x48CC  | `mov.l @(.lit0,pc),r0` | r0 = 0x000000FF |
| 0x48CE  | `mov r4,r2`        | r2 = bits (sign preserved on this copy) |
| 0x48D0  | `shll r4`          | r4 = bits<<1; T = sign |
| 0x48D2  | `mov r4,r1`        | |
| 0x48D4  | `shlr16 r1`        | |
| 0x48D6  | `shlr8 r1`         | r1 = (bits<<1)>>24 |
| 0x48D8  | `and r0,r1`        | r1 = (bits>>23)&0xFF = exponent byte |
| 0x48DA  | `shll8 r4`         | r4 = bits<<9 |
| 0x48DC  | `cmp/eq r0,r1`     | exp == 0xFF? |
| 0x48DE  | `bt .expff`        | |
| 0x48E0  | `tst r1,r1`        | exp == 0? |
| 0x48E2  | `bt .exp0`         | |
| 0x48E4  | `mov #-127,r0`     | |
| 0x48E6  | `add r0,r1`        | e = exp - 127 |
| 0x48E8  | `sett`             | |
| 0x48EA  | `rotcr r4`         | out1 = (bits<<8), bit31 = 1 (implicit 1) |
| 0x48EC  | `extu.w r1,r1`     | e & 0xFFFF |
| 0x48EE  | `shll r1`          | |
| 0x48F0  | `shll r2`          | T = sign |
| 0x48F2  | `rotcr r1`         | out0 = (e&0xFFFF), sign in bit31 |
| 0x48F4  | `mov.l @r15,r0`    | r0 = result pointer |
| 0x48F6  | `mov.l r1,@r0`     | *ptr = out0 |
| 0x48F8  | `rts`              | |
| 0x48FA  | `mov.l r4,@(4,r0)` | [delay] *(ptr+4) = out1 |
| 0x48FC  | `tst r4,r4`        | bits<<9 == 0  ⇔  mantissa == 0 |
| 0x48FE  | `bf .nan`          | |
| 0x4900  | `bra .inf`         | (r2 = bits still intact → sign kept) |
| 0x4904  | `tst r4,r4`        | |
| 0x4906  | `bt .zero`         | |
| 0x4908  | `shll r4`          | T = bit22 (top mantissa bit) |
| 0x490A  | `bt .normdone`     | already normalized |
| 0x490C  | `add #-1,r1`       | e-- |
| 0x490E  | `shll r4`          | next mantissa bit into T |
| 0x4910  | `bf .loop`         | while T == 0 |
| 0x4912  | `bra .norm`        | → 0x48E4 |
| 0x4916  | `mov.l @(.lit1,pc),r1` | r1 = 0xFFFF8001 (zero sentinel) |
| 0x4918  | `bra .exit`        | |
| 0x491A  | `mov #0,r4`        | [delay] out1 = 0 |
| 0x491C  | `mov.l @(.lit2,pc),r1` | r1 = 0x00007FFF |
| 0x491E  | `bra .exit`        | |
| 0x4920  | `mov #0,r4`        | [delay] out1 = 0 |
| 0x4922  | `mov.l @(.lit2,pc),r1` | r1 = 0x00007FFF |
| 0x4924  | `mov #0,r2`        | **r2 = 0 → NaN sign dropped** |
| 0x4926  | `bra .exit`        | |
| 0x4928  | `mov #-1,r4`       | [delay] out1 = 0xFFFFFFFF |
| 0x492A  | `nop`              | (padding) |
| 0x492C  | `.long 0x000000FF` | lit0 |
| 0x4930  | `.long 0x00007FFF` | lit2 |
| 0x4934  | `.long 0xFFFF8001` | lit1 |

## C lift

`c/bitfield_extract_merge.c`:

```c
void bitfield_extract_merge(float value, uint32_t *out);
```

## Note on the repo's annotated listings

The IDA (`src/60E1D400_annotated.s`) and Ghidra (`src/60E0FC00.s`) listings
both mis-decode the tail of this function: they show `mov #0,r2` at 0x4922,
but the raw bytes at 0x4922 are `D1 03` = `mov.l @(.lit2,pc),r1`
(load 0x00007FFF) — the listing shifted by one instruction and merged the
0x4926 `bra .exit` + 0x4928 delay-slot `mov #-1,r4` into the NaN entry.
The byte-level decode here (verified on both ROMs with xxd) is authoritative.
