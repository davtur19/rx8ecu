# shift_right_8_r0 @ 0x467A

**Address:** 0x467A – 0x468C  (18 bytes)
**ROM:** 60E1D400.bin
**Source label:** ida-ai
**Track-A verification:** emulator (12 edge + 1000 random)

---

## Overview

Performs an arithmetic right-shift by 8 bits on the value in r0, returning
the result in r0.  This is a compact helper for extracting the high byte
of a 16-bit value (signed-extended to 32 bits).

## Logic

```c
int32_t shift_right_8_r0(int32_t r0_inout) {
    return r0_inout >> 8;
}
```

The SH-2E `shar8 r0` instruction (arithmetic shift right by 8) is used,
which preserves the sign bit.  Equivalent to `>> 8` on a signed 32-bit
integer in C.

## Note

Unlike most functions, this one reads its input from **r0** (not r4).
The emulator helper `call_r0` handles this calling convention.

## Verification

- [x] Disassembly confirmed against capstone + Ghidra
- [x] C code written (`c/shift_right_8_r0.c`)
- [x] Emulator test: `test_shift_right_8_r0.py` — 12 edge + 1000 random inputs, all pass
