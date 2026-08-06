# shift_right_logical_r0 @ 0x44E0

**Track-A verification:** emulator (18 edge + 100k random) + C-host vs ROM (100k)

## Overview

Logical (zero-fill) right shift.  Value in **r0**, shift count in **r1**,
result in r0.  Count clamping identical to `shift_left_logical_r0`:

- `cnt < 0` → return value unchanged
- `cnt >= 32` → return 0
- else → `val >> cnt` (zero-extended)

## Logic

```c
uint32_t shift_right_logical_r0(uint32_t val, int32_t cnt) {
    if (cnt < 0) return val;
    if (cnt >= 32) return 0;
    return val >> cnt;
}
```

## SH-2E Assembly

Identical skeleton to `shift_left_logical_r0` (0x4308): the 32-entry byte table
@0x44C0 holds the **same byte values** as @0x42E8, indexing an unrolled `shlr r0`
chain @0x450A (7× for counts 0..7; `shlr8`/`shlr16` + remainder for 8..23;
`and #15/7/3/1,r0` + `rotl r0` masked-rotate tails for 24..31).

This function is shared code: `shift_right_arithmetic_r0` (0x43C8) jumps
into its table-dispatch block at 0x44EC for the non-negative-value /
count > 8 path (arithmetic == logical for non-negative operands).

## Note

`rotl` is 0x40n4 — was a missing opcode in both `tools/sh2emu.py` and
`tools/disasm_sh2e.py`, added
2026-07-31.
