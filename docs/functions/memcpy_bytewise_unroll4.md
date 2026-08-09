# memcpy_bytewise_unroll4 @ 0x42B0

**Track-A verification:** emulator (18 edge + 500 random)

## Overview

This function copies memory byte by byte with a manual 4× unrolled loop.
It copies `n` bytes from the source pointer to the destination pointer.
The manual 4× unroll is typical of the SHC compiler.  The loop body copies
4 bytes per iteration.  A tail loop handles the remaining 0–3 bytes.

## Logic

```c
void memcpy_bytewise_unroll4(void *dst, const void *src, uint32_t n) {
    uint32_t i;
    for (i = 0; i + 4 <= n; i += 4) {
        ((uint8_t*)dst)[i]   = ((uint8_t*)src)[i];
        ((uint8_t*)dst)[i+1] = ((uint8_t*)src)[i+1];
        ((uint8_t*)dst)[i+2] = ((uint8_t*)src)[i+2];
        ((uint8_t*)dst)[i+3] = ((uint8_t*)src)[i+3];
    }
    for (; i < n; i++)
        ((uint8_t*)dst)[i] = ((uint8_t*)src)[i];
}
```

## Verification

- [x] Disassembly confirmed against capstone + Ghidra
- [x] C code written (`c/memcpy_bytewise_unroll4.c`)
- [x] Emulator test: `test_memcpy_bytewise_unroll4.py` — 18 edge cases + 500 random (overlapping, zero-length, all boundary alignments), all pass
