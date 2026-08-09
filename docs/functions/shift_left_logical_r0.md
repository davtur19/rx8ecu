# shift_left_logical_r0 @ 0x4308

**Track-A verification:** emulator (18 edge + 100k random) + C-host vs ROM (100k)

## Overview

Logical (zero-fill) left shift.  Value in **r0**, shift count in **r1**,
result in r0.  It clamps the count explicitly instead of masking it:

- `cnt < 0` → return value unchanged
- `cnt >= 32` → return 0
- else → `val << cnt`

## Logic

```c
uint32_t shift_left_logical_r0(uint32_t val, int32_t cnt) {
    if (cnt < 0) return val;
    if (cnt >= 32) return 0;
    return val << cnt;
}
```

## SH-2E Assembly

Jump-table dispatch — no loop.  The 32-entry byte table @0x42E8 maps the
shift count to a signed offset into an unrolled chain of `shll r0`
tales based at 0x4332:

| Count | Target | Body |
|-------|--------|------|
| 0..7  | 0x4332 + (0x0e..0x00) | 0..7 × `shll r0` |
| 8     | 0x4352 | `shll8 r0` |
| 9..15 | 0x4350.. | `shll8 r0` + remainder `shll r0` |
| 16    | 0x4362 | `shll16 r0` |
| 17..23| 0x4366.. | `shll16 r0` + remainder |
| 24..31| 0x4378.. | `and #15/7/3/1,r0` + `rotr r0` ×N (masked rotate) |

Prologue: `cmp/pz r1` (neg count → rts with r0 unchanged); `cmp/ge #32`
(count >= 32 → `mov #0,r0; rts`); else table load + `jmp @r1`.

The 24..31 tails are reached only after `shll r0` in the shared chain
entry; the `and`+`rotr` sequence yields `(val << cnt) & 0xFFFFFFFF`
for those counts.

## Note

`rotr` is 0x40n5 — it was a missing opcode in both `tools/sh2emu.py` and
`tools/disasm_sh2e.py`, added
2026-07-31.
