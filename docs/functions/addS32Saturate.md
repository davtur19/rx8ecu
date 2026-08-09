# addS32Saturate @ 0x2304

**Track-A verification:** emulator (14 edge + 100k random) + C-host vs ROM (100k)

## Overview

Saturating signed 32-bit add: `min(max(a + b, INT32_MIN), INT32_MAX)`.

The IDA label `fpu_compare_float` is wrong. It is an integer helper on the SH-2 `addv`
(signed-overflow detect); no FPU instruction is in the body.

## Logic

```c
int32_t addS32Saturate(int32_t a, int32_t b) {
    int64_t s = (int64_t)a + (int64_t)b;
    if (s >  0x7FFFFFFF)  return  0x7FFFFFFF;
    if (s < -0x80000000LL) return (int32_t)0x80000000;
    return (int32_t)s;
}
```

## SH-2E Assembly

| Address | Instruction   | Meaning |
|---------|---------------|---------|
| 0x2304  | `addv r4,r5`  | r5 = r4 + r5 (wraps); T=1 on signed overflow |
| 0x2306  | `bf/s .ret`   | if !T (no overflow) skip clamp; delay: r0 = r5 |
| 0x2308  | `mov r5,r0`   | [delay] r0 = wrapped sum |
| 0x230A  | `mov.l @(pc),r0` | r0 = 0x7FFFFFFF (literal @0x2318) |
| 0x230C  | `cmp/pz r5`   | T = (wrapped sum >= 0) |
| 0x230E  | `mov #0,r5`   | |
| 0x2310  | `addc r5,r0`  | r0 += T → 0x80000000 if wrapped sum >= 0 |
| 0x2312  | `rts`         | |
| 0x2314  | `nop`         | [delay, not reached] |
| 0x2318  | `.long 0x7FFFFFFF` | literal pool |

On positive overflow the wrapped sum is negative (`cmp/pz` → T=0). Thus the
literal 0x7FFFFFFF is kept. On negative overflow the wrapped sum is
non-negative (T=1), and `addc` flips the literal to 0x80000000.

## Note

`addv` is 0x3nmF. This was a missing opcode in `tools/sh2emu.py` /
`tools/disasm_sh2e.py` and was added on 2026-07-31.
