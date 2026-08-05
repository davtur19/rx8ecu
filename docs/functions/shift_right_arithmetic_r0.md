# shift_right_arithmetic_r0 @ 0x43C8

**Track-A verification:** emulator (24 edge + 100k random) + C-host vs ROM (100k)

## Overview

Arithmetic (sign-extending) right shift.  Value in **r0**, shift count in
**r1**, result in r0.  Count clamping matches the logical siblings:

- `cnt < 0` → return value unchanged
- `cnt >= 32` → return 0xFFFFFFFF if value < 0 else 0
- else → `val >> cnt` (sign-extending)

## Logic

```c
int32_t shift_right_arithmetic_r0(int32_t val, int32_t cnt) {
    if (cnt < 0) return val;
    if (cnt >= 32) return (val < 0) ? -1 : 0;
    return val >> cnt;
}
```

## SH-2E Assembly

The most elaborate of the shift family:

1. `cmp/pz r1` — negative count → rts immediately, r0 unchanged (@0x4442).
2. `cmp/ge #32` — count >= 32 → `shll r0` moves bit31 into T: T==1
   (value < 0) → `mov #-1,r0`, else `mov #0,r0` (@0x4404..0x4412).
3. `rotl r2` copies bit31 into T to branch on the **sign of the value**:
   - **value < 0**: the 8-entry table @0x43C0 indexes base 0x4446 — the
     swap/rotate sign-extension tails for counts 24..31:
     | Count | Tail | Effect |
     |-------|------|--------|
     | 24 | `swap.w r0,r1; swap.b r1,r0; or #-128` | >>24 |
     | 25 | `rotl r0`×7 + `or #-64` | >>25 |
     | 26 | `rotl r0`×6 + `or #-32` | >>26 |
     | 27..30 | `rotl r0`×5..2 + `or #-16..-2` | >>27..30 |
     | 31 | `mov #-1,r0` | >>31 |
     Counts 0..23 read the same table (cnt-24 bytes earlier) and walk
     INTO the 0x4414..0x4440 `shar r0` chain: n shar = `>> n`.
   - **value >= 0**: count <= 8 reuses the `shar` chain (logical ==
     arithmetic for non-negative); count > 8 jumps to the shared
     logical-shift dispatch of 0x44E0 (`mov.l @(.lit),r2; jmp @r2`
     → 0x44EC, table @0x44C0 / base 0x450A).

## Note

`rotl` (0x40n4) and `rotr` (0x40n5) were missing opcodes in both
`tools/sh2emu.py` and `tools/disasm_sh2e.py` — added 2026-07-31.  The
`shar` chain at 0x4414 and the
0x4446 swap tails are shared/overlapping code that IDA's linear
function boundaries cut mid-stream.
