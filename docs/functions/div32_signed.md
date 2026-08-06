# div32_signed @ 0x3FE8

**Track-A verification:** C host test (100K random + 26 edge cases)

## Overview

Full 32-bit signed integer division via the SH-2E div0s/div1 step-by-step algorithm
(no hardware divide; 32 iterations, one quotient bit each).

Returns dividend ÷ divisor, truncated toward zero (C99 semantics).

Divide-by-zero: writes error code 0x44E to 0xFFFF7304, returns 0.

## Signature

```c
int32_t div32_signed(int32_t divisor /* r0 */, int32_t dividend /* r1 */);
```

## Logic

```c
int32_t div32_signed(int32_t divisor, int32_t dividend) {
    if (divisor == 0) {
        error_write(0xFFFF7304, 0x44E);
        return 0;
    }
    return dividend / divisor;  // truncating toward zero
}
```

## Edge case: INT32_MIN / -1

In C, this is undefined behaviour.  On the SH-2E, the div0s/div1 algorithm
wraps and returns INT32_MIN (0x80000000).  This case does not occur in
the ECU firmware (no caller passes INT32_MIN as dividend with -1 as
divisor).

## Verification

- [x] Disassembly confirmed against capstone + Ghidra
- [x] C code written (`c/div32_signed.c`)
- [x] C host test: `test_div32_signed.c` — 100K random + 26 edge cases, matches C99 division
- [ ] Emulator test requires SH-2E DIV1 instruction support (not yet implemented in `sh2emu.py`)
